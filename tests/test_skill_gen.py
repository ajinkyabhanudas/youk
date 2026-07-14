"""Tests for analyze_stack_for_skills() and the stack_analysis signal_type."""
from __future__ import annotations
import pytest


@pytest.fixture
def skill_gen_root(tmp_path, monkeypatch):
    """Isolated YOUK_ROOT + CLAUDE_ROOT for skill_gen."""
    import skill_gen
    youk = tmp_path / "youk"
    claude = tmp_path / "claude"
    (youk / "knowledge").mkdir(parents=True)
    (claude / "skills").mkdir(parents=True)
    monkeypatch.setattr(skill_gen, "YOUK_ROOT", youk)
    monkeypatch.setattr(skill_gen, "CLAUDE_ROOT", claude)
    monkeypatch.setattr(skill_gen, "SKILLS_DIR", claude / "skills")
    # No real skills on disk — stub list_skills so existing_skills is deterministic
    monkeypatch.setattr(skill_gen, "list_skills", lambda: [{"name": "dev-loop"}, {"name": "learn"}])
    return youk


class TestAnalyzeStackForSkills:
    def test_returns_in_session_mode(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python", "fastapi")
        assert r["mode"] == "in_session"

    def test_carries_stack_framework_domain(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python", "fastapi", "data")
        assert r["stack"] == "python"
        assert r["framework"] == "fastapi"
        assert r["domain"] == "data"

    def test_defaults_existing_skills_from_list(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        assert r["existing_skills"] == ["dev-loop", "learn"]

    def test_known_skills_override(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python", known_skills=["custom"])
        assert r["existing_skills"] == ["custom"]

    def test_standard_none_becomes_empty_string(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        assert r["current_standard"] == ""

    def test_standard_carried_when_provided(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python", standard="elite bar v2")
        assert r["current_standard"] == "elite bar v2"

    def test_has_raise_the_bar_step(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        assert "raise_the_bar_step" in r
        assert "BETTER" in r["raise_the_bar_step"]

    def test_search_directive_has_repo_and_internet(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        assert "repo" in r["search_directive"]
        assert "internet" in r["search_directive"]

    def test_convergence_rule_targets_bar_not_skill_count(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        # The core ask: convergence is bar-stable, not skill-count-stable
        assert "Bar stable" in r["convergence_rule"]

    def test_instruction_uses_stack_analysis_signal(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        assert "stack_analysis" in r["instruction"]

    def test_derived_skills_must_cite_sources(self, skill_gen_root):
        from skill_gen import analyze_stack_for_skills
        r = analyze_stack_for_skills("python")
        crit = " ".join(r["derivation_criteria"])
        assert "sources" in crit


class TestStackAnalysisSignalType:
    def test_generate_skill_has_stack_analysis_guidance(self, skill_gen_root):
        from skill_gen import generate_skill
        r = generate_skill("obs", "observability", signal_type="stack_analysis")
        assert r["signal_type"] == "stack_analysis"
        assert "cite its source" in r["signal_guidance"] or "source" in r["signal_guidance"]

    def test_stack_analysis_guidance_mentions_elite_pattern(self, skill_gen_root):
        from skill_gen import generate_skill
        r = generate_skill("obs", "observability", signal_type="stack_analysis")
        assert "elite pattern" in r["signal_guidance"]
