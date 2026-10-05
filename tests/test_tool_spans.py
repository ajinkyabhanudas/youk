"""Server-side spans (servers/shared/tool_spans.py).

The wrapper must be invisible to the tool: same result, same exception, same signature. And
every tool registered on the real servers must actually be wrapped, because a tool added later
that escaped the wrapper would be silently uninstrumented.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import time
from pathlib import Path

import pytest

import events
import tool_spans

REPO = Path(__file__).parent.parent


class FakeMCP:
    """Stands in for FastMCP: records what gets registered."""

    def __init__(self):
        self.registered = {}

    def tool(self, *args, **kwargs):
        def register(fn):
            self.registered[fn.__name__] = fn
            return fn
        return register


def _server(tmp_path, slug="proj"):
    mcp = FakeMCP()
    tool_spans.install_tool_spans(mcp, lambda: tmp_path, lambda: slug)
    return mcp


def _ledger(root, slug="proj"):
    return list(events.read_events(root, slug))


class TestTransparency:
    def test_result_and_signature_pass_through(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def add(a: int, b: int = 2) -> dict:
            """Add."""
            return {"sum": a + b}

        fn = mcp.registered["add"]
        assert fn(1, b=5) == {"sum": 6}
        assert inspect.signature(fn) == inspect.signature(fn.__wrapped__)
        assert fn.__doc__ == "Add." and fn.__name__ == "add"

    def test_exception_is_reraised_and_recorded_as_fail(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def boom():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            mcp.registered["boom"]()
        (tool,) = [e for e in _ledger(tmp_path) if e["kind"] == "tool"]
        assert tool["status"] == "fail" and tool["name"] == "boom" and tool["src"] == "server"

    def test_bare_decorator_form_also_wraps(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool
        def ping():
            return {"ok": True}

        assert mcp.registered["ping"]() == {"ok": True}
        assert [e["name"] for e in _ledger(tmp_path) if e["kind"] == "tool"] == ["ping"]

    def test_an_unwritable_ledger_never_breaks_the_tool(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        mcp = FakeMCP()
        tool_spans.install_tool_spans(mcp, lambda: blocker, lambda: "proj")

        @mcp.tool()
        def fine():
            return {"ok": 1}

        assert mcp.registered["fine"]() == {"ok": 1}

    def test_overhead_is_small(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def noop():
            return {}

        raw, wrapped = noop.__wrapped__ if hasattr(noop, "__wrapped__") else noop, mcp.registered["noop"]
        start = time.perf_counter()
        for _ in range(300):
            wrapped()
        per_call_ms = (time.perf_counter() - start) * 1000 / 300
        assert per_call_ms < 2, f"{per_call_ms:.2f} ms per call"
        assert raw is not None


class TestStatusAndGateEvents:
    def test_blocked_result_is_status_block(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def check_nfr_gate(task: str, size: str):
            return {"blocked": True, "reason": "run nfr_check"}

        mcp.registered["check_nfr_gate"]("t", "M")
        got = _ledger(tmp_path)
        assert [(e["kind"], e["name"], e["status"]) for e in got if e["kind"] == "gate"] == [
            ("gate", "nfr", "block")]
        assert [e["status"] for e in got if e["kind"] == "tool"] == ["block"]

    def test_error_result_is_status_fail(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def flaky():
            return {"error": "bad input", "error_type": "INPUT"}

        mcp.registered["flaky"]()
        assert [e["status"] for e in _ledger(tmp_path) if e["kind"] == "tool"] == ["fail"]

    def test_set_gate_records_which_gate_and_the_task_hashed(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def set_gate(task_id: str, gate_name: str, value: bool, session_id=None):
            return {"ok": True}

        mcp.registered["set_gate"]("migrate-billing", "nfr_cleared", True)
        (gate,) = [e for e in _ledger(tmp_path) if e["kind"] == "gate"]
        assert gate["name"] == "set.nfr_cleared" and gate["n"] == 1
        assert gate["task"] == events.hash_identifier("migrate-billing")
        raw = "".join(p.read_text() for p in (tmp_path / "state" / "events").rglob("*.jsonl"))
        assert "migrate-billing" not in raw

    def test_mark_done_route_checkpoint_and_session_end_become_lifecycle_events(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def mark_task_done(task_id: str):
            return {"ok": True}

        @mcp.tool()
        def route_task(task: str):
            return {"size": "M"}

        @mcp.tool()
        def task_checkpoint(project_dir: str, task_label: str, size: str = "M"):
            return {}

        @mcp.tool()
        def session_end(outcome: str):
            return {}

        mcp.registered["mark_task_done"]("T-1")
        mcp.registered["route_task"]("do the thing")
        mcp.registered["task_checkpoint"]("/p", "label", "L")
        mcp.registered["session_end"]("done")
        names = {(e["kind"], e["name"]) for e in _ledger(tmp_path) if e["kind"] != "tool"}
        assert names == {("outcome", "task_done"), ("gate", "route.M"),
                         ("outcome", "checkpoint.L"), ("outcome", "session_end")}

    def test_free_text_in_arguments_never_reaches_an_event_name(self, tmp_path):
        mcp = _server(tmp_path)

        @mcp.tool()
        def set_gate(task_id: str, gate_name: str, value: bool):
            return {}

        mcp.registered["set_gate"]("t", "please fix the login bug", True)
        assert [e for e in _ledger(tmp_path) if e["kind"] == "gate"] == []

    def test_session_id_carries_the_counter_hashed(self, tmp_path):
        (tmp_path / "state").mkdir()
        (tmp_path / "state" / "session.json").write_text(json.dumps({"session_counter": 7}))
        mcp = _server(tmp_path)

        @mcp.tool()
        def ping():
            return {}

        mcp.registered["ping"]()
        (tool,) = _ledger(tmp_path)
        assert tool["session"] == events.hash_identifier("proj-7")


def _load_server(which: str):
    """Load servers/{which}/src/server.py by path. Both are named server.py, so a plain
    `import server` gets whichever directory is first on sys.path."""
    pytest.importorskip("mcp.server.fastmcp", reason="needs mcp<2")
    path = REPO / "servers" / which / "src" / "server.py"
    spec = importlib.util.spec_from_file_location(f"youk_{which}_server_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEveryRealToolIsWrapped:
    @pytest.mark.parametrize("which,minimum", [("core", 50), ("code", 5)])
    def test_every_registered_tool_is_wrapped(self, which, minimum):
        module = _load_server(which)
        tools = module.mcp._tool_manager.list_tools()
        assert len(tools) >= minimum
        unwrapped = [t.name for t in tools if not getattr(t.fn, "__youk_span__", False)]
        assert unwrapped == []
