"""Tests for CAP-6: adversarial-planning skill transplant.

Covers:
  - Routing resolution: adversarial_planning appears in routes.yaml XL skills
  - Registry format: SKILL-REGISTRY.md has a row matching expected format
  - Start skill structural: founding analysis offer text present in start/SKILL.md
"""
from __future__ import annotations
from pathlib import Path
import yaml

YOUK_ROOT = Path(__file__).parent.parent
SKILLS_DIR = YOUK_ROOT / "skills"
CONFIG_DIR = YOUK_ROOT / "config"


class TestRoutingResolution:
    def test_adversarial_planning_in_xl_skills(self):
        """adversarial_planning is listed in routes.yaml XL skills list."""
        routes_file = CONFIG_DIR / "routes.yaml"
        assert routes_file.exists(), "config/routes.yaml not found"
        data = yaml.safe_load(routes_file.read_text())
        xl_skills = data["task_sizes"]["XL"]["skills"]
        assert "adversarial_planning" in xl_skills, (
            f"adversarial_planning not in XL skills: {xl_skills}"
        )

    def test_adversarial_planning_signals_present(self):
        """routes.yaml XL signals include the required adversarial-planning triggers."""
        routes_file = CONFIG_DIR / "routes.yaml"
        data = yaml.safe_load(routes_file.read_text())
        xl_signals = data["task_sizes"]["XL"]["signals"]
        required = {"audit", "red-team", "founding analysis"}
        missing = required - set(xl_signals)
        assert not missing, f"XL signals missing: {missing}"

    def test_adversarial_planning_skill_file_exists(self):
        """skills/adversarial-planning/SKILL.md exists and is non-empty."""
        skill_file = SKILLS_DIR / "adversarial-planning" / "SKILL.md"
        assert skill_file.exists(), "skills/adversarial-planning/SKILL.md not found"
        assert skill_file.stat().st_size > 1000, "SKILL.md is suspiciously small"

    def test_adversarial_planning_reference_files_present(self):
        """All four reference files are present in the skill folder."""
        refs_dir = SKILLS_DIR / "adversarial-planning" / "references"
        required = {"frames.md", "convergence.md", "templates.md", "evidence.md"}
        present = {f.name for f in refs_dir.iterdir() if f.is_file()}
        missing = required - present
        assert not missing, f"Reference files missing: {missing}"


class TestRegistryFormat:
    def test_adversarial_planning_row_in_registry(self):
        """SKILL-REGISTRY.md has a row for /adversarial-planning."""
        registry = SKILLS_DIR / "SKILL-REGISTRY.md"
        assert registry.exists(), "SKILL-REGISTRY.md not found"
        content = registry.read_text()
        assert "adversarial-planning" in content, (
            "adversarial-planning not found in SKILL-REGISTRY.md"
        )

    def test_registry_row_has_status(self):
        """The adversarial-planning row includes ACTIVE status."""
        registry = SKILLS_DIR / "SKILL-REGISTRY.md"
        content = registry.read_text()
        for line in content.splitlines():
            if "adversarial-planning" in line:
                assert "ACTIVE" in line, (
                    f"adversarial-planning row lacks ACTIVE status: {line}"
                )
                break


class TestStartSkillStructural:
    def test_founding_analysis_offer_present(self):
        """start/SKILL.md contains the founding analysis offer text."""
        start_skill = SKILLS_DIR / "start" / "SKILL.md"
        assert start_skill.exists(), "skills/start/SKILL.md not found"
        content = start_skill.read_text()
        assert "founding analysis" in content.lower(), (
            "start/SKILL.md is missing the founding analysis offer"
        )
        assert "adversarial-planning" in content, (
            "start/SKILL.md founding analysis offer must reference adversarial-planning"
        )

    def test_founding_analysis_is_opt_in(self):
        """start/SKILL.md founding analysis offer is opt-in (never auto-invoked)."""
        start_skill = SKILLS_DIR / "start" / "SKILL.md"
        content = start_skill.read_text()
        assert "Opt-in" in content or "opt-in" in content, (
            "Founding analysis offer must be marked as opt-in in start/SKILL.md"
        )
