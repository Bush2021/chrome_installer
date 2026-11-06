package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Bush2021/chrome_update/feed"
	"github.com/Bush2021/chrome_update/omaha"
)

// updateServer answers protocol 4 checks with versions[ap], or an error
// status when ap isn't listed.
func updateServer(t *testing.T, versions map[string]string) *omaha.Client {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Request struct {
				Apps []struct {
					AP string `json:"ap"`
				} `json:"apps"`
			} `json:"request"`
		}
		json.NewDecoder(r.Body).Decode(&req)
		v, ok := versions[req.Request.Apps[0].AP]
		if !ok {
			fmt.Fprint(w, `)]}'`+"\n"+`{"response":{"apps":[{"status":"ok","updatecheck":{"status":"error-internal"}}]}}`)
			return
		}
		fmt.Fprintf(w, `)]}'`+"\n"+`{"response":{"apps":[{"status":"ok","updatecheck":{"status":"ok","nextversion":%q,"pipelines":[`+
			`{"pipeline_id":"1:full","operations":[{"type":"download","size":1,"out":{"sha256":"aa"},"urls":[{"url":"https://dl.google.com/%s"}]},{"type":"crx3","in":{"sha256":"aa"},"path":"installer.exe"}]}]}}]}}`, v, v)
	}))
	t.Cleanup(srv.Close)
	return &omaha.Client{Endpoint: srv.URL}
}

var (
	day0 = time.Date(2026, 10, 29, 12, 0, 0, 0, time.UTC)
	cur  = curation{Soak: feed.Soak{PatchHours: 24, MilestoneHours: 168}}
)

func TestMakeFeed(t *testing.T) {
	ctx := context.Background()
	c := updateServer(t, map[string]string{"x64-stable": "156.0.8078.74", "arm64-stable": "156.0.8078.74", "x64-canary": "158.0.1.0"})
	first, err := makeFeed(ctx, c, nil, cur, day0)
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Chrome) != 3 || first.Expires != day0.Add(validity) {
		t.Fatalf("feed = %+v", first)
	}
	b, _ := first.Build(omaha.Stable, "x64")
	if b.Published != day0 || b.Pipelines[0].Ops[0].URLs[0] != "https://dl.google.com/156.0.8078.74" {
		t.Fatalf("stable x64 = %+v", b)
	}

	// Three hours on: stable x64 gets a patch, arm64 is the same, and canary
	// fails, which keeps its build.
	c = updateServer(t, map[string]string{"x64-stable": "156.0.8078.80", "arm64-stable": "156.0.8078.74"})
	later := day0.Add(3 * time.Hour)
	next, err := makeFeed(ctx, c, first, cur, later)
	if err != nil {
		t.Fatal(err)
	}
	if next.Generated != later {
		t.Errorf("a changed feed kept the time %v", next.Generated)
	}
	for _, want := range []feed.Build{
		{Channel: omaha.Stable, Arch: "x64", Version: "156.0.8078.80", Published: later},
		{Channel: omaha.Stable, Arch: "arm64", Version: "156.0.8078.74", Published: day0},
		{Channel: omaha.Canary, Arch: "x64", Version: "158.0.1.0", Published: day0},
	} {
		got, ok := next.Build(want.Channel, want.Arch)
		if !ok || got.Version != want.Version || got.Published != want.Published {
			t.Errorf("%s %s = %+v, want %s first seen at %v", want.Channel, want.Arch, got, want.Version, want.Published)
		}
	}

	// Google going back to an older build doesn't take the feed back.
	c = updateServer(t, map[string]string{"x64-stable": "156.0.8078.74", "arm64-stable": "156.0.8078.74", "x64-canary": "158.0.1.0"})
	back, err := makeFeed(ctx, c, next, cur, later.Add(3*time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if b, _ := back.Build(omaha.Stable, "x64"); b.Version != "156.0.8078.80" {
		t.Errorf("stable x64 went back to %s", b.Version)
	}
}

func TestUnchangedFeedKeepsItsBytes(t *testing.T) {
	ctx := context.Background()
	_, priv, err := feed.GenerateKey()
	if err != nil {
		t.Fatal(err)
	}
	keys, err := signingKeys(priv)
	if err != nil {
		t.Fatal(err)
	}
	c := updateServer(t, map[string]string{"x64-stable": "156.0.8078.74"})
	first, err := makeFeed(ctx, c, nil, cur, day0)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := feed.Sign(first, keys...)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "feed.json")
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	prev := loadFeed(path, keys)
	if prev == nil {
		t.Fatal("couldn't read the feed back")
	}

	same, err := makeFeed(ctx, c, prev, cur, day0.Add(3*time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	again, err := feed.Sign(same, keys...)
	if err != nil {
		t.Fatal(err)
	}
	if string(again) != string(raw) {
		t.Error("an unchanged feed signed to new bytes")
	}

	renewed, err := makeFeed(ctx, c, prev, cur, day0.Add(renew))
	if err != nil {
		t.Fatal(err)
	}
	if renewed.Expires != day0.Add(renew+validity) {
		t.Errorf("a day-old feed expires at %v", renewed.Expires)
	}

	held := cur
	held.Holds = []feed.Hold{{Chrome: feed.Range{Min: "157"}, Reason: map[string]string{"en": "Breaks tabs."}}}
	changed, err := makeFeed(ctx, c, prev, held, day0.Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if changed.Generated == day0 {
		t.Error("a new hold kept the old feed's time")
	}
}

func TestLoadCuration(t *testing.T) {
	c, err := loadCuration("curation.json")
	if err != nil {
		t.Fatal(err)
	}
	if c.Soak.PatchHours != 24 || c.Soak.MilestoneHours != 168 {
		t.Errorf("soak = %+v", c.Soak)
	}
	path := filepath.Join(t.TempDir(), "curation.json")
	os.WriteFile(path, []byte(`{"holds":[{"chrome":{"min":"157"},"reason":{"zh-Hans":"标签页无法关闭"}}]}`), 0o644)
	if _, err := loadCuration(path); err == nil {
		t.Error("took a hold without an English reason")
	}
}

func TestSigningKeys(t *testing.T) {
	if _, err := signingKeys(" \n"); err == nil {
		t.Error("took an empty key")
	}
	_, a, _ := feed.GenerateKey()
	_, b, _ := feed.GenerateKey()
	keys, err := signingKeys(a + "\n" + b)
	if err != nil || len(keys) != 2 {
		t.Errorf("two keys: %d, %v", len(keys), err)
	}
}
