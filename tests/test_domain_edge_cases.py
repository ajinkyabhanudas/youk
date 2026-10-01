"""Tests for servers/code/src/domain_edge_cases.py (CIR-163, Phase 2).

Real Domain Brief, not a mock: built via domain_brief.build_domain_brief
against this repo's own actual, committed DECISIONS.md -- same real-
extraction discipline as test_domain_brief.py. knowledge/projects/youk/
decisions.md is instance-local and gitignored (absent in this checkout and
in CI, per test_domain_brief.py's own documented reason), so the real brief
built here has exactly the 3 DECISIONS.md-derived bounded contexts. The
CIR-163 ticket's cited 12/13/9 counts are from one developer's local
~/.claude/youk instance (which also has the gitignored ADR log); this test
asserts against what a real pytest run in this repo can honestly produce.
"""

from __future__ import annotations

import json

import pytest

from domain_brief import REPO_ROOT, build_domain_brief
from domain_edge_cases import (
    domain_edge_case_candidates,
    find_domain_edge_case_candidates,
    load_domain_brief,
)


@pytest.fixture(scope="module")
def real_brief() -> dict:
    """The real Domain Brief for this repo, built fresh from the actual
    committed DECISIONS.md -- not synthetic data."""
    return build_domain_brief(REPO_ROOT).to_dict()


def test_fixture_contains_the_real_langfuse_trace_granularity_context(real_brief):
    """Sanity check the fixture itself is real before testing against it."""
    names = {c["name"] for c in real_brief["bounded_contexts"]}
    assert "Langfuse trace granularity" in names


class TestGenuineMatchSurfacesTheRealInvariant:
    def test_task_matching_langfuse_trace_terms_surfaces_the_real_invariant(self, real_brief):
        task = "Add a new Langfuse trace field to capture retry latency across repairs."
        candidates = find_domain_edge_case_candidates(task, real_brief)

        assert candidates, "expected a real match against 'Langfuse trace granularity'"
        hit = next(c for c in candidates if c["bounded_context"] == "Langfuse trace granularity")
        assert "One trace per run" in hit["invariant"]
        assert hit["source_file"] == "DECISIONS.md"
        assert hit["source_id"] == "2026-08-27 [Langfuse trace granularity]"
        assert "langfuse" in hit["matched_terms"]
        assert "trace" in hit["matched_terms"]
        assert hit["relevance_score"] == len(hit["matched_terms"])

    def test_unrelated_task_returns_no_candidates(self, real_brief):
        """No real invariant is relevant here -- the result must be empty,
        not a forced match."""
        task = "Refactor the color palette used in the onboarding email template."
        candidates = find_domain_edge_case_candidates(task, real_brief)
        assert candidates == []

    def test_top_n_caps_the_candidate_count(self, real_brief):
        task = "Langfuse trace granularity data handling Proxy score definition"
        candidates = find_domain_edge_case_candidates(task, real_brief, top_n=1)
        assert len(candidates) == 1


class TestLoadDomainBriefNeverFabricates:
    def test_missing_file_returns_none(self, tmp_path):
        assert load_domain_brief(tmp_path) is None

    def test_candidates_are_empty_without_a_brief_on_disk(self, tmp_path):
        assert domain_edge_case_candidates("do the thing", youk_root=tmp_path) == []

    def test_malformed_file_returns_none_not_a_crash(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "domain-brief.json").write_text("not valid json {{{")
        assert load_domain_brief(tmp_path) is None

    def test_real_brief_written_to_disk_round_trips(self, tmp_path, real_brief):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "domain-brief.json").write_text(json.dumps(real_brief))

        task = "Add a new Langfuse trace field to capture retry latency."
        candidates = domain_edge_case_candidates(task, youk_root=tmp_path)

        assert candidates
        assert candidates[0]["bounded_context"] == "Langfuse trace granularity"
