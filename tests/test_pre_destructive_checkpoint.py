"""Tests for the pre-destructive-command checkpoint safety net.

A mid-merge `git checkout <ref> -- .` clobbered in-progress conflict resolution in a
real session, and `git stash` — the obvious manual recovery tool — failed at exactly
that moment ("could not write index") because a merge was active. This makes the
safety net automatic (a PreToolUse hook, not something the operator has to remember)
and robust to that exact failure mode (checkpointing via `git diff`, which works
mid-merge, instead of `git stash`, which does not).

Uses real git repos in tmp_path rather than mocking git — the whole point is
verifying behavior against git's actual state machine, particularly the mid-merge
case, which is easy to get subtly wrong with a mock.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "scripts"))

from youk_hook_utils import is_destructive_command, write_pre_destructive_checkpoint


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False,
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-q"], r)
    _git(["config", "user.email", "test@test.com"], r)
    _git(["config", "user.name", "test"], r)
    (r / "file.txt").write_text("line1\n")
    _git(["add", "file.txt"], r)
    _git(["commit", "-q", "-m", "initial"], r)
    return r


class TestIsDestructiveCommand:
    def test_the_exact_command_that_caused_the_original_incident(self):
        assert is_destructive_command("git checkout origin/main -- .") is True

    @pytest.mark.parametrize("cmd", [
        "git checkout origin/main -- servers/shared/ab_experiments.py",
        "git checkout .",
        "rm -rf /tmp/foo",
        "rm -fr node_modules",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git merge --abort",
        "git rebase --abort",
        "git push --force origin main",
        "git branch -D old-branch",
        "git stash drop",
        "git stash clear",
        "git restore file.py",
    ])
    def test_destructive_patterns_are_caught(self, cmd):
        assert is_destructive_command(cmd) is True

    @pytest.mark.parametrize("cmd", [
        "git status",
        "git checkout main",
        "git checkout -b feature",
        "git log --oneline",
        "git push --force-with-lease origin main",
        "ls -la",
        "git diff",
        "rm file.txt",
    ])
    def test_safe_commands_are_not_flagged(self, cmd):
        assert is_destructive_command(cmd) is False


class TestWriteCheckpointBasics:
    def test_returns_none_outside_a_git_repo(self, tmp_path):
        assert write_pre_destructive_checkpoint(str(tmp_path), "rm -rf x") is None

    def test_returns_none_when_working_tree_is_clean(self, repo):
        assert write_pre_destructive_checkpoint(str(repo), "git checkout .") is None

    def test_returns_a_checkpoint_id_when_there_are_changes(self, repo):
        (repo / "file.txt").write_text("modified\n")
        cid = write_pre_destructive_checkpoint(str(repo), "git checkout .")
        assert cid is not None
        assert (repo / ".git" / "youk-checkpoints" / cid / "manifest.json").exists()

    def test_git_dir_is_anchored_to_the_target_repo_not_the_caller_cwd(self, repo, tmp_path, monkeypatch):
        """Regression: --git-dir is commonly relative ("./.git"), which resolves
        against whatever the CALLING process's cwd happens to be unless explicitly
        anchored to the target repo. A hook process's own cwd is not guaranteed to
        match the repo it was asked to checkpoint."""
        (repo / "file.txt").write_text("modified\n")
        elsewhere = tmp_path / "somewhere-else"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        cid = write_pre_destructive_checkpoint(str(repo), "git checkout .")

        assert cid is not None
        assert (repo / ".git" / "youk-checkpoints" / cid).exists()
        assert not (elsewhere / ".git").exists()

    def test_manifest_records_expected_fields(self, repo):
        (repo / "file.txt").write_text("modified\n")
        cid = write_pre_destructive_checkpoint(str(repo), "git checkout . # trailing")
        manifest = json.loads(
            (repo / ".git" / "youk-checkpoints" / cid / "manifest.json").read_text()
        )
        assert manifest["branch"] in ("main", "master")
        assert len(manifest["head_sha"]) == 40
        assert manifest["merge_in_progress"] is False
        assert "git checkout ." in manifest["triggering_command"]

    def test_patch_captures_tracked_file_changes(self, repo):
        (repo / "file.txt").write_text("modified content\n")
        cid = write_pre_destructive_checkpoint(str(repo), "git checkout .")
        patch = (repo / ".git" / "youk-checkpoints" / cid / "working_tree.patch").read_text()
        assert "modified content" in patch

    def test_untracked_files_are_copied(self, repo):
        (repo / "file.txt").write_text("modified\n")
        (repo / "new_file.txt").write_text("brand new\n")
        cid = write_pre_destructive_checkpoint(str(repo), "git checkout .")
        entry = repo / ".git" / "youk-checkpoints" / cid
        manifest = json.loads((entry / "manifest.json").read_text())
        assert "new_file.txt" in manifest["untracked_files"]
        assert (entry / "untracked" / "new_file.txt").read_text() == "brand new\n"

    def test_only_untracked_change_still_produces_a_checkpoint(self, repo):
        """No tracked-file diff, but a new file exists — must not be treated as clean."""
        (repo / "new_file.txt").write_text("only this is new\n")
        cid = write_pre_destructive_checkpoint(str(repo), "rm -rf .")
        assert cid is not None

    def test_rolling_cap_keeps_only_20_most_recent(self, repo):
        for i in range(25):
            (repo / "file.txt").write_text(f"version {i}\n")
            write_pre_destructive_checkpoint(str(repo), f"git checkout . # {i}")
        remaining = list((repo / ".git" / "youk-checkpoints").iterdir())
        assert len(remaining) == 20

    def test_never_raises_on_malformed_cwd(self):
        # must degrade to None, not propagate — a checkpoint failure must never be
        # able to block the real command it was trying to protect
        assert write_pre_destructive_checkpoint("/definitely/not/a/real/path", "rm -rf x") is None


class TestCheckpointDuringActiveMerge:
    """The exact scenario that caused the original incident: git stash fails mid-merge,
    so the checkpoint mechanism must not depend on stash succeeding."""

    @pytest.fixture
    def conflicted_repo(self, repo: Path) -> Path:
        _git(["checkout", "-q", "-b", "feature"], repo)
        (repo / "file.txt").write_text("feature change\n")
        _git(["commit", "-q", "-am", "feature change"], repo)
        _git(["checkout", "-q", "main"], repo)
        (repo / "file.txt").write_text("main change\n")
        _git(["commit", "-q", "-am", "main change"], repo)
        _git(["merge", "feature", "-q"], repo)  # produces a conflict
        return repo

    def test_git_stash_actually_fails_here(self, conflicted_repo):
        """Pins the premise: if this ever stops being true, the regression this
        test file protects against no longer applies the way it's described."""
        result = _git(["stash"], conflicted_repo)
        assert result.returncode != 0

    def test_checkpoint_succeeds_where_stash_fails(self, conflicted_repo):
        cid = write_pre_destructive_checkpoint(str(conflicted_repo), "git checkout main -- .")
        assert cid is not None

    def test_manifest_flags_merge_in_progress(self, conflicted_repo):
        cid = write_pre_destructive_checkpoint(str(conflicted_repo), "git checkout main -- .")
        manifest = json.loads(
            (conflicted_repo / ".git" / "youk-checkpoints" / cid / "manifest.json").read_text()
        )
        assert manifest["merge_in_progress"] is True

    def test_patch_preserves_conflict_markers(self, conflicted_repo):
        cid = write_pre_destructive_checkpoint(str(conflicted_repo), "git checkout main -- .")
        patch = (
            conflicted_repo / ".git" / "youk-checkpoints" / cid / "working_tree.patch"
        ).read_text()
        assert "<<<<<<<" in patch
        assert "feature change" in patch
        assert "main change" in patch
