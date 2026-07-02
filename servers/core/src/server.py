"""youk-core MCP server — session, routing, self-heal."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from session import start_session, end_session
from routing import route_task as _route_task
from health import (
    run_health_check_with_skill_signals,
    add_proposal as _add_proposal,
    apply_proposal as _apply_proposal,
    _load_pending_proposals,
)
from guardrails import check_knowledge_write, check_destructive_command, HardRuleViolation
from intent import optimize_intent as _optimize_intent
from compaction import build_brief, write_contracts
from tokens import init_token_tracker, record_checkpoint

YOUK_ROOT = Path("/youk")

mcp = FastMCP("youk-core")


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

    Returns: knowledge_extracted, proposals_added, audit_written,
             session_close_cluster_detected, contracts_saved.
    """
    try:
        check_knowledge_write(summary)
    except HardRuleViolation as e:
        return {"error": str(e), "blocked": True, "rule_id": e.rule_id}

    return end_session(summary, commits_made, explicit_contracts, skills_used, close_cluster, skill_gaps)


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
    """
    return _optimize_intent(raw_input, clarified_context)


@mcp.tool()
def route_task(task: str, skills_already_invoked: list[str] | None = None) -> dict:
    """
    Determine the size and skill routing for a task. Read this before acting —
    apply the returned ceremony level silently without announcing the routing.

    task: One-sentence description of what needs to be done.
    skills_already_invoked: Skills already run this session (to avoid double-triggering warnings).

    Returns: size, ceremony, skills (suggested), nfr_mode, warnings (soft rule violations).
    """
    decision = _route_task(task, skills_already_invoked or [])
    return decision.to_dict()


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
def apply_proposal(proposal_id: str, confirmed: bool = False) -> dict:
    """
    Apply an approved self-heal proposal.

    HARD RULE: confirmed must be True, set only when the founder has explicitly
    reviewed and approved this specific proposal. This tool will error if
    confirmed=False — that is intentional enforcement, not a bug.

    proposal_id: The PENDING-XXX identifier from get_proposals().
    confirmed: Must be True to proceed. Pass False to see what would happen.

    Returns: applied, target_file, change_summary.
    """
    try:
        return _apply_proposal(proposal_id, confirmed)
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
def compact_context(project_dir: str) -> dict:
    """
    Build a structured context brief from youk's knowledge store.

    Call this proactively when the session is getting long (25+ exchanges) —
    BEFORE Claude's generic auto-compaction triggers. The brief preserves
    Contracts verbatim, Decisions as key-fact + rationale, and drops
    Clarifications entirely. It is generated from structured files, not
    by summarizing conversation, so no information is lost.

    Use the returned 'brief' as your working context anchor: state it
    explicitly in your response so it appears in recent context and
    survives the next compaction cycle.

    project_dir: The current project directory (same as session_start).

    Returns: brief (pin this), contracts_count, decisions_count, instruction.
    """
    return build_brief(project_dir)


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


if __name__ == "__main__":
    mcp.run()
