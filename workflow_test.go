package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Bush2021/chrome_update/feed"
)

func TestWorkflowStatus(t *testing.T) {
	for _, tc := range []struct {
		name      string
		change    string
		staged    bool
		installer bool
		tag       bool
	}{
		{name: "unchanged"},
		{name: "changed metadata", change: "readme.md"},
		{name: "staged metadata", change: "data.json", staged: true},
		{name: "downloaded installer", installer: true},
		{name: "existing tag", installer: true, tag: true},
		{name: "unrelated change", change: "curation.json"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			workflowRepo(t)
			const version = "156.0.8078.74"
			t.Setenv("latest_version", version)
			if tc.change != "" {
				writeFixture(t, tc.change, "changed\n")
				if tc.staged {
					testGit(t, "add", "--", tc.change)
				}
			}
			if tc.installer {
				writeFixture(t, "x64_installer.exe", "installer")
			}
			if tc.tag {
				testGit(t, "tag", version)
			}
			before := testGit(t, "status", "--porcelain")
			head := testGit(t, "rev-parse", "HEAD")
			if err := workflowStatus(context.Background()); err != nil {
				t.Fatal(err)
			}
			env := workflowEnv(t)
			wantChanged := tc.change == "readme.md" || tc.change == "data.json"
			for name, want := range map[string]bool{"exe_exists": tc.installer, "tag_exists": tc.tag, "metadata_changed": wantChanged} {
				if got := env[name]; got != "true" && got != "false" || (got == "true") != want {
					t.Errorf("%s = %q, want %t", name, got, want)
				}
			}
			zone, err := time.LoadLocation("America/New_York")
			if err != nil {
				t.Fatal(err)
			}
			stamp := strings.TrimPrefix(env["commit_message"], ":pencil: Auto update Chrome at ")
			when, err := time.ParseInLocation("2006-01-02 15:04", stamp, zone)
			if err != nil || time.Since(when) < 0 || time.Since(when) > 2*time.Minute {
				t.Errorf("commit_message = %q, parse error = %v", env["commit_message"], err)
			}
			if got := testGit(t, "status", "--porcelain"); got != before {
				t.Errorf("status changed from %q to %q", before, got)
			}
			if got := testGit(t, "rev-parse", "HEAD"); got != head {
				t.Error("workflow-status changed HEAD")
			}
		})
	}
}

func TestWorkflowStatusErrors(t *testing.T) {
	t.Run("missing version", func(t *testing.T) {
		workflowRepo(t)
		writeFixture(t, "installer.exe", "installer")
		if err := workflowStatus(context.Background()); err == nil {
			t.Fatal("accepted an installer without latest_version")
		}
	})
	t.Run("not a repository", func(t *testing.T) {
		t.Chdir(t.TempDir())
		t.Setenv("latest_version", "")
		t.Setenv("GITHUB_ENV", "")
		if err := workflowStatus(context.Background()); err == nil {
			t.Fatal("treated a Git error as no changes")
		}
	})
}

func TestWorkflowOrphanCommit(t *testing.T) {
	workflowRepo(t)
	tree := testGit(t, "rev-parse", "HEAD^{tree}")
	testGit(t, "checkout", "--orphan", "temp_branch")
	testGit(t, "commit", "-m", "Init")
	if got := testGit(t, "rev-parse", "HEAD^{tree}"); got != tree {
		t.Fatal("orphan commit changed the tracked files")
	}
	if got := testGit(t, "rev-list", "--parents", "-n", "1", "HEAD"); len(strings.Fields(got)) != 1 {
		t.Fatalf("orphan commit has parents: %s", got)
	}
}

func TestPrepareFeed(t *testing.T) {
	workflowRepo(t)
	remote := filepath.Join(t.TempDir(), "origin.git")
	testGit(t, "init", "--bare", remote)
	testGit(t, "remote", "add", "origin", remote)
	public, private, err := feed.GenerateKey()
	if err != nil {
		t.Fatal(err)
	}
	pub, err := feed.ParsePublicKey(public)
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("FEED_SIGNING_KEY", private)
	ctx := context.Background()
	c := updateServer(t, map[string]string{"x64-stable": "156.0.8078.74"})
	head := testGit(t, "rev-parse", "HEAD")
	status := testGit(t, "status", "--porcelain")
	if err := prepareFeed(ctx, c); err != nil {
		t.Fatal(err)
	}
	env := workflowEnv(t)
	commit := env["feed_commit"]
	if env["feed_changed"] != "true" || commit == "" {
		t.Fatalf("first feed status = %v", env)
	}
	if got := testGit(t, "ls-remote", "origin", "refs/heads/feed"); got != "" {
		t.Fatalf("prepare-feed pushed to origin: %s", got)
	}
	if got := testGit(t, "ls-tree", "--name-only", commit); got != "feed.json" {
		t.Fatalf("feed tree = %q", got)
	}
	if got := testGit(t, "rev-list", "--parents", "-n", "1", commit); got != commit {
		t.Fatalf("feed commit has parents: %s", got)
	}
	raw := testGit(t, "show", commit+":feed.json")
	first, err := feed.Open([]byte(raw), pub)
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Chrome) != 1 || first.Chrome[0].Version != "156.0.8078.74" {
		t.Fatalf("first feed = %+v", first)
	}

	// Only the workflow's explicit push publishes the prepared commit.
	testGit(t, "push", "origin", commit+":refs/heads/feed")
	if err := prepareFeed(ctx, c); err != nil {
		t.Fatal(err)
	}
	if got := workflowEnv(t)["feed_changed"]; got != "false" {
		t.Fatalf("unchanged feed marked %q", got)
	}
	if got := testGit(t, "ls-remote", "origin", "refs/heads/feed"); !strings.HasPrefix(got, commit+"\t") {
		t.Fatal("unchanged feed replaced the published commit")
	}

	c = updateServer(t, map[string]string{"x64-stable": "156.0.8078.80"})
	if err := prepareFeed(ctx, c); err != nil {
		t.Fatal(err)
	}
	env = workflowEnv(t)
	if env["feed_changed"] != "true" || env["feed_commit"] == commit {
		t.Fatalf("changed feed status = %v", env)
	}
	next, err := feed.Open([]byte(testGit(t, "show", env["feed_commit"]+":feed.json")), pub)
	if err != nil {
		t.Fatal(err)
	}
	if len(next.Chrome) != 1 || next.Chrome[0].Version != "156.0.8078.80" {
		t.Fatalf("next feed = %+v", next)
	}
	if got := testGit(t, "rev-parse", "HEAD"); got != head {
		t.Error("prepare-feed changed HEAD")
	}
	if got := testGit(t, "status", "--porcelain"); got != status {
		t.Errorf("prepare-feed changed status from %q to %q", status, got)
	}
}

func TestPrepareFeedWithoutKey(t *testing.T) {
	t.Chdir(t.TempDir())
	t.Setenv("FEED_SIGNING_KEY", "")
	t.Setenv("GITHUB_ENV", filepath.Join(t.TempDir(), "env"))
	writeFixture(t, os.Getenv("GITHUB_ENV"), "")
	if err := prepareFeed(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	if got := workflowEnv(t)["feed_changed"]; got != "false" {
		t.Errorf("missing key marked feed_changed=%q", got)
	}
}

func TestPrepareFeedRemoteFailure(t *testing.T) {
	workflowRepo(t)
	_, private, err := feed.GenerateKey()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("FEED_SIGNING_KEY", private)
	testGit(t, "remote", "add", "origin", filepath.Join(t.TempDir(), "missing.git"))
	if err := prepareFeed(context.Background(), nil); err == nil {
		t.Fatal("treated an inaccessible remote as a missing feed branch")
	}
	if got := workflowEnv(t)["feed_changed"]; got != "false" {
		t.Errorf("remote failure marked feed_changed=%q", got)
	}
}

func workflowRepo(t *testing.T) {
	t.Helper()
	t.Setenv("GIT_CONFIG_NOSYSTEM", "1")
	t.Setenv("GIT_CONFIG_GLOBAL", os.DevNull)
	t.Setenv("GIT_TERMINAL_PROMPT", "0")
	t.Setenv("latest_version", "")
	t.Setenv("FEED_SIGNING_KEY", "")
	t.Setenv("GITHUB_ENV", filepath.Join(t.TempDir(), "env"))
	writeFixture(t, os.Getenv("GITHUB_ENV"), "")
	t.Chdir(t.TempDir())
	testGit(t, "init", "--initial-branch=main")
	testGit(t, "config", "user.name", "Test")
	testGit(t, "config", "user.email", "test@example.com")
	for name, body := range map[string]string{"data.json": "{}\n", "readme.md": "readme\n", "curation.json": "{}\n", ".gitignore": "*.exe\n"} {
		writeFixture(t, name, body)
	}
	testGit(t, "add", "--", "data.json", "readme.md", "curation.json", ".gitignore")
	testGit(t, "commit", "-m", "Initial files")
}

func testGit(t *testing.T, args ...string) string {
	t.Helper()
	out, err := exec.Command("git", args...).CombinedOutput()
	if err != nil {
		t.Fatalf("git %s: %v\n%s", strings.Join(args, " "), err, out)
	}
	return strings.TrimSpace(string(out))
}

func writeFixture(t *testing.T, name, body string) {
	t.Helper()
	if err := os.WriteFile(name, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func workflowEnv(t *testing.T) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(os.Getenv("GITHUB_ENV"))
	if err != nil {
		t.Fatal(err)
	}
	env := map[string]string{}
	for line := range strings.SplitSeq(string(raw), "\n") {
		if name, value, ok := strings.Cut(line, "="); ok {
			env[name] = value
		}
	}
	return env
}
