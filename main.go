// Command chrome_installer lists the newest Chrome installer of every
// channel and architecture in data.json and readme.md, and downloads the
// listed ones newer than the last release:
//
//	go run . fetch
//	go run . download win_stable_x86 win_stable_x64 win_stable_arm64
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"slices"
	"strconv"
	"strings"

	"github.com/Bush2021/chrome_update/fetch"
	"github.com/Bush2021/chrome_update/omaha"
)

var archs = []string{"x86", "x64", "arm64"}

type entry struct {
	Version string   `json:"version"`
	Size    int64    `json:"size"`
	SHA1    string   `json:"sha1"`
	SHA256  string   `json:"sha256"`
	URLs    []string `json:"urls"`
}

func main() {
	log.SetFlags(0)
	ctx := context.Background()
	results := load("data.json")
	var err error
	switch {
	case len(os.Args) == 2 && os.Args[1] == "fetch":
		if err = check(ctx, &omaha.Client{}, results); err == nil {
			err = save(results)
		}
	case len(os.Args) > 2 && os.Args[1] == "download":
		var last string
		if last, err = lastTag(); err == nil {
			err = download(ctx, results, last, os.Args[2:])
		}
	default:
		fmt.Fprintln(os.Stderr, "usage: chrome_installer fetch | download <key>...")
		os.Exit(2)
	}
	if err != nil {
		log.Fatal(err)
	}
}

func key(ch omaha.Channel, arch string) string {
	return "win_" + string(ch) + "_" + arch
}

func load(path string) map[string]entry {
	var results map[string]entry
	b, err := os.ReadFile(path)
	if err != nil || json.Unmarshal(b, &results) != nil || results == nil {
		return map[string]entry{}
	}
	return results
}

func check(ctx context.Context, c *omaha.Client, results map[string]entry) error {
	for _, ch := range omaha.Channels {
		for _, arch := range archs {
			k := key(ch, arch)
			in, err := c.Installer(ctx, ch, arch)
			if errors.Is(err, omaha.ErrStatus) {
				log.Printf("%s: %v", k, err)
				continue
			}
			if err != nil {
				return fmt.Errorf("%s: %w", k, err)
			}
			if old := results[k].Version; compareVersions(in.Version, old) < 0 {
				log.Printf("%s: keeping %s over the older %s", k, old, in.Version)
				continue
			}
			results[k] = entry{Version: in.Version, Size: in.Size, SHA1: in.SHA1, SHA256: in.SHA256, URLs: in.URLs}
		}
	}
	return nil
}

func save(results map[string]entry) error {
	if err := os.WriteFile("readme.md", render(results), 0o644); err != nil {
		return err
	}
	return os.WriteFile("data.json", encode(results), 0o644)
}

// encode keeps data.json's key order, which a map would sort.
func encode(results map[string]entry) []byte {
	var b bytes.Buffer
	b.WriteByte('{')
	for _, ch := range omaha.Channels {
		for _, arch := range archs {
			e, ok := results[key(ch, arch)]
			if !ok {
				continue
			}
			if b.Len() > 1 {
				b.WriteByte(',')
			}
			v, _ := json.Marshal(e)
			fmt.Fprintf(&b, "%q:%s", key(ch, arch), v)
		}
	}
	b.WriteByte('}')
	var out bytes.Buffer
	json.Indent(&out, b.Bytes(), "", "    ")
	return out.Bytes()
}

func render(results map[string]entry) []byte {
	var b bytes.Buffer
	b.WriteString("# Google Chrome Offline Installers (extract with 7-Zip)\n")
	b.WriteString("Stable release archive: https://github.com/Bush2021/chrome_installer/releases\n\n")
	b.WriteString("## Contents\n\n")
	var channels []omaha.Channel
	for _, ch := range omaha.Channels {
		for _, arch := range archs {
			if _, ok := results[key(ch, arch)]; ok {
				channels = append(channels, ch)
				break
			}
		}
	}
	for _, ch := range channels {
		fmt.Fprintf(&b, "- [%s](#%s)\n", title(ch), ch)
	}
	b.WriteString("\n")
	for _, ch := range channels {
		fmt.Fprintf(&b, "## %s\n\n", title(ch))
		b.WriteString("| Architecture | Version | Size | SHA-256 | Download |\n")
		b.WriteString("|--------------|---------|------|---------|----------|\n")
		for _, arch := range archs {
			e, ok := results[key(ch, arch)]
			if !ok {
				continue
			}
			name, sum := arch, e.SHA256
			if arch == "arm64" {
				name = "ARM64"
			}
			if len(sum) > 16 {
				sum = sum[:16] + "..."
			}
			fmt.Fprintf(&b, "| **%s** | `%s` | %s | `%s` | [Download](%s) |\n", name, e.Version, humanSize(e.Size), sum, link(e.URLs))
		}
		b.WriteString("\n<details>\n<summary>Full SHA-256 (sha256sum -c)</summary>\n\n```\n")
		for _, arch := range archs {
			if e, ok := results[key(ch, arch)]; ok {
				fmt.Fprintf(&b, "%s  %s\n", e.SHA256, asset(arch, e))
			}
		}
		b.WriteString("```\n\n</details>\n\n")
	}
	return b.Bytes()
}

func title(ch omaha.Channel) string {
	return strings.ToUpper(string(ch[:1])) + string(ch[1:])
}

func humanSize(n int64) string {
	units := []string{"B", "KB", "MB", "GB", "TB", "PB"}
	f, i := float64(n), 0
	for f >= 1024 && i < len(units)-1 {
		f /= 1024
		i++
	}
	return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%.2f", f), "0"), ".") + " " + units[i]
}

func link(urls []string) string {
	for _, u := range urls {
		if strings.HasPrefix(u, "https://") && strings.Contains(u, "google.com") {
			return u
		}
	}
	if len(urls) > 0 {
		return urls[0]
	}
	return "N/A"
}

// asset is the installer's name in a release.
func asset(arch string, e entry) string {
	u := link(e.URLs)
	return arch + "_" + u[strings.LastIndex(u, "/")+1:]
}

func download(ctx context.Context, results map[string]entry, last string, keys []string) error {
	for _, k := range keys {
		e, ok := results[k]
		if !ok {
			return fmt.Errorf("no %s in data.json", k)
		}
		// The workflow names the release after the last key's version.
		if err := setEnv("latest_version", e.Version); err != nil {
			return err
		}
		if compareVersions(e.Version, last) <= 0 {
			log.Printf("%s: %s is not newer than %s", k, e.Version, last)
			continue
		}
		name := asset(k[strings.LastIndex(k, "_")+1:], e)
		log.Printf("%s: downloading %s", k, name)
		if err := fetch.Get(ctx, nil, fetch.File{URLs: []string{link(e.URLs)}, Size: e.Size, SHA256: e.SHA256, Dest: name}, nil); err != nil {
			return fmt.Errorf("%s: %w", k, err)
		}
	}
	return nil
}

func setEnv(name, value string) error {
	path := os.Getenv("GITHUB_ENV")
	if path == "" {
		return nil
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(f, "%s=%s\n", name, value)
	return errors.Join(err, f.Close())
}

func lastTag() (string, error) {
	cmd := exec.Command("git", "tag", "--sort=-creatordate")
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("git tag: %w", err)
	}
	first, _, _ := strings.Cut(string(out), "\n")
	return strings.TrimSpace(first), nil
}

// compareVersions orders versions by their numbers; "" comes first.
func compareVersions(a, b string) int {
	numbers := func(v string) (n []int) {
		for _, s := range strings.Split(v, ".") {
			i, _ := strconv.Atoi(s)
			n = append(n, i)
		}
		return n
	}
	return slices.Compare(numbers(a), numbers(b))
}
