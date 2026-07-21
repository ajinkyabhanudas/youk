"""L1 — Infrastructure: Docker daemon, images, MCP handshake both servers."""
import subprocess
from pathlib import Path

import pytest

from .mcp_client import YOUK_DIR, get_tools

CLAUDE_DIR = Path.home() / ".claude"

CORE_CRITICAL_TOOLS = {
    "session_start", "session_end", "route_task",
    "check_nfr_gate", "check_challenge_gate", "apply_proposal",
}
CODE_CRITICAL_TOOLS = {
    "route_to_skill", "nfr_check", "check_commit_quality",
}


# ---------------------------------------------------------------------------
# Docker daemon
# ---------------------------------------------------------------------------

def test_docker_daemon_running():
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
    assert result.returncode == 0, "Docker daemon not running. Fix: open -a Docker"


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_youk_core_image_exists():
    result = subprocess.run(
        ["docker", "image", "inspect", "youk-core:latest"],
        capture_output=True, timeout=10,
    )
    assert result.returncode == 0, "youk-core:latest image missing. Fix: make build"


def test_youk_code_image_exists():
    result = subprocess.run(
        ["docker", "image", "inspect", "youk-code:latest"],
        capture_output=True, timeout=10,
    )
    assert result.returncode == 0, "youk-code:latest image missing. Fix: make build"


def test_image_freshness_vs_shared():
    """Warn (not fail) if servers/shared/ was committed after the image was built."""
    shared_dir = YOUK_DIR / "servers" / "shared"
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", str(shared_dir)],
        capture_output=True, text=True, cwd=str(YOUK_DIR), timeout=10,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip("Could not read git log for servers/shared/")

    shared_ts = int(result.stdout.strip())

    inspect = subprocess.run(
        ["docker", "image", "inspect", "--format={{.Metadata.LastTagTime}}", "youk-core:latest"],
        capture_output=True, text=True, timeout=10,
    )
    if inspect.returncode != 0:
        pytest.skip("Could not inspect youk-core image timestamp")

    # Image timestamp is RFC3339; just warn via pytest.warns equivalent (xfail soft)
    # We surface this as a warning, not a hard failure.
    import datetime
    raw = inspect.stdout.strip().rstrip("Z").split(".")[0]
    try:
        image_dt = datetime.datetime.fromisoformat(raw)
        image_ts = int(image_dt.timestamp())
        if shared_ts > image_ts:
            pytest.xfail(
                "servers/shared/ has commits newer than youk-core image. Fix: make rebuild"
            )
    except (ValueError, OSError):
        pytest.skip("Could not parse image timestamp")


# ---------------------------------------------------------------------------
# MCP handshake — youk-core
# ---------------------------------------------------------------------------

def test_youk_core_handshake():
    tools = get_tools("youk-core:latest")
    assert len(tools) > 0, "youk-core handshake returned no tools — is the server broken?"


def test_youk_core_tool_count():
    tools = get_tools("youk-core:latest")
    assert len(tools) >= 20, (
        f"youk-core only returned {len(tools)} tools (expected ≥20) — possible schema drift"
    )


def test_youk_core_critical_tools_present():
    tools = set(get_tools("youk-core:latest"))
    missing = CORE_CRITICAL_TOOLS - tools
    assert not missing, f"youk-core missing critical tools: {missing}"


# ---------------------------------------------------------------------------
# MCP handshake — youk-code
# ---------------------------------------------------------------------------

def test_youk_code_handshake():
    tools = get_tools("youk-code:latest")
    assert len(tools) > 0, "youk-code handshake returned no tools — is the server broken?"


def test_youk_code_tool_count():
    tools = get_tools("youk-code:latest")
    assert len(tools) >= 8, (
        f"youk-code only returned {len(tools)} tools (expected ≥8) — possible schema drift"
    )


def test_youk_code_critical_tools_present():
    tools = set(get_tools("youk-code:latest"))
    missing = CODE_CRITICAL_TOOLS - tools
    assert not missing, f"youk-code missing critical tools: {missing}"
