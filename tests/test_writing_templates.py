"""Writing templates: the layout is chosen by the situation, and the checks stay structural."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import contract_guard as cg
import writing_templates as wt

MSG3 = "adds the guard\n\nthe hook denies eight commands.\n\nthe model had to remember them.\n\nthey cost no tokens now."


class TestCommitLayout:
    def test_body_paragraphs_needed_grow_with_the_change(self):
        assert wt.required_paragraphs(1, 5) == 0
        assert wt.required_paragraphs(2, 20) == 1
        assert wt.required_paragraphs(2, 50) == 2
        assert wt.required_paragraphs(3, 10) == 3
        assert wt.required_paragraphs(1, 120) == 3

    def test_a_tiny_change_may_be_just_a_subject(self):
        assert wt.validate_commit("fix a typo in the readme", files=1, lines=2) == []

    def test_a_large_change_needs_what_why_and_impact(self):
        problems = wt.validate_commit("adds the guard\n\nthe hook denies eight commands.", files=5, lines=200)
        assert len(problems) == 1 and "3 body paragraph" in problems[0]
        assert "what changed, why, the impact" in problems[0]
        assert wt.validate_commit(MSG3, files=5, lines=200) == []

    def test_trailers_and_git_comments_do_not_count_as_paragraphs(self):
        msg = ("adds the guard\n\nthe hook denies eight commands.\n\n"
               "Co-Authored-By: Someone <s@x.com>\n# a git comment")
        assert len(wt.split_commit(msg)[1]) == 1
        assert wt.validate_commit(msg, files=5, lines=200)

    def test_merge_revert_and_fixup_commits_are_exempt(self):
        for subject in ("Merge branch 'x' into main", "Revert \"adds the guard\"", "fixup! adds the guard"):
            assert wt.validate_commit(subject, files=9, lines=999) == []

    def test_a_long_subject_is_flagged(self):
        assert any("subject line" in p for p in wt.validate_commit("x" * 90, files=1, lines=1))

    def test_an_empty_message_is_left_to_git(self):
        assert wt.validate_commit("", files=3, lines=100) == []


class TestStagedSize:
    def test_counts_staged_files_and_lines(self, tmp_path):
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        (tmp_path / "a.txt").write_text("1\n2\n3\n")
        (tmp_path / "b.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        assert wt.staged_size(str(tmp_path)) == (2, 4)

    def test_a_non_repo_is_zero(self, tmp_path):
        assert wt.staged_size(str(tmp_path)) == (0, 0)


class TestPrLayout:
    FULL = ("## What changed\nx\n\n## Why\ny\n\n## Impact\nz\n\n## How it was checked\nw")

    def test_a_complete_body_passes(self):
        assert wt.validate_pr(self.FULL) == []

    def test_missing_sections_are_named(self):
        assert wt.validate_pr("## What changed\nx\n\n## Why\ny") == ["Impact", "How it was checked"]
        assert wt.validate_pr("just a paragraph") == [name for name, _ in wt.PR_SECTIONS]

    def test_common_heading_variants_are_accepted(self):
        body = "### What this adds\na\n\n### Motivation\nb\n\n### Result\nc\n\n### Tests\nd"
        assert wt.validate_pr(body) == []


class TestSituations:
    def test_each_situation_has_its_own_layout(self):
        shown = {s: wt.template_for(s) for s in wt.SITUATIONS}
        assert len(set(shown.values())) == len(wt.SITUATIONS)
        assert "## What changed" in shown["pr"] and "## What changed" not in shown["commit"]
        assert "Chose:" in shown["decision"]
        assert "Answer first" in shown["chat"]

    def test_an_unknown_situation_is_an_error(self):
        with pytest.raises(ValueError):
            wt.template_for("email")


class TestPrGuardRule:
    def _rules(self, command: str, cwd=Path(__file__).parent.parent) -> list[str]:
        return [v.rule for v in cg.evaluate_bash(command, str(cwd))]

    def test_a_pr_body_without_the_layout_is_blocked_and_names_the_gaps(self):
        found = cg.evaluate_bash('gh pr create --title t --body "just some text"', ".")
        assert [v.rule for v in found] == ["pr-structure"]
        assert "What changed" in found[0].message

    def test_a_title_only_edit_is_not_checked_for_layout(self):
        assert self._rules('gh pr edit 5 --title "new title"') == []

    def test_the_layout_rule_can_be_switched_off_on_purpose(self, monkeypatch):
        monkeypatch.setenv("YOUK_GUARD_OFF", "pr-structure")
        assert self._rules('gh pr create --title t --body "just some text"') == []
