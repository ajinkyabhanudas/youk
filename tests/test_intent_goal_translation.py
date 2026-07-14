"""
Tests for intent-level goal translation gate.

optimize_intent now detects two distinct failure modes:
1. Scope ambiguity: implementation forks ("5 lines vs 80 lines"). Caught by ambiguity_detected.
2. Intent opacity: stated goal doesn't map to observable outcome. Caught by goal_translation.

route_task blocks on EITHER. These tests verify the second gate — the one that wasn't there
before and that caused "get it to elite level" to pass through as a concrete task.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


class TestGoalTranslationInFallback:
    """
    Tests the fallback path (no API) in optimize_intent.
    The fallback is what runs in CI and in tests — it must detect translation_risk
    correctly from keyword matching so the gate works even without an API key.
    """

    def _run(self, raw_input: str) -> dict:
        import intent as intent_mod
        original = intent_mod._ANTHROPIC_AVAILABLE
        intent_mod._ANTHROPIC_AVAILABLE = False
        try:
            return intent_mod.optimize_intent(raw_input)
        finally:
            intent_mod._ANTHROPIC_AVAILABLE = original

    def test_quality_word_elite_triggers_high_translation_risk(self):
        result = self._run("get it to elite level")
        gt = result.get("goal_translation", {})
        assert gt.get("translation_risk") == "high", (
            "'elite' is a quality word without a referent — translation_risk must be high"
        )

    def test_quality_word_better_triggers_high_risk(self):
        result = self._run("make it better")
        gt = result.get("goal_translation", {})
        assert gt.get("translation_risk") == "high"

    def test_mindset_goal_triggers_high_risk(self):
        result = self._run("discover the underlying pattern")
        gt = result.get("goal_translation", {})
        assert gt.get("translation_risk") == "high", (
            "'pattern' is a mindset/principle word — no concrete deliverable implied"
        )

    def test_specific_deliverable_is_not_high_risk(self):
        result = self._run("add the goal_translation field to optimize_intent output")
        gt = result.get("goal_translation", {})
        assert gt.get("translation_risk") in ("none", "low"), (
            "A specific technical deliverable must not trigger high translation_risk"
        )

    def test_high_risk_result_includes_translation_question(self):
        result = self._run("get it to elite level")
        gt = result.get("goal_translation", {})
        assert gt.get("translation_risk") == "high"
        assert gt.get("translation_question"), (
            "High translation_risk must include a translation_question to surface to the user"
        )

    def test_goal_translation_always_present(self):
        """goal_translation must appear in every optimize_intent return, not just opaque inputs."""
        result = self._run("add logging to the auth endpoint")
        assert "goal_translation" in result, (
            "goal_translation must be present in every optimize_intent result — "
            "route_task reads it unconditionally"
        )

    def test_fast_path_also_returns_goal_translation(self):
        """Fast pattern matches must also include goal_translation."""
        import intent as intent_mod
        result = intent_mod.optimize_intent("fix the bug")
        assert "goal_translation" in result, (
            "Fast-path results must include goal_translation — "
            "they skip the API but still pass through route_task"
        )


class TestRouteTaskIntentCollapseGate:
    """
    route_task must block when goal_translation.translation_risk == "high".
    This is a hard gate — same enforcement as scope-ambiguity.
    """

    def _route(self, task: str, intent_brief: dict) -> object:
        import routing
        return routing.route_task(task, intent_brief=intent_brief)

    def test_blocks_on_high_translation_risk(self):
        intent_brief = {
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "high",
                "translation_question": "What would you observe that tells you this worked?",
            },
        }
        result = self._route("get it to elite level", intent_brief)
        assert result.blocked is True, (
            "route_task must block when goal_translation.translation_risk is high — "
            "this is the gate that was missing when 'elite level' passed through"
        )

    def test_collapsing_question_is_translation_question(self):
        intent_brief = {
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "high",
                "translation_question": "What would you observe that tells you this worked?",
            },
        }
        result = self._route("make it better", intent_brief)
        assert "observe" in result.collapsing_question or "experience" in result.collapsing_question or "worked" in result.collapsing_question

    def test_does_not_block_on_low_translation_risk(self):
        intent_brief = {
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "low",
                "translation_question": None,
            },
        }
        result = self._route("add a field to the output schema", intent_brief)
        assert result.blocked is False, (
            "route_task must NOT block on low translation_risk — only high blocks"
        )

    def test_does_not_block_when_goal_translation_absent(self):
        """Backwards compat: intent_brief without goal_translation must not crash or block."""
        intent_brief = {
            "ambiguity_detected": False,
        }
        result = self._route("add a test", intent_brief)
        assert result.blocked is False

    def test_scope_ambiguity_gate_still_fires_independently(self):
        """Scope-ambiguity gate must still block even when translation_risk is low."""
        intent_brief = {
            "ambiguity_detected": True,
            "solution_fork": {
                "collapsing_question": "Should this be a new endpoint or modify the existing one?"
            },
            "goal_translation": {
                "translation_risk": "low",
                "translation_question": None,
            },
        }
        result = self._route("add authentication", intent_brief)
        assert result.blocked is True, (
            "Scope-ambiguity gate is independent of intent-collapse gate — both can block"
        )
