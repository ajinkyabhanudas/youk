"""Tests for Phase 4v1 of the reaction-classifier plan
(~/.claude/plans/zany-squishing-crayon.md): replay-based youk-vs-no-youk
self-measurement.

Three pieces: a real scored rework_rate metric (previously only an inline ad-hoc
list inside org_score's finding text), a Duration field parsed from the audit log
(previously no duration signal existed anywhere), and a partition-and-compare
function using both. All three are pure functions over session dicts — no live
gate is ever bypassed, this only reads history that already happened.
"""
from __future__ import annotations

import json
import time

from health import compute_rework_rate, compare_youk_vs_no_youk, _parse_audit_sessions


def _session(**overrides) -> dict:
    base = {
        "skills": [],
        "capability_skills": [],
        "developer_caught": [],
        "loop_correction": False,
        "direction_reversal": False,
        "findings_total": 0,
        "duration_min": None,
    }
    base.update(overrides)
    return base


class TestComputeReworkRate:
    def test_below_threshold_returns_none_rate(self):
        sessions = [_session() for _ in range(3)]
        result = compute_rework_rate(sessions, lookback=20, threshold=5)
        assert result["rate"] is None
        assert result["total_sessions"] == 3

    def test_no_rework_sessions_is_zero(self):
        sessions = [_session() for _ in range(6)]
        result = compute_rework_rate(sessions, lookback=20, threshold=5)
        assert result["rate"] == 0.0
        assert result["rework_sessions"] == 0

    def test_counts_loop_correction_and_direction_reversal(self):
        sessions = (
            [_session(loop_correction=True) for _ in range(2)]
            + [_session(direction_reversal=True) for _ in range(1)]
            + [_session() for _ in range(3)]
        )
        result = compute_rework_rate(sessions, lookback=20, threshold=5)
        assert result["rework_sessions"] == 3
        assert result["total_sessions"] == 6
        assert result["rate"] == 0.5

    def test_lookback_windows_to_most_recent(self):
        old = [_session(loop_correction=True) for _ in range(10)]
        recent_clean = [_session() for _ in range(5)]
        sessions = old + recent_clean
        result = compute_rework_rate(sessions, lookback=5, threshold=5)
        assert result["rework_sessions"] == 0
        assert result["total_sessions"] == 5


class TestCompareYoukVsNoYouk:
    def test_inconclusive_when_a_cohort_is_too_small(self):
        sessions = [_session(skills=["challenge"]) for _ in range(2)] + [_session() for _ in range(5)]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=3)
        assert result["verdict"] == "inconclusive"
        assert result["ran_cohort"]["n"] == 2

    def test_compared_when_both_cohorts_meet_minimum(self):
        sessions = [_session(skills=["challenge"]) for _ in range(4)] + [_session() for _ in range(4)]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=3)
        assert result["verdict"] == "compared"
        assert result["ran_cohort"]["n"] == 4
        assert result["skipped_cohort"]["n"] == 4

    def test_partitions_by_skills_field(self):
        sessions = [
            _session(skills=["challenge", "nfr-check"]),
            _session(skills=["dev-loop"]),
        ]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=1)
        assert result["ran_cohort"]["n"] == 1
        assert result["skipped_cohort"]["n"] == 1

    def test_developer_caught_counts_as_exercised(self):
        """capability_skills already folds in DeveloperCaught (pre-empted skills) —
        partitioning must credit that, not just skills that were formally routed."""
        sessions = [
            _session(capability_skills=["challenge"]),
            _session(skills=[], capability_skills=[]),
        ]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=1)
        assert result["ran_cohort"]["n"] == 1

    def test_hyphen_and_underscore_names_are_equivalent(self):
        sessions = [_session(skills=["nfr_check"]), _session(skills=["nfr-check"])]
        result = compare_youk_vs_no_youk(sessions, "nfr-check", min_cohort=1)
        assert result["ran_cohort"]["n"] == 2

    def test_avg_findings_computed_per_cohort(self):
        sessions = [
            _session(skills=["challenge"], findings_total=2),
            _session(skills=["challenge"], findings_total=4),
            _session(findings_total=0),
        ]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=1)
        assert result["ran_cohort"]["avg_findings"] == 3.0
        assert result["skipped_cohort"]["avg_findings"] == 0.0

    def test_avg_duration_ignores_sessions_with_no_duration_data(self):
        sessions = [
            _session(skills=["challenge"], duration_min=10.0),
            _session(skills=["challenge"], duration_min=None),
            _session(skills=["challenge"], duration_min=20.0),
        ]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=1)
        assert result["ran_cohort"]["avg_duration_min"] == 15.0

    def test_avg_duration_none_when_no_cohort_session_has_data(self):
        sessions = [_session(skills=["challenge"], duration_min=None)]
        result = compare_youk_vs_no_youk(sessions, "challenge", min_cohort=1)
        assert result["ran_cohort"]["avg_duration_min"] is None

    def test_empty_sessions_list_is_inconclusive_not_a_crash(self):
        result = compare_youk_vs_no_youk([], "challenge")
        assert result["verdict"] == "inconclusive"
        assert result["ran_cohort"]["n"] == 0
        assert result["skipped_cohort"]["n"] == 0


class TestParseAuditSessionsDuration:
    def _block(self, duration_line: str = "") -> str:
        return (
            "### Session — 2026-01-01 10:00 UTC\n"
            "Project: youk\nSkills: nfr-check\n"
            "CloseCluster: yes\nCommits: yes\n"
            f"{duration_line}"
        )

    def test_duration_line_is_parsed(self):
        sessions = _parse_audit_sessions([self._block("Duration: 12.5 min\n")])
        assert sessions[0]["duration_min"] == 12.5

    def test_integer_duration_is_parsed(self):
        sessions = _parse_audit_sessions([self._block("Duration: 45 min\n")])
        assert sessions[0]["duration_min"] == 45.0

    def test_missing_duration_is_none(self):
        sessions = _parse_audit_sessions([self._block()])
        assert sessions[0]["duration_min"] is None


class TestEndSessionWritesDuration:
    """End-to-end: the write side actually lands a Duration: line, not just the
    read side tolerating one. Skips start_session (heavy git-freshness checks
    that pull in the real project state) and instead writes the exact open.json
    shape start_session leaves behind, which is all end_session's duration code
    reads from."""

    def test_duration_line_appears_in_the_audit_entry(self, youk_root, claude_root, monkeypatch):
        import session
        import state_paths as sp

        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

        slug = "test-project"
        slug_dir = youk_root / "state" / "sessions" / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.time() - 90  # 1.5 minutes ago
        (slug_dir / "open.json").write_text(json.dumps({
            "timestamp": "2026-01-01T10:00:00Z",
            "slug": slug,
            "written_at": started_at,
            "session_counter": 1,
            "plan_items": [],
        }))

        session.end_session("test summary", commits_made=False)

        month = time.strftime("%Y-%m", time.gmtime())
        audit_file = claude_root / "audit" / f"{month}.md"
        assert audit_file.exists()
        content = audit_file.read_text()
        assert "Duration:" in content
        assert "min" in content

    def test_no_open_json_omits_duration_without_raising(self, youk_root, claude_root, monkeypatch):
        import session

        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)
        session.end_session("test summary", commits_made=False)  # must not raise

        month = time.strftime("%Y-%m", time.gmtime())
        audit_file = claude_root / "audit" / f"{month}.md"
        assert audit_file.exists()
        assert "Duration:" not in audit_file.read_text()
