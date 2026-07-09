"""Tests for routing.py — scope-collapse gate, intent_brief size override, net-score sizing."""
from __future__ import annotations
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def patch_routes(tmp_path, monkeypatch):
    """Write a minimal routes.yaml so routing tests don't need the real config."""
    routes = tmp_path / "config" / "routes.yaml"
    routes.parent.mkdir(parents=True)
    routes.write_text("""\
version: "1.1"
task_sizes:
  XS:
    signals: [typo, rename, one-liner]
    negative_signals: []
    ceremony: none
    skills: []
  S:
    signals: [bug fix, hotfix, fix the]
    negative_signals: [multiple, system]
    ceremony: minimal
    skills: [nfr_check]
    nfr_mode: fast_path_2q
  M:
    signals: [feature, add, implement, build, create]
    negative_signals: [typo, rename, one-liner]
    ceremony: standard
    skills: [nfr_check, dev_loop, code_review, verify]
    nfr_mode: quick_4q
  L:
    signals: [system, architecture, new module, multi-day]
    negative_signals: [typo]
    ceremony: full
    skills: [nfr_check, write_spec, dev_loop, code_review, verify]
    nfr_mode: full
  XL:
    signals: [platform, rewrite, major migration]
    negative_signals: []
    ceremony: full
    skills: [nfr_check, write_spec, stress_test, dev_loop, code_review, verify]
    nfr_mode: full
token_budgets:
  XS: 2000
  S: 5000
  M: 15000
  L: 40000
  XL: 80000
""")
    import routing
    monkeypatch.setattr(routing, "ROUTES_FILE", routes)


class TestScopeCollapseGate:
    """route_task returns blocked=True when intent_brief has ambiguity_detected=True."""

    def test_blocked_when_ambiguous_brief_provided(self):
        from routing import route_task
        brief = {
            "ambiguity_detected": True,
            "solution_fork": {
                "collapsing_question": "Is this for latency reduction or rate-limit protection?"
            },
            "clarifying_questions": ["Is this for latency reduction or rate-limit protection?"],
        }
        decision = route_task("add caching to the API", intent_brief=brief)
        assert decision.blocked is True

    def test_blocked_surfaces_collapsing_question_from_fork(self):
        from routing import route_task
        brief = {
            "ambiguity_detected": True,
            "solution_fork": {
                "collapsing_question": "Is this for latency reduction or rate-limit protection?"
            },
            "clarifying_questions": [],
        }
        decision = route_task("add caching to the API", intent_brief=brief)
        assert "latency" in decision.collapsing_question

    def test_blocked_falls_back_to_clarifying_questions_when_no_fork(self):
        from routing import route_task
        brief = {
            "ambiguity_detected": True,
            "solution_fork": None,
            "clarifying_questions": ["Which module should be cached?"],
        }
        decision = route_task("add caching", intent_brief=brief)
        assert decision.blocked is True
        assert "Which module" in decision.collapsing_question

    def test_blocked_decision_has_empty_skills(self):
        from routing import route_task
        brief = {"ambiguity_detected": True, "solution_fork": {"collapsing_question": "Q?"}}
        decision = route_task("implement feature", intent_brief=brief)
        assert decision.skills == []
        assert decision.ceremony == "blocked"

    def test_not_blocked_when_ambiguity_resolved(self):
        from routing import route_task
        brief = {
            "ambiguity_detected": False,
            "estimated_size": "M",
            "solution_fork": None,
            "clarifying_questions": [],
        }
        decision = route_task("add caching to reduce API latency", intent_brief=brief)
        assert decision.blocked is False
        assert decision.skills  # routing proceeds normally

    def test_not_blocked_when_no_brief_provided(self):
        from routing import route_task
        decision = route_task("fix the login bug")
        assert decision.blocked is False

    def test_to_dict_includes_blocked_field(self):
        from routing import route_task
        brief = {"ambiguity_detected": True, "solution_fork": {"collapsing_question": "Q?"}}
        d = route_task("add feature", intent_brief=brief).to_dict()
        assert "blocked" in d
        assert d["blocked"] is True
        assert "collapsing_question" in d

    def test_to_dict_blocked_false_omits_collapsing_question(self):
        from routing import route_task
        d = route_task("fix the login bug").to_dict()
        assert d["blocked"] is False
        assert "collapsing_question" not in d


class TestIntentBriefSizeOverride:
    """When intent_brief is resolved (ambiguity_detected=False), use brief's estimated_size."""

    def test_brief_size_overrides_keyword_scoring(self):
        from routing import route_task
        # "fix the bug" would score S by keyword, but brief says L
        brief = {"ambiguity_detected": False, "estimated_size": "L", "clarifying_questions": []}
        decision = route_task("fix the bug in the authentication module", intent_brief=brief)
        assert decision.size.value == "L"

    def test_invalid_brief_size_falls_back_to_keyword_scoring(self):
        from routing import route_task
        brief = {"ambiguity_detected": False, "estimated_size": "INVALID", "clarifying_questions": []}
        decision = route_task("implement new feature", intent_brief=brief)
        # Falls back to keyword scoring — "implement" → M
        assert decision.size.value == "M"

    def test_no_brief_uses_keyword_scoring(self):
        from routing import route_task
        decision = route_task("implement new feature")
        assert decision.size.value == "M"


class TestNetScoreRouting:
    """Existing routing behavior is preserved."""

    def test_typo_routes_xs(self):
        from routing import route_task
        assert route_task("fix a typo in README").size.value == "XS"

    def test_feature_routes_m(self):
        from routing import route_task
        assert route_task("implement user notifications").size.value == "M"

    def test_architecture_routes_l(self):
        from routing import route_task
        assert route_task("design new module architecture").size.value == "L"

    def test_negative_signal_downgrades_size(self):
        from routing import route_task
        # "add" → M signal, but "one-liner" → M negative signal (×2 weight)
        decision = route_task("add one-liner helper")
        assert decision.size.value in ("XS", "S")  # downgraded from M
