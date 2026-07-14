"""
Tests for adaptive nfr_check ceremony and youk-lite growth section.

Covers:
1. _compute_skill_autonomy_rate: per-skill rate from DeveloperCaught audit field
2. SessionState carries nfr_autonomy_mode + developer_autonomy_rate
3. nfr-check/SKILL.md has Adaptive Mode section with validate/standard modes
4. youk-lite.md template has Growth section with NFR pre-empts counter
5. validate mode fires at ≥0.4 rate; standard mode below threshold
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block(developer_caught: str = "") -> str:
    caught_line = f"DeveloperCaught: {developer_caught}\n" if developer_caught else ""
    return (
        "### Session — 2026-01-01 10:00 UTC\n"
        "Project: youk\nSkills: nfr-check, dev-loop\n"
        "CloseCluster: yes\nCommits: yes\n"
        f"{caught_line}"
    )


# ---------------------------------------------------------------------------
# 1. _compute_skill_autonomy_rate
# ---------------------------------------------------------------------------

class TestComputeSkillAutonomyRate:
    def test_returns_zero_below_6_sessions(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        blocks = [_make_block("nfr_check")] * 5
        sessions = _parse_audit_sessions(["\n".join(blocks)])
        assert _compute_skill_autonomy_rate(sessions, "nfr_check") == 0.0

    def test_correct_rate_all_caught(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        blocks = [_make_block("nfr_check")] * 10
        sessions = _parse_audit_sessions(["\n".join(blocks)])
        rate = _compute_skill_autonomy_rate(sessions, "nfr_check")
        assert rate == pytest.approx(1.0)

    def test_correct_rate_half_caught(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        caught = [_make_block("nfr_check")] * 5
        missed = [_make_block()] * 5
        sessions = _parse_audit_sessions(["\n".join(caught + missed)])
        rate = _compute_skill_autonomy_rate(sessions, "nfr_check")
        assert rate == pytest.approx(0.5)

    def test_different_skill_not_counted(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        blocks = [_make_block("challenge")] * 10
        sessions = _parse_audit_sessions(["\n".join(blocks)])
        rate = _compute_skill_autonomy_rate(sessions, "nfr_check")
        assert rate == 0.0

    def test_hyphen_underscore_normalized(self):
        """nfr-check and nfr_check are the same skill."""
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        blocks = [_make_block("nfr-check")] * 10
        sessions = _parse_audit_sessions(["\n".join(blocks)])
        rate = _compute_skill_autonomy_rate(sessions, "nfr_check")
        assert rate == pytest.approx(1.0)

    def test_zero_when_no_developer_caught_field(self):
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate
        blocks = [_make_block()] * 10
        sessions = _parse_audit_sessions(["\n".join(blocks)])
        assert _compute_skill_autonomy_rate(sessions, "nfr_check") == 0.0


# ---------------------------------------------------------------------------
# 2. validate mode threshold
# ---------------------------------------------------------------------------

class TestAdaptiveModeThreshold:
    def _rate_to_mode(self, rate: float) -> str:
        return "validate" if rate >= 0.4 else "standard"

    def test_standard_below_threshold(self):
        assert self._rate_to_mode(0.0) == "standard"
        assert self._rate_to_mode(0.39) == "standard"

    def test_validate_at_threshold(self):
        assert self._rate_to_mode(0.4) == "validate"

    def test_validate_above_threshold(self):
        assert self._rate_to_mode(0.8) == "validate"
        assert self._rate_to_mode(1.0) == "validate"


# ---------------------------------------------------------------------------
# 3. SessionState carries nfr_autonomy_mode + developer_autonomy_rate
# ---------------------------------------------------------------------------

class TestSessionStateAdaptiveFields:
    def test_default_mode_is_standard(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
        )
        assert s.nfr_autonomy_mode == "standard"
        assert s.developer_autonomy_rate == 0.0

    def test_validate_mode_set_explicitly(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
            nfr_autonomy_mode="validate",
            developer_autonomy_rate=0.6,
        )
        assert s.nfr_autonomy_mode == "validate"
        assert s.developer_autonomy_rate == pytest.approx(0.6)

    def test_to_dict_includes_adaptive_fields(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
            nfr_autonomy_mode="validate",
            developer_autonomy_rate=0.5,
        )
        d = s.to_dict()
        assert d["nfr_autonomy_mode"] == "validate"
        assert d["developer_autonomy_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 4. nfr-check SKILL.md has Adaptive Mode section
# ---------------------------------------------------------------------------

class TestNfrCheckSkillAdaptiveMode:
    def test_adaptive_mode_section_present(self):
        skill_path = Path(__file__).parent.parent / "skills" / "nfr-check" / "SKILL.md"
        content = skill_path.read_text()
        assert "Adaptive Mode" in content

    def test_validate_mode_documented(self):
        skill_path = Path(__file__).parent.parent / "skills" / "nfr-check" / "SKILL.md"
        content = skill_path.read_text()
        assert "validate" in content
        assert "nfr_autonomy_mode" in content

    def test_validate_mode_before_invocation_grammar(self):
        skill_path = Path(__file__).parent.parent / "skills" / "nfr-check" / "SKILL.md"
        content = skill_path.read_text()
        adaptive_pos = content.find("Adaptive Mode")
        invocation_pos = content.find("Invocation Grammar")
        assert adaptive_pos < invocation_pos, "Adaptive Mode section must precede Invocation Grammar"

    def test_nfr_covered_emit_documented(self):
        skill_path = Path(__file__).parent.parent / "skills" / "nfr-check" / "SKILL.md"
        content = skill_path.read_text()
        assert "NFR COVERED" in content

    def test_always_emit_decision_block(self):
        """validate mode must still emit an NFR DECISION BLOCK — skipping is not allowed."""
        skill_path = Path(__file__).parent.parent / "skills" / "nfr-check" / "SKILL.md"
        content = skill_path.read_text()
        assert "always run it" in content or "always emit" in content.lower()


# ---------------------------------------------------------------------------
# 5. youk-lite Growth section
# ---------------------------------------------------------------------------

class TestYoukLiteGrowthSection:
    def test_growth_section_present(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "## Growth" in content

    def test_nfr_preempts_counter(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "NFR pre-empts" in content

    def test_ceremony_reduction_at_threshold(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "validation mode" in content or "validate" in content

    def test_direction_gate_preempts_counter(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "Direction gate pre-empts" in content

    def test_growth_section_in_template(self):
        """Growth section must be inside the markdown code block (the template)."""
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        # Template is between the first ``` opening and final ``` close
        # Growth section should appear before the closing ```
        growth_pos = content.find("## Growth")
        closing_pos = content.rfind("```", 0, content.find("That's it"))
        assert growth_pos < closing_pos, "Growth section must be inside the template block"
