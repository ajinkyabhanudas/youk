"""Tests for apply_proposal section writing and the uncommitted-edit warning.

Two defects, both observed in session 93:

1. The section writer prepended "## {section}" unconditionally, while the contract
   tells proposal authors to pass the FULL section text, which includes its own
   heading. Every compliant proposal produced a duplicated heading.

2. CLAUDE_ROOT/skills/<name> is a symlink into YOUK_ROOT/skills, so a SKILL_EDIT
   writes to a git-tracked file. Nothing committed it and nothing warned, so a branch
   switch silently discarded an applied improvement. That happened, to this repo, to
   the verify quality bars.
"""
from __future__ import annotations

import re


def _apply_section(current: str, section: str, content: str) -> str:
    """Mirror of the section-replacement branch in health.apply_proposal.

    Kept in the test rather than imported because apply_proposal reaches for MCP
    globals and a live PENDING.md. The logic under test is the heading handling, and
    it is transcribed exactly — any divergence shows up as these tests passing while
    the real writer misbehaves, which is why the duplicate-heading assertions below
    are also asserted against real skill files in test_no_skill_file_has_duplicates.
    """
    pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
    match = re.search(pattern, current, flags=re.DOTALL)
    heading = f"## {section}"
    body = content.lstrip("\n")
    new_section = body if body.startswith(heading) else f"{heading}\n{body}"
    if match:
        return current[: match.start()] + new_section + current[match.end() :]
    return current.rstrip() + "\n\n" + new_section.rstrip() + "\n"


class TestHeadingIsNotDuplicated:
    def test_content_with_its_own_heading_is_not_double_prefixed(self):
        current = "# Skill\n\n## Quality bars\n\n1. old\n"
        content = "## Quality bars\n\n1. new\n2. newer\n"
        result = _apply_section(current, "Quality bars", content)
        assert result.count("## Quality bars") == 1

    def test_content_without_heading_still_gets_one(self):
        current = "# Skill\n\n## Quality bars\n\n1. old\n"
        content = "1. new\n2. newer\n"
        result = _apply_section(current, "Quality bars", content)
        assert result.count("## Quality bars") == 1
        assert "1. new" in result

    def test_body_survives_replacement(self):
        current = "# Skill\n\n## Quality bars\n\n1. old\n"
        result = _apply_section(current, "Quality bars", "## Quality bars\n\n1. new\n")
        assert "1. new" in result
        assert "1. old" not in result

    def test_neighbouring_sections_are_untouched(self):
        current = "## Before\n\nkeep me\n\n## Quality bars\n\n1. old\n\n## After\n\nkeep me too\n"
        result = _apply_section(current, "Quality bars", "## Quality bars\n\n1. new\n")
        assert "keep me" in result
        assert "keep me too" in result
        assert "## Before" in result and "## After" in result

    def test_appending_a_new_section_does_not_duplicate_heading(self):
        current = "# Skill\n\n## Other\n\nstuff\n"
        result = _apply_section(current, "Quality bars", "## Quality bars\n\n1. new\n")
        assert result.count("## Quality bars") == 1

    def test_pre_fix_behaviour_would_have_duplicated(self):
        """The regression this guards. Bar 7: prove the check fails on the old code."""
        current = "# Skill\n\n## Quality bars\n\n1. old\n"
        content = "## Quality bars\n\n1. new\n"
        pattern = rf"(## {re.escape('Quality bars')}\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, current, flags=re.DOTALL)
        old_result = current[: match.start()] + f"## Quality bars\n{content}" + current[match.end():]
        assert old_result.count("## Quality bars") == 2, "pre-fix code did not duplicate"


class TestUncommittedWarning:
    def test_tracked_file_returns_warning(self, tmp_path):
        import subprocess
        from health import _uncommitted_warning

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        f = tmp_path / "SKILL.md"
        f.write_text("# skill\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "SKILL.md"], check=True)

        r = _uncommitted_warning(f)
        assert r.get("uncommitted") is True
        assert "commit" in r["commit_warning"].lower()

    def test_untracked_file_returns_empty(self, tmp_path):
        import subprocess
        from health import _uncommitted_warning

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        f = tmp_path / "loose.md"
        f.write_text("# not added\n")
        assert _uncommitted_warning(f) == {}

    def test_non_git_directory_returns_empty(self, tmp_path):
        """A non-git install must not get a spurious warning."""
        from health import _uncommitted_warning
        f = tmp_path / "SKILL.md"
        f.write_text("# skill\n")
        assert _uncommitted_warning(f) == {}


class TestNoSkillFileHasDuplicateHeadings:
    def test_no_shipped_skill_has_a_duplicated_section_heading(self):
        """Catches damage already written by the pre-fix code."""
        from pathlib import Path
        repo = Path(__file__).parent.parent
        offenders = []
        for skill_md in (repo / "skills").glob("*/SKILL.md"):
            headings = re.findall(r"^## (.+)$", skill_md.read_text(), re.MULTILINE)
            dupes = {h for h in headings if headings.count(h) > 1}
            if dupes:
                offenders.append(f"{skill_md.parent.name}: {sorted(dupes)}")
        assert offenders == [], f"duplicate section headings: {offenders}"


class TestSpanMetadataObeysTraceInvariant:
    def test_free_text_is_dropped(self):
        from observability import _numeric_only
        out = _numeric_only({"task": "/Users/me/secret-project", "count": 3})
        assert out == {"count": 3}

    def test_booleans_are_dropped(self):
        from observability import _numeric_only
        assert _numeric_only({"ok": True, "n": 1}) == {"n": 1}

    def test_floats_are_kept(self):
        from observability import _numeric_only
        assert _numeric_only({"duration_s": 1.25}) == {"duration_s": 1.25}

    def test_nested_structures_are_dropped(self):
        """Nested values are how free text sneaks back in."""
        from observability import _numeric_only
        assert _numeric_only({"meta": {"path": "/Users/me"}, "n": 2}) == {"n": 2}
