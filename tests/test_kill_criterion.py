"""Tests for the kill_criterion enforcement added for CIR-150 item 4 / CIR-151.

OUTCOMES.md's stop condition ("If skill_invocation_rate stays below 50% for 4
consecutive weeks... stop tuning nudges, redesign the gate") was prose only —
nothing read it or acted on it. This proves two things with real code:

1. _skill_invocation_rate_below_floor_for_weeks correctly identifies a real
   4-consecutive-week-below-threshold streak, and correctly does NOT fire on
   insufficient history, a gap in the week sequence, or a recovered week.
2. _compute_improvement_velocity writes/clears state/kill-criterion-triggered.json
   as a real, checkable consequence — the same flag file
   plugin/scripts/youk_hook_utils.check_m_plus_write_gate reads to decide
   whether to deny an Edit/Write.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _weekly_entries(rates: list[float], anchor: datetime) -> list[dict]:
    """One entry per week, oldest first, ending at `anchor`'s week."""
    n = len(rates)
    return [
        {"timestamp": _ts(anchor - timedelta(weeks=(n - 1 - i))), "skill_invocation_rate": r}
        for i, r in enumerate(rates)
    ]


class TestSkillInvocationRateBelowFloorForWeeks:
    def test_four_consecutive_weeks_below_threshold_triggers(self):
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = _weekly_entries([0.43, 0.30, 0.31, 0.32], now)
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is True

    def test_fewer_than_four_weeks_of_history_never_triggers(self):
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = _weekly_entries([0.30, 0.31, 0.32], now)
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is False

    def test_one_week_at_or_above_threshold_breaks_the_streak(self):
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = _weekly_entries([0.30, 0.55, 0.31, 0.32], now)
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is False

    def test_gap_in_week_sequence_breaks_the_streak(self):
        """A missing health-check week must not be silently skipped over —
        that would understate how long the metric went unexamined."""
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = [
            {"timestamp": _ts(now - timedelta(weeks=5)), "skill_invocation_rate": 0.30},
            # week -4 missing
            {"timestamp": _ts(now - timedelta(weeks=3)), "skill_invocation_rate": 0.30},
            {"timestamp": _ts(now - timedelta(weeks=2)), "skill_invocation_rate": 0.31},
            {"timestamp": _ts(now - timedelta(weeks=1)), "skill_invocation_rate": 0.32},
        ]
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is False

    def test_only_latest_entry_per_week_counts(self):
        """Two health-check cycles land in the same ISO week — a late recovery
        that week must win over an earlier bad reading."""
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = _weekly_entries([0.30, 0.30, 0.31], now)
        # Add a same-week-as-latest recovery entry with a later timestamp.
        entries.append({"timestamp": _ts(now + timedelta(hours=1)), "skill_invocation_rate": 0.90})
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is False

    def test_entries_missing_rate_or_timestamp_are_ignored_not_crashed_on(self):
        from health import _skill_invocation_rate_below_floor_for_weeks
        now = datetime.now(UTC)
        entries = _weekly_entries([0.30, 0.31, 0.32, 0.33], now)
        entries.append({"timestamp": None, "skill_invocation_rate": 0.9})
        entries.append({"skill_invocation_rate": 0.9})
        entries.append({"timestamp": _ts(now)})
        assert _skill_invocation_rate_below_floor_for_weeks(entries) is True


class TestKillCriterionFlagIsRealConsequence:
    """Integration-level: _compute_improvement_velocity must write/clear the
    actual flag file, not just a findings string."""

    def _audit_with(self, sessions: list[dict]) -> str:
        blocks = []
        for i, s in enumerate(sessions):
            skills = s.get("skills", "none")
            close = "yes" if s.get("close_cluster") else "no"
            blocks.append(
                f"### Session — 2026-07-0{i + 1} 10:00 UTC\n"
                f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
            )
        return "\n".join(blocks)

    def test_flag_written_when_fourth_consecutive_low_week_lands(self, youk_root, host_root):
        from health import _compute_improvement_velocity, _score_org

        now = datetime.now(UTC)
        metrics_file = youk_root / "state" / "improvement-metrics.json"
        metrics_file.write_text(json.dumps({
            "entries": [
                {"timestamp": _ts(now - timedelta(weeks=3)), "skill_invocation_rate": 0.30},
                {"timestamp": _ts(now - timedelta(weeks=2)), "skill_invocation_rate": 0.31},
                {"timestamp": _ts(now - timedelta(weeks=1)), "skill_invocation_rate": 0.32},
            ],
            "projects": {},
        }))

        # This call's own session mix scores skill_invocation_rate 0.0 — the 4th
        # consecutive low week.
        audit = self._audit_with([{"skills": "none", "close_cluster": False}])
        score = _score_org([audit])
        result = _compute_improvement_velocity([audit], score)

        assert result["kill_criterion_triggered"] is True
        flag_file = youk_root / "state" / "kill-criterion-triggered.json"
        assert flag_file.exists()
        flag = json.loads(flag_file.read_text())
        assert flag["triggered"] is True
        assert flag["metric"] == "skill_invocation_rate"

    def test_flag_cleared_when_rate_recovers(self, youk_root, host_root):
        from health import _compute_improvement_velocity, _score_org

        flag_file = youk_root / "state" / "kill-criterion-triggered.json"
        flag_file.write_text(json.dumps({"triggered": True}))
        (youk_root / "state" / "improvement-metrics.json").write_text(json.dumps({
            "entries": [], "projects": {},
        }))

        audit = self._audit_with([{"skills": "code-review", "close_cluster": True}])
        score = _score_org([audit])
        result = _compute_improvement_velocity([audit], score)

        assert result["kill_criterion_triggered"] is False
        assert not flag_file.exists()

    def test_not_triggered_with_no_history_at_all(self, youk_root, host_root):
        from health import _compute_improvement_velocity, _score_org

        audit = self._audit_with([{"skills": "none", "close_cluster": False}])
        score = _score_org([audit])
        result = _compute_improvement_velocity([audit], score)

        assert result["kill_criterion_triggered"] is False
        assert not (youk_root / "state" / "kill-criterion-triggered.json").exists()
