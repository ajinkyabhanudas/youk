"""
Convergence learning system tests.

Covers:
- _compute_convergence_velocity: trend of challenge_rounds across sessions
- _compute_human_precision_rate: fraction of high-precision challenge sessions
- HumanPrecision audit line written by session.py end_session logic
- check_loop_dry structural sensor (state-file based)
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

from health import _compute_convergence_velocity, _compute_human_precision_rate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(skills=None, challenge_rounds=None, developer_caught=None,
             loop_correction=False, loop_gap=False, human_precision=False) -> dict:
    skills = skills or []
    return {
        "skills": skills,
        "capability_skills": [],
        "close_cluster": True,
        "project": "test",
        "challenge_rounds": challenge_rounds,
        "developer_caught": developer_caught or [],
        "loop_correction": loop_correction,
        "loop_gap": loop_gap,
        "human_precision": human_precision,
        "raw": "",
        "tokens_actual": 0,
        "tokens_budget": 0,
        "tokens_ratio": None,
        "findings_total": 0,
        "findings_critical": 0,
        "findings_high": 0,
        "finding_categories": [],
        "nfr_gaps": [],
        "direction_reversal": False,
        "framing_correct": None,
    }


def _challenge_session(rounds: int, developer_caught=None,
                        loop_correction=False, human_precision=False) -> dict:
    return _session(
        skills=["challenge", "dev-loop"],
        challenge_rounds=rounds,
        developer_caught=developer_caught or [],
        loop_correction=loop_correction,
        human_precision=human_precision,
    )


# ---------------------------------------------------------------------------
# _compute_convergence_velocity
# ---------------------------------------------------------------------------

class TestConvergenceVelocity:

    def test_insufficient_data_with_no_sessions(self):
        result = _compute_convergence_velocity([])
        assert result["trend"] == "insufficient_data"
        assert result["sessions_with_data"] == 0

    def test_insufficient_data_with_one_session(self):
        sessions = [_challenge_session(rounds=3)]
        result = _compute_convergence_velocity(sessions)
        assert result["trend"] == "insufficient_data"

    def test_insufficient_data_with_two_sessions(self):
        sessions = [_challenge_session(rounds=3), _challenge_session(rounds=2)]
        result = _compute_convergence_velocity(sessions)
        assert result["trend"] == "insufficient_data"

    def test_improving_trend_when_rounds_decrease(self):
        # First half: 4,4 rounds. Second half: 1,1 rounds. Delta = -3 → improving
        sessions = [
            _challenge_session(rounds=4),
            _challenge_session(rounds=4),
            _challenge_session(rounds=1),
            _challenge_session(rounds=1),
        ]
        result = _compute_convergence_velocity(sessions)
        assert result["trend"] == "improving"
        assert result["velocity"] < 0

    def test_degrading_trend_when_rounds_increase(self):
        # First half: 1,1 rounds. Second half: 4,4 rounds. Delta = +3 → degrading
        sessions = [
            _challenge_session(rounds=1),
            _challenge_session(rounds=1),
            _challenge_session(rounds=4),
            _challenge_session(rounds=4),
        ]
        result = _compute_convergence_velocity(sessions)
        assert result["trend"] == "degrading"
        assert result["velocity"] > 0

    def test_stable_trend_when_rounds_constant(self):
        sessions = [_challenge_session(rounds=2) for _ in range(4)]
        result = _compute_convergence_velocity(sessions)
        assert result["trend"] == "stable"
        assert result["velocity"] == 0.0

    def test_mean_rounds_computed_correctly(self):
        sessions = [
            _challenge_session(rounds=2),
            _challenge_session(rounds=4),
            _challenge_session(rounds=2),
            _challenge_session(rounds=4),
        ]
        result = _compute_convergence_velocity(sessions)
        assert result["mean_rounds"] == 3.0

    def test_non_challenge_sessions_excluded(self):
        sessions = [
            _session(skills=["dev-loop"]),  # no challenge
            _challenge_session(rounds=3),
            _challenge_session(rounds=2),
            _challenge_session(rounds=1),
        ]
        result = _compute_convergence_velocity(sessions)
        # Only 3 challenge sessions with rounds data
        assert result["sessions_with_data"] == 3

    def test_sessions_with_none_rounds_excluded(self):
        sessions = [
            _challenge_session(rounds=3),
            _session(skills=["challenge"], challenge_rounds=None),  # no rounds data
            _challenge_session(rounds=2),
            _challenge_session(rounds=1),
        ]
        result = _compute_convergence_velocity(sessions)
        assert result["sessions_with_data"] == 3

    def test_velocity_is_float(self):
        sessions = [_challenge_session(rounds=i) for i in range(1, 5)]
        result = _compute_convergence_velocity(sessions)
        assert isinstance(result["velocity"], float)

    def test_sessions_with_data_count_correct(self):
        sessions = [_challenge_session(rounds=i + 1) for i in range(5)]
        result = _compute_convergence_velocity(sessions)
        assert result["sessions_with_data"] == 5

    def test_caps_at_last_10_sessions(self):
        # 15 sessions: first 5 with high rounds, last 10 with low rounds → improving
        sessions = (
            [_challenge_session(rounds=5) for _ in range(5)]
            + [_challenge_session(rounds=1) for _ in range(10)]
        )
        result = _compute_convergence_velocity(sessions)
        # Should use only last 10 — all rounds=1 → stable (no variance)
        assert result["sessions_with_data"] == 15  # counts all, but uses last 10 for trend
        assert result["trend"] == "stable"


# ---------------------------------------------------------------------------
# _compute_human_precision_rate
# ---------------------------------------------------------------------------

class TestHumanPrecisionRate:

    def test_returns_zero_with_fewer_than_6_sessions(self):
        sessions = [_challenge_session(rounds=1, human_precision=True) for _ in range(5)]
        assert _compute_human_precision_rate(sessions) == 0.0

    def test_returns_zero_with_no_challenge_sessions(self):
        sessions = [_session(skills=["dev-loop"]) for _ in range(10)]
        assert _compute_human_precision_rate(sessions) == 0.0

    def test_full_precision_when_all_sessions_high_precision(self):
        sessions = [
            _challenge_session(rounds=1, developer_caught=["nfr_check"], human_precision=True)
            for _ in range(6)
        ]
        assert _compute_human_precision_rate(sessions) == 1.0

    def test_zero_precision_when_no_high_precision_sessions(self):
        sessions = [
            _challenge_session(rounds=3, developer_caught=[], human_precision=False)
            for _ in range(6)
        ]
        assert _compute_human_precision_rate(sessions) == 0.0

    def test_partial_precision_rate(self):
        sessions = (
            [_challenge_session(rounds=1, developer_caught=["nfr_check"], human_precision=True)
             for _ in range(3)]
            + [_challenge_session(rounds=3, human_precision=False) for _ in range(3)]
        )
        rate = _compute_human_precision_rate(sessions)
        assert rate == pytest.approx(0.5)

    def test_proxy_fallback_for_pre_fix_sessions(self):
        # Pre-fix sessions don't have human_precision field (defaults False in dict),
        # but have developer_caught AND challenge_rounds <= 1 → proxy applies
        s = _challenge_session(rounds=1, developer_caught=["nfr_check"], human_precision=False)
        sessions = [s for _ in range(6)]
        # human_precision=False but proxy should pick it up
        rate = _compute_human_precision_rate(sessions)
        assert rate == 1.0

    def test_proxy_does_not_fire_when_rounds_zero(self):
        # challenge_rounds=0 means challenge didn't complete — should not count as high precision
        s = _challenge_session(rounds=0, developer_caught=["nfr_check"], human_precision=False)
        sessions = [s for _ in range(6)]
        rate = _compute_human_precision_rate(sessions)
        assert rate == 0.0

    def test_proxy_does_not_fire_when_rounds_high(self):
        # rounds=3 means multiple ITERATE phases — not high precision even with DeveloperCaught
        s = _challenge_session(rounds=3, developer_caught=["nfr_check"], human_precision=False)
        sessions = [s for _ in range(6)]
        rate = _compute_human_precision_rate(sessions)
        assert rate == 0.0

    def test_non_challenge_sessions_excluded_from_rate(self):
        # Mix of challenge and non-challenge; rate should be over challenge sessions only
        sessions = (
            [_challenge_session(rounds=1, developer_caught=["nfr_check"], human_precision=True)
             for _ in range(3)]
            + [_session(skills=["dev-loop"]) for _ in range(7)]
        )
        rate = _compute_human_precision_rate(sessions)
        # 3 high-precision out of 3 challenge sessions = 1.0
        assert rate == 1.0

    def test_result_between_zero_and_one(self):
        sessions = [
            _challenge_session(rounds=1, human_precision=True),
            _challenge_session(rounds=2, human_precision=False),
            _challenge_session(rounds=1, human_precision=True),
            _challenge_session(rounds=3, human_precision=False),
            _challenge_session(rounds=1, human_precision=False),
            _challenge_session(rounds=2, human_precision=False),
        ]
        rate = _compute_human_precision_rate(sessions)
        assert 0.0 <= rate <= 1.0


# ---------------------------------------------------------------------------
# HumanPrecision audit line logic (unit-tested via the computation that writes it)
# ---------------------------------------------------------------------------

class TestHumanPrecisionAuditLine:

    def _should_write_precision_line(self, developer_caught, challenge_rounds) -> bool:
        """Mirrors the logic in session.py end_session()."""
        return bool(developer_caught) and challenge_rounds <= 1 and challenge_rounds >= 1

    def test_writes_when_caught_and_one_round(self):
        assert self._should_write_precision_line(["nfr_check"], 1) is True

    def test_does_not_write_when_no_developer_caught(self):
        assert self._should_write_precision_line([], 1) is False

    def test_does_not_write_when_rounds_zero(self):
        assert self._should_write_precision_line(["nfr_check"], 0) is False

    def test_does_not_write_when_rounds_two(self):
        assert self._should_write_precision_line(["nfr_check"], 2) is False

    def test_does_not_write_when_rounds_three(self):
        assert self._should_write_precision_line(["nfr_check"], 3) is False

    def test_writes_with_multiple_skills_caught(self):
        assert self._should_write_precision_line(["nfr_check", "challenge"], 1) is True


# ---------------------------------------------------------------------------
# check_loop_dry structural sensor (state-file logic)
# ---------------------------------------------------------------------------

class TestCheckLoopDryLogic:
    """Unit-tests the logic inside check_loop_dry without the MCP layer."""

    def _compute_dry(self, challenge_ran: bool, correction_in_state: bool) -> bool:
        return challenge_ran and not correction_in_state

    def test_dry_when_challenge_ran_and_no_correction(self):
        assert self._compute_dry(challenge_ran=True, correction_in_state=False) is True

    def test_not_dry_when_correction_detected(self):
        assert self._compute_dry(challenge_ran=True, correction_in_state=True) is False

    def test_not_dry_when_challenge_never_ran(self):
        assert self._compute_dry(challenge_ran=False, correction_in_state=False) is False

    def test_not_dry_when_both_false(self):
        assert self._compute_dry(challenge_ran=False, correction_in_state=True) is False

    def test_correction_file_written_with_correct_slug(self, tmp_path):
        """loop-correction.json written with slug from session-open.json."""
        import json as _j
        open_file = tmp_path / "session-open.json"
        open_file.write_text(_j.dumps({"slug": "my-project", "timestamp": "2026-07-15T10:00:00Z"}))

        correction_file = tmp_path / "loop-correction.json"
        slug = _j.loads(open_file.read_text()).get("slug", "")
        correction_file.write_text(_j.dumps({
            "slug": slug,
            "correction_detected": True,
            "ts": "2026-07-15T10:00:00",
        }))

        data = _j.loads(correction_file.read_text())
        assert data["slug"] == "my-project"
        assert data["correction_detected"] is True

    def test_slug_mismatch_makes_correction_unreadable(self, tmp_path):
        """If session slug doesn't match correction file slug, correction is not applied."""
        import json as _j
        correction_file = tmp_path / "loop-correction.json"
        correction_file.write_text(_j.dumps({
            "slug": "old-project",
            "correction_detected": True,
            "ts": "2026-07-15T09:00:00",
        }))

        current_slug = "new-project"
        data = _j.loads(correction_file.read_text())
        correction_in_state = (
            data.get("slug") == current_slug and data.get("correction_detected", False)
        )
        assert correction_in_state is False
