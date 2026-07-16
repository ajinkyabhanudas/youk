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


# ---------------------------------------------------------------------------
# 4. Capability signal enrichment — DeveloperCaught and TaskCheckpoints
# ---------------------------------------------------------------------------

_V4_DEVELOPER_CAUGHT_ONLY = """\
### Session — 2026-07-01 10:00 UTC
Project: myproject
Skills: none
CloseCluster: yes
Commits: yes
DeveloperCaught: nfr_check
"""

_V4_DEVELOPER_CAUGHT_NON_CAPABILITY = """\
### Session — 2026-07-02 10:00 UTC
Project: myproject
Skills: none
CloseCluster: yes
Commits: yes
DeveloperCaught: humanize
"""

_V4_TASK_CHECKPOINT_M = """\
### Session — 2026-07-03 10:00 UTC
Project: myproject
Skills: code-review, learn
CloseCluster: yes
Commits: yes
TaskCheckpoints: 1 — implement growth loop (M)
"""

_V4_TASK_CHECKPOINT_XL = """\
### Session — 2026-07-04 10:00 UTC
Project: myproject
Skills: code-review
CloseCluster: yes
Commits: yes
TaskCheckpoints: 2 — migrate database (XL); add auth layer (L)
"""

_V4_TASK_CHECKPOINT_S_ONLY = """\
### Session — 2026-07-05 10:00 UTC
Project: myproject
Skills: none
CloseCluster: no
Commits: yes
TaskCheckpoints: 1 — fix typo (S)
"""

_V4_DEVLOOP_ALREADY_IN_SKILLS = """\
### Session — 2026-07-06 10:00 UTC
Project: myproject
Skills: dev-loop, code-review
CloseCluster: yes
Commits: yes
TaskCheckpoints: 1 — implement feature (M)
"""

_V4_CAUGHT_ALREADY_IN_SKILLS = """\
### Session — 2026-07-07 10:00 UTC
Project: myproject
Skills: nfr-check, dev-loop
CloseCluster: yes
Commits: yes
DeveloperCaught: nfr_check
"""


class TestCapabilitySignalEnrichment:
    """DeveloperCaught and TaskCheckpoints M+ must enrich capability_skills."""

    def test_developer_caught_capability_skill_added(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_DEVELOPER_CAUGHT_ONLY])
        assert "nfr_check" in sessions[0]["capability_skills"]

    def test_developer_caught_non_capability_skill_not_added(self):
        """humanize is not in _CAPABILITY_SKILLS — must not be added."""
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_DEVELOPER_CAUGHT_NON_CAPABILITY])
        assert sessions[0]["capability_skills"] == []

    def test_task_checkpoint_m_adds_dev_loop(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_TASK_CHECKPOINT_M])
        assert "dev-loop" in sessions[0]["capability_skills"]

    def test_task_checkpoint_xl_adds_dev_loop(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_TASK_CHECKPOINT_XL])
        assert "dev-loop" in sessions[0]["capability_skills"]

    def test_task_checkpoint_s_does_not_add_dev_loop(self):
        """S-size checkpoints are context compactions, not M+ routing evidence."""
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_TASK_CHECKPOINT_S_ONLY])
        assert "dev-loop" not in sessions[0]["capability_skills"]
        assert sessions[0]["capability_skills"] == []

    def test_dev_loop_not_duplicated_when_already_in_skills(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_DEVLOOP_ALREADY_IN_SKILLS])
        assert sessions[0]["capability_skills"].count("dev-loop") == 1

    def test_developer_caught_not_duplicated_when_already_in_skills(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_CAUGHT_ALREADY_IN_SKILLS])
        nfr_variants = [
            s for s in sessions[0]["capability_skills"]
            if "nfr" in s.lower()
        ]
        assert len(nfr_variants) == 1

    def test_old_entry_without_developer_caught_unaffected(self):
        """V0 blocks have no DeveloperCaught — capability_skills from Skills: only."""
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V0_BLOCK])
        assert set(sessions[0]["capability_skills"]) == {"nfr-check", "dev-loop"}

    def test_session_with_only_developer_caught_counts_as_hit_in_score(self):
        """A developer-caught session must contribute to capability_count in _score_org."""
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_DEVELOPER_CAUGHT_ONLY])
        assert sessions[0]["capability_skills"]  # non-empty = counts as hit

    def test_session_with_only_task_checkpoint_m_counts_as_hit_in_score(self):
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([_V4_TASK_CHECKPOINT_S_ONLY])
        # S-only = no hit
        assert not sessions[0]["capability_skills"]
        # Now M
        sessions_m = _parse_audit_sessions([_V4_TASK_CHECKPOINT_M])
        assert sessions_m[0]["capability_skills"]


class TestSkillInvocationRateEnrichment:
    """_compute_skill_invocation_rate must also credit DeveloperCaught and M+ checkpoints."""

    def _make_audit_dir(self, tmp_path, content: str) -> Path:
        f = tmp_path / "2026-07.md"
        f.write_text(content)
        return tmp_path

    def test_developer_caught_counts_as_hit(self, tmp_path):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
        from session import _compute_skill_invocation_rate
        audit_dir = self._make_audit_dir(tmp_path, _V4_DEVELOPER_CAUGHT_ONLY)
        rate, skips = _compute_skill_invocation_rate(audit_dir)
        assert rate == 100
        assert skips == 0

    def test_task_checkpoint_m_counts_as_hit(self, tmp_path):
        from session import _compute_skill_invocation_rate
        audit_dir = self._make_audit_dir(tmp_path, _V4_TASK_CHECKPOINT_M)
        rate, skips = _compute_skill_invocation_rate(audit_dir)
        assert rate == 100
        assert skips == 0

    def test_task_checkpoint_s_does_not_count_as_hit(self, tmp_path):
        from session import _compute_skill_invocation_rate
        audit_dir = self._make_audit_dir(tmp_path, _V4_TASK_CHECKPOINT_S_ONLY)
        rate, skips = _compute_skill_invocation_rate(audit_dir)
        assert rate == 0
        assert skips == 1

    def test_consecutive_skips_not_broken_by_enrichment(self, tmp_path):
        """Two skill-less sessions followed by a developer-caught session → 0 trailing skips."""
        content = (
            _V0_NO_SKILLS_BLOCK
            + _V4_TASK_CHECKPOINT_S_ONLY
            + _V4_DEVELOPER_CAUGHT_ONLY
        )
        from session import _compute_skill_invocation_rate
        audit_dir = self._make_audit_dir(tmp_path, content)
        _, skips = _compute_skill_invocation_rate(audit_dir)
        assert skips == 0  # last session had developer_caught

    def test_non_capability_developer_caught_not_a_hit(self, tmp_path):
        from session import _compute_skill_invocation_rate
        audit_dir = self._make_audit_dir(tmp_path, _V4_DEVELOPER_CAUGHT_NON_CAPABILITY)
        rate, skips = _compute_skill_invocation_rate(audit_dir)
        assert rate == 0
        assert skips == 1
