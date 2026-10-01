"""Tests for scripts/host_inventory.py (CIR-154 item 1).

These run the real scanner against the real repository it lives in — no
fixtures, no fakes — because the whole point of this module is that it must
be trusted to describe the actual current codebase. A scanner that only
passes against synthetic fixtures proves nothing about whether it would have
caught CIR-152's real miss.
"""
from __future__ import annotations

from host_inventory import (
    extract_declared_capabilities,
    scan,
    scan_host_conditional_branches,
)


def test_claude_code_declares_every_known_capability():
    declared = extract_declared_capabilities()
    assert declared["claude-code"] == {
        "session_context", "compaction_context", "prompt_context", "pre_tool_guard",
    }


def test_codex_declares_a_strict_subset_excluding_prompt_context():
    declared = extract_declared_capabilities()
    assert declared["codex"] == {"session_context", "compaction_context", "pre_tool_guard"}
    assert "prompt_context" not in declared["codex"]


def test_pre_tool_guard_is_wired_for_claude_code_via_hooks_json():
    graph = scan()
    hosts = graph["pre_tool_guard"]["hosts"]
    assert hosts["claude-code"]["wired"] is True
    assert hosts["claude-code"]["evidence"] == "plugin/hooks/hooks.json:37"


def test_pre_tool_guard_is_now_wired_for_codex_cir_155_closed_the_cir_152_gap():
    """CIR-152's original gap: agent_host.py's CodexHost declared PRE_TOOL_GUARD
    supported, but nothing in the codebase called check_m_plus_write_gate from any
    Codex-reachable boundary. CIR-155 confirmed Codex's own PreToolUse hook contract
    (developers.openai.com/codex/hooks, 2026) uses the identical stdin shape and the
    identical deny envelope ({"hookSpecificOutput": {"permissionDecision": "deny",
    ...}}) Claude Code's hook already uses, and wired Codex's canonical file-edit
    tool name ("apply_patch") into the same plugin/scripts/pre_tool_use.py gate --
    same script, same check_m_plus_write_gate call, no Codex-specific code path."""
    graph = scan()
    hosts = graph["pre_tool_guard"]["hosts"]
    assert "codex" in hosts, "codex declares pre_tool_guard supported and must appear as a row"
    assert hosts["codex"]["wired"] is True
    assert hosts["codex"]["evidence"] is not None


def test_pre_tool_guard_codex_evidence_comes_from_real_wiring_not_the_declaring_docstring():
    """agent_host.py's CodexHost docstring literally contains the string
    "PreToolUse" while explicitly disclaiming real wiring at the time it was
    written. A scanner that treated that prose as evidence would launder a mere
    declaration into a false "wired": true without any real wiring existing.
    Regression guard: the evidence this scanner reports must point at the real
    wiring site CIR-155 added (plugin/scripts/pre_tool_use.py), never at
    agent_host.py's own docstring."""
    graph = scan()
    evidence = graph["pre_tool_guard"]["hosts"]["codex"]["evidence"]
    assert evidence is not None
    assert "agent_host.py" not in evidence
    assert "pre_tool_use.py" in evidence


def test_compaction_context_is_genuinely_wired_for_both_hosts():
    """Unlike pre_tool_guard, this one really is wired end to end for Codex
    (verbatim_lines flow through CodexHost.render_session_context) — a
    positive control proving the scanner isn't just defaulting every codex
    row to False."""
    graph = scan()
    hosts = graph["compaction_context"]["hosts"]
    assert hosts["claude-code"]["wired"] is True
    assert hosts["codex"]["wired"] is True
    assert hosts["codex"]["evidence"] is not None


def test_session_context_is_now_wired_for_claude_code_cir_155_closed_the_gap():
    """Before CIR-155, hooks.json had no SessionStart key at all -- the only
    thing delivering session context to Claude Code was a CLAUDE.md instruction
    the model could skip, same prose-not-a-backstop shape CIR-150 closed for
    Edit/Write. CIR-155 added a real SessionStart hook (plugin/scripts/
    session_start.py) that calls the already-running youk-core server's
    /session-start-hook route directly over plain HTTP (Claude Code's own
    mcp_tool hook type is documented inert at SessionStart, so this bypasses
    that restriction rather than fighting it)."""
    graph = scan()
    hosts = graph["session_context"]["hosts"]
    assert hosts["claude-code"]["wired"] is True
    assert hosts["claude-code"]["evidence"] is not None
    assert hosts["claude-code"]["evidence"].startswith("plugin/hooks/hooks.json:")


def test_prompt_context_has_no_codex_row_because_codex_never_declared_it():
    """codex doesn't claim prompt_context support at all, so there is nothing
    to check — this must not be confused with a declared-but-unwired gap."""
    graph = scan()
    assert "codex" not in graph["prompt_context"]["hosts"]


def test_host_conditional_branches_finds_real_claude_plugin_root_usage():
    hits = scan_host_conditional_branches()
    files = {h["file"] for h in hits}
    assert "plugin/hooks/hooks.json" in files
    assert all("CLAUDE_PLUGIN_ROOT" in h["text"] or "host" in h["text"].lower() for h in hits)
