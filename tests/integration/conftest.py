"""Integration test fixtures.

These operate against the real filesystem and real Docker containers —
NOT against mocked paths. Do not monkeypatch YOUK_ROOT here.

Marks:
  @pytest.mark.integration — applied to all tests in this package via
  pytest.ini / pyproject.toml; excluded from `make test` (unit-only).
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

YOUK_DIR = Path.home() / ".claude" / "youk"
STATE_DIR = YOUK_DIR / "state"

# ---------------------------------------------------------------------------
# sys.path — so integration tests can import server modules for direct calls
# ---------------------------------------------------------------------------
for _p in [
    str(YOUK_DIR / "servers" / "shared"),
    str(YOUK_DIR / "servers" / "core" / "src"),
    str(YOUK_DIR / "servers" / "code" / "src"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Session-isolation guard
# ---------------------------------------------------------------------------
def _live_session_running() -> bool:
    return (STATE_DIR / "session-open.json").exists()


def pytest_collection_modifyitems(items):
    """Auto-add integration mark to all tests in this package."""
    integration_mark = pytest.mark.integration
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(integration_mark)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def require_docker(docker_available):
    if not docker_available:
        pytest.skip("Docker not running")


@pytest.fixture
def require_no_live_session():
    """Skip state-mutation tests when a real Claude Code session is active."""
    if _live_session_running():
        pytest.skip("Live session detected (session-open.json exists) — skipping state-mutation test")


@pytest.fixture
def sandbox_state(tmp_path, require_no_live_session) -> Path:
    """Isolated state dir for tests that call session_start / session_end.

    Passes this path to mcp_client as state_dir so Docker mounts it at
    /youk/state instead of the live state directory.
    Returns the Path to the temp state dir.
    """
    state = tmp_path / f"state-{uuid.uuid4().hex[:8]}"
    state.mkdir()
    return state


@pytest.fixture
def seed_state(sandbox_state):
    """Helper to write synthetic JSON state files into the sandbox."""
    def _write(filename: str, content: dict) -> Path:
        p = sandbox_state / filename
        p.write_text(json.dumps(content))
        return p
    return _write
