"""youk-core MCP server — session, routing, self-heal."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from session import start_session, end_session, task_checkpoint as _task_checkpoint, update_convergence_state as _update_convergence_state, _record_outcome_followup, enrich_route_result as _enrich_route_result_impl, write_routing_context as _write_routing_context_impl, append_gate_to_active_task as _append_gate_impl
from routing import route_task as _route_task
from health import (
    run_health_check_with_skill_signals,
    add_proposal as _add_proposal,
    apply_proposal as _apply_proposal,
    _load_pending_proposals,
    _build_review_bundle,
)
from guardrails import check_knowledge_write, check_destructive_command, HardRuleViolation
from schemas import (
    OptimizeIntentResult,
    RouteTaskResult,
    TaskContractResult,
    CheckNfrGateResult,
    CheckChallengeGateResult,
)
from nfr_gate import check_nfr_gate as _check_nfr_gate
from challenge_gate import check_challenge_gate as _check_challenge_gate
from ceremony_sequencer import record_gate as _record_gate, check_order as _check_order
from intake_gate import check_intake_gate as _check_intake_gate
from intent import optimize_intent as _optimize_intent
from compaction import build_brief, write_contracts
from tokens import init_token_tracker, record_checkpoint
from session_slug import get_session_slug as _get_session_slug_impl
import state_paths as _sp
from graph import (
    create_task_graph as _create_task_graph,
    set_gate as _set_gate,
    is_unblocked as _is_unblocked,
    next_task as _next_task,
    mark_done as _mark_done,
)
from file_index import (
    index_project as _index_project,
    find_relevant as _find_relevant,
    find_affected as _find_affected,
    find_relations as _find_relations,
    find_related_docs as _find_related_docs,
    find_stale_relations as _find_stale_relations,
    get_index_stats as _get_index_stats,
)
from steering_vocab import (
    record_decomposition as _record_decomposition,
    get_steering as _get_steering,
)
from concept_graph import (
    query_concept_graph as _query_concept_graph,
    get_concept_stats as _get_concept_stats,
)
from revisable_sets import (
    enroll as _rs_enroll,
    learn_add as _rs_learn_add,
    unlearn_prune as _rs_unlearn_prune,
    revert as _rs_revert,
    get_set as _rs_get_set,
    list_enrolled as _rs_list_enrolled,
    EnrollmentError as _EnrollmentError,
)
from revision_detectors import (
    detect_grow_candidates as _detect_grow_candidates,
    detect_prune_candidates as _detect_prune_candidates,
)
from skill_signals import (
    generate_improvement_proposal as _generate_skill_improvement_proposal,
    select_skill_arm as _select_skill_arm,
    record_arm_reward as _record_arm_reward,
    mark_proposal_applied as _mark_proposal_applied,
)

import argparse as _argparse
_p = _argparse.ArgumentParser(add_help=False)
_p.add_argument("--transport", default="stdio")
_p.add_argument("--port", type=int, default=8000)
_p.add_argument("--host", default="0.0.0.0")
_server_args, _ = _p.parse_known_args()

YOUK_ROOT = Path("/youk")
CLAUDE_ROOT = Path("/claude")

_TOOL_CALL_COUNT_FILE = YOUK_ROOT / "state" / "tool-call-count.json"

# Seed the first enrolled judgment-set at server startup (idempotent).
# _SEVEN_CONVERGENCE is the proof-of-concept set for the self-revision meta-loop.
# Other sets are enrolled only when a concrete revision is first proposed (ADR decision).
try:
    _rs_enroll(
        "_SEVEN_CONVERGENCE",
        policy="both",
        initial_elements=[
            "structural", "operational", "experiential",
            "adversarial", "temporal", "outcome", "semantic",
        ],
    )
except Exception:
    # youk: silent enrollment failure → upgrade to structured warning when server gains logging.
    pass


def _get_session_slug() -> str:
    _sp.YOUK_ROOT = YOUK_ROOT
    return _get_session_slug_impl(YOUK_ROOT)


def _increment_tool_call_count() -> int:
    """Increment per-session tool call counter. Returns new count."""
    import json as _json
    count = 0
    if _TOOL_CALL_COUNT_FILE.exists():
        try:
            count = _json.loads(_TOOL_CALL_COUNT_FILE.read_text()).get("count", 0)
        except Exception:
            pass
    count += 1
    _TOOL_CALL_COUNT_FILE.write_text(_json.dumps({"count": count}))
    return count


def _reset_tool_call_count() -> None:
    """Reset counter when compact_context fires."""
    _TOOL_CALL_COUNT_FILE.write_text('{"count": 0}')


def _write_routing_context(task: str, result: dict) -> None:
    """Delegate to session.write_routing_context — lives in session.py for testability."""
    _write_routing_context_impl(task, result, youk_root=YOUK_ROOT)


def _append_gate_to_active_task(gate_name: str) -> None:
    """Delegate to session.append_gate_to_active_task — lives in session.py for testability."""
    _append_gate_impl(gate_name, youk_root=YOUK_ROOT)


mcp = FastMCP(
    "youk-core",
    host=_server_args.host,
    port=_server_args.port,
    instructions=(
        "youk behavioral DNA — always active.\n"
        "1. Reasoning loops exit on zero new objections from ALL angles, not on round count. "
        "Before any verdict: (a) did the last round produce zero new objections? "
        "(b) is any angle unchallenged? Both must be true to exit.\n"
        "2. No filler. No openers. Lead with the answer.\n"
        "3. M+ tasks: challenge → nfr_check → check_nfr_gate → check_challenge_gate → dev-loop. "
        "Never skip. Never reorder."
    ),
)


@mcp.tool()
def session_start(project_dir: str) -> dict:
    """
    Start a youk session. Loads L1/L2/L3 context from the project directory.
    Call this at the beginning of every session — fold the result naturally into
    your first response without announcing 'context loaded'.

    Returns: project, resume_point, context_health, pending_proposals_count,
             session_counter, health_check_due, session_plan, contracts.
    """
    state = start_session(project_dir)
    # Reset token tracker for the new session
    init_token_tracker(session_id=state.project + "-" + str(state.session_counter))
    return state.to_dict()


@mcp.tool()
def session_end(
    summary: str,
    commits_made: bool = False,
    explicit_contracts: list[str] | None = None,
    skills_used: list[str] | None = None,
    close_cluster: bool = False,
    skill_gaps: dict | None = None,
    mid_session_adaptations_applied: int = 0,
    findings: dict | None = None,
    finding_categories: list[str] | None = None,
    nfr_gaps: list[str] | None = None,
    direction_reversal: bool = False,
    developer_caught: list[str] | None = None,
    loop_correction_detected: bool = False,
    loop_gap_detected: bool = False,
    challenge_rounds: int = 0,
    decision_retrospectives: list[dict] | None = None,
    autonomy_depth: dict[str, str] | None = None,
    contract_violations: list[str] | None = None,
    outcome: str = "NONE",
    outcome_result: str = "UNKNOWN",
) -> dict:
    """
    End a youk session. Writes audit log entry, saves contracts, checks session-close cluster.

    summary: Structured summary of what was done — NOT raw conversation transcript.
    Must not contain 'Human:', 'Assistant:', or other transcript markers.

    commits_made: True if any git commits were made this session.

    explicit_contracts: Working agreements from this session to preserve verbatim.
    Extract these from the conversation before calling — e.g. commit format rules,
    test cadence, review requirements. Written to contracts.md so compact_context
    can pin them in future sessions. Phrase-detection runs automatically on the
    summary, but explicit_contracts takes priority.

    skills_used: List of skill names invoked this session (e.g. ["nfr_check", "dev-loop"]).
    Written as a structured line in the audit log so future sessions can detect
    which skills were consistently used or skipped.

    close_cluster: True if context-sync + learn + humanize were completed this session.
    Written as CloseCluster: yes/no in the audit log. The next session_start reads this
    to set close_cluster_missed — which surfaces as a session_plan item if False.

    skill_gaps: Optional dict mapping skill_name to list of gap descriptions observed
    this session. Example: {"nfr-check": ["dark mode not surfaced for CSS change"]}.
    Written as SkillGap: lines in the audit log. These accumulate across sessions and
    feed into self_heal() skill_gap_signals → assess_skill() evolution loop.

    mid_session_adaptations_applied: Count of skill adaptations applied within this
    session via assess_skill + apply_proposal (not deferred to session_end). Written
    as MidSessionAdaptations: N in the audit log so self_heal can skip re-flagging
    gaps that were already fixed this session.

    findings: Dict with severity keys (CRITICAL, HIGH, MEDIUM, LOW) mapping to int counts.
    Written as Findings: N (CRITICAL=X, HIGH=Y) line. Pass when code-review or
    security-review ran and produced findings. Used by health.py to compute
    finding_actionability_rate and prevented_cost_score.

    finding_categories: List of finding category labels (e.g. ["auth", "idempotency"]).
    Written as FindingCategories: auth,idempotency line. Parsed by health.py for
    recurring pattern detection across sessions.

    nfr_gaps: List of NFR gap categories flagged pre-build (e.g. ["idempotency", "caching"]).
    Written as NFRGap: {category} lines. Feeds prevented_cost_score — each pre-build gap
    flagged = prevented incident candidate.

    direction_reversal: True if challenge skill rejected the initial direction this session.
    Written as DirectionReversal: yes. Feeds prevented_cost_score — each reversal
    represents saved wrong-path sessions.

    developer_caught: List of skill names where the developer's prompt already answered
    the questions before the skill ran (e.g. ["nfr_check"] when the developer included
    performance/reliability/security/observability decisions in their initial request).
    Written as DeveloperCaught: nfr_check line. Parsed by health.py to compute
    developer_autonomy_rate — a rising rate across sessions signals the compounding
    loop is working: the developer is internalising what youk was previously catching.

    loop_correction_detected: True when the user corrected a reasoning verdict this
    session ("you missed", "what about", "unchallenged" after a [CHALLENGE PASSED]).
    Written as LoopCorrection: yes. Feeds loop_dry_rate in health.py. Pass True
    when you detect correction language following a verdict token this session.

    loop_gap_detected: True when the /done retrospective lens check found an objection
    the original loop missed. Written as LoopGap: yes. When True, run

    decision_retrospectives: Prior decisions validated or invalidated this session.
    Each entry: {"decision": str, "outcome": "VALIDATED"|"INVALIDATED", "evidence": str}.
    Written as Retrospectives: N (VALIDATED=X, INVALIDATED=Y) in audit log.
    Feeds decision_durability_rate in health.py — rising rate = decisions getting more
    durable over time. This is the closest the system gets to validating its own value
    hypothesis without external telemetry.

    autonomy_depth: Depth level at which the developer caught each skill this session.
    Keys match developer_caught entries. Values: SURFACE | WORKING | DEEP | ELITE.
    Example: {"nfr_check": "DEEP", "challenge": "WORKING"}.
    Written as AutonomyDepth: nfr_check=DEEP,challenge=WORKING in audit log.
    Feeds autonomy_depth_score in health.py — replaces binary autonomy_rate with a
    weighted score that rewards genuine depth over surface-level recognition.

    contract_violations: Contracts that were not followed this session.
    Each entry is a contract text (or short description) that was violated.
    Written as ContractViolation: {text} lines in audit log.
    Feeds contract_compliance_rate in health.py — surfaces when the system's
    behavioral contracts are eroding rather than being internalized.
    assess_skill("challenge") before closing — mid-session self-correction.

    challenge_rounds: Total ITERATE phases across all challenge invocations this session.
    Written as ChallengeRounds: N. Low values with loop_correction_detected=True = early exit signal.

    outcome: What happened to the work at the end of this session.
    Enum: SHIPPED | STAGED | ABANDONED | NONE (default).
    SHIPPED = committed and pushed / deployed.
    STAGED = committed but not yet pushed (e.g. feature branch, awaiting review).
    ABANDONED = work started but discarded (decision reversed, approach wrong).
    NONE = no code work happened this session (planning, review, exploration).

    outcome_result: How the shipped/staged work actually performed.
    Enum: WORKED | FAILED | UNKNOWN | PENDING (default UNKNOWN).
    WORKED = deployed and confirmed functional in the target environment.
    FAILED = deployed but produced errors, regressions, or was reverted.
    PENDING = staged/deployed but not yet observed in production.
    UNKNOWN = outcome not yet known or not applicable.
    Written as OutcomeResult: <v> in audit log. Feeds outcome_quality_rate in health.py.

    Returns: knowledge_extracted, proposals_added, audit_written,
             session_close_cluster_detected, contracts_saved.
    """
    _OUTCOME_ENUM = {"SHIPPED", "STAGED", "ABANDONED", "NONE"}
    _OUTCOME_RESULT_ENUM = {"WORKED", "FAILED", "UNKNOWN", "PENDING"}
    outcome = (outcome or "NONE").upper()
    outcome_result = (outcome_result or "UNKNOWN").upper()
    if outcome not in _OUTCOME_ENUM:
        return {
            "error": f"Invalid outcome '{outcome}'. Must be one of: {', '.join(sorted(_OUTCOME_ENUM))}",
            "blocked": True,
        }
    if outcome_result not in _OUTCOME_RESULT_ENUM:
        return {
            "error": f"Invalid outcome_result '{outcome_result}'. Must be one of: {', '.join(sorted(_OUTCOME_RESULT_ENUM))}",
            "blocked": True,
        }
    try:
        check_knowledge_write(summary)
    except HardRuleViolation as e:
        return {"error": str(e), "blocked": True, "rule_id": e.rule_id}

    # Structural correction detection: scan the summary for post-verdict correction language.
    # This is server-side — doesn't rely on Claude passing loop_correction_detected=True.
    # The summary is the only cross-session artifact we can scan reliably.
    _CORRECTION_PHRASES = [
        "you missed", "what about", "unchallenged", "you didn't consider",
        "still not at floor", "loop not dry", "not at floor", "still not done",
        "angle unchallenged", "you forgot", "missed this",
    ]
    if not loop_correction_detected and summary:
        summary_lower = summary.lower()
        loop_correction_detected = any(p in summary_lower for p in _CORRECTION_PHRASES)

    # Persist correction state to loop-correction.json so check_loop_dry can read it
    # structurally (without re-scanning the summary). Written here, read by check_loop_dry.
    try:
        import json as _jc
        from datetime import datetime as _dtc
        slug_lc = _get_session_slug()
        correction_file = YOUK_ROOT / "state" / "loop-correction.json"
        correction_file.write_text(_jc.dumps({
            "slug": slug_lc,
            "correction_detected": loop_correction_detected,
            "ts": _dtc.utcnow().isoformat(),
        }))
    except Exception:
        pass

    # Structural rounds reading: read challenge_rounds from state file written by
    # mark_challenge_ran() — each call increments the counter, so this is the
    # authoritative count of challenge invocations, not a Claude memory estimate.
    # Use the state-file value when it exceeds the caller-passed value (take max).
    try:
        import json as _j
        flag_file = YOUK_ROOT / "state" / "challenge-ran.json"
        if flag_file.exists():
            _flag_data = _j.loads(flag_file.read_text())
            open_file = YOUK_ROOT / "state" / "session-open.json"
            current_slug = ""
            if open_file.exists():
                current_slug = _j.loads(open_file.read_text()).get("slug", "")
            if _flag_data.get("slug") == current_slug:
                state_rounds = _flag_data.get("rounds", 0)
                challenge_rounds = max(challenge_rounds, state_rounds)
    except Exception:
        pass

    return end_session(
        summary, commits_made, explicit_contracts, skills_used, close_cluster,
        skill_gaps, mid_session_adaptations_applied,
        findings, finding_categories, nfr_gaps, direction_reversal,
        developer_caught, loop_correction_detected, loop_gap_detected, challenge_rounds,
        decision_retrospectives, autonomy_depth, contract_violations,
        outcome, outcome_result,
    )


@mcp.tool()
def record_outcome_followup(session_slug: str, outcome_result: str) -> dict:
    """
    Amend a prior session's outcome_result in the audit log when the result becomes known.

    Call this when a prior session's work shipped as PENDING or UNKNOWN and the real
    result is now observable — e.g., deployed and confirmed working (WORKED), or
    reverted due to a bug (FAILED).

    session_slug: The slug of the prior session whose outcome_result should be updated.
    Matches the 'Project:' slug line in the audit log. Use the value returned by
    session_start as 'project' field, or read from state/session.json.

    outcome_result: The observed result. Enum: WORKED | FAILED | UNKNOWN | PENDING.
    WORKED = confirmed functional in target environment.
    FAILED = produced errors, regressions, or was reverted.
    PENDING = still awaiting observation.
    UNKNOWN = not applicable or cannot be determined.

    Returns: amended (bool), prior_result (str), new_result (str), audit_file (str).
    On error: error (str), blocked (bool).
    """
    _OUTCOME_RESULT_ENUM = {"WORKED", "FAILED", "UNKNOWN", "PENDING"}
    outcome_result = (outcome_result or "UNKNOWN").upper()
    if outcome_result not in _OUTCOME_RESULT_ENUM:
        return {
            "error": f"Invalid outcome_result '{outcome_result}'. Must be one of: {', '.join(sorted(_OUTCOME_RESULT_ENUM))}",
            "blocked": True,
        }
    return _record_outcome_followup(session_slug, outcome_result)


@mcp.tool()
def optimize_intent(raw_input: str, clarified_context: str | None = None) -> OptimizeIntentResult:
    """
    Compress a vague or multi-part user request into a structured intent brief.

    Use this BEFORE route_task when the input is ambiguous, verbose, or multi-part.
    The returned brief is token-efficient and architecturally opinionated — feed the
    'problem' field into route_task and use it to anchor all subsequent reasoning.

    Fast path (no API): matches known interpretation patterns, returns instantly.
    Full path (API via claude-haiku): general optimization, ~10-15s.

    raw_input: What the user said, verbatim.
    clarified_context: Optional — additional context from the conversation so far.

    Returns: problem, success_criteria, constraints, architecture_recommendation,
             anti_patterns, out_of_scope, ambiguity_detected, clarifying_questions,
             estimated_size, token_efficiency_gain, mode.

    Side effect: when a non-empty success_criteria is returned and ambiguity is not
    detected, writes state/session-goal.json so task_checkpoint and /done can
    re-evaluate whether the goal is met after each task completes.
    """
    result = _optimize_intent(raw_input, clarified_context)
    # Persist the goal so the loop can re-evaluate it at every task_checkpoint.
    # Only write when the intent is unblocked and success_criteria is concrete.
    _PLACEHOLDER_CRITERIA = {
        "Task completed as described.",
        "Deliverables match the architecture recommendation.",
    }
    if (
        not result.get("ambiguity_detected")
        and result.get("goal_translation", {}).get("translation_risk") != "high"
        and result.get("success_criteria")
        and result["success_criteria"] not in _PLACEHOLDER_CRITERIA
    ):
        from session import write_session_goal
        write_session_goal(
            raw_input,
            result["success_criteria"],
            result.get("goal_translation", {}).get("observable_outcome", ""),
        )
    return result


@mcp.tool()
def route_task(
    task: str,
    skills_already_invoked: list[str] | None = None,
    intent_brief: dict | None = None,
) -> RouteTaskResult:
    """
    Determine the size and skill routing for a task. Read this before acting —
    apply the returned ceremony level silently without announcing the routing.

    SCOPE-COLLAPSE GATE: If you called optimize_intent first and it returned
    ambiguity_detected=true, pass the full result as intent_brief. This tool
    will return blocked=true with a collapsing_question. Surface that question
    to the user, get their answer, re-call optimize_intent with clarified_context,
    then re-call route_task with the resolved brief. Do not proceed when blocked=true.

    If intent_brief is provided and ambiguity_detected=false, the brief's
    estimated_size is used for routing (more accurate than keyword scoring).

    task: One-sentence description of what needs to be done.
    skills_already_invoked: Skills already run this session (avoids double-triggering warnings).
    intent_brief: Optional — the full dict returned by optimize_intent.

    Returns: size, ceremony, skills, nfr_mode, warnings, plan_hook, blocked, collapsing_question,
             file_context, graph_state, steering_context.
    When blocked=true: stop. Surface collapsing_question. Do not invoke any skill.
    If file_context is non-empty, pass it as leading context to the first route_to_skill call.
    If steering_context is non-empty, steer using the listed behaviors instead of the raw quality
    label. After work completes, call record_steering_decomposition with confidence="verified" if
    tests passed or "approved" if the user accepted the result.
    """
    slug = _get_session_slug()
    decision = _route_task(task, skills_already_invoked or [], intent_brief, slug=slug)
    result = decision.to_dict()
    # Steering vocab: detect quality labels in the task and attach learned decompositions.
    # Only labels with learned=True are included — cold labels surface as absent, not guessed.
    _QUALITY_LABELS = {
        "rigorous", "thorough", "careful", "elite", "principal", "l9", "l10",
        "exhaustive", "skeptical", "adversarial", "precise",
    }
    task_words = set(task.lower().split())
    steering_context: list[dict] = []
    for label in _QUALITY_LABELS & task_words:
        sv = _get_steering(label)
        if sv.get("learned"):
            steering_context.append(sv)
    if steering_context:
        result["steering_context"] = steering_context
    # Write routing flag so session_start can detect when routing ran this session.
    # Analogous to nfr-check-ran.json — enables "routing was missed" recovery at next open.
    if not result.get("blocked"):
        import hashlib as _hashlib
        import json as _json
        from datetime import datetime as _dt
        flag_file = _sp.slug_state_dir(slug) / "route-task-ran.json"
        task_hash = _hashlib.md5(task.encode()).hexdigest()[:8]
        new_entry = {
            "slug": slug,
            "task": task[:120],
            "task_hash": task_hash,
            "size": result.get("size", "?"),
            "ts": _dt.utcnow().isoformat(),
        }
        # Maintain array so multi-task sessions track all routed tasks, not just last
        existing: list[dict] = []
        if flag_file.exists():
            try:
                raw = _json.loads(flag_file.read_text())
                existing = raw if isinstance(raw, list) else [raw]
            except Exception:
                pass
        existing.append(new_entry)
        _sp.atomic_write(flag_file, _json.dumps(existing))
        # Write semantic routing context into active_task.json so context-clear loses nothing.
        _write_routing_context(task, result)
        # Seed task graph node for M+ tasks so gate tools can write to it immediately.
        # Fails silently — graph is the durable record, not the gate enforcer.
        if result.get("size") in {"M", "L", "XL"}:
            try:
                import hashlib as _hashlib2
                task_id = _hashlib2.sha1(task.encode()).hexdigest()[:12]
                _create_task_graph([{"id": task_id, "label": task[:120]}])
            except Exception:
                pass
    _enrich_route_result(result, task)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


def _enrich_route_result(result: dict, task: str) -> None:
    """Delegate to session.enrich_route_result — lives in session.py for testability."""
    _enrich_route_result_impl(result, task)


@mcp.tool()
def check_command(command: str) -> dict:
    """
    Check a shell command against the no-destructive-without-confirm hard rule.
    Call this before executing any rm, DROP TABLE, force push, reset --hard,
    truncate, or similar destructive operation.

    command: The shell command about to be executed.

    Returns: {"safe": bool, "blocked": bool, "reason": str}
    """
    try:
        check_destructive_command(command)
        return {"safe": True, "blocked": False, "reason": ""}
    except HardRuleViolation as e:
        return {"safe": False, "blocked": True, "reason": str(e), "rule_id": e.rule_id}


@mcp.tool()
def task_contract(task: str, size: str | None = None) -> TaskContractResult:
    """
    Generate a task intake contract before heavy work starts.

    Converts the developer's request into a filled, editable contract surfacing:
    (a) what youk understood, (b) adversarial provocations from frame rotation,
    (c) what this pass will NOT include. Fill, don't interrogate — present a
    complete interpretation for editing, never a questionnaire.

    Sizing gate (F6 ceremony-proportionality):
      XS/S → {contract_required: False, reason: "below contract line"}
      M    → MINI contract (GOAL, DONE-MEANS, SCOPE-OUT, ≤3 provocations inline)
      L/XL → FULL contract (all fields, 5-7 provocations, CUT-LIST)

    Flow: present the returned `contract` to the developer → wait for edits →
    call approve_task_contract() with the edited version → only then proceed.
    For L/XL: check_task_contract_gate() blocks until an approved contract exists.

    task: One-sentence description of what needs to be done.
    size: Optional override (XS/S/M/L/XL). If omitted, computed from task signals.

    Returns: contract_required, reason (when False), contract_id, path, contract (markdown), size.
    """
    from task_contract import generate_task_contract
    result = generate_task_contract(task, size)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


@mcp.tool()
def approve_task_contract(
    contract_id: str,
    as_approved: str,
    disposition_map: dict[str, str] | None = None,
) -> dict:
    """
    Record the developer's approved version of the task contract.

    Call this after the developer has reviewed and edited the contract returned
    by task_contract(). Persists the approved text and records dispositions.

    contract_id: The ID returned by task_contract() (e.g. TC-20260718-001).
    as_approved: The full contract text after developer edits.
    disposition_map: {P1: "IN-SCOPE", P2: "DEFER", P3: "ACCEPT-RISK", ...}
      Valid dispositions: IN-SCOPE, DEFER, ACCEPT-RISK, N/A.
      ACCEPT-RISK entries are appended to state/risk-ledger.jsonl.

    Returns: saved, fields_edited, edit_rate, unresolved_provocations, blocked.
    When blocked=True: some provocations have no disposition — resolve before L/XL work.
    """
    from task_contract import approve_task_contract as _approve
    result = _approve(contract_id, as_approved, disposition_map)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


@mcp.tool()
def check_task_contract_gate(size: str) -> dict:
    """
    Gate that blocks L/XL implementation when no approved task contract exists this session.

    Call after approve_task_contract(), before dev-loop, for L/XL tasks.
    Returns blocked=False immediately for M/S/XS — those sizes don't require the gate.

    size: The routing size from route_task (XS/S/M/L/XL).

    Returns: {"blocked": bool, "reason": str, "contract_id": str (when unblocked)}
    When blocked=True: call task_contract() → present to developer → approve_task_contract()
    → re-call check_task_contract_gate.
    """
    from task_contract import check_task_contract_gate as _gate
    result = _gate(size)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


@mcp.tool()
def rebuild_knowledge_index() -> dict:
    """
    Scan knowledge/ and rebuild INDEX.md with the per-entry table.

    Idempotent: existing usage columns (last-used, use-count) are preserved on rebuild.
    New entries are added with tier=HOT and use-count=0.
    This is the CAP-10 knowledge diet tool — call it after /learn adds new entries
    or after any knowledge/ restructuring.

    Returns: entries_total, hot, cold, archived, index_bytes.
    """
    from knowledge_index import rebuild_knowledge_index as _rebuild
    result = _rebuild(YOUK_ROOT)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


@mcp.tool()
def check_nfr_gate(task: str, size: str, nfr_decision_block: str | None = None) -> CheckNfrGateResult:
    """
    Gate that blocks M+ implementation when no NFR Decision Block is present.
    Call this after route_task returns size M/L/XL, before invoking dev-loop.

    task: The task being implemented (for logging context — not evaluated here).
    size: The routing size returned by route_task — XS, S, M, L, or XL.
    nfr_decision_block: The structured output from `/nfr-check`. Pass None or
        omit if nfr-check has not run yet.

    Returns: {"blocked": bool, "reason": str}
    When blocked=True: run `/nfr-check` first, then re-call check_nfr_gate with
    the NFR output as nfr_decision_block. Do not start dev-loop while blocked.
    When blocked=False: proceed to dev-loop.
    """
    result = _check_nfr_gate(task, size, nfr_decision_block)
    # Ceremony order check: warn if nfr fires before challenge on M+ tasks.
    if size in {"M", "L", "XL"}:
        try:
            slug = _get_session_slug()
            order = _check_order("nfr", slug, size)
            if not order["ok"] and order.get("warning"):
                result = dict(result)
                result["ceremony_warning"] = order["warning"]
        except Exception:
            pass
    # Write NFR-ran flag so hook doesn't re-nudge this session.
    # Slug from session-open.json — task text is natural language, not a file path.
    if not result["blocked"] and size in {"M", "L", "XL"}:
        try:
            import json as _json
            from datetime import datetime as _dt
            slug = _get_session_slug()
            flag_file = _sp.slug_state_dir(slug) / "nfr-check-ran.json"
            flag_file.write_text(_json.dumps({
                "slug": slug,
                "ts": _dt.utcnow().isoformat(),
            }))
        except Exception:
            pass
        _append_gate_to_active_task("nfr")
        # Mirror gate passage to task graph for cross-session recovery.
        # Fails silently — JSON flag file is the authoritative gate; graph is the durable record.
        try:
            breadcrumb_file = YOUK_ROOT / "state" / "routing-breadcrumb.json"
            if breadcrumb_file.exists():
                import json as _json2
                task_id = _json2.loads(breadcrumb_file.read_text()).get("task_id", task[:40])
            else:
                task_id = task[:40]
            _set_gate(task_id, "nfr_cleared", True)
        except Exception:
            pass
    return result


@mcp.tool()
def mark_challenge_ran(
    task: str,
    angles_checked: list[str],
    mode: str = "full",
    objections_this_round: int = 0,
) -> dict:
    """
    Record that the challenge skill has run for the current M+ task.

    angles_checked: List of angle names that were run (e.g. ["framing", "scope",
        "assumptions", "opportunity", "structural", "operational", "experiential",
        "adversarial", "temporal", "outcome", "semantic"]).
        Required — omitting it returns blocked=True.
    mode: Challenge mode — "full" (default), "quick", "silent", or "plan".
        Determines which angles are required. "full" requires all 11 angles;
        "quick"/"silent"/"plan" require the 4 lenses only.
    objections_this_round: Count of NEW objections raised in this round. Pass 0 only
        when the last pass produced zero new objections from ALL angles. A value > 0
        means the loop is NOT dry — check_loop_dry will return not_converged=True.

    Each call increments the challenge_rounds counter — session_end reads this
    directly from state rather than trusting Claude's passed-in value.

    Returns: {"recorded": bool, "challenge_rounds": int, "angles_validated": bool,
              "converged": bool}
    When blocked: {"blocked": True, "missing_angles": [...], "reason": str}
    """
    from challenge_gate import validate_angles
    validation = validate_angles(angles_checked, mode)
    if not validation["valid"]:
        return {
            "blocked": True,
            "missing_angles": validation["missing_angles"],
            "reason": validation["reason"],
        }
    try:
        import json as _json
        from datetime import datetime as _dt
        slug = _get_session_slug()
        flag_file = YOUK_ROOT / "state" / "challenge-ran.json"
        existing_rounds = 0
        if flag_file.exists():
            try:
                existing = _json.loads(flag_file.read_text())
                if existing.get("slug") == slug:
                    existing_rounds = existing.get("rounds", 0)
            except Exception:
                pass
        new_rounds = existing_rounds + 1
        converged = objections_this_round == 0
        flag_file.write_text(_json.dumps({
            "slug": slug,
            "task": task,
            "ts": _dt.utcnow().isoformat(),
            "rounds": new_rounds,
            "angles_validated": True,
            "mode": mode,
            "objections_last_round": objections_this_round,
            "converged": converged,
        }))
        _append_gate_to_active_task("challenge")
        _record_gate("challenge", slug)
        return {
            "recorded": True,
            "challenge_rounds": new_rounds,
            "angles_validated": True,
            "converged": converged,
        }
    except Exception:
        return {"recorded": False, "challenge_rounds": 0, "angles_validated": False,
                "converged": False}


@mcp.tool()
def check_challenge_gate(task: str, size: str) -> CheckChallengeGateResult:
    """
    Gate that blocks M+ implementation when challenge skill has not run for this task.
    Call this after nfr_check passes and before invoking dev-loop on M+ tasks.

    task: The task being implemented (for logging context).
    size: The routing size returned by route_task — XS, S, M, L, or XL.

    Returns: {"blocked": bool, "reason": str}
    When blocked=True: run challenge skill first (route_to_skill('challenge', task)),
    then call mark_challenge_ran(task), then re-call check_challenge_gate.
    When blocked=False: proceed to dev-loop.
    """
    challenge_ran = False
    try:
        import json as _json
        flag_file = YOUK_ROOT / "state" / "challenge-ran.json"
        if flag_file.exists():
            data = _json.loads(flag_file.read_text())
            current_slug = _get_session_slug()
            challenge_ran = data.get("slug", "") == current_slug
    except Exception:
        pass

    result = _check_challenge_gate(task, size, challenge_ran)
    _cg_slug = _get_session_slug()
    # Ceremony order check: warn if challenge_gate fires before nfr on M+ tasks.
    if size in {"M", "L", "XL"}:
        try:
            order = _check_order("challenge_gate", _cg_slug, size)
            if not order["ok"] and order.get("warning"):
                result = dict(result)
                result["ceremony_warning"] = order["warning"]
        except Exception:
            pass
    if not result["blocked"] and size in {"M", "L", "XL"}:
        try:
            import json as _json
            from datetime import datetime as _dt
            flag_file = YOUK_ROOT / "state" / "challenge-gate-passed.json"
            flag_file.write_text(_json.dumps({
                "slug": _cg_slug,
                "ts": _dt.utcnow().isoformat(),
            }))
        except Exception:
            pass
        _append_gate_to_active_task("challenge_gate")
        _record_gate("challenge_gate", _cg_slug)
        # Mirror gate passage to task graph for cross-session recovery.
        # Also set unblocked=True when challenge clears — challenge is the final gate before dev-loop.
        try:
            import json as _json2
            breadcrumb_file = YOUK_ROOT / "state" / "routing-breadcrumb.json"
            if breadcrumb_file.exists():
                task_id = _json2.loads(breadcrumb_file.read_text()).get("task_id", task[:40])
            else:
                task_id = task[:40]
            _set_gate(task_id, "challenge_cleared", True)
            # Mark unblocked only if nfr also cleared — check graph state first
            from graph import is_unblocked as _graph_is_unblocked
            state = _graph_is_unblocked(task_id)
            if state.get("gates", {}).get("nfr_cleared"):
                _set_gate(task_id, "unblocked", True)
        except Exception:
            pass
    return result


@mcp.tool()
def check_intake_gate(task: str, size: str, intake_required: bool) -> dict:
    """
    Gate that blocks M+ implementation when intake was required but has not run.

    Call this on M+ tasks when optimize_intent returned intake_required=True, before
    invoking dev-loop. Mirrors check_nfr_gate and check_challenge_gate — the last
    direction-gate to become machine-checkable rather than prose-enforced.

    task: The task being routed (for logging context).
    size: The routing size from route_task — XS, S, M, L, or XL.
    intake_required: The intake_required field returned by optimize_intent.

    Returns: {"blocked": bool, "reason": str}
    When blocked=True: run the intake protocol (skills/intake), call mark_intake_ran(task),
    then re-call check_intake_gate. Do not route while intake is owed.
    When blocked=False: proceed (to challenge/nfr gates, then dev-loop).
    """
    # Reuse the same session-scoped intake flag intent.py checks.
    intake_has_run = False
    try:
        import json as _json
        flag_file = YOUK_ROOT / "state" / "intake-ran.json"
        if flag_file.exists():
            data = _json.loads(flag_file.read_text())
            intake_has_run = data.get("slug", "") == _get_session_slug()
    except Exception:
        pass

    return _check_intake_gate(task, size, intake_required, intake_has_run)


@mcp.tool()
def create_task_graph(tasks: list[dict], edges: list[list] | None = None) -> dict:
    """
    Create or extend the task graph in SQLite.

    tasks: list of {"id": str, "label": str}
    edges: list of [parent_id, child_id] pairs — parent must complete before child

    Idempotent — existing tasks and edges are silently skipped.
    Returns {"created": int, "edges_added": int, "total_tasks": int}
    """
    edge_tuples = [tuple(e) for e in (edges or [])]
    return _create_task_graph(tasks, edge_tuples)


@mcp.tool()
def set_gate(task_id: str, gate_name: str, value: bool,
             session_id: str | None = None) -> dict:
    """
    Set a gate boolean on a task node in the task graph. Idempotent.

    task_id:    Task node ID (created by create_task_graph, or auto-created as stub).
    gate_name:  One of: challenge_cleared, nfr_cleared, unblocked, in_flight
    value:      True to set, False to clear.
    session_id: When setting in_flight=True, pass "{slug}-{session_counter}" (e.g. "youk-80")
                to record which session claimed this task. Cleared automatically when
                in_flight is set False or mark_task_done runs. Enables stale-claim
                detection across concurrent sessions.

    Called by CLAUDE.md routing after each gate passes — replaces writing individual
    JSON gate files. Existing check_nfr_gate and check_challenge_gate tools are
    unchanged; this tool persists the gate outcome to the graph for cross-session recovery.

    Returns {"ok": bool, "task_id": str, "gate": str, "value": bool}
    """
    import logging
    logging.debug("set_gate: task=%s gate=%s value=%s session_id=%s", task_id, gate_name, value, session_id)
    return _set_gate(task_id, gate_name, value, session_id=session_id)


@mcp.tool()
def is_unblocked(task_id: str) -> dict:
    """
    Return gate state for a task node.

    Returns {"found": bool, "task_id": str, "gates": dict, "unblocked": bool}
    gates dict includes: challenge_cleared, nfr_cleared, unblocked, in_flight, stale
    """
    return _is_unblocked(task_id)


@mcp.tool()
def next_task() -> dict:
    """
    Return the next actionable task for the CURRENT project only.

    Scopes to the active session's project slug so tasks from other projects
    never surface here. Uses recursive CTE to walk the task DAG.
    Returns {"found": bool, "task": dict | None}
    """
    return _next_task(project=_get_session_slug() or None)


@mcp.tool()
def mark_task_done(task_id: str) -> dict:
    """
    Mark a task node as done — clears in_flight, sets unblocked=1.

    Returns {"ok": bool, "task_id": str}
    """
    return _mark_done(task_id)


@mcp.tool()
def mark_intake_ran(task: str) -> dict:
    """
    Record that the intake skill has run for the current session.
    Call this after the intake gap synthesis phase completes (Phase 4).

    task: The task for which intake was run (for audit context).

    Returns: {"recorded": bool, "slug": str}
    Once recorded, optimize_intent will return intake_required=False for this session
    so intake does not fire again on subsequent tasks.
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        slug = _get_session_slug()
        flag_file = YOUK_ROOT / "state" / "intake-ran.json"
        flag_file.write_text(_json.dumps({
            "slug": slug,
            "task": task[:120],
            "ts": _dt.utcnow().isoformat(),
        }))
        return {"recorded": True, "slug": slug}
    except Exception:
        return {"recorded": False, "slug": "unknown"}


@mcp.tool()
def mark_medium_risk_surfaced(task: str) -> dict:
    """
    Record that the medium-translation-risk question was surfaced to the user.
    Call immediately after displaying the collapsing question from route_task warnings
    (rule_id="medium-translation-risk"). Clears the pending flag so task_checkpoint
    does not surface medium_risk_unsurfaced.

    task: The task being worked on (for audit context).

    Returns: {"recorded": bool}
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        slug = _get_session_slug()
        target = (
            _sp.slug_state_dir(slug) / "medium-risk-question.json"
            if slug
            else YOUK_ROOT / "state" / "medium-risk-question.json"
        )
        if target.exists():
            data = _json.loads(target.read_text())
            data["surfaced"] = True
            data["surfaced_at"] = _dt.utcnow().isoformat()
            target.write_text(_json.dumps(data))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_json.dumps({
                "question": "",
                "surfaced": True,
                "surfaced_at": _dt.utcnow().isoformat(),
            }))
        return {"recorded": True}
    except Exception:
        return {"recorded": False}


@mcp.tool()
def check_loop_dry(task: str = "") -> dict:
    """
    Structural sensor for whether the last challenge loop was dry.

    Reads challenge-ran.json (written by mark_challenge_ran) and the loop_correction
    state derived from the summary scan in session_end. Returns a per-session verdict
    without requiring Claude to reconstruct this from memory.

    Called automatically by session_end when close_cluster=True. Also exposed as an
    explicit MCP tool so the done skill can call it for transparency at /done.

    task: optional — the task label to validate against the recorded challenge task.

    Returns: {
        "dry": bool — True when challenge ran, no correction detected, AND last round
                     had zero new objections (objections_last_round == 0),
        "rounds": int — number of mark_challenge_ran calls this session,
        "challenge_ran": bool — whether challenge ran at all,
        "loop_correction_in_state": bool — whether a correction was written to state,
        "not_converged": bool — True when last round still had objections (loop not dry),
        "objections_last_round": int — objection count from the most recent round,
        "session_slug": str,
    }
    """
    try:
        import json as _json
        current_slug = _get_session_slug()
        flag_file = _sp.slug_state_dir(current_slug) / "challenge-ran.json"
        correction_file = _sp.slug_state_dir(current_slug) / "loop-correction.json"

        rounds = 0
        challenge_ran = False
        converged = True
        objections_last_round = 0
        if flag_file.exists():
            data = _json.loads(flag_file.read_text())
            if data.get("slug") == current_slug:
                rounds = data.get("rounds", 0)
                challenge_ran = rounds > 0
                objections_last_round = data.get("objections_last_round", 0)
                # Legacy records without the field are treated as converged.
                converged = data.get("converged", True)

        # Read loop-correction state — written by session_end when correction language
        # detected in summary. This is the structural half of loop_gap detection.
        correction_in_state = False
        if correction_file.exists():
            try:
                corr_data = _json.loads(correction_file.read_text())
                if corr_data.get("slug") == current_slug:
                    correction_in_state = corr_data.get("correction_detected", False)
            except Exception:
                pass

        not_converged = challenge_ran and not converged
        dry = challenge_ran and not correction_in_state and converged
        return {
            "dry": dry,
            "rounds": rounds,
            "challenge_ran": challenge_ran,
            "loop_correction_in_state": correction_in_state,
            "not_converged": not_converged,
            "objections_last_round": objections_last_round,
            "session_slug": current_slug,
        }
    except Exception:
        return {
            "dry": False,
            "rounds": 0,
            "challenge_ran": False,
            "loop_correction_in_state": False,
            "not_converged": False,
            "objections_last_round": 0,
            "session_slug": "",
        }


@mcp.tool()
def self_heal(research_mode: bool = False) -> dict:
    """
    Run a health analysis on the last 30 days of audit logs.
    Identifies skill usage patterns, skipped sessions, and improvement signals.
    Proposals are written to knowledge/proposals/PENDING.md — never auto-applied.

    Also returns skill_gap_signals when recurring skill gaps are detected in audit logs.
    For each signal: call youk-code.assess_skill(skill_name) to get proposed_additions,
    then call add_proposal() here for each one you approve.

    research_mode: when True, also returns research_topics — suggested search queries
    derived from gap signals. Pass these to the youk-research skill (/research [topic])
    to find external solutions. Does not perform web research itself.

    Returns: org_score, sessions_analyzed, findings, proposals_count,
             skill_gap_signals (if any — skills needing evolution),
             research_topics (if research_mode=True and gaps exist).
    """
    return run_health_check_with_skill_signals(research_mode=research_mode)


@mcp.tool()
def add_proposal(
    title: str,
    rationale: str,
    change_type: str,
    target: str,
    content: str = "",
    target_section: str = "",
) -> dict:
    """
    Add an improvement proposal to PENDING.md for founder review.
    Use this after assess_skill() returns proposed_additions, or to register
    a generate_skill() draft before applying it.

    title: Short description (e.g. "Add null check to session_end")
    rationale: Why this change is needed — include signal type if from assess_skill
    change_type: SKILL_EDIT | CONFIG_EDIT | REFERENCE_ADD | FILE_CREATE
    target: skill name for SKILL_EDIT, file path for FILE_CREATE/CONFIG_EDIT
    content: The new content to write (full file for FILE_CREATE, section text for SKILL_EDIT)
    target_section: Section heading within target skill (for SKILL_EDIT only)

    Returns: proposal_id, status. Review with get_proposals(), apply with apply_proposal().
    """
    from models import Proposal
    from datetime import datetime
    import json as _json

    # Stamp with current project slug so session_start can filter by project.
    # Skill-system proposals (change_type SKILL_EDIT / REFERENCE_ADD) belong to "youk"
    # regardless of calling project — they improve the global skill set.
    _sopen = YOUK_ROOT / "state" / "session-open.json"
    _current_slug = "youk"
    if change_type not in ("SKILL_EDIT", "REFERENCE_ADD") and _sopen.exists():
        try:
            _current_slug = _json.loads(_sopen.read_text()).get("slug", "youk")
        except Exception:
            pass

    proposal = Proposal(
        id=f"PENDING-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        target=target,
        change_description=title,
        reason=rationale,
        before="",
        after=content[:300] if content else "",
        status="PENDING",
        proposed_date=datetime.utcnow().strftime("%Y-%m-%d"),
        change_type=change_type,
        target_section=target_section,
        content=content,
        project_slug=_current_slug,
    )
    _add_proposal(proposal)
    return {"proposal_id": proposal.id, "status": "added", "target": target}


@mcp.tool()
def get_proposals(project_slug: str | None = None) -> dict:
    """
    Return pending self-heal proposals for the current project.

    project_slug: filter to a specific project. If None, reads current slug from
    session-open.json. Pass project_slug="" explicitly to see all projects (admin use).
    Skill-system proposals (SKILL_EDIT / REFERENCE_ADD) are always attributed to "youk".

    Returns: proposals (list with id, target, change, reason, before, after, status, project).
    """
    import json as _json

    # Resolve slug: explicit arg > session-open.json > show all
    if project_slug is None:
        _sopen = YOUK_ROOT / "state" / "session-open.json"
        try:
            project_slug = _json.loads(_sopen.read_text()).get("slug", "youk") if _sopen.exists() else "youk"
        except Exception:
            project_slug = "youk"

    # Pass slug to DB for efficient filtering; empty string = fetch all projects
    proposals = _load_pending_proposals(project_slug if project_slug else None)

    # Legacy in-memory filter: normalize empty project_slug to "youk" for old rows
    if project_slug:
        proposals = [
            p for p in proposals
            if (p.project_slug or "youk") == project_slug
        ]

    return {
        "count": len(proposals),
        "project_filter": project_slug or "all",
        "proposals": [
            {
                "id": p.id,
                "target": p.target,
                "change": p.change_description,
                "reason": p.reason,
                "before": p.before,
                "after": p.after,
                "status": p.status,
                "proposed_date": p.proposed_date,
                "project": p.project_slug or "youk",
            }
            for p in proposals
        ],
    }


@mcp.tool()
def apply_proposal(
    proposal_id: str,
    confirmed: bool = False,
    safe_types: list[str] | None = None,
    review_required_override: bool = False,
) -> dict:
    """
    Apply an approved self-heal proposal.

    confirmed must be True to write anything. Pass False to preview what would change.

    safe_types: optional allowlist of change_type values that may be auto-applied.
    Any proposal whose change_type is NOT in safe_types returns blocked=True and
    must be reviewed manually. Use safe_types=["SKILL_EDIT","FILE_CREATE"] for
    autonomous /improve runs. Omit safe_types (or pass None) to apply any type
    after explicit human review.

    review_required_override: pass True after the user has reviewed and approved a
    net-new skill proposal (review_required=True). Without this flag, proposals
    generated by Track A skill generation will return blocked=True even with confirmed=True.

    Examples:
      apply_proposal("PENDING-123", confirmed=True)  # explicit human apply, any type
      apply_proposal("PENDING-123", confirmed=True, safe_types=["SKILL_EDIT","FILE_CREATE"])  # /improve safe path
      apply_proposal("PENDING-123", confirmed=True, review_required_override=True)  # after user approves Track A skill

    proposal_id: The PENDING-XXX identifier from get_proposals().
    Returns: applied, blocked, change_type, change_summary, message.
    """
    try:
        return _apply_proposal(proposal_id, confirmed, safe_types, review_required_override)
    except ValueError as e:
        return {"applied": False, "error": str(e), "rule_id": "no-auto-apply-proposals"}


@mcp.tool()
def save_contract(contract: str, project_dir: str) -> dict:
    """
    Immediately write a working agreement to contracts.md.

    Call this the moment a contract phrase is detected in conversation —
    do NOT wait for session_end. Contracts held only in conversation context
    are lost to Claude's auto-compaction. Once written here, compact_context
    pins them verbatim in every future brief and session_start loads them first.

    contract: The verbatim agreement (e.g. "always run ruff before committing").
    project_dir: Current project directory (same as session_start).

    Returns: saved, contract, slug, contracts_file, note.
    """
    # Guard: reject bare trigger phrases with no specific behavior attached.
    # "always" alone is noise from phrase detection on the contracts.md header text.
    # A valid contract must name a specific action (≥ 20 chars, ≥ 3 words).
    stripped = contract.strip().rstrip(".,;:")
    words = stripped.split()
    if len(stripped) < 20 or len(words) < 3:
        return {
            "saved": False,
            "contract": contract,
            "slug": "",
            "contracts_file": "",
            "conflicts": [],
            "note": f"contract too vague — include specific behavior (e.g. 'always run ruff before committing'). Got: {repr(contract)}",
        }

    slug = Path(project_dir).name or "unknown"
    result = write_contracts(slug, [contract])
    added = result["added"]
    conflicts = result.get("conflicts", [])
    return {
        "saved": added > 0,
        "contract": contract,
        "slug": slug,
        "contracts_file": f"knowledge/projects/{slug}/contracts.md",
        "conflicts": conflicts,
        "note": "already in contracts.md" if added == 0 else "written — will survive compaction",
    }


@mcp.tool()
def task_checkpoint(
    project_dir: str,
    task_label: str,
    size: str = "M",
    session_learnings: dict | None = None,
) -> dict:
    """
    Write a mid-session checkpoint when a task completes and the user moves on.

    Call this when the user signals task completion ("done", "ok", "next", or topic
    shifts after a multi-exchange task). Proportional to task size:
    - XS/S: rebuilds context brief only — lightweight compact, zero audit overhead.
    - M+: compact + appends a structured entry to state/task-checkpoints.jsonl,
      which session_end rolls up into the final audit entry.

    Paste the returned 'brief' verbatim in your response to anchor context.

    project_dir: Current project directory (same as session_start).
    task_label: Short description of the completed task (e.g. "fixed login bug").
    size: Task size — XS, S, M, L, or XL (defaults to M).
    session_learnings: optional observations from the current sub-task, e.g.
      {"contract_unsaved": "always use async", "skill_gap": "nfr_check skipped",
       "route_correction": "S→M override"}.
      When the same gap_type appears 2+ times across checkpoints, returns
      pattern_trigger so Claude acts immediately (mid-session adaptation).

    Returns: brief (paste verbatim), checkpoint_written, pattern_trigger (if any),
             goal_check (if a session goal is active — goal_met: bool, goal_gap: str),
             calls_since_compact (int — compact if > 8).
             IMPORTANT: if goal_check.goal_met is False, do NOT close the session.
             Derive the next task toward the stated goal and continue.
    """
    result = _task_checkpoint(project_dir, task_label, size, session_learnings)
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


@mcp.tool()
def update_convergence_state(
    angle: str,
    status: str,
    pressure_source: str = "model",
    unknown_unknown: str | None = None,
) -> dict:
    """
    Update the convergence state for a single angle of the seven-angle traversal.

    Call this when external pressure (user push, user correction, real outcome) arrives
    and an angle's convergence status changes.

    angle: structural | operational | experiential | adversarial | temporal | outcome | semantic
    status: converged | diverged | unknown
    pressure_source: user | model — only user pressure credits convergence.
                     Model-generated pressure that doesn't move the answer = noise.
    unknown_unknown: describe the angle if it cannot be resolved without real external collision.

    Returns the updated convergence_state with distance_from_optimum.
    """
    import json as _json
    from session import _slug_state_dir as _ssd
    # Resolve per-slug convergence file from active session
    _slug = None
    _sopen = YOUK_ROOT / "state" / "session-open.json"
    if _sopen.exists():
        try:
            _slug = _json.loads(_sopen.read_text()).get("slug", "")
        except Exception:
            pass
    if not _slug:
        _sessions = YOUK_ROOT / "state" / "sessions"
        if _sessions.exists():
            _cands = sorted(_sessions.glob("*/open.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if _cands:
                try:
                    _slug = _json.loads(_cands[0].read_text()).get("slug", "")
                except Exception:
                    pass
    cs_file = (_ssd(_slug) / "convergence.json") if _slug else (YOUK_ROOT / "state" / "convergence-state.json")
    current = {}
    try:
        if cs_file.exists():
            current = _json.loads(cs_file.read_text())
    except Exception:
        pass
    updated = _update_convergence_state(current, angle, status, pressure_source, unknown_unknown)
    try:
        cs_file.parent.mkdir(parents=True, exist_ok=True)
        cs_file.write_text(_json.dumps(updated, indent=2))
    except Exception:
        pass
    return updated


@mcp.tool()
def compact_context(project_dir: str, intent: str = "") -> dict:
    """
    Build a structured context brief from youk's knowledge store.

    Call this proactively when the session is getting long (25+ exchanges) —
    BEFORE Claude's generic auto-compaction triggers. The brief preserves
    Contracts verbatim, Decisions as key-fact + rationale, and drops
    Clarifications entirely. It is generated from structured files, not
    by summarizing conversation, so no information is lost.

    When intent is provided, Decision blocks matching the intent keywords are
    pinned verbatim instead of compressed. Use this after an NFR decision to
    keep that decision block intact through subsequent compaction cycles.
    Example: compact_context(cwd, intent="payment webhook idempotency")

    Use the returned 'brief' as your working context anchor: state it
    explicitly in your response so it appears in recent context and
    survives the next compaction cycle.

    project_dir: The current project directory (same as session_start).
    intent: Optional keywords describing the active work (e.g. "payment webhook nfr").

    Returns: brief (pin this), contracts_count, decisions_count, instruction.
    """
    _reset_tool_call_count()
    return build_brief(project_dir, intent)


@mcp.tool()
def track_tokens(
    input_tokens: int,
    output_tokens: int,
    note: str = "",
    token_budget: int = 0,
) -> dict:
    """
    Record token usage at a checkpoint in the current session.

    Call this after each significant work unit:
    - Right after route_task returns: pass token_budget from its response to register the
      session budget (input_tokens=0, output_tokens=0, note="route_task", token_budget=<value>)
    - After a route_to_skill call returns (note = skill name)
    - After a commit is made (note = "commit")
    - Before session_end as the final tally (note = "final")

    Token counts are estimates from your context window usage indicator —
    rough figures are fine. The goal is trend detection across sessions,
    not per-call accounting precision.

    input_tokens: approximate tokens in this exchange (prompt + context)
    output_tokens: approximate tokens generated in this exchange
    note: optional label for this checkpoint
    token_budget: pass route_task's token_budget here on the first call to register
                  the session budget; ignored (0) on subsequent calls

    Returns: session_total_input, session_total_output, token_budget, vs_budget_pct.
    """
    return record_checkpoint(input_tokens, output_tokens, note, token_budget)


@mcp.tool()
def check_doc_graph() -> dict:
    """
    Audit the concept coherence graph declared in docs/doc-map.yaml.

    For each concept in the `concepts:` block, checks whether the authority
    file has been updated more recently than its derived files. Uses git commit
    timestamps (stable across clones) with mtime fallback.

    Returns: concepts_checked, stale_concepts (list of {concept, authority,
             stale_in}), clean_concepts, verdict.

    Call explicitly for a full audit. session_start also consults this
    automatically (capped at 2 warnings to avoid flooding session_plan).
    """
    from doc_graph import load_concept_graph, check_concept_staleness
    concepts = load_concept_graph(YOUK_ROOT)
    stale = check_concept_staleness(concepts, YOUK_ROOT, CLAUDE_ROOT)
    return {
        "concepts_checked": len(concepts),
        "stale_concepts": stale,
        "clean_concepts": len(concepts) - len(stale),
        "verdict": (
            "COHERENT — all derived files are up-to-date with their authorities"
            if not stale
            else f"DRIFT DETECTED — {len(stale)} concept(s) need review"
        ),
    }


@mcp.resource("youk://session/state")
def get_session_state() -> str:
    """Current session state from the last session_start call."""
    state_file = YOUK_ROOT / "state" / "session.json"
    if state_file.exists():
        return state_file.read_text()
    return '{"status": "no session started"}'


@mcp.resource("youk://config/routes")
def get_routes() -> str:
    """Task sizing and skill routing configuration (routes.yaml)."""
    routes_file = YOUK_ROOT / "config" / "routes.yaml"
    return routes_file.read_text() if routes_file.exists() else "routes.yaml not found"


@mcp.resource("youk://config/guardrails")
def get_guardrails() -> str:
    """Hard and soft rule definitions (guardrails.yaml)."""
    gr_file = YOUK_ROOT / "config" / "guardrails.yaml"
    return gr_file.read_text() if gr_file.exists() else "guardrails.yaml not found"


@mcp.resource("youk://knowledge/interpretation")
def get_interpretation() -> str:
    """Interpretation patterns — how the developer's phrases map to actual intent."""
    ui_file = YOUK_ROOT / "knowledge" / "interpretation" / "user-intent.md"
    return ui_file.read_text() if ui_file.exists() else "No interpretation patterns yet."


@mcp.resource("youk://knowledge/proposals")
def get_proposals_resource() -> str:
    """Pending self-heal proposals (rendered from SQLite store)."""
    from health import _load_pending_proposals, _render_pending_md
    proposals = _load_pending_proposals()
    pending_only = [p for p in proposals if p.status == "PENDING"]
    if not pending_only:
        return "No pending proposals."
    return _render_pending_md(pending_only)


@mcp.tool()
def promote_to_global_contracts(contracts: list[str]) -> dict:
    """Promote confirmed cross-project patterns to the user's global intelligence layer.

    Appends to knowledge/global/contracts.md — loaded on every future project start.
    Deduplicates case-insensitively. Returns {promoted: N, skipped: N, conflicts: [...]}.
    Call after confirming candidates from self_heal()'s global_pattern_candidates field.
    """
    global_file = YOUK_ROOT / "knowledge" / "global" / "contracts.md"
    global_file.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if global_file.exists():
        existing_lines = [
            line.strip().lstrip("- ")
            for line in global_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    existing_normalized = {c.lower() for c in existing_lines}

    promoted, skipped, conflicts = 0, 0, []
    with open(global_file, "a") as f:
        for c in contracts:
            normalized = c.strip().lower()
            if normalized in existing_normalized:
                skipped += 1
                continue
            # Conflict check: look for semantically opposing patterns
            for existing in existing_lines:
                if ("always" in normalized and "never" in existing.lower() and normalized[7:20] in existing.lower()) or \
                   ("never" in normalized and "always" in existing.lower() and normalized[6:20] in existing.lower()):
                    conflicts.append(f"Conflict: new '{c}' vs existing '{existing}'")
            f.write(f"- {c.strip()}\n")
            existing_normalized.add(normalized)
            promoted += 1

    return {"promoted": promoted, "skipped": skipped, "conflicts": conflicts}


@mcp.tool()
def index_project(project_dir: str, project_slug: str, force: bool = False) -> dict:
    """Index a project's files into the shared SQLite file index for BM25 retrieval.

    Incremental: unchanged files (same hash) are skipped automatically.
    Call at session_start or after significant changes. Safe to call repeatedly.

    project_dir: absolute path to the project root on the host
    project_slug: short name for this project (e.g. "canopy", "youk")
    force: if True, re-index all files regardless of hash

    Returns: {indexed, skipped, total_files, project_slug}
    """
    return _index_project(project_dir, project_slug, force=force)


@mcp.tool()
def find_relevant(query: str, project_slug: str | None = None, limit: int = 10) -> dict:
    """BM25 search over indexed files across all projects.

    Returns ranked files with summary and attribution. Current project results
    surface first when project_slug is provided.

    query: natural language or symbol name (e.g. "session start contracts", "route_task")
    project_slug: if set, boosts results from this project and fills remainder from others
    limit: max results (default 10)

    Returns: {results: [{project_slug, file_path, summary, score}], query, total}
    """
    return _find_relevant(query, project_slug=project_slug, limit=limit)


@mcp.tool()
def find_affected(file_path: str, project_slug: str) -> dict:
    """Return files that import or reference the given file — impact analysis.

    Searches indexed imports for the file's module stem. Use before changing a
    shared module to understand blast radius.

    file_path: relative path within the project (e.g. "servers/core/src/session.py")
    project_slug: the project this file belongs to

    Returns: {source_file, module_stem, affected: [{project_slug, file_path, summary}], affected_count}
    """
    return _find_affected(file_path, project_slug)


@mcp.tool()
def find_relations(file_path: str, project_slug: str, direction: str = "both") -> dict:
    """Return relation edges for a file from the relation graph.

    direction: "out" = what this file links to; "in" = what links to this file;
               "both" = union (default).

    Relation types captured during indexing:
    - doc_link: markdown [text](path) hrefs pointing to another file
    - doc_map_ref: explicit declarations in docs/doc-map.yaml (weight 2.0 — authoritative)
    - config_ref: file paths found as values in YAML/TOML/JSON config files
    - import: code → imported module (stem-level, same as find_affected)

    Use to answer:
    - "What docs reference session.py?" → direction="in"
    - "What does guardrails.md link to?" → direction="out"
    - "Full neighbourhood of this file?" → direction="both"

    Returns: {file_path, relations: [{file_path, rel_type, weight, direction}],
              total, outbound_count, inbound_count}
    """
    return _find_relations(file_path, project_slug, direction=direction)


@mcp.tool()
def find_related_docs(query: str, project_slug: str | None = None, limit: int = 8) -> dict:
    """BM25 search that bridges code and non-code docs via the relation graph.

    Returns two ranked buckets:
    - related_code: code files matching the query or linked from matching docs
    - related_docs: doc/config files matching the query or linked from matching code

    Each result includes: file_path, project_slug, summary, score, source
    (source is "bm25" for direct hits, "relation:<type>" for graph-expanded hits).

    Example questions this answers:
    - "What docs explain route_task?" → surfaces README + doc-map + server.py
    - "What code implements the NFR gate?" → surfaces session.py + nfr.py via doc hits
    - "What is connected to guardrails?" → surfaces guardrails.yaml + guardrails.md + server.py

    query: natural language or symbol name
    project_slug: if set, boosts current-project results first
    limit: max results per bucket (code and docs capped separately)

    Returns: {related_code, related_docs, query, project_slug, total}
    """
    return _find_related_docs(query, project_slug=project_slug, limit=limit)


@mcp.tool()
def find_stale_relations(project_slug: str | None = None, limit: int = 20) -> dict:
    """Graph-driven staleness: flag derived files whose source changed more recently.

    Walks the full file_relations graph (every indexed link) and reports each relation
    where the source/authority (from_path) was re-indexed more recently than its derived
    file (to_path) — meaning the source changed and the derived doc may not have followed.

    Replaces the hand-maintained doc-map.yaml staleness list (which only covered a handful
    of files) with the whole indexed link graph across all indexed files. Use at session
    start or before a docs commit to catch stale derived files no one remembered to update.

    project_slug: restrict to one project, or None for all.
    limit: max stale relations to return (most-recently-diverged first).

    Returns: {stale: [{project_slug, from_path, to_path, rel_type, source_indexed,
              derived_indexed}], checked: int, stale_count: int}
    """
    return _find_stale_relations(project_slug=project_slug, limit=limit)


@mcp.tool()
def get_file_index_stats(project_slug: str | None = None) -> dict:
    """Return file index health: file counts, relation edge counts, last indexed timestamps.

    project_slug: if set, returns stats for that project only; None returns all projects.
    Returns: {status, projects: [{project_slug, file_count, last_indexed}],
              total_files, relations: {rel_type: count}, total_relations}
    """
    return _get_index_stats(project_slug=project_slug)


@mcp.tool()
def query_concept_graph(query: str, project_slug: str | None = None, limit: int = 5) -> dict:
    """Search the cross-session concept graph for concepts matching the query label.

    Returns seed matches (label substring) extended with one-hop neighbors via
    concept_edges. Use to surface related patterns, decisions, and domain knowledge
    from past sessions across all projects.

    query: search term (substring match on concept label)
    project_slug: filter to a specific project (youk, canopy, genie-fertility); None = all
    limit: max seed results (neighbors are additive, capped at 2x limit)

    Returns: {concepts: [{label, type, project_slug, session_n, summary, match}], total}
    match field: "direct" | "neighbor:{edge_type}"
    """
    return _query_concept_graph(query, project_slug=project_slug, limit=limit)


@mcp.tool()
def get_concept_graph_stats(project_slug: str | None = None) -> dict:
    """Return concept graph health: concept and edge counts per project.

    project_slug: filter to one project; None returns all.
    Returns: {status, projects: [{project_slug, concept_count}], total_concepts, total_edges}
    """
    return _get_concept_stats(project_slug=project_slug)


@mcp.tool()
def get_skill_signals(skill_name: str | None = None, window: int = 10) -> dict:
    """Return skill self-improvement signals and health summary.

    skill_name: filter to one skill; None returns all tracked skills.
    window: number of recent sessions to include in pattern detection.
    Returns: {health: {skill: {points, status}}, patterns: [...], fork_candidates: [...]}
    """
    try:
        from skill_signals import get_skill_health_summary, detect_patterns, get_fork_candidates
        health = get_skill_health_summary()
        if skill_name:
            health = {k: v for k, v in health.items() if k == skill_name}
        patterns = detect_patterns(window=window)
        if skill_name:
            patterns = [p for p in patterns if p["skill"] == skill_name]
        fork_candidates = get_fork_candidates()
        if skill_name:
            fork_candidates = [c for c in fork_candidates if c["skill"] == skill_name]
        return {
            "health": health,
            "patterns": patterns,
            "fork_candidates": fork_candidates,
            "improvement_queue_ready": len(patterns) > 0,
        }
    except Exception as e:
        return {"error": str(e), "health": {}, "patterns": [], "fork_candidates": []}


@mcp.tool()
def generate_skill_improvement_proposal(skill_name: str, dimension: str = "") -> dict:
    """Generate a 5-part evaluable improvement proposal for a skill with a detected pattern.

    Reads the current improvement queue (state/skill-improvement-queue.json), finds the
    pattern for skill_name (optionally filtered by dimension), loads the skill SKILL.md,
    and produces a structured proposal in the 5-part evaluable format. Queues it via
    add_proposal — requires human approval before apply_proposal can act on it.

    Returns: {proposal_id, proposal_text, queued, pattern_used}
    Returns {no_pattern: true} if no qualifying pattern exists for this skill.
    """
    return _generate_skill_improvement_proposal(skill_name, dimension)


@mcp.tool()
def select_skill_arm(skill_name: str, task_type: str = "other", developer_stage: str = "COMPETENT") -> dict:
    """LinUCB arm selection for a skill with an active candidate competition.

    When a skill has been forked (dropped below 40 points and a candidate was generated),
    this selects which version to use for the current task based on task_type and
    developer_stage context.

    Returns: {arm: "current"|"candidate", candidate_id, reason}
    Returns {arm: "current", reason: "no candidate"} if no competition is active.
    """
    return _select_skill_arm(skill_name, task_type, developer_stage)


@mcp.tool()
def record_arm_reward(
    skill_name: str,
    arm_index: int,
    reward: float,
    task_type: str = "other",
    developer_stage: str = "COMPETENT",
    session_n: int = 0,
) -> dict:
    """Record a reward signal for a LinUCB arm after observing session outcome.

    arm_index: 0=current/archived version, 1=candidate version.
    reward: positive (STABLE/VALIDATED) or negative (GAP/SCOPE_MISS weight).
    Updates arm statistics and triggers promotion/reversion check after 5 sessions.

    Returns: {updated, promoted, reverted, promotion_note?, reversion_note?}
    """
    return _record_arm_reward(skill_name, arm_index, reward, task_type, developer_stage, session_n)


@mcp.tool()
def mark_proposal_applied(proposal_id: str, session_n: int) -> dict:
    """Mark a skill improvement proposal as applied so the falsifier monitor can watch it.

    Call this immediately after apply_proposal succeeds on a SKILL-SIGNAL-* proposal.
    Updates applied-proposals.json with applied status and session number so
    session_start can check falsifier conditions in future sessions.

    Returns: {marked: bool, proposal_id}
    """
    marked = _mark_proposal_applied(proposal_id, session_n)
    return {"marked": marked, "proposal_id": proposal_id}


@mcp.tool()
def request_external_review(scope: str, notes: str = "") -> dict:
    """Package the current youk state for external review by a discriminator.

    Creates state/relay/REVIEW-<yyyy-mm-dd>/ containing:
      - MANIFEST.md: git SHA, date, scope, notes, R10 metric block
      - evidence bundle: health JSON, PENDING.md, audit tail (last 10 entries),
        plus target SKILL.md when scope=SKILL
      - RUBRIC.md: copied from adversarial-planning/SKILL.md Discriminator
        Grading-Rubric Template (single source of truth, copied at call time)

    scope: GATE | HEALTH | SKILL | ROADMAP
    notes: optional context for the discriminator (e.g. "focus on CAP-7 acceptance")

    Returns: folder_path, instructions for handing off to external grader.
    Does NOT affect org_score — scoring the fix for self-scoring recreates the disease.
    """
    return _build_review_bundle(scope, notes, youk_root=YOUK_ROOT, claude_root=CLAUDE_ROOT)


# ---------------------------------------------------------------------------
# Self-revision meta-loop (Task 2) — youk revises its own judgment-sets
# ---------------------------------------------------------------------------

@mcp.tool()
def enroll_revisable_set(name: str, policy: str, initial_elements: list[str]) -> dict:
    """Register a judgment-set as revisable (grow/prune/both). Opt-in; default is frozen.

    Safety/fact sets (_ALLOWED_WRITE_ROOTS, _CODE_EXTS, secret rules, etc.) are hard-blocked
    and raise — self-revision there is a breach, not learning. Use only for sets that encode
    an OPINION youk could be wrong about (challenge angles, NFR questions, risk tiers).

    Returns {"enrolled", "policy", "element_count"} or {"error"} if hard-blocked.
    """
    try:
        return _rs_enroll(name, policy, initial_elements)
    except _EnrollmentError as e:
        return {"error": str(e), "enrolled": None}
    except ValueError as e:
        return {"error": str(e), "enrolled": None}


@mcp.tool()
def propose_set_revisions(
    name: str,
    recurring_gaps: list[str] | None = None,
    fire_counts: dict[str, int] | None = None,
    corrected: list[str] | None = None,
) -> dict:
    """Surface grow/prune candidates for an enrolled set — the LEARN/UNLEARN detectors.

    recurring_gaps: gap/unknown_unknown labels seen this window (grow input).
    fire_counts: element -> times it fired this window (prune input — 0 = dead).
    corrected: elements the developer explicitly rejected (prune input).

    Returns {"grow": [...], "prune": [...]}. Each candidate STILL owes a challenge pass
    before you call apply_set_revision — this only proposes, it does not apply.
    """
    grow = _detect_grow_candidates(name, recurring_gaps or []) if recurring_gaps else []
    prune = (
        _detect_prune_candidates(name, fire_counts, corrected)
        if fire_counts is not None else []
    )
    return {"set": name, "grow": grow, "prune": prune}


@mcp.tool()
def apply_set_revision(name: str, action: str, element: str, driver: str) -> dict:
    """Apply a grow or prune to an enrolled set — AFTER the candidate survived challenge.

    action: "grow" (add element) | "prune" (remove element) | "revert" (undo last change)

    The candidate-challenge gate is machine-checked, not self-certified: grow/prune are
    refused unless the challenge-ran flag for this session is present (same mechanism as
    check_challenge_gate — a caller cannot bypass it by asserting a boolean). Run
    route_to_skill('challenge') + mark_challenge_ran first. Ignored for revert.

    Every mutation is versioned; use action="revert" to roll back (the human veto / revert
    floor). Autonomous apply + after-the-fact veto.
    """
    if action == "revert":
        return _rs_revert(name)

    # Machine-checked challenge gate: read the flag, don't trust a caller boolean.
    challenge_ran = False
    try:
        import json as _json
        flag_file = YOUK_ROOT / "state" / "challenge-ran.json"
        if flag_file.exists():
            data = _json.loads(flag_file.read_text())
            challenge_ran = data.get("slug", "") == _get_session_slug()
    except Exception:
        pass
    if not challenge_ran:
        return {"ok": False, "reason": "revision must survive challenge before apply — "
                "run route_to_skill('challenge') + mark_challenge_ran, then retry"}

    if action == "grow":
        return _rs_learn_add(name, element, driver)
    if action == "prune":
        return _rs_unlearn_prune(name, element, driver)
    return {"ok": False, "reason": f"unknown action '{action}'; use grow|prune|revert"}


@mcp.tool()
def get_revisable_sets() -> dict:
    """List enrolled revisable sets and their current state (for session_end accountability)."""
    names = _rs_list_enrolled()
    return {"enrolled": names, "sets": {n: _rs_get_set(n) for n in names}}


# ---------------------------------------------------------------------------
# Steering vocabulary (Task 3) — steer Claude in its own terms, not with personas
# ---------------------------------------------------------------------------

@mcp.tool()
def get_steering_vocab(label: str) -> dict:
    """Get learned behavior decompositions for a quality label ("rigorous", "L9", "thorough").

    Returns {"label", "behaviors": [{behavior, confidence, weight, count}], "learned": bool}.
    - learned=True: steer with these concrete behaviors (weighted by confidence — verified >
      approved; corrected excluded) instead of injecting the raw label.
    - learned=False: youk hasn't learned this label yet — elicit a fresh decomposition from
      the model for THIS task (point-of-use), then record it below. Do NOT fall back to the
      stereotype the bare label evokes.
    """
    return _get_steering(label)


@mcp.tool()
def record_steering_decomposition(
    label: str, behavior: str, task_context: str, confidence: str = "approved"
) -> dict:
    """Record that a quality label decomposed into a concrete behavior for a task.

    confidence: "verified" (the work it steered passed an objective check — tests/bug real),
    "approved" (user accepted the result), or "corrected" (user rejected this decomposition —
    a veto that drops it from future steering). Nothing is rejected at write time; quality is
    applied at read time via get_steering_vocab's weighting, so the vocabulary fills fast and
    the strictness stays tunable. Call after work completes with the honest confidence.
    """
    return _record_decomposition(label, behavior, task_context, confidence=confidence)


if __name__ == "__main__":
    mcp.run(transport=_server_args.transport)
