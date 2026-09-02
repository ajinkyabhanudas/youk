"""
Experiment-gap detector — Phase 3 of the reaction-classifier plan
(~/.claude/plans/zany-squishing-crayon.md).

Walks a fixed list of known decision points in youk's own routing code — each
one a real behavioral fork with zero instrumentation on which branch actually
fires or what happens after — and proposes an experiment for each, never
deploys one. Reuses the existing proposal governance exactly as-is:
change_type="EXPERIMENT_PROPOSAL" always sets review_required=True, so
apply_proposal blocks it without review_required_override=True regardless of
any safe_types allowlist an autonomous caller passes (Tier 1, see
health.py:3517-3522 for the trust-tier rationale). No new plumbing — this is
the same two-tier trust split Track A skill generation already uses,
pointed at a new change_type.

Deliberately not a generic regex scanner over source: the plan's own research
identified these 4 candidates by hand as the highest-value gaps, and a
generic "find any inert branch" detector is exactly the kind of premature
infrastructure the plan already declined to build once (see Phase 2's
explicit non-goal). This module's job is narrower and safer: hold the 4
known candidates, generate one proposal per candidate exactly once
(idempotent via a stable proposal id), never more.
"""
from __future__ import annotations

from datetime import datetime, UTC

EXPERIMENT_GAP_CANDIDATES: list[dict] = [
    {
        "key": "medium-translation-risk",
        "name": "medium-translation-risk soft block",
        "citation": "route_task soft rule, rule_id='medium-translation-risk'",
        "risk": (
            "The soft-rule warning surfaces once per task and the developer's response "
            "(proceed / redirect / ignore) is never recorded — youk cannot tell whether "
            "this warning changes behavior or is routine noise the developer has learned "
            "to skip past."
        ),
        "metric": "developer response to the warning (proceed / redirect), joined against whether a later finding matched the flagged risk",
        "guardrail": "surfacing the warning itself must not be suppressed or delayed by adding instrumentation",
    },
    {
        "key": "ceremony-sequencer-ordering",
        "name": "ceremony_sequencer step ordering",
        "citation": "servers/shared/ceremony_sequencer.py",
        "risk": (
            "The gate order (contract -> plan -> challenge -> nfr_check -> dev-loop) is "
            "fixed and enforced, but nothing measures whether reordering would change "
            "outcomes — the order was chosen once and never revisited with data."
        ),
        "metric": "gate-skip attempts and challenge-round count, correlated with position in the fixed sequence",
        "guardrail": "the enforced order itself must not be altered by adding instrumentation — this proposes measurement, not a reorder",
    },
    {
        "key": "coverage-tree-adversary-threshold",
        "name": "coverage_tree adversary-spawn threshold",
        "citation": "must_spawn_adversary(...) in coverage_tree.py",
        "risk": (
            "The threshold that decides whether an adversary subagent gets spawned is a "
            "fixed constant — no data exists on whether tasks just below the threshold "
            "would have benefited from adversary review, or whether tasks just above it "
            "found the spawn unnecessary."
        ),
        "metric": "finding count and severity for tasks near the threshold, split by whether the adversary spawned",
        "guardrail": "the threshold itself must not move as a side effect of adding instrumentation",
    },
    {
        "key": "nfr-autonomy-mode-branch",
        "name": "run_nfr_check size-mode branching",
        "citation": "nfr_autonomy_mode computed in session.py, not yet read by nfr.py",
        "risk": (
            "nfr_autonomy_mode ('standard' vs 'validate') is already computed and handed "
            "to the session but nfr.py never branches on it — a currently inert decision "
            "point. This is also Phase 2's candidate pilot skill: flagging it here as a "
            "gap keeps the detector's list complete even though Phase 2 addresses it "
            "directly rather than waiting on this proposal's disposition."
        ),
        "metric": "same signal Phase 2 wires: nfr-check behavior compared control vs treatment by nfr_autonomy_mode",
        "guardrail": "flagged here as a gap, not a duplicate build — see Phase 2 for the actual pilot wiring",
    },
]


def _proposal_id(key: str) -> str:
    return f"EXPGAP-{key}"


def _render_proposal_content(candidate: dict) -> str:
    return (
        f"EXPERIMENT PROPOSAL: {candidate['name']}\n"
        f"Decision point: {candidate['citation']}\n\n"
        f"Risk: {candidate['risk']}\n\n"
        f"Candidate metric: {candidate['metric']}\n"
        f"Guardrail: {candidate['guardrail']}\n\n"
        f"Disposition required: -> IN-SCOPE | DEFER | ACCEPT-RISK | N/A"
    )


def detect_experiment_gaps(existing_proposal_ids: set[str] | None = None) -> list[dict]:
    """Build one Proposal per known gap candidate, skipping any already proposed.

    existing_proposal_ids: ids already present in the proposals store (caller loads
    these — this module has no DB access of its own, matching failure_pattern_detector's
    read-only, side-effect-free shape). Idempotency also holds at the storage layer
    (INSERT OR IGNORE keyed by proposal id), so a duplicate call is harmless even if
    this check is skipped or stale.

    Returns a list of {candidate_key, proposal_id, status} — status is "added" or
    "already_proposed". Does not write anything itself; the caller (an MCP tool with
    DB access) persists the proposals it returns.
    """
    existing = existing_proposal_ids or set()
    results: list[dict] = []
    for candidate in EXPERIMENT_GAP_CANDIDATES:
        proposal_id = _proposal_id(candidate["key"])
        if proposal_id in existing:
            results.append({
                "candidate_key": candidate["key"],
                "proposal_id": proposal_id,
                "status": "already_proposed",
            })
            continue
        results.append({
            "candidate_key": candidate["key"],
            "proposal_id": proposal_id,
            "status": "added",
            "title": f"Experiment gap: {candidate['name']}",
            "rationale": candidate["risk"],
            "target": candidate["citation"],
            "content": _render_proposal_content(candidate),
            "proposed_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        })
    return results
