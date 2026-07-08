"""Tests for skill_loader.py — load_skill, overlays, list_skills, fast-path extraction."""
from __future__ import annotations
import pytest
from pathlib import Path


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    """Isolated SKILLS_DIR pointing to tmp."""
    import skill_loader
    sdir = tmp_path / "skills"
    sdir.mkdir()
    monkeypatch.setattr(skill_loader, "SKILLS_DIR", sdir)
    return sdir


def _write_skill(skills_dir: Path, name: str, content: str) -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


class TestLoadSkill:
    def test_loads_skill_content(self, skills_dir):
        _write_skill(skills_dir, "code-review", "---\nname: code-review\n---\n# Code Review\nDo a review.")
        from skill_loader import load_skill
        content = load_skill("code-review")
        assert "Code Review" in content

    def test_raises_for_missing_skill(self, skills_dir):
        from skill_loader import load_skill
        with pytest.raises(FileNotFoundError):
            load_skill("nonexistent-skill")

    def test_raises_for_skill_dir_without_skill_md(self, skills_dir):
        (skills_dir / "empty-skill").mkdir()
        from skill_loader import load_skill
        with pytest.raises(FileNotFoundError):
            load_skill("empty-skill")


class TestLoadSkillWithContext:
    _BASE = "---\nname: code-review\n---\n# Code Review\nBase content."

    def test_returns_base_when_no_overlay(self, skills_dir):
        _write_skill(skills_dir, "code-review", self._BASE)
        from skill_loader import load_skill_with_context
        result = load_skill_with_context("code-review")
        assert "Base content." in result
        assert "Stack context" not in result

    def test_appends_stack_overlay_when_exists(self, skills_dir):
        skill_dir = _write_skill(skills_dir, "code-review", self._BASE)
        (skill_dir / "references" / "stacks").mkdir(parents=True)
        (skill_dir / "references" / "stacks" / "python.md").write_text("Use ruff for linting.")
        from skill_loader import load_skill_with_context
        result = load_skill_with_context("code-review", stack="python")
        assert "Use ruff for linting." in result
        assert "Stack context: python" in result

    def test_framework_overlay_takes_priority_over_stack(self, skills_dir):
        skill_dir = _write_skill(skills_dir, "code-review", self._BASE)
        (skill_dir / "references" / "stacks").mkdir(parents=True)
        (skill_dir / "references" / "stacks" / "fastapi.md").write_text("FastAPI-specific.")
        (skill_dir / "references" / "stacks" / "python.md").write_text("Python generic.")
        from skill_loader import load_skill_with_context
        result = load_skill_with_context("code-review", stack="python", framework="fastapi")
        assert "FastAPI-specific." in result
        assert "Python generic." not in result

    def test_domain_overlay_appended(self, skills_dir):
        skill_dir = _write_skill(skills_dir, "code-review", self._BASE)
        (skill_dir / "references" / "domain").mkdir(parents=True)
        (skill_dir / "references" / "domain" / "fintech.md").write_text("Audit trail required.")
        from skill_loader import load_skill_with_context
        result = load_skill_with_context("code-review", domain="fintech")
        assert "Audit trail required." in result
        assert "Domain context: fintech" in result

    def test_missing_overlay_silently_skipped(self, skills_dir):
        _write_skill(skills_dir, "code-review", self._BASE)
        from skill_loader import load_skill_with_context
        result = load_skill_with_context("code-review", stack="rust", framework="axum", domain="embedded")
        assert "Base content." in result
        assert "Stack context" not in result
        assert "Domain context" not in result


class TestLoadSkillFastPath:
    def test_returns_fast_path_content(self, skills_dir):
        _write_skill(skills_dir, "nfr-check", (
            "---\nname: nfr-check\nfast-path: |\n  Skip if XS task.\n---\n# NFR Check\nBody."
        ))
        from skill_loader import load_skill_fast_path
        result = load_skill_fast_path("nfr-check")
        assert result is not None
        assert "Skip if XS task" in result

    def test_returns_auto_skip_when_no_fast_path(self, skills_dir):
        _write_skill(skills_dir, "research", (
            "---\nname: research\nauto-skip: |\n  Skip if ran within 7 days.\n---\n# Research\nBody."
        ))
        from skill_loader import load_skill_fast_path
        result = load_skill_fast_path("research")
        assert result is not None
        assert "Skip if ran within 7 days" in result

    def test_returns_none_when_no_frontmatter(self, skills_dir):
        _write_skill(skills_dir, "simple", "# Simple Skill\nNo frontmatter here.")
        from skill_loader import load_skill_fast_path
        assert load_skill_fast_path("simple") is None

    def test_returns_none_for_missing_skill(self, skills_dir):
        from skill_loader import load_skill_fast_path
        assert load_skill_fast_path("missing") is None


class TestListSkills:
    def test_lists_skills_with_skill_md(self, skills_dir):
        _write_skill(skills_dir, "code-review", "---\nname: code-review\n---\n# Code Review\nDo it.")
        from skill_loader import list_skills
        skills = list_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "code-review"
        assert skills[0]["has_skill_md"] is True

    def test_flags_dirs_without_skill_md(self, skills_dir):
        (skills_dir / "orphan-dir").mkdir()
        from skill_loader import list_skills
        skills = list_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "orphan-dir"
        assert skills[0]["has_skill_md"] is False

    def test_returns_empty_when_no_skills_dir(self, tmp_path, monkeypatch):
        import skill_loader
        monkeypatch.setattr(skill_loader, "SKILLS_DIR", tmp_path / "nonexistent")
        from skill_loader import list_skills
        assert list_skills() == []

    def test_size_bytes_populated(self, skills_dir):
        _write_skill(skills_dir, "verify", "---\nname: verify\n---\n# Verify\nCheck things.")
        from skill_loader import list_skills
        skills = list_skills()
        assert skills[0]["size_bytes"] > 0

    def test_has_fast_path_detected(self, skills_dir):
        _write_skill(skills_dir, "quick-skill", "---\nname: quick\nfast-path: skip if XS\n---\n# Q\nBody.")
        from skill_loader import list_skills
        skills = list_skills()
        assert skills[0]["has_fast_path"] is True

    def test_multiple_skills_sorted(self, skills_dir):
        _write_skill(skills_dir, "zebra", "# Z")
        _write_skill(skills_dir, "alpha", "# A")
        from skill_loader import list_skills
        names = [s["name"] for s in list_skills()]
        assert names == sorted(names)
