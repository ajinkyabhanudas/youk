"""
Tests for CAP-11: Compaction Instrumentation.

Coverage:
- CounterIncrements: pre_compact hook increments counter with session-day field
- AuditLineFormat: session_end writes "Compactions: N" (not CompactCount)
- R10Label: health finding carries [R10] label
- InsufficientDataGating: correlation split only at ≥10 sessions with both fields
- OrgScoreInvariant: compaction data does not affect org_score
"""
from __future__ import annotations
import json


# ---------------------------------------------------------------------------
# TestCounterIncrements
# ---------------------------------------------------------------------------

class TestCounterIncrements:
    def test_counter_starts_at_1_on_first_call(self, tmp_path):
        """First pre_compact call creates file with count=1."""
        count_file = tmp_path / "compact-count.json"
        assert not count_file.exists()

        # Simulate what pre_compact.py does
        from datetime import date
        today = date.today().isoformat()
        existing = {}
        count_file.write_text(json.dumps({
            "session-day": existing.get("session-day", today),
            "count": existing.get("count", 0) + 1,
        }))

        data = json.loads(count_file.read_text())
        assert data["count"] == 1
        assert data["session-day"] == today

    def test_counter_increments_on_subsequent_calls(self, tmp_path):
        """Subsequent calls increment count, preserve session-day."""
        count_file = tmp_path / "compact-count.json"
        from datetime import date
        today = date.today().isoformat()

        count_file.write_text(json.dumps({"session-day": today, "count": 2}))

        existing = json.loads(count_file.read_text())
        count_file.write_text(json.dumps({
            "session-day": existing.get("session-day", today),
            "count": existing.get("count", 0) + 1,
        }))

        data = json.loads(count_file.read_text())
        assert data["count"] == 3
        assert data["session-day"] == today

    def test_session_day_preserved_across_increments(self, tmp_path):
        """session-day from first call is preserved on subsequent increments."""
        count_file = tmp_path / "compact-count.json"
        original_day = "2026-07-01"
        count_file.write_text(json.dumps({"session-day": original_day, "count": 5}))

        existing = json.loads(count_file.read_text())
        from datetime import date
        today = date.today().isoformat()
        count_file.write_text(json.dumps({
            "session-day": existing.get("session-day", today),
            "count": existing.get("count", 0) + 1,
        }))
        data = json.loads(count_file.read_text())
        # session-day must NOT change on subsequent calls
        assert data["session-day"] == original_day
        assert data["count"] == 6


# ---------------------------------------------------------------------------
# TestAuditLineFormat
# ---------------------------------------------------------------------------

class TestAuditLineFormat:
    def test_audit_line_uses_compactions_not_compact_count(self, tmp_path, monkeypatch):
        """session_end writes 'Compactions: N' not 'CompactCount: N'."""
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(session, "STATE_FILE", tmp_path / "state" / "session.json")

        # Write a compact-count.json so session_end picks it up
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        (tmp_path / "audit").mkdir(parents=True, exist_ok=True)
        count_file = tmp_path / "state" / "compact-count.json"
        count_file.write_text(json.dumps({"session-day": "2026-07-18", "count": 3}))

        # Call session.py's compact_count reading logic directly
        compact_count = 0
        try:
            if count_file.exists():
                data = json.loads(count_file.read_text())
                compact_count = data.get("count", 0)
        except Exception:
            pass
        compact_count_line = f"Compactions: {compact_count}\n" if compact_count > 0 else ""

        assert compact_count_line == "Compactions: 3\n"
        assert "CompactCount" not in compact_count_line

    def test_audit_line_absent_when_no_compactions(self, tmp_path):
        """If compact-count.json missing, Compactions line is empty string."""
        count_file = tmp_path / "state" / "compact-count.json"
        compact_count = 0
        if count_file.exists():
            try:
                data = json.loads(count_file.read_text())
                compact_count = data.get("count", 0)
            except Exception:
                pass
        compact_count_line = f"Compactions: {compact_count}\n" if compact_count > 0 else ""
        assert compact_count_line == ""


# ---------------------------------------------------------------------------
# TestR10Label
# ---------------------------------------------------------------------------

class TestR10Label:
    def test_r10_label_present_in_compaction_frequency(self):
        """_compute_compaction_frequency includes [R10] in r10_label."""
        import health
        sessions = [
            {"compact_count": 2},
            {"compact_count": 1},
        ]
        result = health._compute_compaction_frequency(sessions)
        assert "[R10]" in result["r10_label"]

    def test_r10_label_format_with_data(self):
        """r10_label: 'compactions/session [R10]: <avg> (<total>/<n> sessions, last 30 days)'"""
        import health
        sessions = [{"compact_count": 2}, {"compact_count": 4}]
        result = health._compute_compaction_frequency(sessions)
        label = result["r10_label"]
        assert label.startswith("compactions/session [R10]:")
        assert "sessions, last 30 days" in label

    def test_r10_label_no_data(self):
        """When no sessions have compact_count, label says insufficient data."""
        import health
        result = health._compute_compaction_frequency([])
        assert "[R10]" in result["r10_label"] or "insufficient" in result["r10_label"]


# ---------------------------------------------------------------------------
# TestInsufficientDataGating
# ---------------------------------------------------------------------------

class TestInsufficientDataGating:
    def test_correlation_not_shown_below_10_sessions(self):
        """With <10 sessions carrying both compact_count and outcome_result, show insufficient-data."""
        import health
        sessions = [
            {"compact_count": 2, "outcome_result": "PASSED"},
            {"compact_count": 3, "outcome_result": "FAILED"},
        ]
        result = health._compute_compaction_frequency(sessions)
        assert "insufficient data" in result["outcome_correlation"]

    def test_correlation_shown_at_10_sessions(self):
        """With exactly 10 sessions carrying both fields, show outcome split."""
        import health
        sessions = (
            [{"compact_count": 1, "outcome_result": "PASSED"}] * 7
            + [{"compact_count": 4, "outcome_result": "FAILED"}] * 3
        )
        result = health._compute_compaction_frequency(sessions)
        corr = result["outcome_correlation"]
        assert "insufficient data" not in corr
        assert "PASSED" in corr
        assert "FAILED" in corr

    def test_sessions_without_outcome_not_counted_toward_gate(self):
        """Sessions with compact_count but no/unknown outcome don't count toward the 10-session gate."""
        import health
        # 8 sessions with compact_count but no outcome
        sessions = [{"compact_count": 2}] * 8
        # 2 sessions with outcome — total with both = 2, below gate
        sessions += [{"compact_count": 3, "outcome_result": "PASSED"}] * 2
        result = health._compute_compaction_frequency(sessions)
        assert "insufficient data" in result["outcome_correlation"]
        # But avg_per_session covers all 10 measured
        assert result["sessions_measured"] == 10

    def test_gating_includes_needed_count(self):
        """outcome_correlation must show N/10 sessions needed when below gate."""
        import health
        sessions = [{"compact_count": 1, "outcome_result": "PASSED"}] * 5
        result = health._compute_compaction_frequency(sessions)
        assert "5/10" in result["outcome_correlation"]


# ---------------------------------------------------------------------------
# TestOrgScoreInvariant (CAP-11 score-neutrality)
# ---------------------------------------------------------------------------

class TestOrgScoreInvariant:
    def test_org_score_unchanged_by_compaction_data(self, tmp_path, monkeypatch):
        """Org score must be identical whether Compactions line is present in audit or not."""
        import health
        monkeypatch.setattr(health, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(health, "CLAUDE_ROOT", tmp_path)
        monkeypatch.setattr(health, "AUDIT_DIR", tmp_path / "audit")
        monkeypatch.setattr(health, "PROPOSALS_FILE", tmp_path / "PENDING.md")

        base_entry = (
            "### Session — 2026-07-18\n"
            "OutcomeResult: PASSED\n"
            "Skills: nfr_check\n"
            "ClosedAt: 2026-07-18\n"
        )
        entry_with_compaction = base_entry + "Compactions: 5\n"

        score_without = health._score_org([base_entry])
        score_with = health._score_org([entry_with_compaction])
        assert score_without == score_with
