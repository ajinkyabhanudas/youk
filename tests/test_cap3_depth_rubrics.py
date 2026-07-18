"""Tests for CAP-3: autonomy depth rubrics.

Structural drift sentinels — assert that the Depth Rubric section is present
in each skill file with all four level tokens (SURFACE/WORKING/DEEP/ELITE).

These tests fail if the rubric is accidentally deleted or renamed, ensuring
the depth rubric language remains stable and parseable by session_end callers.
"""
from __future__ import annotations
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"
_LEVEL_TOKENS = {"SURFACE", "WORKING", "DEEP", "ELITE"}
_RUBRIC_HEADER = "## Autonomy Depth Rubric"


def _assert_rubric(skill_name: str) -> None:
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_file.exists(), f"{skill_name}/SKILL.md not found"
    content = skill_file.read_text()
    assert _RUBRIC_HEADER in content, (
        f"{skill_name}/SKILL.md missing '## Autonomy Depth Rubric' section"
    )
    for level in _LEVEL_TOKENS:
        assert level in content, (
            f"{skill_name}/SKILL.md Depth Rubric missing level token '{level}'"
        )


class TestDepthRubricPresence:
    def test_nfr_check_has_depth_rubric(self):
        """nfr-check/SKILL.md contains ## Autonomy Depth Rubric with all four levels."""
        _assert_rubric("nfr-check")

    def test_challenge_has_depth_rubric(self):
        """challenge/SKILL.md contains ## Autonomy Depth Rubric with all four levels."""
        _assert_rubric("challenge")

    def test_adversary_loop_has_depth_rubric(self):
        """adversary-loop/SKILL.md contains ## Autonomy Depth Rubric with all four levels."""
        _assert_rubric("adversary-loop")

    def test_done_skill_elicits_autonomy_depth(self):
        """done/SKILL.md growth-loop sweep references autonomy_depth and DEEP/ELITE levels."""
        done_file = Path(__file__).parent.parent.parent / "skills" / "done" / "SKILL.md"
        # done skill lives in userSettings, not in the repo's skills/
        # Check the userSettings path if repo path doesn't exist
        if not done_file.exists():
            done_file = Path.home() / ".claude" / "skills" / "done" / "SKILL.md"
        assert done_file.exists(), "done/SKILL.md not found"
        content = done_file.read_text()
        assert "autonomy_depth" in content
        assert "DEEP" in content
        assert "ELITE" in content
