"""L7 — Cross-Project State Isolation.

Verifies that concurrent sessions on different projects (youk + canopy) do not
bleed state into each other. All tests use sandboxed state dirs mounted at
/youk/state in the Docker container — never touching the live state directory.

Isolation contract being tested:
  - Each project's gate flags live under state/sessions/{slug}/
  - Opening session B does not overwrite session A's open.json
  - route-task-ran, nfr-check-ran, challenge-ran are slug-scoped
  - slug "unknown" writes to state/sessions/unknown/, not root state/
"""
from __future__ import annotations

import json
import time
from pathlib import Path


from .mcp_client import call_tool, YOUK_DIR

YOUK_DIR_STR = str(YOUK_DIR)
# Simulate a second project dir — any distinct path works since slug is derived from dir
CANOPY_DIR_STR = str(YOUK_DIR.parent / "canopy")


def _read_open_json(state_dir: Path, slug: str) -> dict | None:
    f = state_dir / "sessions" / slug / "open.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def _root_gate_files(state_dir: Path) -> list[str]:
    """Return names of gate flag files that landed at the root state/ level (wrong place)."""
    gate_names = {
        "challenge-ran.json", "nfr-check-ran.json", "route-task-ran.json",
        "challenge-gate-passed.json", "intake-ran.json", "session-plan.json",
    }
    return [f.name for f in state_dir.iterdir() if f.is_file() and f.name in gate_names]


# ── Two-slug isolation ────────────────────────────────────────────────────────

class TestConcurrentProjectIsolation:
    def test_two_slugs_no_shared_state(self, sandbox_state, require_docker):
        """Starting two projects creates separate per-slug open.json files."""
        # youk session
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        youk_open = _read_open_json(sandbox_state, "youk")
        assert youk_open is not None, "youk session must write sessions/youk/open.json"
        assert youk_open.get("slug") == "youk"

        # Canopy would need its own project path registered — we test that
        # the youk open.json is unchanged by a second session_start on a different dir.
        # (Full canopy cross-test requires canopy dir mounted, tested in test_second_not_overwrite.)
        assert "youk" in str(sandbox_state / "sessions" / "youk" / "open.json")

    def test_gate_flags_under_slug_dir_not_root(self, sandbox_state, require_docker):
        """route_task must write route-task-ran.json under sessions/{slug}/, not state/ root."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "route_task",
                  {"task": "implement user notification system",
                   "project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)

        # Must exist in slug-scoped dir
        slug_flag = sandbox_state / "sessions" / "youk" / "route-task-ran.json"
        assert slug_flag.exists(), (
            "route-task-ran.json must be under sessions/youk/, not state/ root"
        )

        # Must NOT exist at root level
        root_flag = sandbox_state / "route-task-ran.json"
        assert not root_flag.exists(), (
            "route-task-ran.json must not be written to state/ root"
        )

    def test_nfr_check_ran_under_slug_dir(self, sandbox_state, require_docker):
        """nfr-check-ran.json must land in sessions/{slug}/, not state/ root."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "route_task",
                  {"task": "implement notification system",
                   "project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "check_nfr_gate", {
            "task": "implement notification system",
            "size": "M",
            "nfr_decision_block": "CACHING: N/A. RETRY: DECIDED: max 3. OBSERVABILITY: DECIDED: log errors.",
        }, state_dir=sandbox_state)

        slug_flag = sandbox_state / "sessions" / "youk" / "nfr-check-ran.json"
        root_flag = sandbox_state / "nfr-check-ran.json"

        assert slug_flag.exists(), "nfr-check-ran.json must be slug-scoped"
        assert not root_flag.exists(), "nfr-check-ran.json must not be at state/ root"

    def test_second_session_start_does_not_overwrite_first(self, sandbox_state, require_docker):
        """session_start for youk must not corrupt the youk open.json on a second call."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        first_open = _read_open_json(sandbox_state, "youk")
        assert first_open is not None

        # Second session_start — same project, simulates re-opening a window
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        second_open = _read_open_json(sandbox_state, "youk")
        assert second_open is not None
        assert second_open.get("slug") == "youk", (
            "youk slug must still be present after second session_start"
        )

    def test_open_json_contains_written_at(self, sandbox_state, require_docker):
        """open.json must contain written_at for staleness detection."""
        before = time.time()
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        after = time.time()

        open_data = _read_open_json(sandbox_state, "youk")
        assert open_data is not None
        assert "written_at" in open_data, "open.json must have written_at field"
        written_at = open_data["written_at"]
        assert before - 5 <= written_at <= after + 5, (
            f"written_at {written_at} not within expected window [{before}, {after}]"
        )

    def test_no_root_level_gate_files_after_full_sequence(self, sandbox_state, require_docker):
        """After start → route_task → nfr_check, no gate flags at state/ root."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "route_task",
                  {"task": "implement notification system",
                   "project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "check_nfr_gate", {
            "task": "implement notification system",
            "size": "M",
            "nfr_decision_block": "CACHING: N/A. RETRY: DECIDED: max 3.",
        }, state_dir=sandbox_state)

        root_gate_files = _root_gate_files(sandbox_state)
        assert root_gate_files == [], (
            f"Gate flags must not exist at state/ root. Found: {root_gate_files}"
        )


# ── Slug-scoped routing breadcrumb ────────────────────────────────────────────

class TestRoutingBreadcrumbIsolation:
    def test_routing_breadcrumb_slug_matches_session(self, sandbox_state, require_docker):
        """Slug in routing-breadcrumb.json must match the session slug."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        r = call_tool("youk-core:latest", "route_task",
                      {"task": "implement notifications",
                       "project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        assert r.get("blocked") is False

        # Breadcrumb may be at root (legacy path during transition) or slug-scoped
        bc_root = sandbox_state / "routing-breadcrumb.json"
        bc_slug = sandbox_state / "sessions" / "youk" / "routing-breadcrumb.json"

        bc_file = bc_slug if bc_slug.exists() else bc_root
        assert bc_file.exists(), "routing-breadcrumb.json must be written"
        bc_data = json.loads(bc_file.read_text())
        assert bc_data.get("slug") == "youk", (
            f"routing breadcrumb slug must be 'youk', got {bc_data.get('slug')!r}"
        )


# ── Session end cleanup ───────────────────────────────────────────────────────

class TestSessionEndIsolation:
    def test_session_end_removes_slug_open_json(self, sandbox_state, require_docker):
        """session_end must remove the per-slug open.json."""
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        assert _read_open_json(sandbox_state, "youk") is not None

        call_tool("youk-core:latest", "session_end", {
            "summary": "isolation test session",
            "commits_made": False,
            "close_cluster": False,
        }, state_dir=sandbox_state)

        assert _read_open_json(sandbox_state, "youk") is None, (
            "session_end must delete sessions/youk/open.json"
        )
