"""youk-code MCP server — software engineering skills."""
from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from mcp.server.fastmcp import FastMCP

from nfr import run_nfr_check
from skills import route_to_skill as _route_to_skill, get_skill_list, get_skill_content, get_skill_fast_path
from review import check_commit_quality as _check_commit_quality
from skill_loader import list_skills as _list_skills
from skill_gen import generate_skill as _generate_skill, assess_skill as _assess_skill, detect_skill_gaps as _detect_skill_gaps

CLAUDE_ROOT = Path("/claude")

mcp = FastMCP("youk-code")


@mcp.tool()
def nfr_check(task: str, size: str = "M") -> dict:
    """
    Run an NFR (Non-Functional Requirements) check on a task.

    XS/S: 2-question fast path, no API call, instant.
    M: 4-question block via API (~10-15s).
    L/XL: Full 5-phase check via API (~20-30s).

    task: What you're about to build.
    size: XS, S, M, L, or XL. Defaults to M.

    Returns: size, mode, decisions, connections, raw_output.
    """
    result = run_nfr_check(task, size)
    return {
        "task": result.task,
        "size": result.size.value,
        "mode": result.mode,
        "decisions": result.decisions,
        "connections": result.connections,
        "markdown": result.to_markdown(),
    }


@mcp.tool()
def route_to_skill(skill: str, task: str, context: dict | None = None) -> str:
    """
    Run any skill against a task by loading its SKILL.md as the system prompt.
    Phase tokens are preserved in the output so you can use them for audit.

    skill: Skill name (e.g. 'pm-review', 'write-spec', 'adr', 'stress-test', 'humanize', 'learn').
    task: Task description for the skill.
    context: Optional key-value pairs (e.g. {'framework': 'Gradio', 'project': 'canopy'}).

    Returns: Skill output in native format.
    """
    return _route_to_skill(skill, task, context)


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
    Generate a new SKILL.md from signals — project context, audit gaps, or best-practice patterns.

    name: kebab-case skill name (e.g. 'security-review', 'python-ml')
    purpose: What the skill does and when it triggers (1-3 sentences)
    project_context: Optional dict — project type, stack, domain patterns, detected signals
    signal_type: "engineer_request" | "demand_gap" | "project_type_gap" | "best_practices_gap"
      - demand_gap: route_task referenced this skill but no SKILL.md exists
      - project_type_gap: project type detected, no domain skill exists
      - best_practices_gap: cross-project pattern not encoded in any skill

    Returns draft content + proposal dict. Does NOT write to disk.
    Review content, then call youk-core.add_proposal() + apply_proposal() to write.
    """
    return _generate_skill(name, purpose, project_context, signal_type)


@mcp.tool()
def assess_skill(skill_name: str) -> dict:
    """
    Assess how well an existing skill covers its domain.

    Reads the skill's SKILL.md, recent audit evidence (sessions where skill was used),
    and cross-project best-practices knowledge. Returns gaps and proposed SKILL_EDIT additions.

    skill_name: Name of the skill to assess (e.g. 'dev-loop', 'adr')

    Returns:
    - coverage_score: 0-10
    - strengths: what the skill covers well
    - gaps: specific gaps with evidence
    - proposed_additions: list of SKILL_EDIT additions ready for add_proposal()

    Each item in proposed_additions maps directly to a youk-core.add_proposal() call.
    """
    return _assess_skill(skill_name)


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
