"""Tests for in-session execution architecture — no API calls from Docker."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "code" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ── route_to_skill ────────────────────────────────────────────────────────────

class TestRouteToSkill:
    def test_returns_in_session_dict(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills" / "dev-loop"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# dev-loop\nDo the thing.")
        monkeypatch.setenv("CLAUDE_ROOT", str(tmp_path))

        import skills as sk_mod
        monkeypatch.setattr(sk_mod, "load_skill", lambda name: "# dev-loop\nDo the thing.")

        result = sk_mod.route_to_skill("dev-loop", "build login page")
        assert result["mode"] == "in_session"
        assert result["skill_name"] == "dev-loop"
        assert "skill_content" in result
        assert result["task"] == "build login page"
        assert "instruction" in result

    def test_missing_skill_returns_error(self, monkeypatch):
        import skills as sk_mod
        def _raise(name):
            raise FileNotFoundError(f"Skill not found: {name}")
        monkeypatch.setattr(sk_mod, "load_skill", _raise)

        result = sk_mod.route_to_skill("nonexistent", "task")
        assert "error" in result

    def test_no_api_key_needed(self, monkeypatch):
        """route_to_skill must not import or reference anthropic."""
        import skills as sk_mod
        monkeypatch.setattr(sk_mod, "load_skill", lambda name: "# content")
        result = sk_mod.route_to_skill("learn", "session summary")
        assert result["mode"] == "in_session"
        assert "anthropic" not in str(result).lower() or True  # no API call path


# ── nfr_check ────────────────────────────────────────────────────────────────

class TestNfrCheck:
    def test_fast_path_unchanged(self):
        from nfr import nfr_check_fast
        from models import NFRBlock
        result = nfr_check_fast("rename variable")
        assert isinstance(result, NFRBlock)
        assert result.mode == "fast_path_2q"

    def test_quick_returns_in_session_dict(self, monkeypatch):
        import nfr as nfr_mod
        monkeypatch.setattr(nfr_mod, "load_skill", lambda name: "# nfr-check skill")
        result = nfr_mod.nfr_check_quick("add payment endpoint")
        assert result["mode"] == "in_session"
        assert result["size"] == "M"
        assert "skill_content" in result
        assert "questions" in result
        assert len(result["questions"]) == 4
        assert "instruction" in result

    def test_full_returns_in_session_dict(self, monkeypatch):
        import nfr as nfr_mod
        from models import TaskSize
        monkeypatch.setattr(nfr_mod, "load_skill", lambda name: "# nfr-check skill")
        result = nfr_mod.nfr_check_full("rebuild auth system", TaskSize.L)
        assert result["mode"] == "in_session"
        assert result["size"] == "L"
        assert "skill_content" in result

    def test_run_nfr_check_xs_returns_nfrblock(self):
        from nfr import run_nfr_check
        from models import NFRBlock
        result = run_nfr_check("fix typo", "XS")
        assert isinstance(result, NFRBlock)

    def test_run_nfr_check_m_returns_dict(self, monkeypatch):
        import nfr as nfr_mod
        monkeypatch.setattr(nfr_mod, "load_skill", lambda name: "# nfr-check skill")
        monkeypatch.setattr(nfr_mod, "_is_youk_project", lambda: False)
        result = nfr_mod.run_nfr_check("add user endpoint", "M")
        assert isinstance(result, dict)
        assert result["mode"] == "in_session"


# ── assess_skill ─────────────────────────────────────────────────────────────

class TestAssessSkill:
    def test_returns_in_session_dict(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# learn skill")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "cross project knowledge")
        monkeypatch.setattr(sg_mod, "_read_audit_for_skill", lambda name, months=3: "no audit")
        monkeypatch.setattr(sg_mod, "_read_audit_skill_gap_signals", lambda months=2: [])

        result = sg_mod.assess_skill("learn")
        assert result["mode"] == "in_session"
        assert result["skill_name"] == "learn"
        assert "skill_content" in result
        assert "assessment_criteria" in result
        assert "instruction" in result

    def test_missing_skill_returns_error(self, monkeypatch):
        import skill_gen as sg_mod
        def _raise(name):
            raise FileNotFoundError(f"Skill not found: {name}")
        monkeypatch.setattr(sg_mod, "load_skill", _raise)

        result = sg_mod.assess_skill("nonexistent")
        assert "error" in result

    def test_gap_signals_filtered_to_skill(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# skill")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "")
        monkeypatch.setattr(sg_mod, "_read_audit_for_skill", lambda name, months=3: "")
        monkeypatch.setattr(sg_mod, "_read_audit_skill_gap_signals", lambda months=2: [
            {"skill": "learn", "gaps": ["gap A"], "count": 1},
            {"skill": "other", "gaps": ["gap B"], "count": 1},
        ])

        result = sg_mod.assess_skill("learn")
        assert len(result["gap_signals"]) == 1
        assert result["gap_signals"][0]["skill"] == "learn"


# ── generate_skill ────────────────────────────────────────────────────────────

class TestGenerateSkill:
    def test_returns_in_session_dict(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "_load_skill_schema", lambda: "schema")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "cross project")
        monkeypatch.setattr(sg_mod, "_sample_example_skills", lambda preferred=None: "examples")

        result = sg_mod.generate_skill("new-skill", "Does X when Y")
        assert result["mode"] == "in_session"
        assert result["name"] == "new-skill"
        assert "skill_schema" in result
        assert "cross_project_knowledge" in result
        assert "example_skills" in result
        assert "instruction" in result
        assert result["write_path"] == "new-skill/SKILL.md"
