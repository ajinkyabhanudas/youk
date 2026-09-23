"""Vendor-neutral agent-host capabilities and boundary adapters.

Core policy consumes ``HostCapabilities`` and never branches on an LLM vendor. A host
adapter is the only place allowed to translate a normalized context payload into a
vendor-specific hook response.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class HostCapability(StrEnum):
    """Capabilities an agent host may provide to youk."""

    SESSION_CONTEXT = "session_context"
    COMPACTION_CONTEXT = "compaction_context"
    PROMPT_CONTEXT = "prompt_context"
    PRE_TOOL_GUARD = "pre_tool_guard"


class CapabilityRequirement(StrEnum):
    """Policy class for a host capability."""

    SAFETY = "safety"
    ADVISORY = "advisory"


class CapabilityStatus(StrEnum):
    """Deterministic outcome of a capability policy evaluation."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


_REQUIREMENTS: Final[dict[HostCapability, CapabilityRequirement]] = {
    HostCapability.SESSION_CONTEXT: CapabilityRequirement.SAFETY,
    HostCapability.COMPACTION_CONTEXT: CapabilityRequirement.ADVISORY,
    HostCapability.PROMPT_CONTEXT: CapabilityRequirement.ADVISORY,
    HostCapability.PRE_TOOL_GUARD: CapabilityRequirement.SAFETY,
}
CAPABILITY_SCHEMA_VERSION: Final = 1


@dataclass(frozen=True)
class HostCapabilities:
    """Immutable, versioned declaration supplied by one agent-host adapter."""

    host_id: str
    schema_version: int
    supported: frozenset[HostCapability]


@dataclass(frozen=True)
class CapabilityDecision:
    """A policy outcome that callers can handle without vendor-specific branches."""

    host_id: str
    capability: str
    requirement: CapabilityRequirement
    status: CapabilityStatus
    reason: str


class CapabilityUnavailableError(RuntimeError):
    """Raised when a host cannot provide a safety-required capability."""


def evaluate_capability(
    host: HostCapabilities, capability: HostCapability | str
) -> CapabilityDecision:
    """Evaluate one capability without I/O, retries, or hidden fallback behavior."""
    if host.schema_version != CAPABILITY_SCHEMA_VERSION:
        return CapabilityDecision(
            host_id=host.host_id,
            capability=str(capability),
            requirement=CapabilityRequirement.SAFETY,
            status=CapabilityStatus.BLOCKED,
            reason="unsupported capability schema version",
        )
    try:
        normalized = HostCapability(capability)
    except ValueError:
        return CapabilityDecision(
            host_id=host.host_id,
            capability=str(capability),
            requirement=CapabilityRequirement.SAFETY,
            status=CapabilityStatus.BLOCKED,
            reason="unknown capability fails closed",
        )

    requirement = _REQUIREMENTS.get(normalized)
    if requirement is None:
        return CapabilityDecision(
            host_id=host.host_id,
            capability=normalized.value,
            requirement=CapabilityRequirement.SAFETY,
            status=CapabilityStatus.BLOCKED,
            reason="capability requirement is undefined",
        )
    if normalized in host.supported:
        return CapabilityDecision(
            host_id=host.host_id,
            capability=normalized.value,
            requirement=requirement,
            status=CapabilityStatus.AVAILABLE,
            reason="host declares capability",
        )

    status = (
        CapabilityStatus.BLOCKED
        if requirement is CapabilityRequirement.SAFETY
        else CapabilityStatus.DEGRADED
    )
    return CapabilityDecision(
        host_id=host.host_id,
        capability=normalized.value,
        requirement=requirement,
        status=status,
        reason=(
            "required safety capability is unavailable"
            if status is CapabilityStatus.BLOCKED
            else "advisory capability is unavailable"
        ),
    )


def require_capability(host: HostCapabilities, capability: HostCapability | str) -> None:
    """Enforce a host capability at the runtime boundary without a vendor branch."""
    decision = evaluate_capability(host, capability)
    if decision.status is CapabilityStatus.BLOCKED:
        raise CapabilityUnavailableError(
            f"{decision.host_id}: {decision.capability}: {decision.reason}"
        )


class ClaudeCodeHost:
    """Claude Code boundary declaration; no core policy belongs here."""

    capabilities = HostCapabilities(
        host_id="claude-code",
        schema_version=CAPABILITY_SCHEMA_VERSION,
        supported=frozenset(HostCapability),
    )


class CodexHost:
    """Codex boundary declaration and SessionStart hook renderer."""

    capabilities = HostCapabilities(
        host_id="codex",
        schema_version=CAPABILITY_SCHEMA_VERSION,
        supported=frozenset({
            HostCapability.SESSION_CONTEXT,
            HostCapability.COMPACTION_CONTEXT,
        }),
    )

    @staticmethod
    def render_session_context(brief: str) -> dict:
        """Render the only Codex-specific SessionStart response shape."""
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": brief,
            }
        }
