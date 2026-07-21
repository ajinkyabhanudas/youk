"""L2 — Route Reachability: route_task sizing + session lifecycle via real MCP calls."""
import json

import pytest

from .mcp_client import call_tool, YOUK_DIR

YOUK_DIR_STR = str(YOUK_DIR)

# ---------------------------------------------------------------------------
# route_task sizing (all via MCP — verifies JSON-RPC wiring, not just the function)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def route(sandbox_state):
    """Call route_task via MCP, return the result dict."""
    def _route(task: str, intent_brief: dict | None = None) -> dict:
        args = {"task": task, "project_dir": YOUK_DIR_STR}
        if intent_brief:
            args["intent_brief"] = intent_brief
        return call_tool("youk-core:latest", "route_task", args, state_dir=sandbox_state)
    return _route


def test_xs_task_routes_xs(route):
    r = route("fix typo in README")
    assert r.get("size") == "XS"
    assert r.get("blocked") is False


def test_s_task_routes_s(route):
    r = route("fix the login validation bug")
    assert r.get("size") == "S"
    assert r.get("blocked") is False


def test_m_task_routes_m(route):
    r = route("implement user notification system")
    assert r.get("size") == "M"
    assert r.get("blocked") is False
    skills = r.get("skills", [])
    assert any("dev" in s for s in skills), f"dev_loop not in M skills: {skills}"


def test_l_task_routes_l(route):
    r = route("design and implement a new authentication module with OAuth2 support")
    assert r.get("size") in ("L", "XL")
    assert r.get("blocked") is False


def test_ambiguous_brief_blocks(sandbox_state):
    args = {
        "task": "make it better",
        "project_dir": YOUK_DIR_STR,
        "intent_brief": {
            "ambiguity_detected": True,
            "collapsing_question": "Better for whom — Jajean's query speed or the admin's throughput?",
        },
    }
    r = call_tool("youk-core:latest", "route_task", args, state_dir=sandbox_state)
    assert r.get("blocked") is True
    assert r.get("collapsing_question"), "blocked=True but no collapsing_question returned"


def test_m_task_writes_routing_breadcrumb(sandbox_state):
    args = {"task": "implement retry logic for health endpoint", "project_dir": YOUK_DIR_STR}
    call_tool("youk-core:latest", "route_task", args, state_dir=sandbox_state)
    breadcrumb = sandbox_state / "routing-breadcrumb.json"
    assert breadcrumb.exists(), "route_task(M) should write routing-breadcrumb.json"
    data = json.loads(breadcrumb.read_text())
    assert data.get("size") == "M"


def test_xs_task_does_not_write_breadcrumb(sandbox_state):
    existing = sandbox_state / "routing-breadcrumb.json"
    if existing.exists():
        existing.unlink()
    args = {"task": "fix typo in README", "project_dir": YOUK_DIR_STR}
    call_tool("youk-core:latest", "route_task", args, state_dir=sandbox_state)
    assert not existing.exists(), "route_task(XS) must NOT write routing-breadcrumb.json"


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def test_session_start_returns_required_fields(sandbox_state):
    r = call_tool("youk-core:latest", "session_start", {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
    for field in ("project", "resume_point", "session_counter", "session_plan"):
        assert field in r, f"session_start missing field: {field}"


def test_session_start_writes_session_open(sandbox_state):
    call_tool("youk-core:latest", "session_start", {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
    f = sandbox_state / "session-open.json"
    assert f.exists(), "session_start must write state/session-open.json"
    data = json.loads(f.read_text())
    assert data.get("slug"), "session-open.json must contain a non-empty slug"


def test_session_end_deletes_session_open(sandbox_state):
    call_tool("youk-core:latest", "session_start", {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
    assert (sandbox_state / "session-open.json").exists()
    call_tool("youk-core:latest", "session_end", {
        "summary": "integration test session",
        "commits_made": False,
    }, state_dir=sandbox_state)
    assert not (sandbox_state / "session-open.json").exists(), (
        "session_end must delete session-open.json"
    )


def test_session_end_deletes_goal_anchor(seed_state, sandbox_state):
    import datetime
    seed_state("goal-anchor.json", {
        "stated_goal": "test goal",
        "success_criteria": ["criterion A"],
        "set_at": datetime.datetime.utcnow().isoformat(),
    })
    call_tool("youk-core:latest", "session_start", {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
    call_tool("youk-core:latest", "session_end", {
        "summary": "test cleanup",
        "commits_made": False,
    }, state_dir=sandbox_state)
    assert not (sandbox_state / "goal-anchor.json").exists(), (
        "session_end must delete goal-anchor.json"
    )


def test_session_end_deletes_reentry_log(seed_state, sandbox_state):
    import datetime
    seed_state("reentry-log.json", [
        {"from": "code-review", "to": "nfr-check", "ts": datetime.datetime.utcnow().isoformat(), "label": "test"},
    ])
    call_tool("youk-core:latest", "session_start", {"project_dir": YOUK_DIR_STR}, state_dir=sandbox_state)
    call_tool("youk-core:latest", "session_end", {
        "summary": "test cleanup",
        "commits_made": False,
    }, state_dir=sandbox_state)
    assert not (sandbox_state / "reentry-log.json").exists(), (
        "session_end must delete reentry-log.json"
    )
