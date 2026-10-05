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
    HostSelectionStatus,
    HostConfiguration,
    load_host_configuration,
    rollback_host_configuration,
    save_host_configuration,
    select_host,
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
    host = HostCapabilities(
        "bare-host", CAPABILITY_SCHEMA_VERSION, frozenset({HostCapability.SESSION_CONTEXT})
    )
    decision = evaluate_capability(host, HostCapability.PROMPT_CONTEXT)
    assert decision.requirement is CapabilityRequirement.ADVISORY
    assert decision.status is CapabilityStatus.DEGRADED
    assert decision.reason == "advisory capability is unavailable"


def test_codex_declares_prompt_context():
    """CIR-155 (second finding): PROMPT_CONTEXT was absent from CodexHost's
    declared set entirely until now, not declared-and-unwired -- confirmed
    Codex has a real UserPromptSubmit hook (developers.openai.com/codex/hooks)
    using the same stdin field ("prompt") and response envelope Claude Code's
    hook already uses."""
    decision = evaluate_capability(CodexHost.capabilities, HostCapability.PROMPT_CONTEXT)
    assert decision.requirement is CapabilityRequirement.ADVISORY
    assert decision.status is CapabilityStatus.AVAILABLE


def test_codex_declares_pre_tool_guard():
    """CIR-150 item 5 / CIR-151: pre_tool_use.py's M+ write gate (CIR-150 item 4)
    is vendor-neutral by construction -- pure Python reading session state
    files, no Claude-specific API -- and wired at the hook boundary, not
    in-process. CodexHost now declares the capability to reflect that."""
    decision = evaluate_capability(CodexHost.capabilities, HostCapability.PRE_TOOL_GUARD)
    assert decision.requirement is CapabilityRequirement.SAFETY
    assert decision.status is CapabilityStatus.AVAILABLE


def test_missing_safety_capability_fails_closed():
    host = HostCapabilities(
        "bare-host", CAPABILITY_SCHEMA_VERSION, frozenset({HostCapability.SESSION_CONTEXT})
    )
    decision = evaluate_capability(host, HostCapability.PRE_TOOL_GUARD)
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


def test_codex_hook_rendering_with_no_verbatim_lines_is_unchanged():
    """Backward compatible: omitting verbatim_lines (or passing []) must not
    change the rendered output at all."""
    assert CodexHost.render_session_context("brief", []) == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "brief",
        }
    }
    assert CodexHost.render_session_context("brief", None) == CodexHost.render_session_context("brief")


def test_codex_hook_rendering_prepends_verbatim_lines_tag_free():
    """CIR-150 item 5 / CIR-151: verbatim_lines renders as an explicit,
    tag-free preservation block ahead of `brief` -- Codex's continuity must
    not depend on it parsing Claude-oriented [TIER:CONTRACT] tag syntax."""
    result = CodexHost.render_session_context("brief", ["- always run ruff", "- no force push"])
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "[TIER:" not in context.split("\n\n")[0]
    assert "- always run ruff" in context
    assert "- no force push" in context
    assert context.endswith("brief")
    assert "preserved verbatim" in context.lower()


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
    host = HostCapabilities(
        "bare-host", CAPABILITY_SCHEMA_VERSION, frozenset({HostCapability.SESSION_CONTEXT})
    )
    with pytest.raises(CapabilityUnavailableError, match="pre_tool_guard"):
        require_capability(host, HostCapability.PRE_TOOL_GUARD)


def test_runtime_requirement_allows_codex_pre_tool_guard_now():
    """The mirror case: CodexHost now HAS the capability, so require_capability
    must not raise -- proving the declaration is actually load-bearing, not
    just an unused enum member."""
    require_capability(CodexHost.capabilities, HostCapability.PRE_TOOL_GUARD)


def test_runtime_host_selection_blocks_ambiguous_evidence():
    result = select_host(frozenset({"codex", "claude-code"}))
    assert result.status is HostSelectionStatus.AMBIGUOUS


def test_explicit_host_configuration_overrides_runtime_evidence():
    result = select_host(frozenset({"codex", "claude-code"}), "codex")
    assert result.status is HostSelectionStatus.SELECTED
    assert result.source == "configuration"


def test_host_configuration_rollback_restores_prior_selection(tmp_path):
    path = tmp_path / "host.json"
    original = HostConfiguration("codex")
    save_host_configuration(path, original)
    previous = save_host_configuration(path, HostConfiguration("claude-code"))
    rollback_host_configuration(path, previous)
    assert load_host_configuration(path) == original


def test_usage_capture_is_advisory_and_both_hosts_declare_it():
    """It records what happened; losing it costs measurement, never safety."""
    from agent_host import ClaudeCodeHost
    for host in (ClaudeCodeHost.capabilities, CodexHost.capabilities):
        decision = evaluate_capability(host, HostCapability.USAGE_CAPTURE)
        assert decision.status.value == "available"
    undeclared = HostCapabilities(host_id="other", schema_version=1, supported=frozenset())
    degraded = evaluate_capability(undeclared, HostCapability.USAGE_CAPTURE)
    assert degraded.status.value == "degraded" and degraded.requirement.value == "advisory"
