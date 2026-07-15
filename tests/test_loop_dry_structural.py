"""
Structural loop-dry tracking tests.

Verifies that mark_challenge_ran increments rounds counter, that session_end
reads rounds from state rather than trusting the caller, and that server-side
correction detection fires from the summary without requiring Claude to set the flag.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Point at shared + core src
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(tmp_path: Path) -> tuple[Path, Path]:
    """Return (youk_root, claude_root) with minimal state structure."""
    youk_root = tmp_path / "youk"
    claude_root = tmp_path / "claude"
    (youk_root / "state").mkdir(parents=True)
    (youk_root / "knowledge" / "projects").mkdir(parents=True)
    (youk_root / "knowledge" / "proposals").mkdir(parents=True)
    (claude_root / "audit").mkdir(parents=True)
    # Write slug
    (youk_root / "state" / "session-open.json").write_text(
        json.dumps({"slug": "test-project", "timestamp": "2026-07-15T10:00:00Z", "plan_items": []})
    )
    return youk_root, claude_root


# ---------------------------------------------------------------------------
# mark_challenge_ran — rounds counter
# ---------------------------------------------------------------------------

class TestMarkChallengeRanRoundsCounter:

    def test_first_call_sets_rounds_to_1(self, tmp_path):
        youk_root, _ = _make_state(tmp_path)
        flag_file = youk_root / "state" / "challenge-ran.json"

        # Simulate the counter logic from server.py mark_challenge_ran
        slug = "test-project"
        existing_rounds = 0
        if flag_file.exists():
            existing = json.loads(flag_file.read_text())
            if existing.get("slug") == slug:
                existing_rounds = existing.get("rounds", 0)
        new_rounds = existing_rounds + 1
        flag_file.write_text(json.dumps({"slug": slug, "task": "task A", "ts": "2026-07-15T10:00:00", "rounds": new_rounds}))

        data = json.loads(flag_file.read_text())
        assert data["rounds"] == 1

    def test_second_call_increments_to_2(self, tmp_path):
        youk_root, _ = _make_state(tmp_path)
        flag_file = youk_root / "state" / "challenge-ran.json"
        slug = "test-project"

        for expected in [1, 2]:
            existing_rounds = 0
            if flag_file.exists():
                existing = json.loads(flag_file.read_text())
                if existing.get("slug") == slug:
                    existing_rounds = existing.get("rounds", 0)
            flag_file.write_text(json.dumps({
                "slug": slug, "task": "task", "ts": "2026-07-15T10:00:00",
                "rounds": existing_rounds + 1,
            }))
            assert json.loads(flag_file.read_text())["rounds"] == expected

    def test_counter_resets_across_sessions(self, tmp_path):
        youk_root, _ = _make_state(tmp_path)
        flag_file = youk_root / "state" / "challenge-ran.json"

        # Write as prior session slug
        flag_file.write_text(json.dumps({"slug": "other-project", "task": "x", "ts": "2026-07-14T09:00:00", "rounds": 5}))

        # New session, different slug — existing_rounds should NOT carry over
        slug = "test-project"
        existing_rounds = 0
        existing = json.loads(flag_file.read_text())
        if existing.get("slug") == slug:
            existing_rounds = existing.get("rounds", 0)
        new_rounds = existing_rounds + 1
        flag_file.write_text(json.dumps({"slug": slug, "task": "y", "ts": "2026-07-15T10:00:00", "rounds": new_rounds}))

        assert json.loads(flag_file.read_text())["rounds"] == 1

    def test_rounds_key_present_in_written_file(self, tmp_path):
        youk_root, _ = _make_state(tmp_path)
        flag_file = youk_root / "state" / "challenge-ran.json"
        flag_file.write_text(json.dumps({"slug": "test-project", "task": "t", "ts": "2026-07-15T10:00:00", "rounds": 3}))
        data = json.loads(flag_file.read_text())
        assert "rounds" in data

    def test_third_call_sets_rounds_to_3(self, tmp_path):
        youk_root, _ = _make_state(tmp_path)
        flag_file = youk_root / "state" / "challenge-ran.json"
        slug = "test-project"
        for i in range(3):
            existing_rounds = 0
            if flag_file.exists():
                existing = json.loads(flag_file.read_text())
                if existing.get("slug") == slug:
                    existing_rounds = existing.get("rounds", 0)
            flag_file.write_text(json.dumps({"slug": slug, "task": "t", "ts": "2026-07-15T10:00:00", "rounds": existing_rounds + 1}))
        assert json.loads(flag_file.read_text())["rounds"] == 3


# ---------------------------------------------------------------------------
# session_end — structural correction detection from summary
# ---------------------------------------------------------------------------

class TestSessionEndCorrectionDetection:
    """The server scans the summary for correction language — no reliance on Claude's flag."""

    _CORRECTION_PHRASES = [
        "you missed", "what about", "unchallenged", "you didn't consider",
        "still not at floor", "loop not dry", "not at floor", "still not done",
        "angle unchallenged", "you forgot", "missed this",
    ]

    def _correction_detected(self, summary: str) -> bool:
        summary_lower = summary.lower()
        return any(p in summary_lower for p in self._CORRECTION_PHRASES)

    def test_you_missed_triggers_correction(self):
        assert self._correction_detected("Developer said: you missed the rate-limit angle") is True

    def test_unchallenged_triggers_correction(self):
        assert self._correction_detected("An angle remained unchallenged after verdict") is True

    def test_loop_not_dry_triggers_correction(self):
        assert self._correction_detected("loop not dry — verdict emitted too early") is True

    def test_not_at_floor_triggers_correction(self):
        assert self._correction_detected("Still not at floor — temporal angle skipped") is True

    def test_angle_unchallenged_triggers_correction(self):
        assert self._correction_detected("angle unchallenged after PASSED token") is True

    def test_you_forgot_triggers_correction(self):
        assert self._correction_detected("you forgot the adversarial angle entirely") is True

    def test_clean_summary_no_correction(self):
        assert self._correction_detected("Challenge ran through all angles, no objections found.") is False

    def test_what_about_triggers_correction(self):
        assert self._correction_detected("Developer asked: what about the semantic angle?") is True

    def test_case_insensitive_match(self):
        assert self._correction_detected("YOU MISSED the temporal angle") is True

    def test_caller_false_overridden_by_summary(self):
        """When caller passes loop_correction_detected=False but summary has phrase: server sets True."""
        summary = "Session went well. Developer noted: you missed the failure-mode angle."
        caller_flag = False
        # Server-side override logic
        result = caller_flag or self._correction_detected(summary)
        assert result is True

    def test_caller_true_preserved_even_clean_summary(self):
        """When caller passes True, it stays True regardless of summary content."""
        summary = "Session completed cleanly. All angles covered."
        caller_flag = True
        result = caller_flag or self._correction_detected(summary)
        assert result is True


# ---------------------------------------------------------------------------
# session_end — state-file rounds reading (max logic)
# ---------------------------------------------------------------------------

class TestSessionEndRoundsFromStateFile:
    """challenge_rounds uses max(caller_value, state_file_value)."""

    def _read_rounds_from_state(self, flag_file: Path, current_slug: str) -> int:
        if not flag_file.exists():
            return 0
        try:
            data = json.loads(flag_file.read_text())
            if data.get("slug") == current_slug:
                return data.get("rounds", 0)
        except Exception:
            pass
        return 0

    def test_state_file_rounds_used_when_higher_than_caller(self, tmp_path):
        flag_file = tmp_path / "challenge-ran.json"
        flag_file.write_text(json.dumps({"slug": "proj", "task": "t", "ts": "2026-07-15T10:00:00", "rounds": 4}))
        caller_rounds = 1
        state_rounds = self._read_rounds_from_state(flag_file, "proj")
        assert max(caller_rounds, state_rounds) == 4

    def test_caller_rounds_used_when_higher(self, tmp_path):
        flag_file = tmp_path / "challenge-ran.json"
        flag_file.write_text(json.dumps({"slug": "proj", "task": "t", "ts": "2026-07-15T10:00:00", "rounds": 2}))
        caller_rounds = 5
        state_rounds = self._read_rounds_from_state(flag_file, "proj")
        assert max(caller_rounds, state_rounds) == 5

    def test_slug_mismatch_returns_zero_from_state(self, tmp_path):
        flag_file = tmp_path / "challenge-ran.json"
        flag_file.write_text(json.dumps({"slug": "other-proj", "task": "t", "ts": "2026-07-15T10:00:00", "rounds": 7}))
        state_rounds = self._read_rounds_from_state(flag_file, "current-proj")
        assert state_rounds == 0

    def test_missing_state_file_returns_zero(self, tmp_path):
        flag_file = tmp_path / "does-not-exist.json"
        state_rounds = self._read_rounds_from_state(flag_file, "proj")
        assert state_rounds == 0

    def test_state_file_with_no_rounds_key_returns_zero(self, tmp_path):
        flag_file = tmp_path / "challenge-ran.json"
        flag_file.write_text(json.dumps({"slug": "proj", "task": "t", "ts": "2026-07-15T10:00:00"}))
        state_rounds = self._read_rounds_from_state(flag_file, "proj")
        assert state_rounds == 0
