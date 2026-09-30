"""Tests for CIR-150 item 1 / CIR-151: proactive functional edge-case derivation.

CIR-150 found nfr-check's Phase 1 CLASSIFY is the one skill that genuinely derives
categories from raw task text before a plan exists — but only for NFR-shaped
categories (caching, retry, auth, idempotency). stress-test's Agent B has the real
functional edge-case lens (empty/null inputs, boundary values, partial failure,
ordering) but only ever runs reactively, against an already-finished plan.

This proves: (1) the question bank lives in exactly one place
(skills/stress-test/references/edge-case-questions.md) and nfr.py reads that same
file rather than a second, driftable copy; (2) nfr_check_quick/nfr_check_full (the
M/L/XL in-session paths, which take raw `task: str` and nothing plan-shaped) surface
those questions proactively, before any plan exists — proven structurally by the
function signature, not just by convention.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models import TaskSize


@pytest.fixture(autouse=True)
def _real_skills_dir(monkeypatch):
    """Point skill_loader at this checkout's real skills/ dir, same pattern as
    test_nfr_autonomy_mode.py — nfr.py loads real SKILL.md/reference content."""
    import skill_loader
    repo_skills = Path(__file__).parent.parent / "skills"
    monkeypatch.setattr(skill_loader, "SKILLS_DIR", repo_skills)


class TestSingleCanonicalQuestionBank:
    def test_loader_returns_the_real_reference_file_content(self):
        from nfr import load_functional_edge_case_questions
        questions = load_functional_edge_case_questions()
        assert len(questions) == 7
        assert any("empty inputs" in q for q in questions)
        assert any("interrupted mid-way" in q for q in questions)

    def test_questions_match_the_stress_test_reference_file_verbatim(self):
        """The list nfr.py returns must be parsed from the SAME file stress-test's
        SKILL.md points Agent B at — not a hardcoded second copy that could drift."""
        import skill_loader
        from nfr import load_functional_edge_case_questions, _parse_markdown_bullets

        raw = skill_loader.load_skill_reference("stress-test", "edge-case-questions.md")
        expected = _parse_markdown_bullets(raw)
        assert load_functional_edge_case_questions() == expected
        assert len(expected) > 0

    def test_stress_test_skill_md_points_at_the_shared_reference_file(self):
        """Agent B's section must reference the shared file, not re-inline the
        list — otherwise the two copies are free to drift apart again."""
        skill_md = (
            Path(__file__).parent.parent / "skills" / "stress-test" / "SKILL.md"
        ).read_text()
        assert "references/edge-case-questions.md" in skill_md

    def test_missing_reference_file_degrades_to_empty_list_not_a_crash(self, monkeypatch):
        import skill_loader
        monkeypatch.setattr(skill_loader, "SKILLS_DIR", Path("/nonexistent-path-xyz"))
        from nfr import load_functional_edge_case_questions
        assert load_functional_edge_case_questions() == []


class TestProactiveDerivationOnMPath:
    def test_quick_path_includes_functional_edge_case_questions(self):
        from nfr import nfr_check_quick
        result = nfr_check_quick("add a bulk CSV import endpoint")
        assert result["functional_edge_case_questions"]
        assert len(result["functional_edge_case_questions"]) == 7
        assert "functional_edge_case_instruction" in result

    def test_instruction_says_before_any_plan(self):
        from nfr import nfr_check_quick
        result = nfr_check_quick("add a bulk CSV import endpoint")
        assert "before drafting any plan" in result["functional_edge_case_instruction"].lower()

    def test_derivation_present_regardless_of_autonomy_mode(self):
        """Autonomy mode changes framing of the 4 core NFR questions, not whether
        functional edge cases get derived — this is a separate, unconditional lens."""
        from nfr import nfr_check_quick
        standard = nfr_check_quick("add a bulk CSV import endpoint", autonomy_mode="standard")
        validate = nfr_check_quick("add a bulk CSV import endpoint", autonomy_mode="validate")
        assert standard["functional_edge_case_questions"] == validate["functional_edge_case_questions"]


class TestProactiveDerivationOnFullPath:
    def test_full_path_includes_functional_edge_case_questions(self):
        from nfr import nfr_check_full
        result = nfr_check_full("migrate the billing schema to support multi-currency", TaskSize.L)
        assert result["functional_edge_case_questions"]
        assert len(result["functional_edge_case_questions"]) == 7

    def test_xl_size_also_included(self):
        from nfr import nfr_check_full
        result = nfr_check_full("rearchitect the notification pipeline", TaskSize.XL)
        assert result["functional_edge_case_questions"]


class TestFastPathUnaffected:
    def test_xs_fast_path_has_no_functional_edge_case_field(self):
        """XS/S is a static 2-question no-reasoning fast path by design — this
        phase intentionally only wires into the in-session M/L/XL paths where the
        model actually reasons with full context."""
        from nfr import nfr_check_fast
        block = nfr_check_fast("fix a typo in the README")
        assert not hasattr(block, "functional_edge_case_questions")


class TestRunNfrCheckDispatchesCorrectly:
    def test_m_size_carries_functional_edge_cases(self):
        from nfr import run_nfr_check
        result = run_nfr_check("add real-time notifications", size_str="M")
        assert result["functional_edge_case_questions"]

    def test_l_size_carries_functional_edge_cases(self):
        from nfr import run_nfr_check
        result = run_nfr_check("rebuild the payments reconciliation job", size_str="L")
        assert result["functional_edge_case_questions"]
