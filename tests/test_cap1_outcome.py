"""Tests for CAP-1: outcome-anchored session signals.

Covers:
  - _compute_outcome_rates (health.py): math, PENDING/warmup gate, denominator edge cases
  - end_session enum validation (session.py): invalid values are rejected
  - audit line format (session.py): Outcome/OutcomeResult written correctly
  - _record_outcome_followup (session.py): amends OutcomeResult in prior audit entry
"""
from __future__ import annotations
import json


# ── Health: _compute_outcome_rates ───────────────────────────────────────────

def _make_sessions(
    count: int,
    outcome: str = "SHIPPED",
    outcome_result: str = "WORKED",
    real_work: bool = True,
) -> list[dict]:
    """Build fake session dicts. real_work=True adds capability_skills so sessions
    are counted in the real-work denominator for outcome_signal_rate."""
    base = {"outcome": outcome, "outcome_result": outcome_result}
    if real_work:
        base["capability_skills"] = ["dev-loop"]
    return [dict(base) for _ in range(count)]


class TestComputeOutcomeRates:
    def test_returns_none_when_below_warmup(self):
        """outcome_signal_rate and outcome_quality_rate are None until 10 sessions have outcome data."""
        from health import _compute_outcome_rates
        sessions = _make_sessions(9, "SHIPPED", "WORKED")
        result = _compute_outcome_rates(sessions)
        assert result["outcome_signal_rate"] is None
        assert result["outcome_quality_rate"] is None
        assert result["sessions_with_outcome"] == 9

    def test_active_at_ten_sessions(self):
        """Rates become active at exactly 10 sessions with outcome data."""
        from health import _compute_outcome_rates
        sessions = _make_sessions(10, "SHIPPED", "WORKED")
        result = _compute_outcome_rates(sessions)
        assert result["outcome_signal_rate"] is not None
        assert result["outcome_quality_rate"] is not None

    def test_none_outcome_excluded_from_warmup_count(self):
        """Sessions with outcome=NONE don't count toward the warmup threshold."""
        from health import _compute_outcome_rates
        # 8 with NONE + 2 with SHIPPED — total 10 but only 2 carry data
        sessions = (
            [{"outcome": "NONE", "outcome_result": "UNKNOWN"}] * 8
            + _make_sessions(2, "SHIPPED", "WORKED")
        )
        result = _compute_outcome_rates(sessions)
        assert result["sessions_with_outcome"] == 2
        assert result["outcome_signal_rate"] is None  # below warmup

    def test_quality_rate_all_worked(self):
        """When all resolved outcomes are WORKED, quality_rate is 1.0."""
        from health import _compute_outcome_rates
        sessions = _make_sessions(10, "SHIPPED", "WORKED")
        result = _compute_outcome_rates(sessions)
        assert result["outcome_quality_rate"] == 1.0

    def test_quality_rate_half_failed(self):
        """When half of resolved outcomes failed, quality_rate is 0.5."""
        from health import _compute_outcome_rates
        sessions = (
            _make_sessions(5, "SHIPPED", "WORKED")
            + _make_sessions(5, "SHIPPED", "FAILED")
        )
        result = _compute_outcome_rates(sessions)
        assert result["outcome_quality_rate"] == 0.5

    def test_pending_not_counted_in_quality_rate(self):
        """PENDING outcomes are excluded from quality_rate denominator."""
        from health import _compute_outcome_rates
        sessions = (
            _make_sessions(5, "SHIPPED", "WORKED")
            + _make_sessions(5, "SHIPPED", "PENDING")  # not resolved
        )
        result = _compute_outcome_rates(sessions)
        # only 5 resolved (all WORKED) — quality_rate should be 1.0
        assert result["outcome_quality_rate"] == 1.0
        assert result["sessions_resolved"] == 5

    def test_signal_rate_when_all_shipped_have_result(self):
        """signal_rate is 1.0 when all real-work sessions have a non-UNKNOWN outcome."""
        from health import _compute_outcome_rates
        sessions = _make_sessions(10, "SHIPPED", "WORKED")
        result = _compute_outcome_rates(sessions)
        assert result["outcome_signal_rate"] == 1.0

    def test_all_abandoned_yields_no_free_bonus(self):
        """ABANDONED sessions with UNKNOWN result do not grant a free 1.0 signal_rate.
        If all real-work sessions have UNKNOWN outcome_result, signal_rate should be 0.0,
        not 1.0 (the old empty-denominator fallback was wrong)."""
        from health import _compute_outcome_rates
        # 10 sessions with outcome=ABANDONED but result=UNKNOWN (developer never followed up)
        sessions = _make_sessions(10, "ABANDONED", "UNKNOWN")
        result = _compute_outcome_rates(sessions)
        # warmup met: 10 sessions_with_outcome (ABANDONED != NONE)
        assert result["sessions_with_outcome"] == 10
        # signal_rate: 0 of 10 real-work sessions have outcome_result != UNKNOWN
        assert result["outcome_signal_rate"] == 0.0

    def test_pending_does_not_lower_signal_rate(self):
        """PENDING counts as recorded — reporting PENDING must not lower signal_rate
        compared to not reporting anything. UNKNOWN is the only value that misses the signal."""
        from health import _compute_outcome_rates
        # 10 sessions: 5 WORKED (clearly recorded) + 5 PENDING (intent recorded)
        sessions_with_pending = (
            _make_sessions(5, "SHIPPED", "WORKED")
            + _make_sessions(5, "SHIPPED", "PENDING")
        )
        # 10 sessions: 10 WORKED (all fully resolved)
        sessions_all_worked = _make_sessions(10, "SHIPPED", "WORKED")
        result_pending = _compute_outcome_rates(sessions_with_pending)
        result_worked = _compute_outcome_rates(sessions_all_worked)
        # PENDING does not lower signal rate vs all-WORKED
        assert result_pending["outcome_signal_rate"] == result_worked["outcome_signal_rate"]

    def test_r10_label_format_in_findings(self, monkeypatch):
        """_generate_findings includes R10-labeled outcome signal rate with n/d and 'real-work sessions'.
        Patches _compute_outcome_rates directly to avoid full session fixture complexity."""
        import health
        fake_rates = {
            "outcome_signal_rate": 0.8,
            "outcome_quality_rate": 0.9,
            "sessions_with_outcome": 10,
            "sessions_resolved": 8,
            "real_work_sessions": 10,
            "outcome_recorded_count": 8,
        }
        monkeypatch.setattr(health, "_compute_outcome_rates", lambda sessions: fake_rates)
        # Build sessions list with required fields for _generate_findings internals
        sessions = [
            {
                "close_cluster": True,
                "capability_skills": ["dev-loop"],
                "skills": ["dev-loop"],
                "tokens_ratio": None,
                "raw": "",
                "outcome": "SHIPPED",
                "outcome_result": "WORKED",
                "commits": True,
            }
            for _ in range(10)
        ]
        monkeypatch.setattr(health, "_parse_audit_sessions", lambda texts: sessions)
        monkeypatch.setattr(health, "_consecutive_skill_skips", lambda s: 0)
        monkeypatch.setattr(health, "_check_project_type_coverage", lambda: None)
        monkeypatch.setattr(health, "_check_release_readiness", lambda: [])
        monkeypatch.setattr(health, "_check_git_outcomes", lambda s: [])
        monkeypatch.setattr(health, "PROPOSALS_FILE", health.YOUK_ROOT / "state" / "nonexistent.md")
        findings = health._generate_findings(["### Session — dummy\n"], score=7.0)
        r10_findings = [f for f in findings if "R10" in f and "real-work sessions" in f]
        assert r10_findings, f"No R10-labeled outcome finding found in: {findings}"
        label = r10_findings[0]
        assert "%" in label
        assert "/" in label

    def test_signal_rate_pending_counts_as_recorded(self):
        """PENDING counts as recorded in signal_rate (developer signalled intent).
        Only UNKNOWN is excluded from the numerator."""
        from health import _compute_outcome_rates
        sessions = (
            _make_sessions(5, "SHIPPED", "WORKED")
            + _make_sessions(5, "SHIPPED", "PENDING")  # PENDING = recorded, counts
        )
        result = _compute_outcome_rates(sessions)
        # All 10 real-work sessions have outcome recorded (WORKED or PENDING — both non-UNKNOWN)
        assert result["outcome_signal_rate"] == 1.0


# ── Session: enum validation ──────────────────────────────────────────────────

class TestEndSessionEnumValidation:
    def test_invalid_outcome_returns_error(self, youk_root, claude_root, monkeypatch):
        """Invalid outcome value is rejected with a descriptive error — never silently coerced."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        result = sess.end_session(
            summary="test session",
            commits_made=False,
            outcome="PUBLISHED",  # not in enum
        )
        assert result.get("blocked") is True
        assert "PUBLISHED" in result["error"]
        assert "SHIPPED" in result["error"]

    def test_invalid_outcome_result_returns_error(self, youk_root, claude_root, monkeypatch):
        """Invalid outcome_result value is rejected with a descriptive error."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        result = sess.end_session(
            summary="test session",
            commits_made=False,
            outcome="SHIPPED",
            outcome_result="MAYBE",  # not in enum
        )
        assert result.get("blocked") is True
        assert "MAYBE" in result["error"]
        assert "WORKED" in result["error"]

    def test_valid_outcome_passes_validation(self, youk_root, claude_root, monkeypatch):
        """Valid outcome + outcome_result values are accepted."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        result = sess.end_session(
            summary="shipped something",
            commits_made=True,
            outcome="SHIPPED",
            outcome_result="PENDING",
        )
        assert result.get("blocked") is not True
        assert "error" not in result

    def test_case_insensitive_normalization(self, youk_root, claude_root, monkeypatch):
        """Lowercase enum values are normalized to uppercase before validation."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        result = sess.end_session(
            summary="shipped something",
            commits_made=True,
            outcome="shipped",
            outcome_result="worked",
        )
        assert result.get("blocked") is not True


# ── Session: audit line format ────────────────────────────────────────────────

class TestOutcomeAuditLines:
    def _audit_text(self, youk_root, claude_root, monkeypatch, **kwargs) -> str:
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        (claude_root / "audit").mkdir(parents=True, exist_ok=True)
        month_file = claude_root / "audit" / "2026-07.md"
        sess.end_session(summary="test", commits_made=False, **kwargs)
        return month_file.read_text() if month_file.exists() else ""

    def test_outcome_line_written_when_shipped(self, youk_root, claude_root, monkeypatch):
        """Outcome: SHIPPED is written to audit when outcome=SHIPPED."""
        text = self._audit_text(youk_root, claude_root, monkeypatch, outcome="SHIPPED", outcome_result="PENDING")
        assert "Outcome: SHIPPED" in text
        assert "OutcomeResult: PENDING" in text

    def test_outcome_omitted_when_none(self, youk_root, claude_root, monkeypatch):
        """Outcome: NONE is not written (keeps audit entries compact for no-code sessions)."""
        text = self._audit_text(youk_root, claude_root, monkeypatch, outcome="NONE")
        assert "Outcome:" not in text
        assert "OutcomeResult:" not in text

    def test_outcome_result_written_for_staged(self, youk_root, claude_root, monkeypatch):
        """OutcomeResult is written for STAGED outcome."""
        text = self._audit_text(youk_root, claude_root, monkeypatch, outcome="STAGED", outcome_result="WORKED")
        assert "Outcome: STAGED" in text
        assert "OutcomeResult: WORKED" in text


# ── Session: _record_outcome_followup ────────────────────────────────────────

class TestRecordOutcomeFollowup:
    def _write_audit(self, claude_root, slug: str, outcome: str, outcome_result: str) -> None:
        (claude_root / "audit").mkdir(parents=True, exist_ok=True)
        audit_file = claude_root / "audit" / "2026-07.md"
        audit_file.write_text(
            f"### Session — 2026-07-18 10:00 UTC\n"
            f"Project: {slug}\n"
            f"Skills: code-review\n"
            f"CloseCluster: yes\n"
            f"Commits: yes\n"
            f"Outcome: {outcome}\n"
            f"OutcomeResult: {outcome_result}\n"
        )

    def test_amends_outcome_result_in_audit(self, claude_root, monkeypatch):
        """record_outcome_followup replaces OutcomeResult in the matching audit entry."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        self._write_audit(claude_root, "myproject", "SHIPPED", "PENDING")
        result = sess._record_outcome_followup("myproject", "WORKED")
        assert result["amended"] is True
        assert result["prior_result"] == "PENDING"
        assert result["new_result"] == "WORKED"
        text = (claude_root / "audit" / "2026-07.md").read_text()
        assert "OutcomeResult: WORKED" in text
        assert "OutcomeResult: PENDING" not in text

    def test_no_match_returns_not_amended(self, claude_root, monkeypatch):
        """record_outcome_followup returns amended=False when slug not found."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        self._write_audit(claude_root, "otherproject", "SHIPPED", "PENDING")
        result = sess._record_outcome_followup("notexist", "WORKED")
        assert result["amended"] is False

    def test_amends_entry_when_no_existing_outcome_result(self, claude_root, monkeypatch):
        """record_outcome_followup appends OutcomeResult when the entry has none."""
        import session as sess
        monkeypatch.setattr(sess, "CLAUDE_ROOT", claude_root)
        (claude_root / "audit").mkdir(parents=True, exist_ok=True)
        audit_file = claude_root / "audit" / "2026-07.md"
        audit_file.write_text(
            "### Session — 2026-07-18 10:00 UTC\n"
            "Project: myproject\n"
            "Skills: code-review\n"
            "Outcome: SHIPPED\n"
            # No OutcomeResult line
        )
        result = sess._record_outcome_followup("myproject", "WORKED")
        assert result["amended"] is True
        text = audit_file.read_text()
        assert "OutcomeResult: WORKED" in text
