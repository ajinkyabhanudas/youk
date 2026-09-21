"""L8 — Agent guards: the plain-HTTP guard service Paperclip agents curl directly.

Unlike the rest of this package, these hit the persistent youk-core-server container
on its real port (127.0.0.1:8001) rather than spinning up a fresh stdio container --
the endpoints under test are Starlette custom_route handlers reachable only over the
server's real HTTP transport, not the MCP tools/call protocol the stdio harness drives.

Skips entirely if the persistent server isn't reachable, so this suite doesn't fail
in an environment that only runs the fresh-container L0-L7 suites.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

BASE = "http://127.0.0.1:8001"


def _server_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{BASE}/agent-guards?agent_type=paperclip_support", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_reachable(), reason="persistent youk-core-server not reachable on :8001")


def _get(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestGetAgentGuards:
    def test_paperclip_support_returns_real_content(self):
        status, body = _get("/agent-guards?agent_type=paperclip_support")
        assert status == 200
        assert body["agent_type"] == "paperclip_support"
        assert "No self-authorization past a named escalation" in body["guards"]
        assert "Check edge cases and input validation" in body["guards"]

    def test_paperclip_department_head_returns_real_content(self):
        status, body = _get("/agent-guards?agent_type=paperclip_department_head")
        assert status == 200
        assert body["agent_type"] == "paperclip_department_head"
        assert "Independent review means re-deriving the claim" in body["guards"]

    def test_unknown_agent_type_rejected_with_valid_set(self):
        status, body = _get("/agent-guards?agent_type=not-a-real-type")
        assert status == 400
        assert "paperclip_support" in body["valid_agent_types"]
        assert "paperclip_department_head" in body["valid_agent_types"]

    def test_missing_agent_type_rejected(self):
        status, body = _get("/agent-guards")
        assert status == 400


class TestReportAgentGap:
    def test_valid_report_logs_and_is_cleaned_up(self):
        marker = "INTEGRATION-TEST-MARKER-l8-agent-guards-do-not-treat-as-real-gap"
        status, body = _post("/agent-guards/gap", {
            "agent_type": "paperclip_support",
            "agent_name": "test-harness",
            "gap": marker,
        })
        assert status == 200
        assert body["logged"] is True
        # "path" is container-internal (this server runs inside youk-core-server);
        # "path_relative" is relative to ~/.claude, resolvable from this host-side test.
        assert body["path_relative"]

        # Verify it actually landed, then remove exactly the block this test added --
        # a real integration test must not leave permanent noise in the real audit log.
        from pathlib import Path
        audit_path = Path.home() / ".claude" / body["path_relative"]
        content = audit_path.read_text()
        assert marker in content
        lines = content.splitlines(keepends=True)
        marker_idx = next(i for i, l in enumerate(lines) if marker in l)
        block_start = marker_idx
        while block_start > 0 and not lines[block_start].startswith("### Paperclip Agent Report"):
            block_start -= 1
        new_lines = lines[:block_start] + lines[marker_idx + 1:]
        audit_path.write_text("".join(new_lines))
        assert marker not in audit_path.read_text()

    def test_missing_fields_rejected(self):
        status, body = _post("/agent-guards/gap", {"agent_type": "paperclip_support"})
        assert status == 422
        assert body["logged"] is False

    def test_invalid_agent_type_rejected(self):
        status, body = _post("/agent-guards/gap", {
            "agent_type": "bogus", "agent_name": "x", "gap": "y",
        })
        assert status == 422
