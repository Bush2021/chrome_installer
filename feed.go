package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/Bush2021/chrome_update/feed"
	"github.com/Bush2021/chrome_update/omaha"
)

const (
	validity = 7 * 24 * time.Hour
	// An unchanged feed is signed again only once a day, so a client that
	// checks every 3 hours mostly gets a 304.
	renew = 24 * time.Hour
)

// curation is what the team sets by hand in curation.json.
type curation struct {
	Soak  feed.Soak   `json:"soak"`
	Holds []feed.Hold `json:"holds"`
}

// runFeed writes the signed feed. previous is the feed published last,
// which keeps each build's first-seen time; a missing or unreadable one
// starts the soaks over.
func runFeed(ctx context.Context, c *omaha.Client, args []string) error {
	fs := flag.NewFlagSet("feed", flag.ExitOnError)
	previous := fs.String("previous", "", "the feed published last")
	curated := fs.String("curation", "curation.json", "soak periods and holds")
	out := fs.String("out", "", "where to write the feed")
	fs.Parse(args)
	if *out == "" {
		return errors.New("feed: -out is required")
	}
	keys, err := signingKeys(os.Getenv("FEED_SIGNING_KEY"))
	if err != nil {
		return err
	}
	cur, err := loadCuration(*curated)
	if err != nil {
		return err
	}
	var prev *feed.Feed
	if *previous != "" {
		prev = loadFeed(*previous, keys)
	}
	f, err := makeFeed(ctx, c, prev, cur, time.Now().UTC().Truncate(time.Second))
	if err != nil {
		return err
	}
	raw, err := feed.Sign(f, keys...)
	if err != nil {
		return err
	}
	return os.WriteFile(*out, raw, 0o644)
}

// signingKeys reads the private keys, separated by spaces. During a
// rotation the old key and the new one both sign.
func signingKeys(s string) ([]ed25519.PrivateKey, error) {
	var keys []ed25519.PrivateKey
	for f := range strings.FieldsSeq(s) {
		k, err := feed.ParsePrivateKey(f)
		if err != nil {
			return nil, err
		}
		keys = append(keys, k)
	}
	if len(keys) == 0 {
		return nil, errors.New("feed: FEED_SIGNING_KEY is empty")
	}
	return keys, nil
}

func loadCuration(path string) (curation, error) {
	var c curation
	b, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, fmt.Errorf("%s: %w", path, err)
	}
	for i, h := range c.Holds {
		if h.Reason["en"] == "" {
			return c, fmt.Errorf("%s: hold %d has no English reason", path, i+1)
		}
	}
	return c, nil
}

func loadFeed(path string, keys []ed25519.PrivateKey) *feed.Feed {
	raw, err := os.ReadFile(path)
	if err != nil {
		log.Printf("previous feed: %v", err)
		return nil
	}
	var pubs []ed25519.PublicKey
	for _, k := range keys {
		pubs = append(pubs, k.Public().(ed25519.PublicKey))
	}
	f, err := feed.Open(raw, pubs...)
	if err != nil {
		log.Printf("previous feed: %v", err)
		return nil
	}
	return f
}

func makeFeed(ctx context.Context, c *omaha.Client, prev *feed.Feed, cur curation, now time.Time) (*feed.Feed, error) {
	f := &feed.Feed{Schema: feed.Schema, Generated: now, Expires: now.Add(validity), Soak: cur.Soak, Holds: cur.Holds}
	for _, ch := range omaha.Channels {
		for _, arch := range archs {
			k := key(ch, arch)
			var old feed.Build
			had := false
			if prev != nil {
				old, had = prev.Build(ch, arch)
			}
			ans, err := c.Check(ctx, omaha.Request{Channel: ch, Arch: arch})
			if errors.Is(err, omaha.ErrStatus) {
				log.Printf("%s: %v", k, err)
				if had {
					f.Chrome = append(f.Chrome, old)
				}
				continue
			}
			if err != nil {
				return nil, fmt.Errorf("%s: %w", k, err)
			}
			b := feed.Build{Channel: ch, Arch: arch, Version: ans.Version, Published: now, Pipelines: ans.Pipelines}
			if had {
				switch d := compareVersions(ans.Version, old.Version); {
				case d < 0:
					log.Printf("%s: keeping %s over the older %s", k, old.Version, ans.Version)
					b = old
				case d == 0:
					// The first answer for a version stands, so the feed
					// changes only when a version does.
					b = old
				}
			}
			f.Chrome = append(f.Chrome, b)
		}
	}
	// Ed25519 signatures are deterministic, so keeping the times of an
	// unchanged feed reproduces its bytes, and the workflow skips the push.
	if prev != nil && now.Sub(prev.Generated) < renew && bytes.Equal(content(f), content(prev)) {
		f.Generated, f.Expires = prev.Generated, prev.Expires
	}
	return f, nil
}

func content(f *feed.Feed) []byte {
	c := *f
	c.Generated, c.Expires = time.Time{}, time.Time{}
	b, _ := json.Marshal(c)
	return b
}

func keygen() error {
	pub, priv, err := feed.GenerateKey()
	if err != nil {
		return err
	}
	k, err := feed.ParsePublicKey(pub)
	if err != nil {
		return err
	}
	fmt.Printf("public key (ID %s), for Pitstop:\n%s\n", feed.KeyID(k), pub)
	fmt.Printf("private key, for the FEED_SIGNING_KEY secret:\n%s\n", priv)
	return nil
}
