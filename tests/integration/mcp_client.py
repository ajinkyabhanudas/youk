"""MCP stdio client for integration tests.

Drives youk-core and youk-code via JSON-RPC over subprocess stdin/stdout —
the same protocol that Claude Code uses, and the same pattern as make test-core.

Each call spins up a fresh `docker run -i --rm` container, sends the three-line
handshake (initialize → notifications/initialized → tools/call), and returns the
parsed result dict. No long-running container needed.
"""
from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path
from typing import Any

import os
CLAUDE_DIR = Path(os.environ["CLAUDE_DIR"]) if "CLAUDE_DIR" in os.environ else Path.home() / ".claude"
YOUK_DIR = Path(os.environ["YOUK_DIR"]) if "YOUK_DIR" in os.environ else CLAUDE_DIR / "youk"

_MCP_INIT = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "checkup", "version": "0"},
    },
})
_MCP_DONE = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})


def get_tools(image: str, state_dir: Path | None = None) -> list[str]:
    """Return the list of tool names from a tools/list handshake."""
    msg = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    result = _run(image, msg, state_dir=state_dir)
    return [t["name"] for t in result.get("tools", [])]


def call_tool(
    image: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Call a single MCP tool and return the parsed result dict.

    Raises RuntimeError if the server returns an error or times out.
    """
    msg = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    })
    raw_result = _run(image, msg, state_dir=state_dir)

    # tools/call wraps content in result.content[].text (JSON string)
    content = raw_result.get("content", [])
    for block in content:
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except (json.JSONDecodeError, TypeError):
                return {"_raw": block["text"]}

    # Some tools return content directly as a dict
    if content:
        return {"_content": content}
    return raw_result


def _run(
    image: str,
    payload_msg: str,
    state_dir: Path | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    payload = f"{_MCP_INIT}\n{_MCP_DONE}\n{payload_msg}\n"

    cmd = ["docker", "run", "-i", "--rm"]

    if state_dir is not None:
        # Sandbox: mount temp state dir instead of live state/.
        # /claude is still mounted for skills/config, but audit and
        # knowledge/projects writes get their own sandbox override mounts —
        # otherwise session_end writes real "Skills: none" entries into the
        # live audit log every test run, silently dragging down
        # skill_invocation_rate with sessions that were never real work.
        audit_sandbox = state_dir / "claude-audit"
        knowledge_sandbox = state_dir / "claude-knowledge-projects"
        audit_sandbox.mkdir(parents=True, exist_ok=True)
        knowledge_sandbox.mkdir(parents=True, exist_ok=True)
        cmd += [
            "-v", f"{CLAUDE_DIR}:/claude",
            "-v", f"{YOUK_DIR}:/youk",
            "-v", f"{state_dir}:/youk/state",
            "-v", f"{audit_sandbox}:/claude/audit",
            "-v", f"{knowledge_sandbox}:/claude/knowledge/projects",
        ]
    else:
        cmd += [
            "-v", f"{CLAUDE_DIR}:/claude",
            "-v", f"{YOUK_DIR}:/youk",
        ]

    cmd.append(image)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        raise RuntimeError("docker not found — is Docker Desktop installed?") from e

    stdout: list[str] = []
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(payload)
        proc.stdin.flush()

        deadline = time.monotonic() + timeout
        while remaining := deadline - time.monotonic():
            readable, _, _ = select.select([proc.stdout], [], [], remaining)
            if not readable:
                break
            raw = proc.stdout.readline()
            if not raw:
                break
            stdout.append(raw)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2:
                if "error" in msg:
                    raise RuntimeError(f"MCP error from {image}: {msg['error']}")
                return msg.get("result", {})

        stderr = ""
        if proc.stderr is not None:
            readable, _, _ = select.select([proc.stderr], [], [], 0)
            if readable:
                stderr = proc.stderr.read(200)
        raise RuntimeError(
            f"No result in MCP response from {image}.\n"
            f"stdout: {''.join(stdout)[:400]}\nstderr: {stderr}"
        )
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
