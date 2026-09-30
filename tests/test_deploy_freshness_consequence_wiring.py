"""Wiring guard for CIR-153 — the deploy-freshness gate must actually be on
the PreToolUse boundary Claude Code invokes, not just exist as an importable
module nothing calls. Mirrors test_deploy_freshness_wiring.py's approach for
the original (warning-only) gate.
"""
from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HOOK = _REPO / "plugin" / "scripts" / "pre_tool_use.py"
_HOOKS_JSON = _REPO / "plugin" / "hooks" / "hooks.json"


def test_hooks_json_routes_youk_mcp_tool_calls_to_pre_tool_use():
    spec = json.loads(_HOOKS_JSON.read_text())
    matchers = [
        entry.get("matcher", "")
        for entry in spec["hooks"]["PreToolUse"]
    ]
    assert any("mcp__youk-core__" in m and "mcp__youk-code__" in m for m in matchers), (
        "PreToolUse matcher never grew the mcp__youk-core__* / mcp__youk-code__* "
        "pattern — the deploy-freshness consequence gate would never fire."
    )


def test_pre_tool_use_imports_and_calls_server_freshness_enforce():
    t = _HOOK.read_text()
    assert "from server_freshness import enforce" in t, (
        "pre_tool_use.py no longer imports the deploy-freshness enforcement gate"
    )
    assert "enforce_deploy_freshness(" in t, (
        "server_freshness.enforce is imported but never called"
    )


def test_pre_tool_use_can_deny_on_stale_verdict():
    t = _HOOK.read_text()
    assert 'verdict["action"] == "deny"' in t and "deny(verdict[\"message\"])" in t, (
        "a stale/indeterminate verdict from server_freshness.enforce must be able "
        "to actually deny the tool call, not just be computed and ignored"
    )
