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
    assert hosts["claude-code"]["evidence"] == "plugin/hooks/hooks.json:26"


def test_pre_tool_guard_is_not_wired_for_codex_this_is_the_cir_152_gap():
    """The exact real gap CIR-154 exists to make mechanical: agent_host.py's
    CodexHost declares PRE_TOOL_GUARD supported, but nothing in the codebase
    calls check_m_plus_write_gate from any Codex-reachable boundary. The
    founder found this by asking directly; this scanner must find it by
    reading the code."""
    graph = scan()
    hosts = graph["pre_tool_guard"]["hosts"]
    assert "codex" in hosts, "codex declares pre_tool_guard supported and must appear as a row"
    assert hosts["codex"]["wired"] is False
    assert hosts["codex"]["evidence"] is None


def test_declaring_a_capability_in_a_docstring_is_not_wiring_evidence():
    """agent_host.py's CodexHost docstring literally contains the string
    "PreToolUse" while explicitly disclaiming real wiring ("not a claim that
    Codex's own hook wiring has been exercised live"). A scanner that treats
    prose mentioning a mechanism as evidence of that mechanism being wired
    would silently launder the exact gap it exists to catch back into a false
    "wired": true. Regression guard for that specific failure mode."""
    graph = scan()
    assert graph["pre_tool_guard"]["hosts"]["codex"]["wired"] is False


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
