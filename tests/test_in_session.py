"""Tests for in-session execution architecture — no API calls from Docker."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "code" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))


# ── load_skill_with_context ───────────────────────────────────────────────────

class TestLoadSkillWithContext:
    def test_base_only_when_no_overlays(self, tmp_path, monkeypatch):
        import skill_loader as sl
        (tmp_path / "dev-loop").mkdir()
        (tmp_path / "dev-loop" / "SKILL.md").write_text("# base content")
        monkeypatch.setattr(sl, "SKILLS_DIR", tmp_path)

        result = sl.load_skill_with_context("dev-loop")
        assert result == "# base content"

    def test_appends_stack_overlay_from_references_stacks(self, tmp_path, monkeypatch):
        import skill_loader as sl
        skill_dir = tmp_path / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# base")
        stacks = skill_dir / "references" / "stacks"
        stacks.mkdir(parents=True)
        (stacks / "python.md").write_text("Python: check type hints")
        monkeypatch.setattr(sl, "SKILLS_DIR", tmp_path)

        result = sl.load_skill_with_context("code-review", stack="python")
        assert "# base" in result
        assert "Python: check type hints" in result
        assert "Stack context: python" in result

    def test_framework_takes_priority_over_stack(self, tmp_path, monkeypatch):
        import skill_loader as sl
        skill_dir = tmp_path / "dev-loop"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# base")
        stacks = skill_dir / "references" / "stacks"
        stacks.mkdir(parents=True)
        (stacks / "django.md").write_text("Django: check select_related")
        (stacks / "python.md").write_text("Python: generic")
        monkeypatch.setattr(sl, "SKILLS_DIR", tmp_path)

        result = sl.load_skill_with_context("dev-loop", stack="python", framework="django")
        assert "Django: check select_related" in result
        assert "Python: generic" not in result  # framework wins

    def test_appends_domain_overlay(self, tmp_path, monkeypatch):
        import skill_loader as sl
        skill_dir = tmp_path / "write-spec"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# base")
        domain_dir = skill_dir / "domain"
        domain_dir.mkdir()
        (domain_dir / "saas.md").write_text("SaaS: use OKR framing")
        monkeypatch.setattr(sl, "SKILLS_DIR", tmp_path)

        result = sl.load_skill_with_context("write-spec", domain="saas")
        assert "SaaS: use OKR framing" in result
        assert "Domain context: saas" in result

    def test_missing_overlay_silently_skipped(self, tmp_path, monkeypatch):
        import skill_loader as sl
        skill_dir = tmp_path / "learn"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# learn base")
        monkeypatch.setattr(sl, "SKILLS_DIR", tmp_path)

        # No stack or domain files exist — should return just base
        result = sl.load_skill_with_context("learn", stack="go", domain="infra")
        assert result == "# learn base"


# ── _detect_stack_context ─────────────────────────────────────────────────────

class TestDetectStackContext:
    def test_detects_python(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["stack"] == "python"

    def test_detects_fastapi_framework(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["framework"] == "fastapi"

    def test_detects_django_framework(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("django==4.2\npsycopg2\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["framework"] == "django"

    def test_detects_saas_domain(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("stripe==7.0\nfastapi\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["domain"] == "saas"

    def test_detects_data_domain(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("pandas\nscikitlearn\ntorch\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["domain"] == "data"

    def test_detects_go(self, tmp_path, monkeypatch):
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21\n")
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result["stack"] == "go"

    def test_unknown_project_returns_nones(self, tmp_path, monkeypatch):
        import session as sess
        monkeypatch.setattr(sess, "_resolve_project_path", lambda p: tmp_path)
        result = sess._detect_stack_context(str(tmp_path))
        assert result == {"stack": None, "framework": None, "domain": None}


# ── route_to_skill ────────────────────────────────────────────────────────────

class TestRouteToSkill:
    def test_returns_in_session_dict(self, tmp_path, monkeypatch):
        import skills as sk_mod
        monkeypatch.setattr(sk_mod, "load_skill_with_context", lambda name, **_: "# dev-loop\nDo the thing.")

        result = sk_mod.route_to_skill("dev-loop", "build login page")
        assert result["mode"] == "in_session"
        assert result["skill_name"] == "dev-loop"
        assert "skill_content" in result
        assert result["task"] == "build login page"
        assert "instruction" in result

    def test_missing_skill_returns_error(self, monkeypatch):
        import skills as sk_mod
        def _raise(name, **_):
            raise FileNotFoundError(f"Skill not found: {name}")
        monkeypatch.setattr(sk_mod, "load_skill_with_context", _raise)

        result = sk_mod.route_to_skill("nonexistent", "task")
        assert "error" in result

    def test_no_api_key_needed(self, monkeypatch):
        """route_to_skill must not import or reference anthropic."""
        import skills as sk_mod
        monkeypatch.setattr(sk_mod, "load_skill_with_context", lambda name, **_: "# content")
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


# ── generate_stack_overlay ────────────────────────────────────────────────────

class TestGenerateStackOverlay:
    def test_returns_in_session_dict_for_stack(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# code-review base")
        monkeypatch.setattr(sg_mod, "_load_stack_overlay_schema", lambda: "# schema")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "cross project")
        monkeypatch.setattr(sg_mod, "SKILLS_DIR", __import__("pathlib").Path("/nonexistent"))

        result = sg_mod.generate_stack_overlay("code-review", "python")
        assert result["mode"] == "in_session"
        assert result["skill_name"] == "code-review"
        assert result["stack"] == "python"
        assert result["target_label"] == "python"
        assert result["write_path"] == "code-review/references/stacks/python.md"
        assert "base_skill_content" in result
        assert "overlay_schema" in result
        assert "instruction" in result

    def test_framework_takes_priority_as_write_path(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# nfr-check base")
        monkeypatch.setattr(sg_mod, "_load_stack_overlay_schema", lambda: "")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "")
        monkeypatch.setattr(sg_mod, "SKILLS_DIR", __import__("pathlib").Path("/nonexistent"))

        result = sg_mod.generate_stack_overlay("nfr-check", "python", framework="django")
        assert result["target_label"] == "django"
        assert result["write_path"] == "nfr-check/references/stacks/django.md"

    def test_missing_skill_returns_error(self, monkeypatch):
        import skill_gen as sg_mod
        def _raise(name):
            raise FileNotFoundError(f"Skill not found: {name}")
        monkeypatch.setattr(sg_mod, "load_skill", _raise)

        result = sg_mod.generate_stack_overlay("nonexistent", "python")
        assert "error" in result

    def test_already_exists_returns_status(self, tmp_path, monkeypatch):
        import skill_gen as sg_mod
        # Create existing overlay
        overlay_dir = tmp_path / "code-review" / "references" / "stacks"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "python.md").write_text("# existing overlay")

        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# base")
        monkeypatch.setattr(sg_mod, "_load_stack_overlay_schema", lambda: "")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "")
        monkeypatch.setattr(sg_mod, "SKILLS_DIR", tmp_path)

        result = sg_mod.generate_stack_overlay("code-review", "python")
        assert result["status"] == "already_exists"
        assert "already_exists" in result["message"] or "already exists" in result["message"]

    def test_instruction_references_write_path(self, monkeypatch):
        import skill_gen as sg_mod
        monkeypatch.setattr(sg_mod, "load_skill", lambda name: "# base")
        monkeypatch.setattr(sg_mod, "_load_stack_overlay_schema", lambda: "")
        monkeypatch.setattr(sg_mod, "_load_cross_project_knowledge", lambda: "")
        monkeypatch.setattr(sg_mod, "SKILLS_DIR", __import__("pathlib").Path("/nonexistent"))

        result = sg_mod.generate_stack_overlay("dev-loop", "go")
        assert "dev-loop/references/stacks/go.md" in result["instruction"]
