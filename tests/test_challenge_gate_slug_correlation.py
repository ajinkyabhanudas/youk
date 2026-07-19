"""
Regression tests for session_slug.get_session_slug and check_challenge_gate
slug correlation fix.

Bug: when session-open.json does not exist, mark_challenge_ran wrote slug="unknown"
and check_challenge_gate read current_slug="" — the comparison always failed, causing
check_challenge_gate to return blocked=True even after mark_challenge_ran recorded
success.

Fix: get_session_slug() falls back to session.json session_counter when
session-open.json is absent, so both functions always agree on the slug.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO / "servers" / "core" / "src"))
sys.path.insert(0, str(_REPO / "servers" / "shared"))

from session_slug import get_session_slug
from challenge_gate import check_challenge_gate


class TestGetSessionSlug:
    """get_session_slug returns consistent values under different state layouts."""

    def test_reads_session_open_when_present(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "session-open.json").write_text(json.dumps({"slug": "my-project"}))
        assert get_session_slug(tmp_path) == "my-project"

    def test_falls_back_to_session_counter_when_session_open_absent(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "session.json").write_text(json.dumps({"session_counter": 50}))
        assert get_session_slug(tmp_path) == "session-50"

    def test_returns_unknown_when_both_files_absent(self, tmp_path):
        (tmp_path / "state").mkdir()
        assert get_session_slug(tmp_path) == "unknown"

    def test_session_open_takes_priority_over_session_json(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "session-open.json").write_text(json.dumps({"slug": "explicit-slug"}))
        (state / "session.json").write_text(json.dumps({"session_counter": 99}))
        assert get_session_slug(tmp_path) == "explicit-slug"

    def test_handles_corrupt_session_open(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "session-open.json").write_text("not valid json{{{")
        (state / "session.json").write_text(json.dumps({"session_counter": 7}))
        assert get_session_slug(tmp_path) == "session-7"

    def test_handles_missing_slug_key_in_session_open(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "session-open.json").write_text(json.dumps({"other_key": "value"}))
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
        """Write challenge-ran.json and return the slug used."""
        (youk_root / "state").mkdir(parents=True, exist_ok=True)
        (youk_root / "state" / "challenge-ran.json").write_text(json.dumps({
            "slug": slug,
            "task": "the task",
            "ts": "2026-07-19T10:00:00",
            "rounds": rounds,
            "angles_validated": True,
            "mode": "full",
        }))
        return slug

    def test_slug_symmetric_with_session_open(self, tmp_path):
        """When session-open.json exists, write and read produce the same slug."""
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "session-open.json").write_text(json.dumps({"slug": "test-project"}))

        write_slug = get_session_slug(tmp_path)
        self._make_challenge_ran(tmp_path, slug=write_slug)

        read_slug = get_session_slug(tmp_path)
        stored_slug = json.loads((tmp_path / "state" / "challenge-ran.json").read_text())["slug"]

        assert write_slug == read_slug == stored_slug == "test-project"
        assert check_challenge_gate("the task", "M", challenge_ran=(stored_slug == read_slug))["blocked"] is False

    def test_slug_symmetric_without_session_open(self, tmp_path):
        """Regression: without session-open.json, write and read both produce session-{counter}."""
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "session.json").write_text(json.dumps({"session_counter": 50}))

        write_slug = get_session_slug(tmp_path)
        assert write_slug == "session-50"

        self._make_challenge_ran(tmp_path, slug=write_slug)

        read_slug = get_session_slug(tmp_path)
        stored_slug = json.loads((tmp_path / "state" / "challenge-ran.json").read_text())["slug"]

        assert write_slug == read_slug == stored_slug == "session-50"
        assert check_challenge_gate("the task", "M", challenge_ran=(stored_slug == read_slug))["blocked"] is False

    def test_stale_slug_does_not_pass_gate(self, tmp_path):
        """challenge-ran.json written for session-49 must not pass session-50's gate."""
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "session.json").write_text(json.dumps({"session_counter": 50}))

        self._make_challenge_ran(tmp_path, slug="session-49")

        current_slug = get_session_slug(tmp_path)
        stored_slug = json.loads((tmp_path / "state" / "challenge-ran.json").read_text())["slug"]
        challenge_ran = stored_slug == current_slug

        assert challenge_ran is False
        assert check_challenge_gate("the task", "M", challenge_ran=challenge_ran)["blocked"] is True

    def test_xs_bypasses_gate_entirely(self, tmp_path):
        (tmp_path / "state").mkdir()
        assert check_challenge_gate("rename var", "XS", challenge_ran=False)["blocked"] is False
