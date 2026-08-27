from __future__ import annotations
import json
import sys
from pathlib import Path

YOUK_ROOT = Path("/youk")
sys.path.insert(0, "/shared")

import yaml
from ceremony_sequencer import record_gate as _record_gate
from skill_reentry import check_reentry as _check_reentry
from skill_loader import (
    load_skill, load_skill_with_context, list_skills, load_skill_fast_path,
    extract_frontmatter_field,
)

_SESSION_STATE = YOUK_ROOT / "state" / "session.json"
_SKILL_GRAPH = YOUK_ROOT / "knowledge" / "skill-graph.yaml"
_RATIONALE_STATE = YOUK_ROOT / "state" / "skill-rationale-state.json"
_RATIONALE_SUPPRESS_AFTER = 3  # suppress teaching after developer pre-empts N times

# Detect at load time whether this container can write to the state directory.
# youk-code mounts /youk read-only by design — writes to state/ must degrade gracefully.
def _state_is_writable() -> bool:
    try:
        probe = _SESSION_STATE.parent / ".write-probe"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False

_STATE_WRITABLE = _state_is_writable()

# Sections that are reference-only (not needed for in-session execution).
# Quality Bars and all phases above them are preserved — these sections are below.
_STRIP_SECTIONS = (
    "## Example Flows",
    "## Hiring Validation",
    "## Reference Files",
    "## Examples",
    "## Validation",
)


def _strip_reference_sections(content: str) -> str:
    """
    Remove reference-only sections from SKILL.md before returning to Claude.

    Preserves: frontmatter, description, invocation grammar, phases, quality bars,
    stack coverage system, and any handoff blocks.
    Strips: Example Flows, Hiring Validation, Reference Files — pure reader content,
    not needed for in-session skill execution. Saves 35-50% per skill load.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    skip = False
    for line in lines:
        stripped = line.rstrip()
        if any(stripped == section or stripped.startswith(section + "\n") for section in _STRIP_SECTIONS):
            skip = True
        elif skip and stripped.startswith("## ") and not any(stripped == s for s in _STRIP_SECTIONS):
            # New top-level section that is NOT a strip target — resume
            skip = False
        if not skip:
            result.append(line)
    return "".join(result).rstrip() + "\n"


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
        if _STATE_WRITABLE:
            _SESSION_STATE.write_text(json.dumps(state, indent=2))
        return "\n\n".join(chunks)
    except Exception:
        return None


def _infer_severity(content: str) -> str:
    """Infer highest severity from handoff content without an API call."""
    upper = content.upper()
    if "BLOCKING" in upper:
        return "BLOCKING"
    if "HIGH" in upper:
        return "HIGH"
    return "MEDIUM"


def write_skill_handoff(from_skill: str, content: str) -> dict:
    """Write skill output to pending_handoff in session.json for consumption by successor skills."""
    result: dict = {"from_skill": from_skill, "content_length": len(content)}
    if not _STATE_WRITABLE:
        result["saved"] = False
        result["error_type"] = "BUSINESS_RULE"
        result["note"] = "state/ is read-only in this container — handoff content is available in session context only"
    else:
        try:
            state = json.loads(_SESSION_STATE.read_text()) if _SESSION_STATE.exists() else {}
            state.setdefault("pending_handoff", {})[from_skill] = content
            _SESSION_STATE.write_text(json.dumps(state, indent=2))
            result["saved"] = True
        except Exception as e:
            result["saved"] = False
            result["error_type"] = "SYSTEM"
            result["error"] = str(e)
    try:
        severity = _infer_severity(content)
        suggestion = _check_reentry(from_skill, severity)
        if suggestion is not None:
            result["reentry_suggestion"] = suggestion
    except Exception:
        pass
    return result


_YOUK_ROOT = YOUK_ROOT
_ROUTE_TASK_RAN = _YOUK_ROOT / "state" / "route-task-ran.json"
_SESSION_OPEN = _YOUK_ROOT / "state" / "session-open.json"

# Skills that require route_task to have run first (M+ gate)
_GATED_SKILLS = {"dev-loop"}


def _get_current_slug() -> str:
    """Read active session slug — prefer per-slug open.json, fall back to root."""
    sessions = _YOUK_ROOT / "state" / "sessions"
    if sessions.exists():
        candidates = sorted(
            sessions.glob("*/open.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for c in candidates:
            try:
                slug = json.loads(c.read_text()).get("slug", "")
                if slug:
                    return slug
            except Exception:
                pass
    if _SESSION_OPEN.exists():
        try:
            return json.loads(_SESSION_OPEN.read_text()).get("slug", "unknown")
        except Exception:
            pass
    return "unknown"


def _get_rationale_state() -> dict:
    """Load skill-rationale-state.json; return {} if absent or corrupt."""
    try:
        if _RATIONALE_STATE.exists():
            return json.loads(_RATIONALE_STATE.read_text())
    except Exception:
        pass
    return {}


def _increment_rationale_shown(skill_name: str) -> int:
    """Increment shown_count for a skill; return new count."""
    state = _get_rationale_state()
    entry = state.get(skill_name, {"shown_count": 0, "suppressed": False})
    entry["shown_count"] = entry.get("shown_count", 0) + 1
    if entry["shown_count"] >= _RATIONALE_SUPPRESS_AFTER:
        entry["suppressed"] = True
    state[skill_name] = entry
    if _STATE_WRITABLE:
        try:
            _RATIONALE_STATE.parent.mkdir(parents=True, exist_ok=True)
            _RATIONALE_STATE.write_text(json.dumps(state, indent=2))
        except Exception:
            pass
    return entry["shown_count"]


def _rationale_suppressed(skill_name: str) -> bool:
    """Return True if the teaching rationale for this skill should be omitted."""
    state = _get_rationale_state()
    return state.get(skill_name, {}).get("suppressed", False)


def mark_rationale_preempted(skill_name: str) -> dict:
    """
    Call when the developer demonstrates they've internalised a skill's rationale
    without being prompted — e.g. they pre-empted nfr_check by answering all four
    questions before the gate ran. Each pre-emption counts toward suppression.
    """
    count = _increment_rationale_shown(skill_name)
    suppressed = count >= _RATIONALE_SUPPRESS_AFTER
    return {
        "skill": skill_name,
        "preemption_count": count,
        "rationale_suppressed": suppressed,
        "message": (
            f"Rationale suppressed for '{skill_name}' — developer has internalised it."
            if suppressed else
            f"Pre-emption {count}/{_RATIONALE_SUPPRESS_AFTER} recorded for '{skill_name}'."
        ),
    }


def _routing_ran_this_session() -> bool:
    """Return True if route_task was called this session for the current slug.

    Checks per-slug path first (state/sessions/{slug}/route-task-ran.json),
    falls back to legacy flat path for backward compat.
    """
    try:
        slug = _get_current_slug()
        # Per-slug path (written by route_task after per-slug migration)
        slug_file = _YOUK_ROOT / "state" / "sessions" / slug / "route-task-ran.json"
        if slug_file.exists():
            raw = json.loads(slug_file.read_text())
            entries = raw if isinstance(raw, list) else [raw]
            if any(e.get("slug") == slug for e in entries):
                return True
        # Legacy flat path fallback
        if _ROUTE_TASK_RAN.exists():
            raw = json.loads(_ROUTE_TASK_RAN.read_text())
            entries = raw if isinstance(raw, list) else [raw]
            if any(e.get("slug") == slug for e in entries):
                return True
    except Exception:
        pass
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

    # Normalize skill name: routes.yaml uses underscores, skill dirs use hyphens.
    # Try the name as-given first; fall back to underscore→hyphen so that
    # route_to_skill("adversarial_planning") resolves to skills/adversarial-planning/.
    resolved_name = skill_name
    # Merge: explicit context overrides session-detected values
    session_ctx = _read_session_stack_context()
    ctx = {**session_ctx, **(context or {})}
    try:
        skill_content = load_skill_with_context(
            resolved_name,
            stack=ctx.get("stack"),
            framework=ctx.get("framework"),
            domain=ctx.get("domain"),
        )
    except FileNotFoundError:
        hyphen_name = skill_name.replace("_", "-")
        if hyphen_name == resolved_name:
            return {"error": f"Skill not found: {skill_name}"}
        try:
            skill_content = load_skill_with_context(
                hyphen_name,
                stack=ctx.get("stack"),
                framework=ctx.get("framework"),
                domain=ctx.get("domain"),
            )
            resolved_name = hyphen_name
        except FileNotFoundError as e:
            return {"error": str(e)}

    skill_content = _strip_reference_sections(skill_content)

    handoff = _read_and_clear_pending_handoff(skill_name)
    if handoff:
        skill_content = handoff + "\n\n---\n\n" + skill_content

    # Register dev-loop in ceremony sequence so task_checkpoint can verify it ran.
    if resolved_name == "dev-loop":
        try:
            _record_gate("dev-loop", _get_current_slug())
        except Exception:
            pass

    # Clear force_learn pending action when /learn fires — the gate is satisfied.
    if skill_name == "learn":
        try:
            pending_action_file = YOUK_ROOT / "state" / "pending-action.json"
            if pending_action_file.exists():
                data = json.loads(pending_action_file.read_text())
                if data.get("action") == "learn":
                    pending_action_file.unlink()
        except Exception:
            pass

    # Teaching rationale — shown until developer internalises it (suppressed after N pre-emptions)
    suppressed = _rationale_suppressed(resolved_name)
    rationale_why = None
    if not suppressed:
        rationale_why = extract_frontmatter_field(resolved_name, "rationale_why")
        if rationale_why:
            _increment_rationale_shown(resolved_name)

    return {
        "mode": "in_session",
        "skill_name": resolved_name,
        "skill_content": skill_content,
        "task": task,
        "context": ctx,
        "rationale": rationale_why,
        "rationale_suppressed": suppressed,
        "instruction": (
            f"You have received the '{resolved_name}' skill. "
            + (
                f"Before executing, surface this rationale to the developer in plain language: "
                f"{rationale_why} "
                if rationale_why and not suppressed else ""
            )
            + "Apply it now using your full session context, tools, and conversation history. "
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
