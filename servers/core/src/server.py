"""youk-core MCP server — session, routing, self-heal."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from session import start_session, end_session, task_checkpoint as _task_checkpoint, update_convergence_state as _update_convergence_state
from routing import route_task as _route_task
from health import (
    run_health_check_with_skill_signals,
    add_proposal as _add_proposal,
    apply_proposal as _apply_proposal,
    _load_pending_proposals,
)
from guardrails import check_knowledge_write, check_destructive_command, HardRuleViolation
from nfr_gate import check_nfr_gate as _check_nfr_gate
from challenge_gate import check_challenge_gate as _check_challenge_gate
from intent import optimize_intent as _optimize_intent
from compaction import build_brief, write_contracts
from tokens import init_token_tracker, record_checkpoint

YOUK_ROOT = Path("/youk")
CLAUDE_ROOT = Path("/claude")

_TOOL_CALL_COUNT_FILE = YOUK_ROOT / "state" / "tool-call-count.json"


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


mcp = FastMCP(
    "youk-core",
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
    assess_skill("challenge") before closing — mid-session self-correction.

    challenge_rounds: Total ITERATE phases across all challenge invocations this session.
    Written as ChallengeRounds: N. Low values with loop_correction_detected=True = early exit signal.

    Returns: knowledge_extracted, proposals_added, audit_written,
             session_close_cluster_detected, contracts_saved.
    """
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
        open_file_lc = YOUK_ROOT / "state" / "session-open.json"
        slug_lc = ""
        if open_file_lc.exists():
            slug_lc = _jc.loads(open_file_lc.read_text()).get("slug", "")
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
    )


@mcp.tool()
def optimize_intent(raw_input: str, clarified_context: str | None = None) -> dict:
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
) -> dict:
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

    Returns: size, ceremony, skills, nfr_mode, warnings, plan_hook, blocked, collapsing_question.
    When blocked=true: stop. Surface collapsing_question. Do not invoke any skill.
    """
    decision = _route_task(task, skills_already_invoked or [], intent_brief)
    result = decision.to_dict()
    # Write routing flag so session_start can detect when routing ran this session.
    # Analogous to nfr-check-ran.json — enables "routing was missed" recovery at next open.
    if not result.get("blocked"):
        import hashlib as _hashlib
        import json as _json
        from datetime import datetime as _dt
        flag_file = YOUK_ROOT / "state" / "route-task-ran.json"
        open_file = YOUK_ROOT / "state" / "session-open.json"
        slug = "unknown"
        if open_file.exists():
            try:
                slug = _json.loads(open_file.read_text()).get("slug", "unknown")
            except Exception:
                pass
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
        existing = [e for e in existing if e.get("slug") == slug]
        existing.append(new_entry)
        flag_file.write_text(_json.dumps(existing))
    result["calls_since_compact"] = _increment_tool_call_count()
    return result


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
def check_nfr_gate(task: str, size: str, nfr_decision_block: str | None = None) -> dict:
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
    # Write NFR-ran flag so hook doesn't re-nudge this session.
    # Slug from session-open.json — task text is natural language, not a file path.
    if not result["blocked"] and size in {"M", "L", "XL"}:
        try:
            import json as _json
            from datetime import datetime as _dt
            slug = "unknown"
            open_file = YOUK_ROOT / "state" / "session-open.json"
            if open_file.exists():
                slug = _json.loads(open_file.read_text()).get("slug", "unknown")
            flag_file = YOUK_ROOT / "state" / "nfr-check-ran.json"
            flag_file.write_text(_json.dumps({
                "slug": slug,
                "ts": _dt.utcnow().isoformat(),
            }))
        except Exception:
            pass
    return result


@mcp.tool()
def mark_challenge_ran(task: str, angles_checked: list[str], mode: str = "full") -> dict:
    """
    Record that the challenge skill has run and passed for the current M+ task.
    Call this after the challenge loop is dry — when all required angles have been covered.

    angles_checked: List of angle names that were run (e.g. ["framing", "scope",
        "assumptions", "opportunity", "structural", "operational", "experiential",
        "adversarial", "temporal", "outcome", "semantic"]).
        Required — omitting it returns blocked=True.
    mode: Challenge mode — "full" (default), "quick", "silent", or "plan".
        Determines which angles are required. "full" requires all 11 angles;
        "quick"/"silent"/"plan" require the 4 lenses only.

    Each call increments the challenge_rounds counter — session_end reads this
    directly from state rather than trusting Claude's passed-in value.

    Returns: {"recorded": bool, "challenge_rounds": int, "angles_validated": bool}
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
        slug = "unknown"
        open_file = YOUK_ROOT / "state" / "session-open.json"
        if open_file.exists():
            slug = _json.loads(open_file.read_text()).get("slug", "unknown")
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
        flag_file.write_text(_json.dumps({
            "slug": slug,
            "task": task,
            "ts": _dt.utcnow().isoformat(),
            "rounds": new_rounds,
            "angles_validated": True,
            "mode": mode,
        }))
        return {"recorded": True, "challenge_rounds": new_rounds, "angles_validated": True}
    except Exception:
        return {"recorded": False, "challenge_rounds": 0, "angles_validated": False}


@mcp.tool()
def check_challenge_gate(task: str, size: str) -> dict:
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
            open_file = YOUK_ROOT / "state" / "session-open.json"
            if open_file.exists():
                current_slug = _json.loads(open_file.read_text()).get("slug", "")
                challenge_ran = data.get("slug", "") == current_slug
    except Exception:
        pass

    result = _check_challenge_gate(task, size, challenge_ran)
    if not result["blocked"] and size in {"M", "L", "XL"}:
        try:
            import json as _json
            from datetime import datetime as _dt
            slug = "unknown"
            open_file = YOUK_ROOT / "state" / "session-open.json"
            if open_file.exists():
                slug = _json.loads(open_file.read_text()).get("slug", "unknown")
            flag_file = YOUK_ROOT / "state" / "challenge-gate-passed.json"
            flag_file.write_text(_json.dumps({
                "slug": slug,
                "ts": _dt.utcnow().isoformat(),
            }))
        except Exception:
            pass
    return result


@mcp.tool()
def check_loop_dry(task: str = "") -> dict:
    """
    Structural sensor for whether the last challenge loop was dry.

    Reads challenge-ran.json (rounds counter written by mark_challenge_ran) and
    the loop_correction state derived from the summary scan in session_end. Returns
    a per-session verdict without requiring Claude to reconstruct this from memory.

    Called automatically by session_end when close_cluster=True. Also exposed as an
    explicit MCP tool so the done skill can call it for transparency at /done.

    task: optional — the task label to validate against the recorded challenge task.

    Returns: {
        "dry": bool — True when challenge ran AND no correction detected this session,
        "rounds": int — number of mark_challenge_ran calls this session,
        "challenge_ran": bool — whether challenge ran at all,
        "loop_correction_in_state": bool — whether a correction was written to state,
        "session_slug": str,
    }
    """
    try:
        import json as _json
        flag_file = YOUK_ROOT / "state" / "challenge-ran.json"
        open_file = YOUK_ROOT / "state" / "session-open.json"
        correction_file = YOUK_ROOT / "state" / "loop-correction.json"

        current_slug = ""
        if open_file.exists():
            current_slug = _json.loads(open_file.read_text()).get("slug", "")

        rounds = 0
        challenge_ran = False
        if flag_file.exists():
            data = _json.loads(flag_file.read_text())
            if data.get("slug") == current_slug:
                rounds = data.get("rounds", 0)
                challenge_ran = rounds > 0

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

        dry = challenge_ran and not correction_in_state
        return {
            "dry": dry,
            "rounds": rounds,
            "challenge_ran": challenge_ran,
            "loop_correction_in_state": correction_in_state,
            "session_slug": current_slug,
        }
    except Exception:
        return {
            "dry": False,
            "rounds": 0,
            "challenge_ran": False,
            "loop_correction_in_state": False,
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
    )
    _add_proposal(proposal)
    return {"proposal_id": proposal.id, "status": "added", "target": target}


@mcp.tool()
def get_proposals() -> dict:
    """
    Return all pending self-heal proposals awaiting founder review.
    Surface these when session_start returns pending_proposals_count > 0.

    Returns: proposals (list with id, target, change, reason, before, after, status).
    """
    proposals = _load_pending_proposals()
    return {
        "count": len(proposals),
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
            }
            for p in proposals
        ],
    }


@mcp.tool()
def apply_proposal(
    proposal_id: str,
    confirmed: bool = False,
    safe_types: list[str] | None = None,
) -> dict:
    """
    Apply an approved self-heal proposal.

    confirmed must be True to write anything. Pass False to preview what would change.

    safe_types: optional allowlist of change_type values that may be auto-applied.
    Any proposal whose change_type is NOT in safe_types returns blocked=True and
    must be reviewed manually. Use safe_types=["SKILL_EDIT","FILE_CREATE"] for
    autonomous /improve runs. Omit safe_types (or pass None) to apply any type
    after explicit human review.

    Examples:
      apply_proposal("PENDING-123", confirmed=True)  # explicit human apply, any type
      apply_proposal("PENDING-123", confirmed=True, safe_types=["SKILL_EDIT","FILE_CREATE"])  # /improve safe path

    proposal_id: The PENDING-XXX identifier from get_proposals().
    Returns: applied, blocked, change_type, change_summary, message.
    """
    try:
        return _apply_proposal(proposal_id, confirmed, safe_types)
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
    cs_file = YOUK_ROOT / "state" / "convergence-state.json"
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
    """Interpretation patterns — how Ajinkya's phrases map to actual intent."""
    ui_file = YOUK_ROOT / "knowledge" / "interpretation" / "user-intent.md"
    return ui_file.read_text() if ui_file.exists() else "No interpretation patterns yet."


@mcp.resource("youk://knowledge/proposals")
def get_proposals_resource() -> str:
    """Pending self-heal proposals."""
    pending = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"
    return pending.read_text() if pending.exists() else "No pending proposals."


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


if __name__ == "__main__":
    mcp.run()
