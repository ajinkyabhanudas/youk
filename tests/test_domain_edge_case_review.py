"""Tests for servers/code/src/domain_edge_case_review.py (CIR-164, Phase 3,
final phase).

Real Domain Brief and a real matched candidate, not mocks -- same
real-extraction discipline as test_domain_brief.py and
test_domain_edge_cases.py: builds the brief from this repo's own committed
DECISIONS.md and reuses CIR-163's real Langfuse trace granularity match.
"""

from __future__ import annotations

import re

import pytest

from domain_brief import REPO_ROOT, build_domain_brief
from domain_edge_cases import find_domain_edge_case_candidates
from domain_edge_case_review import (
    build_independent_review_request,
    reframe_candidate,
    reframe_candidates,
)

_FIRST_PERSON_RE = re.compile(
    r"\b(I|I'm|I've|I'd|my|mine|me|we|we're|we've|we'd|our|ours|us)\b",
    re.IGNORECASE,
)


def _assert_no_first_person(text: str) -> None:
    hit = _FIRST_PERSON_RE.search(text)
    assert hit is None, f"found first-person self-reference {hit.group(0)!r} in: {text!r}"


@pytest.fixture(scope="module")
def real_brief() -> dict:
    return build_domain_brief(REPO_ROOT).to_dict()


@pytest.fixture(scope="module")
def real_langfuse_candidate(real_brief) -> dict:
    """The real CIR-163 match: a task mentioning Langfuse trace terms
    surfaces the real 'One trace per run' invariant."""
    task = "Add a new Langfuse trace field to capture retry latency across repairs."
    candidates = find_domain_edge_case_candidates(task, real_brief)
    hit = next(c for c in candidates if c["bounded_context"] == "Langfuse trace granularity")
    return hit


class TestReframeCandidateIsExternalPrecedentLanguage:
    def test_framed_claim_uses_third_person_precedent_language(self, real_langfuse_candidate):
        framed = reframe_candidate(real_langfuse_candidate)
        assert framed["framed_claim"].startswith("A prior review of a similar codebase flagged:")

    def test_framed_claim_contains_the_real_unaltered_invariant_text(self, real_langfuse_candidate):
        framed = reframe_candidate(real_langfuse_candidate)
        assert "One trace per run" in framed["framed_claim"]
        assert real_langfuse_candidate["invariant"] in framed["framed_claim"]

    def test_framed_claim_has_no_first_person_self_reference(self, real_langfuse_candidate):
        framed = reframe_candidate(real_langfuse_candidate)
        _assert_no_first_person(framed["framed_claim"])

    def test_source_file_and_source_id_survive_unchanged(self, real_langfuse_candidate):
        framed = reframe_candidate(real_langfuse_candidate)
        assert framed["source_file"] == real_langfuse_candidate["source_file"]
        assert framed["source_file"] == "DECISIONS.md"
        assert framed["source_id"] == real_langfuse_candidate["source_id"]
        assert framed["source_id"] == "2026-08-27 [Langfuse trace granularity]"

    def test_original_candidate_dict_is_not_mutated(self, real_langfuse_candidate):
        reframe_candidate(real_langfuse_candidate)
        assert "framed_claim" not in real_langfuse_candidate

    def test_reframe_candidates_preserves_order_and_count(self, real_brief):
        task = "Langfuse trace granularity data handling Proxy score definition"
        candidates = find_domain_edge_case_candidates(task, real_brief)
        reframed = reframe_candidates(candidates)
        assert len(reframed) == len(candidates)
        assert [r["source_id"] for r in reframed] == [c["source_id"] for c in candidates]

    def test_empty_candidate_list_reframes_to_empty_list(self):
        assert reframe_candidates([]) == []


class TestIndependentReviewRequestIsSelfContained:
    def test_request_contains_the_task_and_the_reframed_precedent(
        self, real_brief, real_langfuse_candidate
    ):
        task = "Add a new Langfuse trace field to capture retry latency across repairs."
        reframed = reframe_candidates([real_langfuse_candidate])
        request = build_independent_review_request(task, reframed, real_brief)

        assert request["task"] == task
        assert len(request["precedents"]) == 1
        precedent = request["precedents"][0]
        assert precedent["claim"].startswith("A prior review of a similar codebase flagged:")
        assert "One trace per run" in precedent["claim"]
        assert precedent["source_file"] == "DECISIONS.md"
        assert precedent["source_id"] == "2026-08-27 [Langfuse trace granularity]"
        assert precedent["bounded_context"] == "Langfuse trace granularity"

    def test_request_has_no_first_person_self_reference_anywhere(
        self, real_brief, real_langfuse_candidate
    ):
        task = "Add a new Langfuse trace field to capture retry latency across repairs."
        reframed = reframe_candidates([real_langfuse_candidate])
        request = build_independent_review_request(task, reframed, real_brief)

        _assert_no_first_person(request["review_instructions"])
        for precedent in request["precedents"]:
            _assert_no_first_person(precedent["claim"])

    def test_request_has_no_session_specific_metadata(self, real_brief, real_langfuse_candidate):
        """Self-contained means no run id, no timestamp, no mention of how
        or when the candidates were generated -- just task, precedents,
        project context, and instructions."""
        task = "Add a new Langfuse trace field to capture retry latency across repairs."
        reframed = reframe_candidates([real_langfuse_candidate])
        request = build_independent_review_request(task, reframed, real_brief)

        assert set(request.keys()) == {
            "task",
            "precedents",
            "project_context",
            "review_instructions",
        }
        for forbidden in ("run_id", "session", "timestamp", "generated_at"):
            assert forbidden not in request
            assert forbidden not in request["project_context"]

    def test_request_pulls_only_non_goals_and_boundaries_from_the_brief(
        self, real_brief, real_langfuse_candidate
    ):
        reframed = reframe_candidates([real_langfuse_candidate])
        request = build_independent_review_request("some task", reframed, real_brief)

        assert set(request["project_context"].keys()) == {
            "explicit_non_goals",
            "known_boundaries",
        }
        assert "bounded_contexts" not in request["project_context"]

    def test_empty_candidates_produce_a_well_formed_request_with_no_precedents(self, real_brief):
        request = build_independent_review_request("unrelated task", [], real_brief)
        assert request["precedents"] == []
        assert request["task"] == "unrelated task"

    def test_passing_unreframed_candidates_still_produces_a_claim_field(
        self, real_langfuse_candidate, real_brief
    ):
        """build_independent_review_request falls back to the raw invariant
        if a caller packages candidates that were never reframed -- it
        still produces a structurally valid request, just not a bias-
        resistant one, which is why the documented integration path is
        reframe first, then package."""
        request = build_independent_review_request(
            "some task", [real_langfuse_candidate], real_brief
        )
        assert request["precedents"][0]["claim"] == real_langfuse_candidate["invariant"]
