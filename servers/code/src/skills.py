from __future__ import annotations
import sys
sys.path.insert(0, "/shared")

from skill_loader import load_skill, list_skills, load_skill_fast_path


def route_to_skill(skill_name: str, task: str, context: dict | None = None) -> dict:
    """
    Load a skill and return context for in-session execution by Claude Code.

    Does NOT call the Anthropic API — returns skill_content + task so the
    active Claude Code session executes the skill with full conversation
    context, tools, and history. This is both more capable and requires no
    separate API credits.

    Returns: {mode, skill_name, skill_content, task, context, instruction}
    """
    try:
        skill_content = load_skill(skill_name)
    except FileNotFoundError as e:
        return {"error": str(e)}

    return {
        "mode": "in_session",
        "skill_name": skill_name,
        "skill_content": skill_content,
        "task": task,
        "context": context or {},
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
