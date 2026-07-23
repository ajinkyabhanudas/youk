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

    import datetime
    raw = inspect.stdout.strip()
    # Docker LastTagTime format: "2026-07-19 10:38:35.695258219 +0000 UTC"
    # or zero time "0001-01-01 00:00:00 +0000 UTC" when unset.
    if not raw or raw.startswith("0001-"):
        pytest.skip("Docker image has no tag time metadata (built without explicit tag)")
    try:
        # Parse Go time format: "YYYY-MM-DD HH:MM:SS.nnnnnnnnn +0000 UTC"
        # Strip nanoseconds to microseconds and drop trailing "UTC" label
        parts = raw.split()
        if len(parts) >= 3:
            date_part = parts[0]  # YYYY-MM-DD
            time_part = parts[1]  # HH:MM:SS.nnnnnnnnn
            tz_part = parts[2]    # +0000
            # Truncate sub-second precision to 6 digits
            if "." in time_part:
                sec, frac = time_part.split(".", 1)
                time_part = f"{sec}.{frac[:6]}"
            normalised = f"{date_part}T{time_part}{tz_part}"
            image_dt = datetime.datetime.fromisoformat(normalised)
        else:
            # Fallback: try direct ISO parse after basic cleanup
            normalised = raw.rstrip("Z").split(".")[0].replace(" ", "T")
            image_dt = datetime.datetime.fromisoformat(normalised)
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
