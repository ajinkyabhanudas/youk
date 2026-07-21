"""MCP stdio client for integration tests.

Drives youk-core and youk-code via JSON-RPC over subprocess stdin/stdout —
the same protocol that Claude Code uses, and the same pattern as make test-core.

Each call spins up a fresh `docker run -i --rm` container, sends the three-line
handshake (initialize → notifications/initialized → tools/call), and returns the
parsed result dict. No long-running container needed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

CLAUDE_DIR = Path.home() / ".claude"
YOUK_DIR = CLAUDE_DIR / "youk"

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
        # Sandbox: mount temp state dir instead of live state/
        cmd += [
            "-v", f"{CLAUDE_DIR}:/claude",
            "-v", f"{YOUK_DIR}:/youk",
            "-v", f"{state_dir}:/youk/state",
        ]
    else:
        cmd += [
            "-v", f"{CLAUDE_DIR}:/claude",
            "-v", f"{YOUK_DIR}:/youk",
        ]

    cmd.append(image)

    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise RuntimeError("docker not found — is Docker Desktop installed?") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"MCP call to {image}:{payload_msg[:40]} timed out ({timeout}s)") from e

    for raw in proc.stdout.splitlines():
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            if "error" in msg:
                raise RuntimeError(f"MCP error from {image}: {msg['error']}")
            return msg.get("result", {})

    raise RuntimeError(
        f"No result in MCP response from {image}.\n"
        f"stdout: {proc.stdout[:400]}\nstderr: {proc.stderr[:200]}"
    )
