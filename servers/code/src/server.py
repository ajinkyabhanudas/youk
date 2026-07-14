"""youk-code MCP server — software engineering skills."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from nfr import run_nfr_check
from skills import route_to_skill as _route_to_skill, write_skill_handoff as _write_skill_handoff, get_skill_list, get_skill_content, get_skill_fast_path
from review import check_commit_quality as _check_commit_quality
from skill_loader import list_skills as _list_skills
from skill_gen import generate_skill as _generate_skill, assess_skill as _assess_skill, detect_skill_gaps as _detect_skill_gaps, generate_stack_overlay as _generate_stack_overlay, analyze_stack_for_skills as _analyze_stack_for_skills

CLAUDE_ROOT = Path("/claude")

mcp = FastMCP("youk-code")


@mcp.tool()
def nfr_check(task: str, size: str = "M") -> dict:
    """
    Run an NFR (Non-Functional Requirements) check on a task.

    XS/S: 2-question fast path, instant, no API call.
    M/L/XL: Returns in_session context — Claude Code answers the questions
             using full session context (no separate API call or credits needed).

    task: What you're about to build.
    size: XS, S, M, L, or XL. Defaults to M.

    XS/S returns: size, mode, decisions, connections, markdown.
    M+ returns: mode="in_session", skill_content, questions, instruction.
    """
    result = run_nfr_check(task, size)
    if isinstance(result, dict):
        return result  # in_session — Claude Code executes with full context
    return {
        "task": result.task,
        "size": result.size.value,
        "mode": result.mode,
        "decisions": result.decisions,
        "connections": result.connections,
        "markdown": result.to_markdown(),
    }


@mcp.tool()
def route_to_skill(skill: str, task: str, context: dict | None = None) -> dict:
    """
    Load a skill and return context for in-session execution by Claude Code.

    Returns skill_content (the SKILL.md) + task + instruction. The active
    Claude Code session executes the skill using full conversation context,
    tools, and history — no separate API call or credits needed.

    skill: Skill name (e.g. 'pm-review', 'write-spec', 'adr', 'stress-test', 'humanize', 'learn').
    task: Task description for the skill.
    context: Optional key-value pairs for additional context.

    Returns: {mode: "in_session", skill_name, skill_content, task, context, instruction}
    """
    return _route_to_skill(skill, task, context)


@mcp.tool()
def write_skill_handoff(from_skill: str, content: str) -> dict:
    """
    Write the output of a completed skill to session.json so the next skill in the chain can read it.

    After nfr-check completes, call this with from_skill="nfr-check" and a summary of NFR decisions.
    route_to_skill("dev-loop", ...) will then prepend this context automatically.
    Which handoffs flow where is governed by skill-graph.yaml precedes edges.

    from_skill: Name of the skill that just completed (e.g. "nfr-check", "code-review").
    content: Summary or key findings to pass forward (markdown OK).

    Returns: {saved, from_skill, content_length} or {saved: false, error}.
    """
    return _write_skill_handoff(from_skill, content)


@mcp.tool()
def check_commit_quality(message: str, file_paths: list[str] | None = None) -> dict:
    """
    Score a commit message against youk voice rules and check for credential files.

    HARD RULE enforced: if any file_path matches credential patterns (*.env, *secret*,
    *credential*, *api_key*, *password*), this tool returns blocked=True and the commit
    must not proceed.

    message: The git commit message to evaluate.
    file_paths: Optional list of files being committed (for credential check).

    Returns: score (0-100), violations, suggested_rewrite, blocked, block_reason.
    """
    result = _check_commit_quality(message, file_paths or [])
    return result.to_dict()


@mcp.tool()
def list_skills() -> list[dict]:
    """
    List all skills in the mounted claude/skills directory.

    Returns name, description, has_skill_md, has_fast_path, size_bytes per skill.
    has_skill_md: false means the skill directory exists but SKILL.md is missing — a gap.
    Use this to discover available skills and identify incomplete ones.
    """
    return _list_skills()


@mcp.tool()
def generate_skill(
    name: str,
    purpose: str,
    project_context: dict | None = None,
    signal_type: str = "engineer_request",
) -> dict:
    """
    Assemble context for in-session SKILL.md generation by Claude Code.

    Returns skill_schema + cross-project knowledge + example skills so the
    active Claude Code session writes the SKILL.md with full context.
    No separate API call or credits needed.

    name: kebab-case skill name (e.g. 'security-review', 'python-ml')
    purpose: What the skill does and when it triggers (1-3 sentences)
    project_context: Optional dict — project type, stack, domain patterns
    signal_type: "engineer_request" | "demand_gap" | "project_type_gap" | "best_practices_gap"

    Returns: {mode: "in_session", skill_schema, cross_project_knowledge, example_skills, instruction}
    Claude Code writes content, then calls add_proposal() + apply_proposal() to persist.
    """
    return _generate_skill(name, purpose, project_context, signal_type)


@mcp.tool()
def assess_skill(skill_name: str) -> dict:
    """
    Assemble context for in-session skill assessment by Claude Code.

    Returns SKILL.md + audit evidence + gap signals so the active Claude Code
    session assesses coverage gaps with full conversation context.
    No separate API call or credits needed.

    skill_name: Name of the skill to assess (e.g. 'dev-loop', 'adr')

    Returns: {mode: "in_session", skill_content, audit_evidence, gap_signals,
              assessment_criteria, instruction}
    Claude Code produces coverage_score, strengths, gaps, proposed_additions,
    then calls add_proposal() + apply_proposal() for each approved addition.
    """
    return _assess_skill(skill_name)


@mcp.tool()
def generate_stack_overlay(
    skill_name: str,
    stack: str,
    framework: str | None = None,
    domain: str | None = None,
    project_context: dict | None = None,
) -> dict:
    """
    Assemble context for in-session stack overlay generation.

    Returns the overlay schema + base skill content + cross-project knowledge
    so the active Claude Code session generates the overlay file in-session.
    No separate API call or credits needed.

    skill_name: Skill to generate overlay for (e.g. 'code-review', 'nfr-check', 'dev-loop')
    stack: Language-level stack (e.g. 'python', 'javascript', 'go')
    framework: Framework within stack (e.g. 'django', 'fastapi', 'nextjs') — takes priority over stack
    domain: Optional domain (e.g. 'saas', 'data') — used for context only
    project_context: Optional dict with project-specific context

    Returns: {mode: "in_session", overlay_schema, base_skill_content, cross_project_knowledge,
              write_path, instruction}
    Claude Code generates content, then calls add_proposal(FILE_CREATE) + apply_proposal(confirmed=True).
    """
    return _generate_stack_overlay(skill_name, stack, framework, domain, project_context)


@mcp.tool()
def detect_skill_gaps() -> dict:
    """
    Aggregate all signal sources to surface skills that need generation or evolution.

    Reads audit logs and existing SKILL.md files to find:
    - missing_skills: referenced in sessions but no SKILL.md exists (demand-driven gaps)
    - gap_signals: existing skills with SkillGap: entries in audit (evolution signals)
    - knowledge_gaps: best-practice patterns in cross-project.md not encoded in any skill

    Use this to decide what to generate or assess next. Returns a recommendation field.
    """
    return _detect_skill_gaps()


@mcp.tool()
def analyze_stack_for_skills(
    stack: str,
    framework: str | None = None,
    domain: str | None = None,
    repo_paths: list[str] | None = None,
    known_skills: list[str] | None = None,
    standard: str | None = None,
) -> dict:
    """
    Proactive stack-driven skill discovery (skill-forge Loop A).

    Unlike detect_skill_gaps() (reactive — reads audit history of what already went wrong),
    this asks what an ELITE engineer in this stack would need before any session proves it,
    and loops at a rising standard until even an imagined superior engineer has nothing to add.

    Returns mode='in_session' context. The Claude session performs the deep repo + live
    internet search and derives skills — no API call runs in the server.

    standard: the current elite-bar for this stack. None on first cycle; the session raises
        it each cycle and passes the raised bar back in. Convergence = bar stops rising.
    """
    return _analyze_stack_for_skills(stack, framework, domain, repo_paths, known_skills, standard)


@mcp.resource("youk://skills")
def list_available_skills() -> str:
    """List all available skills with health status and fast-path availability."""
    skills = get_skill_list()
    if not skills:
        return "No skills found at /claude/skills/"
    lines = ["# Available youk-code Skills\n"]
    for s in skills:
        fp = " [fast-path]" if s["has_fast_path"] else ""
        lines.append(f"- **{s['name']}**{fp}: {s['description']}")
    return "\n".join(lines)


@mcp.resource("youk://skills/{skill_name}")
def get_skill(skill_name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    return get_skill_content(skill_name)


@mcp.resource("youk://skills/{skill_name}/fast-path")
def get_fast_path(skill_name: str) -> str:
    """Return fast-path rules for the named skill."""
    return get_skill_fast_path(skill_name)


@mcp.resource("youk://context/{project}")
def get_project_context(project: str) -> str:
    """Return L2 project context file for the named project."""
    # Try common locations
    candidates = [
        CLAUDE_ROOT / "projects" / f"-Users-ajinkya-Desktop-{project}" / "memory",
    ]
    for candidate in candidates:
        if candidate.exists():
            for f in candidate.iterdir():
                if f.suffix == ".md":
                    return f.read_text()
    return f"No context found for project: {project}"


if __name__ == "__main__":
    mcp.run()
