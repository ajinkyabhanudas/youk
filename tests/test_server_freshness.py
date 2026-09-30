"""Tests for server_freshness — the real-consequence half of CIR-153.

deploy_freshness.py's warning is satisfied by a state file (`last_head`) any
session can silently advance, which is exactly why a stale youk-core
container sat unnoticed for a week (CIR-152). server_freshness.py asks a
question no session can quietly answer instead: does the container's actual
Docker boot time predate the last commit touching runtime-sensitive paths?

Docker/launchctl calls are monkeypatched (no real container required to run
this suite); git is exercised against a real temporary repo, matching
test_deploy_freshness.py's convention of never mocking git itself.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "scripts"))

import server_freshness as sf  # noqa: E402


def _git(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t.t")
    _git(d, "config", "user.name", "t")
    (d / "README.md").write_text("x")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "init")
    return d


def _commit(d: Path, rel: str) -> str:
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", f"touch {rel}")
    r = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%cI"],
                        capture_output=True, text=True, check=True)
    return r.stdout.strip()


class TestLatestRuntimeCommitSince:
    def test_runtime_commit_after_since_is_found(self, tmp_path):
        d = _repo(tmp_path)
        before = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%cI"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        _commit(d, "servers/core/src/session.py")
        assert sf.latest_runtime_commit_since(d, before) is not None

    def test_docs_only_commit_after_since_is_not_found(self, tmp_path):
        d = _repo(tmp_path)
        before = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%cI"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        _commit(d, "docs/notes.md")
        assert sf.latest_runtime_commit_since(d, before) is None

    def test_runtime_commit_before_since_is_not_found(self, tmp_path):
        d = _repo(tmp_path)
        _commit(d, "servers/core/src/session.py")
        # strictly after the commit — git's --since is inclusive of an exact
        # timestamp match, so "after" must not equal the commit's own time
        after = subprocess.run(
            ["date", "-u", "-v+1S", "+%Y-%m-%dT%H:%M:%SZ"]
            if sys.platform == "darwin" else
            ["date", "-u", "-d", "+1 second", "+%Y-%m-%dT%H:%M:%SZ"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert sf.latest_runtime_commit_since(d, after) is None


class TestIsStale:
    def test_unknown_server_is_indeterminate(self, tmp_path):
        d = _repo(tmp_path)
        assert sf.is_stale(d, "some-other-server") is None

    def test_container_unreachable_is_indeterminate(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        monkeypatch.setattr(sf, "container_started_at", lambda c: None)
        assert sf.is_stale(d, "youk-core") is None

    def test_container_booted_before_runtime_commit_is_stale(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        boot = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%cI"],
                               capture_output=True, text=True, check=True).stdout.strip()
        _commit(d, "servers/core/src/session.py")
        monkeypatch.setattr(sf, "container_started_at", lambda c: boot)
        assert sf.is_stale(d, "youk-core") is True

    def test_container_booted_after_runtime_commit_is_fresh(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        _commit(d, "servers/core/src/session.py")
        # container boot must be strictly after the commit
        future = "2099-01-01T00:00:00Z"
        monkeypatch.setattr(sf, "container_started_at", lambda c: future)
        assert sf.is_stale(d, "youk-core") is False


class TestRestart:
    def test_kickstart_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr(sf, "container_started_at", lambda c: "2026-01-01T00:00:00Z")

        def fake_run(args, timeout=5.0):
            if args[0] == "launchctl":
                return subprocess.CompletedProcess(args, 1, "", "boom")
            raise AssertionError(f"unexpected call: {args}")

        monkeypatch.setattr(sf, "_run", fake_run)
        assert sf.restart("youk-core", ready_timeout=1, poll_interval=0.1) is False

    def test_container_never_reboots_times_out_false(self, monkeypatch):
        monkeypatch.setattr(sf, "container_started_at", lambda c: "2026-01-01T00:00:00Z")

        def fake_run(args, timeout=5.0):
            assert args[0] == "launchctl"
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(sf, "_run", fake_run)
        assert sf.restart("youk-core", ready_timeout=0.3, poll_interval=0.1) is False

    def test_container_reboots_returns_true(self, monkeypatch):
        calls = {"n": 0}

        def fake_started_at(c):
            calls["n"] += 1
            # First call (the "before" read) sees the old boot time; every
            # poll afterward sees the new one — simulates the restart landing.
            return "T0" if calls["n"] == 1 else "T1"

        monkeypatch.setattr(sf, "container_started_at", fake_started_at)

        def fake_run(args, timeout=5.0):
            assert args[0] == "launchctl"
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(sf, "_run", fake_run)
        assert sf.restart("youk-core", ready_timeout=2, poll_interval=0.1) is True

    def test_unknown_server_returns_false(self):
        assert sf.restart("not-a-real-server") is False


class TestEnforce:
    def test_fresh_server_allows_silently(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        monkeypatch.setattr(sf, "is_stale", lambda root, server: False)
        verdict = sf.enforce(d, "youk-core")
        assert verdict == {"action": "allow"}

    def test_indeterminate_fails_closed(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        monkeypatch.setattr(sf, "is_stale", lambda root, server: None)
        verdict = sf.enforce(d, "youk-core")
        assert verdict["action"] == "deny"
        assert "could not be determined" in verdict["message"]

    def test_stale_server_auto_restarts_and_allows(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        monkeypatch.setattr(sf, "is_stale", lambda root, server: True)
        monkeypatch.setattr(sf, "restart", lambda server, **kw: True)
        verdict = sf.enforce(d, "youk-core")
        assert verdict["action"] == "allow"
        assert "auto-restarted" in verdict["message"].lower()

    def test_stale_server_failed_restart_denies_with_manual_instruction(self, tmp_path, monkeypatch):
        d = _repo(tmp_path)
        monkeypatch.setattr(sf, "is_stale", lambda root, server: True)
        monkeypatch.setattr(sf, "restart", lambda server, **kw: False)
        verdict = sf.enforce(d, "youk-core")
        assert verdict["action"] == "deny"
        assert "launchctl kickstart" in verdict["message"]
        assert "com.youk.core-server" in verdict["message"]
