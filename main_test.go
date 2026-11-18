package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/xml"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/Bush2021/chrome_update/omaha"
)

func TestWritesTheCommittedFiles(t *testing.T) {
	results := load("data.json")
	if len(results) == 0 {
		t.Fatal("no entries in data.json")
	}
	for name, got := range map[string][]byte{"data.json": encode(results), "readme.md": render(results)} {
		want, err := os.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		// With core.autocrlf, git checks the files out with CRLF.
		if want = bytes.ReplaceAll(want, []byte("\r\n"), []byte("\n")); !bytes.Equal(got, want) {
			t.Errorf("%s differs from what the program writes:\n%s", name, got)
		}
	}
}

func TestHumanSize(t *testing.T) {
	for n, want := range map[int64]string{0: "0 B", 1023: "1023 B", 1024: "1 KB", 1536: "1.5 KB", 525470120: "501.13 MB", 1 << 60: "1024 PB"} {
		if got := humanSize(n); got != want {
			t.Errorf("%d: %s, want %s", n, got, want)
		}
	}
}

func TestCheck(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			App struct {
				AP string `xml:"ap,attr"`
			} `xml:"app"`
		}
		xml.NewDecoder(r.Body).Decode(&req)
		if req.App.AP == "arm64-canary" {
			fmt.Fprint(w, `<response><app status="ok"><updatecheck status="error-internal"/></app></response>`)
			return
		}
		fmt.Fprint(w, `<response><app status="ok"><updatecheck status="ok"><urls><url codebase="https://dl.google.com/a/"/></urls>`+
			`<manifest version="200.0.0.1"><packages><package name="200.0.0.1_chrome_installer_uncompressed.exe" size="100" hash="NlwyRePAxOy7u0ptHmwu4TVQwd0=" hash_sha256="00"/></packages></manifest>`+
			`</updatecheck></app></response>`)
	}))
	defer srv.Close()
	results := map[string]entry{
		"win_stable_x64":   {Version: "156.0.8078.74"},
		"win_beta_x64":     {Version: "999.0.0.0"},
		"win_canary_arm64": {Version: "150.0.0.0"},
	}
	if err := check(context.Background(), &omaha.Client{InstallerEndpoint: srv.URL}, results); err != nil {
		t.Fatal(err)
	}
	if len(results) != 12 || results["win_beta_x64"].Version != "999.0.0.0" || results["win_canary_arm64"].Version != "150.0.0.0" {
		t.Errorf("%+v", results)
	}
	want := entry{Version: "200.0.0.1", Size: 100, SHA1: "365c3245e3c0c4ecbbbb4a6d1e6c2ee13550c1dd", SHA256: "00",
		URLs: []string{"https://dl.google.com/a/200.0.0.1_chrome_installer_uncompressed.exe"}}
	if got := results["win_stable_x64"]; !reflect.DeepEqual(got, want) {
		t.Errorf("%+v", got)
	}
}

func TestDownload(t *testing.T) {
	installer := []byte("installer")
	sum := sha256.Sum256(installer)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write(installer)
	}))
	defer srv.Close()
	env := filepath.Join(t.TempDir(), "env")
	if err := os.WriteFile(env, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("GITHUB_ENV", env)
	t.Chdir(t.TempDir())
	results := map[string]entry{
		"win_stable_x86": {Version: "156.0.8078.48"},
		"win_stable_x64": {Version: "156.0.8078.74", Size: int64(len(installer)), SHA256: hex.EncodeToString(sum[:]),
			URLs: []string{srv.URL + "/156.0.8078.74_chrome_installer_uncompressed.exe"}},
	}
	if err := download(context.Background(), results, "156.0.8078.48", []string{"win_stable_x86", "win_stable_x64"}); err != nil {
		t.Fatal(err)
	}
	if names, _ := filepath.Glob("*"); len(names) != 1 || names[0] != "x64_156.0.8078.74_chrome_installer_uncompressed.exe" {
		t.Errorf("downloaded %v", names)
	}
	if b, _ := os.ReadFile(env); string(b) != "latest_version=156.0.8078.48\nlatest_version=156.0.8078.74\n" {
		t.Errorf("GITHUB_ENV holds %q", b)
	}
}
