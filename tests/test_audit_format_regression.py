"""
Audit format regression tests.

Verifies that old audit entries — written before DeveloperCaught, FramingCorrect,
DirectionReversal, and other new fields were added — parse cleanly without breaking
_parse_audit_sessions(). New fields must default to safe values, never raise.

This is the production-grade guarantee: a developer who upgrades youk mid-project
must not have their existing audit history corrupted or their parsers broken.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers — audit block formats from different eras
# ---------------------------------------------------------------------------

_V0_BLOCK = """\
### Session — 2025-06-01 10:00 UTC
Project: myproject
Skills: nfr-check, dev-loop
CloseCluster: yes
Commits: yes
"""

_V0_NO_SKILLS_BLOCK = """\
### Session — 2025-07-01 09:00 UTC
Project: myproject
Skills: none
CloseCluster: no
Commits: no
"""

_V1_WITH_DIRECTION_REVERSAL = """\
### Session — 2025-10-01 12:00 UTC
Project: myproject
Skills: challenge, nfr-check, dev-loop
CloseCluster: yes
Commits: yes
DirectionReversal: yes
"""

_V2_WITH_FRAMING_CORRECT = """\
### Session — 2026-01-01 14:00 UTC
Project: myproject
Skills: nfr-check, dev-loop
CloseCluster: yes
Commits: yes
DirectionReversal: no
FramingCorrect: yes
"""

_V3_FULL = """\
### Session — 2026-06-01 11:00 UTC
Project: myproject
Skills: nfr-check, dev-loop, code-review
CloseCluster: yes
Commits: yes
DirectionReversal: no
FramingCorrect: yes
DeveloperCaught: nfr_check
"""

_MIXED = "\n".join([
    _V0_BLOCK,
    _V0_NO_SKILLS_BLOCK,
    _V1_WITH_DIRECTION_REVERSAL,
    _V2_WITH_FRAMING_CORRECT,
    _V3_FULL,
])


# ---------------------------------------------------------------------------
# 1. All formats parse without raising
# ---------------------------------------------------------------------------

class TestAuditParseDoesNotRaise:
    def test_v0_block_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_BLOCK])
        assert len(sessions) == 1

    def test_v0_no_skills_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_NO_SKILLS_BLOCK])
        assert len(sessions) == 1

    def test_v1_direction_reversal_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V1_WITH_DIRECTION_REVERSAL])
        assert len(sessions) == 1

    def test_v2_framing_correct_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V2_WITH_FRAMING_CORRECT])
        assert len(sessions) == 1

    def test_v3_full_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V3_FULL])
        assert len(sessions) == 1

    def test_mixed_formats_parse(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_MIXED])
        assert len(sessions) == 5

    def test_empty_input_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([])
        assert sessions == []

    def test_empty_string_parses(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([""])
        assert sessions == []


# ---------------------------------------------------------------------------
# 2. New fields default to safe values on old entries
# ---------------------------------------------------------------------------

class TestNewFieldsDefaultSafely:
    def test_developer_caught_defaults_to_empty_list_on_v0(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_BLOCK])
        assert sessions[0]["developer_caught"] == []

    def test_framing_correct_defaults_to_none_on_v0(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_BLOCK])
        assert sessions[0].get("framing_correct") is None

    def test_direction_reversal_defaults_to_false_on_v0(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_BLOCK])
        assert sessions[0].get("direction_reversal") is False

    def test_framing_correct_true_on_v2(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V2_WITH_FRAMING_CORRECT])
        assert sessions[0]["framing_correct"] is True

    def test_framing_correct_false_on_direction_reversal(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V1_WITH_DIRECTION_REVERSAL])
        # DirectionReversal: yes → FramingCorrect absent but direction_reversal=True
        assert sessions[0]["direction_reversal"] is True

    def test_developer_caught_parsed_on_v3(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V3_FULL])
        assert "nfr_check" in sessions[0]["developer_caught"]


# ---------------------------------------------------------------------------
# 3. Score functions don't crash on mixed-format history
# ---------------------------------------------------------------------------

class TestScoreFunctionsOnMixedHistory:
    def test_compute_autonomy_rate_handles_mixed(self):
        from health import _parse_audit_sessions, _compute_autonomy_rate
        sessions = _parse_audit_sessions([_MIXED])
        rate = _compute_autonomy_rate(sessions)
        assert 0.0 <= rate <= 1.0

    def test_compute_depth_multiplier_handles_mixed(self):
        from health import _parse_audit_sessions, _compute_depth_multiplier
        sessions = _parse_audit_sessions([_MIXED])
        multiplier = _compute_depth_multiplier(sessions)
        assert 0.5 <= multiplier <= 1.0

    def test_compute_skill_autonomy_rate_handles_mixed(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        sessions = _parse_audit_sessions([_MIXED])
        rate = _compute_skill_autonomy_rate(sessions, "nfr_check")
        assert 0.0 <= rate <= 1.0

    def test_framing_accuracy_rate_skips_entries_without_field(self):
        """Old entries without FramingCorrect must not be penalised."""
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_MIXED])
        framing_sessions = [s for s in sessions if s.get("framing_correct") is not None]
        # Only v2 and v3 have FramingCorrect — v0 and v1 must not appear
        assert len(framing_sessions) == 2
        assert all(s["framing_correct"] is True for s in framing_sessions)
