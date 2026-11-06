package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
	_ "time/tzdata"

	"github.com/Bush2021/chrome_update/omaha"
)

func workflowStatus(ctx context.Context) error {
	files, err := filepath.Glob("*.exe")
	if err != nil {
		return err
	}
	version := os.Getenv("latest_version")
	if len(files) > 0 && version == "" {
		return errors.New("workflow-status: latest_version is empty")
	}
	tagExists := false
	if version != "" {
		_, err := git(ctx, nil, "show-ref", "--verify", "--quiet", "refs/tags/"+version)
		switch {
		case err == nil:
			tagExists = true
		case !exitCode(err, 1):
			return err
		}
	}

	_, err = git(ctx, nil, "diff", "--quiet", "HEAD", "--", "data.json", "readme.md")
	changed := exitCode(err, 1)
	if err != nil && !changed {
		return err
	}
	zone, err := time.LoadLocation("America/New_York")
	if err != nil {
		return err
	}
	for name, value := range map[string]string{
		"exe_exists":       fmt.Sprint(len(files) > 0),
		"tag_exists":       fmt.Sprint(tagExists),
		"metadata_changed": fmt.Sprint(changed),
		"commit_message":   ":pencil: Auto update Chrome at " + time.Now().In(zone).Format("2006-01-02 15:04"),
	} {
		if err := setEnv(name, value); err != nil {
			return err
		}
	}
	return nil
}

func prepareFeed(ctx context.Context, c *omaha.Client) error {
	if err := setEnv("feed_changed", "false"); err != nil {
		return err
	}
	if os.Getenv("FEED_SIGNING_KEY") == "" {
		log.Print("FEED_SIGNING_KEY isn't set")
		return nil
	}
	var previous []byte
	_, err := git(ctx, nil, "ls-remote", "--exit-code", "origin", "refs/heads/feed")
	switch {
	case err == nil:
		if _, err := git(ctx, nil, "fetch", "--depth=1", "origin", "refs/heads/feed"); err != nil {
			return err
		}
		previous, err = git(ctx, nil, "show", "FETCH_HEAD:feed.json")
		if err != nil {
			return err
		}
	case !exitCode(err, 2):
		return err
	}
	dir, err := os.MkdirTemp("", "chrome-installer-feed-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	old, next := filepath.Join(dir, "previous.json"), filepath.Join(dir, "feed.json")
	args := []string{"-curation", "curation.json", "-out", next}
	if previous != nil {
		if err := os.WriteFile(old, previous, 0o600); err != nil {
			return err
		}
		args = append(args, "-previous", old)
	}
	if err := runFeed(ctx, c, args); err != nil {
		return err
	}
	raw, err := os.ReadFile(next)
	if err != nil {
		return err
	}
	if bytes.Equal(previous, raw) {
		log.Print("The feed hasn't changed")
		return nil
	}
	blob, err := git(ctx, raw, "hash-object", "-w", "--stdin")
	if err != nil {
		return err
	}
	listing := fmt.Appendf(nil, "100644 blob %s\tfeed.json\n", strings.TrimSpace(string(blob)))
	tree, err := git(ctx, listing, "mktree")
	if err != nil {
		return err
	}
	commit, err := git(ctx, nil, "commit-tree", strings.TrimSpace(string(tree)), "-m", "Update the feed")
	if err != nil {
		return err
	}
	if err := setEnv("feed_commit", strings.TrimSpace(string(commit))); err != nil {
		return err
	}
	return setEnv("feed_changed", "true")
}

func git(ctx context.Context, input []byte, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Stdin = bytes.NewReader(input)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("git %s: %w", strings.Join(args, " "), err)
	}
	return out, nil
}

func exitCode(err error, code int) bool {
	var exit *exec.ExitError
	return errors.As(err, &exit) && exit.ExitCode() == code
}
