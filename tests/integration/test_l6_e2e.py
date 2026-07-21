"""L6 — End-to-End Session Trace.

Full round-trip via real MCP JSON-RPC calls against Docker containers.
Uses a sandboxed temp state dir — never touches live state/.

Slug correlation is verified at each step: the slug written by session_start
must appear in every state file written by downstream tools.
"""
import json
import datetime
from pathlib import Path


from .mcp_client import call_tool, YOUK_DIR

YOUK_DIR_STR = str(YOUK_DIR)
STATE_DIR = YOUK_DIR / "state"


def _read_slug(sandbox_state: Path) -> str | None:
    f = sandbox_state / "session-open.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text()).get("slug")
    except (json.JSONDecodeError, KeyError):
        return None


class TestEndToEndSession:
    """Full session round-trip — every step depends on the previous."""

    def test_step1_session_start(self, sandbox_state):
        r = call_tool(
            "youk-core:latest", "session_start",
            {"project_dir": YOUK_DIR_STR},
            state_dir=sandbox_state,
        )
        # Required fields in response
        for field in ("project", "resume_point", "session_counter", "session_plan"):
            assert field in r, f"session_start missing field: {field}"

        # session-open.json written
        f = sandbox_state / "session-open.json"
        assert f.exists(), "session_start must write session-open.json"
        data = json.loads(f.read_text())
        assert data.get("slug"), "session-open.json must have non-empty slug"

    def test_step2_route_task_m_size(self, sandbox_state):
        # Ensure session is open first
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        session_slug = _read_slug(sandbox_state)
        assert session_slug, "session-open.json must exist before route_task"

        r = call_tool(
            "youk-core:latest", "route_task",
            {"task": "implement user notification system", "project_dir": YOUK_DIR_STR},
            state_dir=sandbox_state,
        )
        assert r.get("size") == "M", f"Expected M, got {r.get('size')}"
        assert r.get("blocked") is False

        # Breadcrumb written
        bc = sandbox_state / "routing-breadcrumb.json"
        assert bc.exists(), "route_task(M) must write routing-breadcrumb.json"

        # Slug correlation
        bc_data = json.loads(bc.read_text())
        assert bc_data.get("slug") == session_slug, (
            f"Slug mismatch: session-open.json has '{session_slug}' "
            f"but routing-breadcrumb.json has '{bc_data.get('slug')}'"
        )

    def test_step3_route_to_skill_code_review(self, sandbox_state):
        # Seed a session so route_to_skill has context
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)

        r = call_tool(
            "youk-code:latest", "route_to_skill",
            {"skill": "code-review", "task": "review the auth module changes"},
            state_dir=sandbox_state,
        )
        assert r.get("mode") == "in_session", (
            f"route_to_skill returned mode={r.get('mode')!r}, expected 'in_session'"
        )
        assert r.get("skill_content"), "route_to_skill returned empty skill_content"
        assert r.get("task"), "route_to_skill returned empty task"

    def test_step4_session_end_cleanup(self, sandbox_state):
        # Full sequence: start → route → end
        call_tool("youk-core:latest", "session_start",
                  {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "route_task",
                  {"task": "implement user notifications", "project_dir": YOUK_DIR_STR},
                  state_dir=sandbox_state)

        # Seed transient state files that session_end must clean up
        (sandbox_state / "goal-anchor.json").write_text(json.dumps({
            "stated_goal": "test goal",
            "success_criteria": ["done"],
            "set_at": datetime.datetime.utcnow().isoformat(),
        }))
        (sandbox_state / "reentry-log.json").write_text(json.dumps([
            {"from": "code-review", "to": "nfr-check",
             "ts": datetime.datetime.utcnow().isoformat(), "label": "test"},
        ]))

        call_tool("youk-core:latest", "session_end", {
            "summary": "checkup e2e test session",
            "commits_made": False,
            "close_cluster": True,
        }, state_dir=sandbox_state)

        # session-open.json deleted
        assert not (sandbox_state / "session-open.json").exists(), (
            "session_end must delete session-open.json"
        )
        # routing-breadcrumb.json deleted
        assert not (sandbox_state / "routing-breadcrumb.json").exists(), (
            "session_end must delete routing-breadcrumb.json"
        )
        # goal-anchor.json deleted
        assert not (sandbox_state / "goal-anchor.json").exists(), (
            "session_end must delete goal-anchor.json"
        )
        # reentry-log.json deleted
        assert not (sandbox_state / "reentry-log.json").exists(), (
            "session_end must delete reentry-log.json"
        )

    def test_step6_self_heal_returns_health(self, sandbox_state):
        """Health loop is reachable — self_heal returns org_score via real MCP."""
        r = call_tool("youk-core:latest", "self_heal", {}, state_dir=sandbox_state)
        assert "org_score" in r, f"self_heal missing org_score: {list(r.keys())}"
        assert isinstance(r.get("org_score"), int | float), (
            f"org_score must be numeric, got {type(r.get('org_score'))}"
        )
        assert "findings" in r, "self_heal must return findings list"
        # proposals or skill_gap_signals must be present (may be empty — that's fine)
        assert "proposals" in r or "skill_gap_signals" in r, (
            f"self_heal must return proposals or skill_gap_signals, got keys: {list(r.keys())}"
        )

    def test_step5_session_counter_increments(self, sandbox_state):
        """session_counter in session.json must increment across two sessions."""
        r1 = call_tool("youk-core:latest", "session_start",
                       {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "session_end", {
            "summary": "first session", "commits_made": False,
        }, state_dir=sandbox_state)

        r2 = call_tool("youk-core:latest", "session_start",
                       {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
        call_tool("youk-core:latest", "session_end", {
            "summary": "second session", "commits_made": False,
        }, state_dir=sandbox_state)

        c1 = r1.get("session_counter", 0)
        c2 = r2.get("session_counter", 0)
        assert c2 > c1, (
            f"session_counter must increment: first={c1}, second={c2}"
        )
