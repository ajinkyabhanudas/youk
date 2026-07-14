from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, "/shared")

import yaml
from skill_loader import load_skill, load_skill_with_context, list_skills, load_skill_fast_path

_SESSION_STATE = Path("/youk/state/session.json")
_SKILL_GRAPH = Path("/youk/knowledge/skill-graph.yaml")


def _read_session_stack_context() -> dict:
    """Read stack/framework/domain written by session_start() — zero tokens."""
    try:
        if _SESSION_STATE.exists():
            state = json.loads(_SESSION_STATE.read_text())
            return {
                "stack": state.get("stack"),
                "framework": state.get("framework"),
                "domain": state.get("domain"),
            }
    except Exception:
        pass
    return {"stack": None, "framework": None, "domain": None}


def _get_preceding_skills(skill_name: str) -> list[str]:
    """Return skill names that precede skill_name per skill-graph.yaml."""
    try:
        if not _SKILL_GRAPH.exists():
            return []
        graph = yaml.safe_load(_SKILL_GRAPH.read_text())
        return [
            name
            for name, meta in (graph.get("skills") or {}).items()
            if skill_name in (meta.get("precedes") or [])
        ]
    except Exception:
        return []


def _read_and_clear_pending_handoff(skill_name: str) -> str | None:
    """Return handoff content from preceding skills, then clear it from session.json."""
    try:
        if not _SESSION_STATE.exists():
            return None
        state = json.loads(_SESSION_STATE.read_text())
        pending = state.get("pending_handoff", {})
        if not pending:
            return None
        preceding = _get_preceding_skills(skill_name)
        chunks = [
            f"## Handoff from {skill}\n\n{pending.pop(skill)}"
            for skill in preceding
            if skill in pending
        ]
        if not chunks:
            return None
        state["pending_handoff"] = pending
        _SESSION_STATE.write_text(json.dumps(state, indent=2))
        return "\n\n".join(chunks)
    except Exception:
        return None


def write_skill_handoff(from_skill: str, content: str) -> dict:
    """Write skill output to pending_handoff in session.json for consumption by successor skills."""
    try:
        state = json.loads(_SESSION_STATE.read_text()) if _SESSION_STATE.exists() else {}
        state.setdefault("pending_handoff", {})[from_skill] = content
        _SESSION_STATE.write_text(json.dumps(state, indent=2))
        return {"saved": True, "from_skill": from_skill, "content_length": len(content)}
    except Exception as e:
        return {"saved": False, "error": str(e)}


_ROUTE_TASK_RAN = Path("/youk/state/route-task-ran.json")
_SESSION_OPEN = Path("/youk/state/session-open.json")

# Skills that require route_task to have run first (M+ gate)
_GATED_SKILLS = {"dev-loop"}


def _routing_ran_this_session() -> bool:
    """Return True if route_task was called at any point this session for the current slug."""
    if not _ROUTE_TASK_RAN.exists():
        return False
    try:
        slug = "unknown"
        if _SESSION_OPEN.exists():
            slug = json.loads(_SESSION_OPEN.read_text()).get("slug", "unknown")
        raw = json.loads(_ROUTE_TASK_RAN.read_text())
        entries = raw if isinstance(raw, list) else [raw]
        return any(e.get("slug") == slug for e in entries)
    except Exception:
        return False


def route_to_skill(skill_name: str, task: str, context: dict | None = None) -> dict:
    """
    Load a skill and return context for in-session execution by Claude Code.

    Does NOT call the Anthropic API — returns skill_content + task so the
    active Claude Code session executes the skill with full conversation
    context, tools, and history. This is both more capable and requires no
    separate API credits.

    context keys: stack (e.g. "python"), framework (e.g. "django"), domain (e.g. "saas")
    When stack/framework/domain are present, appends matching overlay files from
    references/stacks/ and domain/ — adds ~300-500 tokens, not the full knowledge base.

    Returns: {mode, skill_name, skill_content, task, context, instruction}
    For gated skills (dev-loop): returns {blocked=True, reason} if route_task hasn't run.
    """
    # Hard gate: dev-loop requires route_task to have run this session
    if skill_name in _GATED_SKILLS and not _routing_ran_this_session():
        return {
            "blocked": True,
            "skill_name": skill_name,
            "reason": (
                f"route_to_skill('{skill_name}') blocked — route_task has not run this session. "
                "Call route_task first, then nfr_check + check_nfr_gate, then dev-loop. "
                "This gate exists to ensure M+ tasks are challenged and NFR-checked before implementation."
            ),
        }

    # Merge: explicit context overrides session-detected values
    session_ctx = _read_session_stack_context()
    ctx = {**session_ctx, **(context or {})}
    try:
        skill_content = load_skill_with_context(
            skill_name,
            stack=ctx.get("stack"),
            framework=ctx.get("framework"),
            domain=ctx.get("domain"),
        )
    except FileNotFoundError as e:
        return {"error": str(e)}

    handoff = _read_and_clear_pending_handoff(skill_name)
    if handoff:
        skill_content = handoff + "\n\n---\n\n" + skill_content

    return {
        "mode": "in_session",
        "skill_name": skill_name,
        "skill_content": skill_content,
        "task": task,
        "context": ctx,
        "instruction": (
            f"You have received the '{skill_name}' skill. "
            "Apply it now using your full session context, tools, and conversation history. "
            "Follow every phase and quality bar defined in skill_content."
        ),
    }


def get_skill_list() -> list[dict]:
    """Return all available skills with metadata."""
    return list_skills()


def get_skill_content(skill_name: str) -> str:
    """Return full SKILL.md content for a named skill."""
    try:
        return load_skill(skill_name)
    except FileNotFoundError as e:
        return f"[ERROR] {e}"


def get_skill_fast_path(skill_name: str) -> str:
    """Return the fast-path rules for a skill if defined."""
    fast_path = load_skill_fast_path(skill_name)
    if fast_path:
        return fast_path
    return f"No fast-path defined for skill: {skill_name}"
