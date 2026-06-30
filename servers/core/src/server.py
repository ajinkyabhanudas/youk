"""youk-core MCP server — session, routing, self-heal."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from session import start_session, end_session
from routing import route_task as _route_task
from health import run_health_check, apply_proposal as _apply_proposal, _load_pending_proposals
from guardrails import check_knowledge_write, check_destructive_command, HardRuleViolation
from intent import optimize_intent as _optimize_intent
from compaction import build_brief

YOUK_ROOT = Path("/youk")

mcp = FastMCP("youk-core")


@mcp.tool()
def session_start(project_dir: str) -> dict:
    """
    Start a youk session. Loads L1/L2/L3 context from the project directory.
    Call this at the beginning of every session — fold the result naturally into
    your first response without announcing 'context loaded'.

    Returns: project, resume_point, context_health, pending_proposals_count,
             session_counter, health_check_due.
    """
    state = start_session(project_dir)
    return state.to_dict()


@mcp.tool()
def session_end(
    summary: str,
    commits_made: bool = False,
    explicit_contracts: list[str] | None = None,
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

    Returns: knowledge_extracted, proposals_added, audit_written,
             session_close_cluster_detected, contracts_saved.
    """
    try:
        check_knowledge_write(summary)
    except HardRuleViolation as e:
        return {"error": str(e), "blocked": True, "rule_id": e.rule_id}

    return end_session(summary, commits_made, explicit_contracts)


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
def self_heal() -> dict:
    """
    Run a health analysis on the last 30 days of audit logs.
    Identifies skill usage patterns, skipped sessions, and generates improvement proposals.
    Proposals are written to knowledge/proposals/PENDING.md — never auto-applied.

    Returns: org_score, sessions_analyzed, findings, proposals_added.
    """
    report = run_health_check()
    return {
        "org_score": report.org_score,
        "sessions_analyzed": report.sessions_analyzed,
        "findings": report.findings,
        "proposals_count": len(report.proposals),
        "report_markdown": report.to_markdown(),
    }


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
