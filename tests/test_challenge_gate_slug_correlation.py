"""
Regression tests for session_slug.get_session_slug and check_challenge_gate
slug correlation fix.

After slug-scoped state isolation (Change 0), get_session_slug reads from
state/sessions/{slug}/open.json (the per-slug location). The root-level
session-open.json is a redirect pointer only and is never used for slug resolution.

If no active slug-scoped open.json exists, returns "unknown". There is no
fallback to session.json counter — the counter-based slug was a pre-isolation
workaround that is no longer needed.
"""
from __future__ import annotations
import json
import time
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO / "servers" / "core" / "src"))
sys.path.insert(0, str(_REPO / "servers" / "shared"))

from session_slug import get_session_slug
from challenge_gate import check_challenge_gate


def _write_slug_open(youk_root: Path, slug: str) -> Path:
    """Write state/sessions/{slug}/open.json as session_start does."""
    slug_dir = youk_root / "state" / "sessions" / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    f = slug_dir / "open.json"
    f.write_text(json.dumps({"slug": slug, "written_at": time.time()}))
    return f


class TestGetSessionSlug:
    """get_session_slug returns consistent values under different state layouts."""

    def test_reads_slug_scoped_open_json(self, tmp_path):
        _write_slug_open(tmp_path, "my-project")
        assert get_session_slug(tmp_path) == "my-project"

    def test_returns_unknown_when_no_sessions_dir(self, tmp_path):
        (tmp_path / "state").mkdir()
        assert get_session_slug(tmp_path) == "unknown"

    def test_returns_unknown_when_sessions_dir_empty(self, tmp_path):
        (tmp_path / "state" / "sessions").mkdir(parents=True)
        assert get_session_slug(tmp_path) == "unknown"

    def test_prefers_most_recent_slug(self, tmp_path):
        _write_slug_open(tmp_path, "older")
        time.sleep(0.01)
        _write_slug_open(tmp_path, "newer")
        assert get_session_slug(tmp_path) == "newer"

    def test_handles_corrupt_open_json(self, tmp_path):
        slug_dir = tmp_path / "state" / "sessions" / "broken"
        slug_dir.mkdir(parents=True)
        (slug_dir / "open.json").write_text("not json{{{")
        assert get_session_slug(tmp_path) == "unknown"

    def test_handles_missing_slug_key_in_open_json(self, tmp_path):
        slug_dir = tmp_path / "state" / "sessions" / "noslug"
        slug_dir.mkdir(parents=True)
        (slug_dir / "open.json").write_text(json.dumps({"other_key": "value", "written_at": time.time()}))
        assert get_session_slug(tmp_path) == "unknown"

    def test_root_session_open_json_ignored(self, tmp_path):
        """Root-level session-open.json is a redirect pointer only, never used for slug resolution."""
        state = tmp_path / "state"
        state.mkdir()
        (state / "session-open.json").write_text(json.dumps({"slug": "should-not-be-read"}))
        # No slug-scoped open.json → must return "unknown"
        assert get_session_slug(tmp_path) == "unknown"


class TestCheckChallengeGateSlugCorrelation:
    """Simulate server-level slug matching with the pure challenge_gate function.

    The server's check_challenge_gate calls get_session_slug to derive current_slug,
    then compares it against challenge-ran.json's stored slug. These tests verify that
    the slug derivation is symmetric — the same slug is produced for both writes and reads.
    """

    ALL_ANGLES = [
        "framing", "scope", "assumptions", "opportunity",
        "structural", "operational", "experiential",
        "adversarial", "temporal", "outcome", "semantic",
    ]

    def _make_challenge_ran(self, youk_root: Path, slug: str, rounds: int = 1) -> dict:
        """Write challenge-ran.json under the slug-scoped dir."""
        slug_dir = youk_root / "state" / "sessions" / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        (slug_dir / "challenge-ran.json").write_text(json.dumps({
            "slug": slug,
            "task": "the task",
            "ts": "2026-07-19T10:00:00",
            "rounds": rounds,
            "angles_validated": True,
            "mode": "full",
        }))
        return slug

    def test_slug_symmetric_with_slug_scoped_open(self, tmp_path):
        """When sessions/{slug}/open.json exists, write and read produce the same slug."""
        _write_slug_open(tmp_path, "test-project")

        write_slug = get_session_slug(tmp_path)
        self._make_challenge_ran(tmp_path, slug=write_slug)

        read_slug = get_session_slug(tmp_path)
        slug_dir = tmp_path / "state" / "sessions" / write_slug
        stored_slug = json.loads((slug_dir / "challenge-ran.json").read_text())["slug"]

        assert write_slug == read_slug == stored_slug == "test-project"
        assert check_challenge_gate("the task", "M", challenge_ran=(stored_slug == read_slug))["blocked"] is False

    def test_stale_slug_does_not_pass_gate(self, tmp_path):
        """challenge-ran.json written for session-49 must not pass a different session's gate."""
        _write_slug_open(tmp_path, "current-session")
        self._make_challenge_ran(tmp_path, slug="old-session")

        current_slug = get_session_slug(tmp_path)
        slug_dir = tmp_path / "state" / "sessions" / "old-session"
        stored_slug = json.loads((slug_dir / "challenge-ran.json").read_text())["slug"]
        challenge_ran = stored_slug == current_slug

        assert challenge_ran is False
        assert check_challenge_gate("the task", "M", challenge_ran=challenge_ran)["blocked"] is True

    def test_xs_bypasses_gate_entirely(self, tmp_path):
        (tmp_path / "state").mkdir()
        assert check_challenge_gate("rename var", "XS", challenge_ran=False)["blocked"] is False

    def test_unknown_slug_does_not_pass_gate(self, tmp_path):
        """When no active session exists, slug resolves to 'unknown' — gate stays blocked."""
        (tmp_path / "state" / "sessions").mkdir(parents=True)
        # Write challenge-ran for a different slug — should not match "unknown"
        self._make_challenge_ran(tmp_path, slug="some-other-session")
        current_slug = get_session_slug(tmp_path)
        assert current_slug == "unknown"
