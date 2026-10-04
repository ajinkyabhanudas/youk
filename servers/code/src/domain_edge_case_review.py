"""
Bias-resistant review packaging for domain-aware edge cases (CIR-164,
Phase 3 of 4 -- final phase).

Phase 2 (domain_edge_cases.py) surfaces candidate invariants that might be
relevant to a task, filtered against a project's real Domain Brief. Left
alone, those candidates would be reviewed by the same session that
elicited them -- generator and checker sharing the same context, and
therefore the same blind spots.

The cited 2026 finding (the Self-Correction Illusion, arXiv 2606.05976) is
specific: relabeling an identical claim as coming from an external role
raised the explicit-error-flagging rate by 23-93 percentage points across 13
model-domain cells. It measures flagging, not final accuracy, and attributes
the effect to chat-template role labeling rather than shared training data. This module does not hide that the
candidates came from this project -- the source_file/source_id stay real
and traceable throughout. It changes only the FRAMING (first-person
"I found this" versus third-person "a prior review flagged this"), and
only the STRUCTURE handed to a reviewer (a self-contained request with no
reference to the eliciting session's own reasoning), because framing is the lever the Self-Correction Illusion paper measured
and structural isolation (a fresh session) is the lever Cross-Context Review,
arXiv 2603.12123, measured (F1 28.6% vs 21.7% for a same-session second
review; a modest gain). Never the facts.

Two real, separately testable functions, not one:

  - reframe_candidate / reframe_candidates (Part A): rewrite each
    candidate's claim in third-person, external-precedent language. The
    real invariant statement and its source_file/source_id are carried
    through unchanged -- only a new `framed_claim` field is added.

  - build_independent_review_request (Part B): package reframed
    candidates + task + the parts of the Domain Brief a reviewer needs
    (never the whole brief verbatim -- see its docstring) into a single
    self-contained dict with no reference to prior reasoning, no
    session-specific metadata (no timestamps, no run ids, no mention of
    how or when the candidates were generated). Deliberately just a data
    structure: actually dispatching it to a separate review session is an
    orchestration-layer decision for whoever calls this module.
"""

from __future__ import annotations

_EXTERNAL_PRECEDENT_TEMPLATE = "A prior review of a similar codebase flagged: {invariant}"

_REVIEW_INSTRUCTIONS = (
    "Each precedent below was flagged by a prior review of a similar codebase, "
    "independent of this task. For every precedent, decide whether the task "
    "description risks violating it. A precedent with no real bearing on the "
    "task should be dismissed explicitly, not silently carried forward. "
    "Base each verdict only on the cited source, not on assumed context."
)


def reframe_candidate(candidate: dict) -> dict:
    """
    Reframes one Phase 2 candidate dict in third-person, external-precedent
    language. Returns a new dict (never mutates the input) with every
    original key preserved -- source_file, source_id, bounded_context,
    matched_terms, relevance_score, invariant all stay real and unchanged
    -- plus one new key:

      - framed_claim: the same invariant statement, reframed as something
        "a prior review of a similar codebase flagged", not something this
        session "found". The cited finding is about framing, not facts, so
        the invariant text itself is never altered or reworded.
    """
    return {
        **candidate,
        "framed_claim": _EXTERNAL_PRECEDENT_TEMPLATE.format(invariant=candidate["invariant"]),
    }


def reframe_candidates(candidates: list[dict]) -> list[dict]:
    """Applies reframe_candidate to a full Phase 2 candidate list, preserving
    order (already ranked by relevance_score by find_domain_edge_case_candidates)."""
    return [reframe_candidate(c) for c in candidates]


def build_independent_review_request(task: str, candidates: list[dict], brief: dict) -> dict:
    """
    Packages a task + its (already reframed) domain edge-case candidates +
    the parts of the Domain Brief a reviewer actually needs into one
    self-contained dict -- consumable by a review with zero memory of this
    session, zero knowledge of how the candidates were generated.

    `candidates` is expected to already be reframe_candidates(...)'s output
    (this function does not call reframe_candidates itself, so a caller
    who wants the unreframed candidates in the package -- e.g. for a
    secondary audit path -- can still build one; the default integration
    path is reframe first, then package).

    Self-containment means no run id, no timestamp, no mention of this
    module or of Phase 2's matching logic, and no first-person language in
    any value this function writes itself -- only the real, traceable
    source_file/source_id/invariant data and the task text travel through.
    Only explicit_non_goals and known_boundaries are pulled from the brief
    (never the full bounded_contexts list) because those two are the parts
    a reviewer needs to judge a candidate's relevance without also needing
    the entire elicitation machinery that produced it.
    """
    return {
        "task": task,
        "precedents": [
            {
                "claim": c.get("framed_claim", c["invariant"]),
                "bounded_context": c["bounded_context"],
                "source_file": c["source_file"],
                "source_id": c["source_id"],
                "matched_terms": c["matched_terms"],
            }
            for c in candidates
        ],
        "project_context": {
            "explicit_non_goals": [n["statement"] for n in brief.get("explicit_non_goals", [])],
            "known_boundaries": [b["statement"] for b in brief.get("known_boundaries", [])],
        },
        "review_instructions": _REVIEW_INSTRUCTIONS,
    }
