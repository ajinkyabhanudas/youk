"""Calibration testbench for the signal/noise framework + skill-forge skill.

Structural drift detection — does not execute the LLM skill. Catches silent
degradation of the SUBTRACT/REVEAL passes and the forge convergence spec.
"""
from __future__ import annotations
import pytest
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"
FRAMEWORK = SKILLS_DIR / "humanize" / "references" / "signal-noise-framework.md"
FORGE = SKILLS_DIR / "skill-forge" / "SKILL.md"
HUMANIZE = SKILLS_DIR / "humanize" / "SKILL.md"


@pytest.fixture
def framework_text():
    return FRAMEWORK.read_text()


@pytest.fixture
def forge_text():
    return FORGE.read_text()


class TestSignalNoiseFramework:
    def test_exists(self):
        assert FRAMEWORK.exists()

    def test_has_subtract_pass(self, framework_text):
        assert "PASS 1 — SUBTRACT" in framework_text

    def test_has_reveal_pass(self, framework_text):
        assert "PASS 2 — REVEAL" in framework_text

    def test_subtract_defaults_to_cut(self, framework_text):
        assert "defaults to CUT" in framework_text
        assert "Burden of proof is on KEEPING" in framework_text

    def test_reveal_has_load_bearing_convergence(self, framework_text):
        # REVEAL's convergence — the fix found by running the framework on itself
        assert "LOAD-BEARING FILTER" in framework_text
        assert "manufactured depth" in framework_text

    def test_reveal_names_missing_frame_connotation(self, framework_text):
        assert "MISSING" in framework_text
        assert "FRAME" in framework_text
        assert "CONNOTATION" in framework_text

    def test_tension_rule_present(self, framework_text):
        assert "TENSION RULE" in framework_text

    def test_goal_is_trust_not_spectacle(self, framework_text):
        # The connotation fix — trust, not astonishment-as-target
        assert "trust" in framework_text.lower()
        assert "not spectacle" in framework_text or "not the target" in framework_text

    def test_grade_before_apply(self, framework_text):
        assert "GRADE before APPLY" in framework_text

    def test_rejects_5whys(self, framework_text):
        # The reasoned instrument choice must remain documented
        assert "5-whys was rejected" in framework_text

    def test_cites_precedent_skills(self, framework_text):
        for skill in ("learn", "challenge", "stress-test"):
            assert skill in framework_text


class TestHumanizeWiring:
    def test_humanize_references_framework(self):
        text = HUMANIZE.read_text()
        assert "signal-noise-framework.md" in text

    def test_humanize_has_conversational_content_type(self):
        text = HUMANIZE.read_text()
        assert "conversational reply" in text

    def test_humanize_names_filler_openers(self):
        text = HUMANIZE.read_text()
        assert "Good question" in text
        assert "Put simply" in text


class TestSkillForge:
    def test_exists(self, forge_text):
        assert "name: skill-forge" in forge_text

    def test_has_discovery_and_definition_loops(self, forge_text):
        assert "PHASE A — DISCOVERY" in forge_text
        assert "PHASE B — DEFINITION" in forge_text

    def test_raise_the_bar_is_the_variable(self, forge_text):
        assert "RAISE-THE-BAR" in forge_text
        assert "standard" in forge_text

    def test_convergence_is_bar_not_count(self, forge_text):
        assert "standard stops rising" in forge_text or "STANDARD-DELTA" in forge_text

    def test_safe_types_restricted(self, forge_text):
        # The critical safety rail — CODE/CONFIG never auto-applied
        assert 'safe_types=["FILE_CREATE"]' in forge_text
        assert 'safe_types=["SKILL_EDIT"]' in forge_text
        assert "never" in forge_text.lower()

    def test_ceiling_reports_honestly(self, forge_text):
        assert "ceiling_hit" in forge_text
        assert "converged=False" in forge_text or "converged=false" in forge_text

    def test_sources_required(self, forge_text):
        assert "cites sources" in forge_text or "cite sources" in forge_text

    def test_references_signal_noise_framework(self, forge_text):
        assert "signal-noise-framework.md" in forge_text
