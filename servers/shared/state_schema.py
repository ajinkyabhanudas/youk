"""Validated schemas for youk's mutable-claim state.

Task 1 (state-store-rework), sub-task 1.1. Governed by ADR-009: stdlib dataclasses
with __post_init__ validation, raise-on-malformed, no coercion. This is the schema
layer that makes silent state corruption impossible — a malformed write raises here,
before it can reach the store.

The SEAM (see state-store-rework.md): only MUTABLE-CLAIM state gets a schema here —
state that can silently diverge from truth (plan, active task, gate flags, session
pointers, pending action). Append-only logs (*.jsonl) and monotonic counters do NOT
get schemas; they cannot lie, only grow, and forcing them through validation is the
speculative completeness ADR-009's contract forbids.

Every schema provides:
  - __post_init__ validation that RAISES StateValidationError on malformed input
    (never coerces — coercion is exactly how the recursive-Resume bug slipped through).
  - to_dict() for serialization, matching the existing models.py idiom.
  - from_dict() that validates on read as well as write (a corrupt file on disk is
    caught when read, not trusted blindly).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class StateValidationError(ValueError):
    """Raised when state fails schema validation on read or write.

    Deliberately a subclass of ValueError so existing broad `except ValueError`
    handlers surface it, but callers that want to distinguish state corruption
    from other value errors can catch this specifically.
    """


# --- validation helpers (raise, never coerce) -------------------------------


def _require_str(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise StateValidationError(
            f"{field_name} must be str, got {type(value).__name__}"
        )
    if not allow_empty and not value.strip():
        raise StateValidationError(f"{field_name} must be a non-empty string")
    return value


def _require_list_of_str(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise StateValidationError(f"{field_name} must be a list of str")
    return value


def _reject_recursive_wrapping(value: str, field_name: str, marker: str) -> None:
    """Guard against the specific recursive-Resume corruption class.

    The bug that motivated this whole task: a resume/plan string got re-wrapped
    with its own prefix ("Resume: Resume: Resume: ...") every session until it was
    meaningless. A schema that only checks `isinstance(str)` would have accepted it.
    We reject any string where a wrapping marker appears more than twice — a real
    value never legitimately contains three copies of its own framing prefix.
    """
    if value.count(marker) > 2:
        raise StateValidationError(
            f"{field_name} appears recursively wrapped "
            f"({value.count(marker)}x '{marker}') — refusing malformed write"
        )


# --- mutable-claim schemas ---------------------------------------------------


@dataclass
class ActiveTask:
    """state/active_task.json — the current in-flight task for a project.

    The historical bug: this file fused a stale task from one project with routing
    context from another, and was never cleared. `slug` is required and non-empty so
    a task can never again be project-ambiguous.
    """

    task: str
    slug: str
    cwd: str = ""
    files_touched: list[str] = field(default_factory=list)
    last_signal: str = ""
    last_tool: str = ""
    updated_at: str = ""
    routing_context: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_str(self.task, "active_task.task", allow_empty=False)
        _require_str(self.slug, "active_task.slug", allow_empty=False)
        _require_list_of_str(self.files_touched, "active_task.files_touched")
        if not isinstance(self.routing_context, dict):
            raise StateValidationError("active_task.routing_context must be a dict")

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "slug": self.slug,
            "cwd": self.cwd,
            "files_touched": self.files_touched,
            "last_signal": self.last_signal,
            "last_tool": self.last_tool,
            "updated_at": self.updated_at,
            "routing_context": self.routing_context,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ActiveTask:
        if not isinstance(d, dict):
            raise StateValidationError("active_task must be a JSON object")
        return cls(
            task=d.get("task", ""),
            slug=d.get("slug", ""),
            cwd=d.get("cwd", ""),
            files_touched=d.get("files_touched", []),
            last_signal=d.get("last_signal", ""),
            last_tool=d.get("last_tool", ""),
            updated_at=d.get("updated_at", ""),
            routing_context=d.get("routing_context", {}),
        )


@dataclass
class SessionPlan:
    """state/session-plan.json — the current session's plan items for a project.

    Each item is guarded against recursive wrapping (the "Resume: Resume:" class).
    """

    plan: list[str]
    slug: str
    generated_at: str = ""

    def __post_init__(self) -> None:
        _require_list_of_str(self.plan, "session_plan.plan")
        _require_str(self.slug, "session_plan.slug", allow_empty=False)
        for i, item in enumerate(self.plan):
            _reject_recursive_wrapping(item, f"session_plan.plan[{i}]", "Resume:")

    def to_dict(self) -> dict:
        return {"plan": self.plan, "slug": self.slug, "generated_at": self.generated_at}

    @classmethod
    def from_dict(cls, d: dict) -> SessionPlan:
        if not isinstance(d, dict):
            raise StateValidationError("session_plan must be a JSON object")
        return cls(
            plan=d.get("plan", []),
            slug=d.get("slug", ""),
            generated_at=d.get("generated_at", ""),
        )


@dataclass
class ResumePointer:
    """The project-scoped "what's next" pointer (ADR contract R3).

    Written automatically at session_end from the project's own validated task graph.
    `text` is guarded against the recursive-wrapping bug that motivated this task.
    """

    slug: str
    text: str

    def __post_init__(self) -> None:
        _require_str(self.slug, "resume_pointer.slug", allow_empty=False)
        _require_str(self.text, "resume_pointer.text")
        _reject_recursive_wrapping(self.text, "resume_pointer.text", "Resume:")
        _reject_recursive_wrapping(self.text, "resume_pointer.text", "Last working on:")

    def to_dict(self) -> dict:
        return {"slug": self.slug, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> ResumePointer:
        if not isinstance(d, dict):
            raise StateValidationError("resume_pointer must be a JSON object")
        return cls(slug=d.get("slug", ""), text=d.get("text", ""))


@dataclass
class PendingAction:
    """state/pending-action.json — a deferred action to run at next session start."""

    action: str
    reason: str = ""
    written_at: str = ""

    def __post_init__(self) -> None:
        _require_str(self.action, "pending_action.action", allow_empty=False)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "written_at": self.written_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PendingAction:
        if not isinstance(d, dict):
            raise StateValidationError("pending_action must be a JSON object")
        return cls(
            action=d.get("action", ""),
            reason=d.get("reason", ""),
            written_at=d.get("written_at", ""),
        )


@dataclass
class GateFlag:
    """A ran/passed gate marker (challenge-ran, nfr-check-ran, challenge-gate-passed,
    route-task-ran, intake-ran). Slug-scoped so a gate cleared in one project can never
    satisfy a gate check in another.
    """

    slug: str
    ts: str = ""

    def __post_init__(self) -> None:
        _require_str(self.slug, "gate_flag.slug", allow_empty=False)

    def to_dict(self) -> dict:
        return {"slug": self.slug, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> GateFlag:
        if not isinstance(d, dict):
            raise StateValidationError("gate_flag must be a JSON object")
        return cls(slug=d.get("slug", ""), ts=d.get("ts", ""))


# --- the seam registry -------------------------------------------------------
# The machine-checked boundary (sub-task 1.5 asserts on this). A state file that
# holds a mutable claim MUST appear here with its schema; a file absent here is
# treated as append-only/counter (no validation). Adding a mutable-claim file
# without registering it is what the seam test catches.

MUTABLE_CLAIM_SCHEMAS: dict[str, type] = {
    "active_task.json": ActiveTask,
    "session-plan.json": SessionPlan,
    "pending-action.json": PendingAction,
    "challenge-ran.json": GateFlag,
    "challenge-gate-passed.json": GateFlag,
    "nfr-check-ran.json": GateFlag,
    "route-task-ran.json": GateFlag,
    "intake-ran.json": GateFlag,
}
