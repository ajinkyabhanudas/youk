from __future__ import annotations
import os
import sys
sys.path.insert(0, "/shared")

from pathlib import Path
from skill_loader import load_skill, list_skills, load_skill_fast_path

def _resolve_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    fallback = Path("/claude/.anthropic/api_key")
    return fallback.read_text().strip() if fallback.exists() else ""

try:
    import anthropic
    _api_key = _resolve_api_key()
    _client = anthropic.Anthropic(api_key=_api_key) if _api_key else None
except Exception:
    _client = None

_MODEL = "claude-sonnet-4-6"


def route_to_skill(skill_name: str, task: str, context: dict | None = None) -> str:
    """
    Run a skill against a task by loading its SKILL.md as the system prompt.
    Returns the skill output in its native format (phase tokens preserved).
    """
    if not _client:
        return "[ERROR] API client not available — check ANTHROPIC_API_KEY"

    try:
        skill_content = load_skill(skill_name)
    except FileNotFoundError as e:
        return f"[ERROR] {e}"

    context_str = ""
    if context:
        context_str = "\n".join(f"{k}: {v}" for k, v in context.items())

    user_msg = f"Task: {task}"
    if context_str:
        user_msg += f"\n\nContext:\n{context_str}"

    try:
        response = _client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=skill_content,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text
    except Exception as e:
        return f"[ERROR] Skill execution failed — {type(e).__name__}: set ANTHROPIC_API_KEY and run make install to enable skill execution from Docker ({e})"


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
