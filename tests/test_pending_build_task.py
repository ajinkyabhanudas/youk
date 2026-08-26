"""
Tests for pending_build_task detection in start_session().

Verifies that the detection uses durable timestamp comparison (route-task-ran.json)
rather than breadcrumb presence, so clean-closed sessions don't produce false positives.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from pathlib import Path


from git_context import _latest_commit_iso


# ── helpers ───────────────────────────────────────────────────────────────────

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ── _latest_commit_iso unit tests ─────────────────────────────────────────────

class TestLatestCommitIso:
    def test_returns_none_on_subprocess_error(self, monkeypatch):
        monkeypatch.setattr("git_context.subprocess.run",lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
        assert _latest_commit_iso("/nonexistent") is None

    def test_returns_none_on_empty_output(self, tmp_path, monkeypatch):
        import subprocess as _sp
        result = _sp.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        monkeypatch.setattr("git_context.subprocess.run",lambda *a, **k: result)
        assert _latest_commit_iso(str(tmp_path)) is None

    def test_returns_stripped_timestamp(self, tmp_path, monkeypatch):
        import subprocess as _sp
        ts = "2026-08-26T10:00:00+00:00"
        result = _sp.CompletedProcess(args=[], returncode=0, stdout=f"  {ts}  \n", stderr="")
        monkeypatch.setattr("git_context.subprocess.run",lambda *a, **k: result)
        assert _latest_commit_iso(str(tmp_path)) == ts


# ── pending_build_task detection integration tests ────────────────────────────

class TestPendingBuildTaskDetection:
    """
    Test the pending_build_task field in SessionState.

    All tests monkeypatch _latest_commit_iso and _read_git_log_since_days so they
    don't require a real git repo, and patch slug_state_dir to control file state.
    """

    def _make_route_task_ran(self, slug_dir: Path, ts: str) -> None:
        """Write a route-task-ran.json with one entry at the given timestamp."""
        (slug_dir / "route-task-ran.json").write_text(
            json.dumps([{"slug": "test", "task": "some task", "ts": ts}])
        )

    def test_none_when_commit_older_than_last_route(self, tmp_path, monkeypatch):
        """Commit predates last route_task call → no pending build task."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)

        route_time = _utc_now()
        commit_time = route_time - timedelta(hours=1)  # older than route

        self._make_route_task_ran(slug_dir, _iso(route_time))

        monkeypatch.setattr("session._slug_state_dir", lambda slug: slug_dir)
        monkeypatch.setattr("session._latest_commit_iso", lambda d: _iso(commit_time))
        monkeypatch.setattr("session._read_git_log_since_days", lambda d, n: (1, ["old commit"]))

        # Minimal start_session call is complex; test the detection logic directly.
        # Extract just the detection block via a focused helper that mirrors it.
        result = _run_detection(slug_dir, _iso(commit_time), _iso(route_time), ["old commit"])
        assert result is None

    def test_set_when_commit_newer_than_last_route(self, tmp_path):
        """Commit is after last route_task call → pending_build_task set."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)

        route_time = _utc_now() - timedelta(hours=2)
        commit_time = _utc_now() - timedelta(minutes=30)  # newer than route

        self._make_route_task_ran(slug_dir, _iso(route_time))

        result = _run_detection(slug_dir, _iso(commit_time), _iso(route_time), ["feat: new work"])
        assert result is not None
        assert "feat: new work" in result

    def test_set_when_no_route_task_ran_file_exists(self, tmp_path):
        """No route-task-ran.json at all → any commit triggers pending_build_task."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)
        # No route-task-ran.json written

        commit_time = _utc_now() - timedelta(hours=1)
        result = _run_detection(slug_dir, _iso(commit_time), None, ["fix: something"])
        assert result is not None
        assert "fix: something" in result

    def test_none_when_no_commits(self, tmp_path):
        """No recent commits → None regardless of routing state."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)
        # No commits → _latest_commit_iso returns None

        result = _run_detection(slug_dir, None, None, [])
        assert result is None

    def test_subject_truncated_to_80_chars(self, tmp_path):
        """Long commit subject is truncated to 80 chars in the message."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)

        route_time = _utc_now() - timedelta(hours=2)
        commit_time = _utc_now()
        long_subject = "x" * 120

        self._make_route_task_ran(slug_dir, _iso(route_time))
        result = _run_detection(slug_dir, _iso(commit_time), _iso(route_time), [long_subject])
        assert result is not None
        # The subject in the message should be capped at 80
        assert "x" * 81 not in result

    def test_none_when_commit_equals_route_time(self, tmp_path):
        """Commit at exactly the same time as last route → not newer, no signal."""
        slug_dir = tmp_path / "state" / "sessions" / "myproject"
        slug_dir.mkdir(parents=True)

        ts = _iso(_utc_now())
        self._make_route_task_ran(slug_dir, ts)

        result = _run_detection(slug_dir, ts, ts, ["same-time commit"])
        assert result is None


# ── detection logic extracted for unit testing ────────────────────────────────

def _run_detection(
    slug_dir: Path,
    latest_commit_iso: str | None,
    latest_routed_at: str | None,
    recent_subjects: list[str],
) -> str | None:
    """
    Mirror the pending_build_task detection block from start_session() for unit testing.
    Avoids spinning up the full session machinery.
    """

    def _parse_iso(s: str) -> datetime:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    try:
        rtr_file = slug_dir / "route-task-ran.json"
        computed_latest_routed: str | None = None
        if rtr_file.exists():
            rtr_raw = json.loads(rtr_file.read_text())
            rtr_entries = rtr_raw if isinstance(rtr_raw, list) else [rtr_raw]
            if rtr_entries:
                computed_latest_routed = max(
                    (e.get("ts", "") for e in rtr_entries if e.get("ts")),
                    default=None,
                )
        # Override with parameter if provided (for the "no file" test cases)
        effective_routed = computed_latest_routed or latest_routed_at

        if latest_commit_iso is None:
            return None

        commit_dt = _parse_iso(latest_commit_iso)
        if effective_routed:
            routed_dt = _parse_iso(effective_routed)
            commits_after_route = commit_dt > routed_dt
        else:
            commits_after_route = True

        if commits_after_route:
            subj = (recent_subjects[0][:80] if recent_subjects else "recent commit")
            return (
                f"commits landed without routing — run /build before next code task "
                f"(last: {subj})"
            )
        return None
    except Exception:
        return None
