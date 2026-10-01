"""Tests for servers/code/src/domain_edge_cases.py (CIR-163, Phase 2 of 4).

Runs against the real, committed state/domain-brief.json on this repo -- not a mock
or a synthetic fixture -- so a passing test is proof the filter works against actual
project data, same discipline as test_domain_brief.py's real-DECISIONS.md tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain_brief import REPO_ROOT
from domain_edge_cases import load_domain_brief, surface_domain_edge_cases
from nfr import nfr_check_full, nfr_check_quick
from models import TaskSize


@pytest.fixture(autouse=True)
def _real_skills_dir(monkeypatch):
    """nfr.py loads the real nfr-check/SKILL.md by name; point skill_loader at
    this checkout's actual skills/ directory rather than the production /claude
    mount these tests don't have (same fixture as test_nfr_autonomy_mode.py)."""
    import skill_loader

    repo_skills = Path(__file__).parent.parent / "skills"
    monkeypatch.setattr(skill_loader, "SKILLS_DIR", repo_skills)


@pytest.fixture(autouse=True)
def _real_youk_root_for_nfr(monkeypatch):
    """Point nfr.py's YOUK_ROOT at this actual checkout so nfr_check_quick/full
    read the real, committed state/domain-brief.json instead of the production
    /youk mount these tests don't have."""
    import nfr

    monkeypatch.setattr(nfr, "YOUK_ROOT", REPO_ROOT)


def test_real_match_surfaces_the_real_invariant():
    """A task that genuinely touches a real bounded context's ubiquitous language
    ("Langfuse" + "trace") must surface that context's real, quoted invariant."""
    task = "Add a new Langfuse trace span for the repair phase"
    candidates = surface_domain_edge_cases(task, root=REPO_ROOT)

    assert candidates, "expected at least one real domain-specific candidate"
    bc_names = {c["bounded_context"] for c in candidates}
    assert "Langfuse trace granularity" in bc_names

    match = next(c for c in candidates if c["bounded_context"] == "Langfuse trace granularity")
    assert "One trace per run" in match["question"]
    assert match["source_file"] == "DECISIONS.md"
    assert match["source_id"] == "2026-08-27 [Langfuse trace granularity]"
    assert set(match["matched_terms"]) <= {"Langfuse", "trace"}
    assert match["matched_terms"]


def test_real_non_match_surfaces_nothing():
    """A task with no real overlap against any bounded context's name or
    ubiquitous language must return an empty list -- never a forced match."""
    task = "Update the onboarding email copy for new users"
    candidates = surface_domain_edge_cases(task, root=REPO_ROOT)
    assert candidates == []


def test_missing_domain_brief_returns_empty_not_error(tmp_path):
    assert load_domain_brief(tmp_path) is None
    assert surface_domain_edge_cases("anything", root=tmp_path) == []


def test_results_capped_at_top_n():
    task = "Langfuse trace granularity data handling event compaction"
    candidates = surface_domain_edge_cases(task, root=REPO_ROOT, top_n=2)
    assert len(candidates) <= 2


def test_results_ranked_by_match_strength():
    """A task matching a bounded context by name AND ubiquitous language terms
    must rank at or above one matching only a single term."""
    task = "Langfuse trace granularity work, plus unrelated youk config"
    candidates = surface_domain_edge_cases(task, root=REPO_ROOT)
    assert candidates
    assert candidates[0]["score"] >= candidates[-1]["score"]


def test_nfr_check_quick_wires_in_real_domain_candidates_distinct_from_generic():
    result = nfr_check_quick("Add a new Langfuse trace span for the repair phase")
    candidates = result["domain_edge_case_candidates"]
    assert candidates, "expected a real domain match wired through nfr_check_quick"
    assert candidates[0]["bounded_context"] == "Langfuse trace granularity"
    assert "domain_edge_case_instruction" in result
    assert candidates != result["functional_edge_case_questions"]


def test_nfr_check_full_wires_in_real_domain_candidates_distinct_from_generic():
    result = nfr_check_full("Add a new Langfuse trace span for the repair phase", TaskSize.L)
    candidates = result["domain_edge_case_candidates"]
    assert candidates, "expected a real domain match wired through nfr_check_full"
    assert candidates[0]["bounded_context"] == "Langfuse trace granularity"
    assert "domain_edge_case_instruction" in result
    assert candidates != result["functional_edge_case_questions"]


def test_nfr_check_quick_empty_when_task_matches_nothing():
    result = nfr_check_quick("Update the onboarding email copy for new users")
    assert result["domain_edge_case_candidates"] == []
