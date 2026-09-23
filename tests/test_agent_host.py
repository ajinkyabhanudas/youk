"""Deterministic contract tests for vendor-neutral agent-host policy."""
from __future__ import annotations

import pytest

from agent_host import (
    CAPABILITY_SCHEMA_VERSION,
    CapabilityUnavailableError,
    CapabilityRequirement,
    CapabilityStatus,
    ClaudeCodeHost,
    CodexHost,
    HostCapability,
    HostCapabilities,
    evaluate_capability,
    require_capability,
)


def test_hosts_share_the_same_capability_contract_version():
    assert ClaudeCodeHost.capabilities.schema_version == CodexHost.capabilities.schema_version == CAPABILITY_SCHEMA_VERSION
    assert evaluate_capability(
        ClaudeCodeHost.capabilities, HostCapability.SESSION_CONTEXT
    ).status is CapabilityStatus.AVAILABLE
    assert evaluate_capability(
        CodexHost.capabilities, HostCapability.SESSION_CONTEXT
    ).status is CapabilityStatus.AVAILABLE


def test_missing_advisory_capability_is_explicitly_degraded():
    decision = evaluate_capability(CodexHost.capabilities, HostCapability.PROMPT_CONTEXT)
    assert decision.requirement is CapabilityRequirement.ADVISORY
    assert decision.status is CapabilityStatus.DEGRADED
    assert decision.reason == "advisory capability is unavailable"


def test_missing_safety_capability_fails_closed():
    decision = evaluate_capability(CodexHost.capabilities, HostCapability.PRE_TOOL_GUARD)
    assert decision.requirement is CapabilityRequirement.SAFETY
    assert decision.status is CapabilityStatus.BLOCKED
    assert decision.reason == "required safety capability is unavailable"


def test_unknown_capability_fails_closed():
    decision = evaluate_capability(CodexHost.capabilities, "future_capability")
    assert decision.requirement is CapabilityRequirement.SAFETY
    assert decision.status is CapabilityStatus.BLOCKED
    assert decision.reason == "unknown capability fails closed"


def test_codex_hook_rendering_stays_at_the_vendor_boundary():
    assert CodexHost.render_session_context("brief") == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "brief",
        }
    }


def test_unsupported_schema_version_is_blocked():
    host = HostCapabilities("future-host", CAPABILITY_SCHEMA_VERSION + 1, frozenset(HostCapability))
    decision = evaluate_capability(host, HostCapability.SESSION_CONTEXT)
    assert decision.status is CapabilityStatus.BLOCKED
    assert decision.reason == "unsupported capability schema version"


def test_missing_requirement_mapping_blocks_instead_of_raising(monkeypatch):
    import agent_host

    monkeypatch.delitem(agent_host._REQUIREMENTS, HostCapability.SESSION_CONTEXT)
    decision = evaluate_capability(CodexHost.capabilities, HostCapability.SESSION_CONTEXT)
    assert decision.status is CapabilityStatus.BLOCKED
    assert decision.reason == "capability requirement is undefined"


def test_runtime_requirement_blocks_a_missing_safety_capability():
    with pytest.raises(CapabilityUnavailableError, match="pre_tool_guard"):
        require_capability(CodexHost.capabilities, HostCapability.PRE_TOOL_GUARD)
