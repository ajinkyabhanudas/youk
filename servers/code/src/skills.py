from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, "/shared")

from skill_loader import load_skill, load_skill_with_context, list_skills, load_skill_fast_path

_SESSION_STATE = Path("/youk/state/session.json")


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
    """
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
