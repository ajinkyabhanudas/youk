"""
Tests for multi-level convergence traversal in optimize_intent and challenge SKILL.md.

Verifies:
1. Quality words trigger translation_risk=high (structural angle fails first)
2. Extended opaque word set catches production-grade, bullet-proof, etc.
3. challenge SKILL.md contains the seven-angle convergence check section
4. Convergence check is positioned before the four lenses
5. Contradiction between angles = BLOCKING documented in SKILL.md
6. Structural angle evaluated first (adversarial ordering)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# 1. Quality words trigger high translation_risk in fallback path
# ---------------------------------------------------------------------------

class TestQualityWordTranslationRisk:
    def _optimize(self, text: str) -> dict:
        from intent import optimize_intent
        return optimize_intent(text)

    def test_elite_triggers_high_risk(self):
        result = self._optimize("get youk to elite status")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_production_grade_triggers_high_risk(self):
        result = self._optimize("make this production grade")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_bullet_proof_triggers_high_risk(self):
        result = self._optimize("make the foundation bullet proof")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_better_triggers_high_risk(self):
        result = self._optimize("make it better")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_solid_triggers_high_risk(self):
        result = self._optimize("make this solid")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_complete_triggers_high_risk(self):
        result = self._optimize("make it complete")
        assert result["goal_translation"]["translation_risk"] == "high"

    def test_specific_task_is_low_or_none_risk(self):
        result = self._optimize("add the theme field to _detect_cross_project_patterns return value")
        assert result["goal_translation"]["translation_risk"] in ("none", "low")

    def test_translation_question_present_when_high_risk(self):
        result = self._optimize("get youk to elite status")
        assert result["goal_translation"]["translation_question"] is not None
        assert len(result["goal_translation"]["translation_question"]) > 10


# ---------------------------------------------------------------------------
# 2. route_task blocks on high translation_risk
# ---------------------------------------------------------------------------

class TestRouteTaskBlocksOnHighRisk:
    def test_high_translation_risk_blocks_routing(self):
        from routing import route_task
        result = route_task("get youk to elite status", intent_brief={
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "high",
                "translation_question": "What would you observe that tells you this worked?",
            },
            "estimated_size": "M",
        })
        assert result.blocked is True
        assert result.collapsing_question != ""

    def test_low_translation_risk_does_not_block(self):
        from routing import route_task
        result = route_task("add theme field to function", intent_brief={
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "low",
                "translation_question": None,
            },
            "estimated_size": "S",
        })
        assert result.blocked is False

    def test_none_translation_risk_does_not_block(self):
        from routing import route_task
        result = route_task("fix typo in README", intent_brief={
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "none",
                "translation_question": None,
            },
            "estimated_size": "XS",
        })
        assert result.blocked is False


# ---------------------------------------------------------------------------
# 3. challenge SKILL.md — multi-level convergence section
# ---------------------------------------------------------------------------

class TestChallengeSkillMultiLevelSection:
    def _content(self) -> str:
        return (Path(__file__).parent.parent / "skills" / "challenge" / "SKILL.md").read_text()

    def test_convergence_check_section_present(self):
        assert "Multi-Level Convergence" in self._content()

    def test_seven_angles_all_present(self):
        content = self._content()
        for angle in ["STRUCTURAL", "OPERATIONAL", "EXPERIENTIAL", "ADVERSARIAL", "TEMPORAL", "OUTCOME", "SEMANTIC"]:
            assert angle in content, f"Missing angle: {angle}"

    def test_structural_evaluated_first(self):
        content = self._content()
        structural_pos = content.find("**STRUCTURAL**")
        operational_pos = content.find("**OPERATIONAL**")
        assert structural_pos < operational_pos, "STRUCTURAL must come before OPERATIONAL"

    def test_semantic_evaluated_last(self):
        content = self._content()
        outcome_pos = content.find("**OUTCOME**")
        semantic_pos = content.find("**SEMANTIC**")
        assert outcome_pos < semantic_pos, "SEMANTIC must come after OUTCOME"

    def test_convergence_check_before_four_lenses(self):
        content = self._content()
        convergence_pos = content.find("Multi-Level Convergence")
        lenses_pos = content.find("## The Four Lenses")
        assert convergence_pos < lenses_pos, "Convergence check must precede the four lenses"

    def test_contradiction_is_blocking(self):
        content = self._content()
        assert "BLOCKING" in content
        assert "CONTRADICTION" in content

    def test_convergence_emit_block_documented(self):
        content = self._content()
        assert "[CONVERGENCE CHECK]" in content

    def test_structural_fails_first_rationale_present(self):
        content = self._content()
        assert "fails most often" in content or "fails first" in content

    def test_false_unanimity_documented(self):
        content = self._content()
        assert "false unanimity" in content


# ---------------------------------------------------------------------------
# 4. intent.py system prompt — seven angles documented
# ---------------------------------------------------------------------------

class TestIntentSystemPromptAngles:
    def _prompt(self) -> str:
        import intent
        return intent._INTENT_SYSTEM_PROMPT

    def test_multi_level_convergence_in_prompt(self):
        assert "Multi-level convergence" in self._prompt() or "multi-level" in self._prompt().lower()

    def test_seven_angles_in_prompt(self):
        prompt = self._prompt()
        for angle in ["STRUCTURAL", "OPERATIONAL", "EXPERIENTIAL", "ADVERSARIAL", "TEMPORAL", "OUTCOME", "SEMANTIC"]:
            assert angle in prompt, f"Missing angle in system prompt: {angle}"

    def test_structural_first_in_prompt(self):
        prompt = self._prompt()
        structural_pos = prompt.find("STRUCTURAL")
        operational_pos = prompt.find("OPERATIONAL")
        assert structural_pos < operational_pos

    def test_contradiction_blocks_in_prompt(self):
        prompt = self._prompt()
        assert "Contradiction between any two angles" in prompt or "contradiction" in prompt.lower()

    def test_semantic_label_after_convergence_in_prompt(self):
        prompt = self._prompt()
        assert "angles 1-6 converge" in prompt or "after angles" in prompt
