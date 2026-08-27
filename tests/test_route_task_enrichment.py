"""Tests for route_task DB enrichment — file_context and graph_state fields.

Tests enrich_route_result() from session.py directly — session.py has no mcp
dependency so these tests run on the host without Docker. Both enrichments must
be silent-fail: route_task never raises due to DB errors.
"""
from __future__ import annotations

import json
from pathlib import Path


import session as _session_mod  # conftest puts servers/core/src on sys.path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_open(state_dir: Path, slug: str = "testproject") -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "session-open.json").write_text(json.dumps({"slug": slug}))


def _enrich(monkeypatch, tmp_path, task="test task", *,
            find_relevant_return=None, get_all_tasks_return=None, next_task_return=None):
    """Call enrich_route_result with patched dependencies, return mutated result dict."""
    state_dir = tmp_path / "state"
    _make_session_open(state_dir)
    monkeypatch.setattr(_session_mod, "YOUK_ROOT", tmp_path)

    # Patch lazy imports inside enrich_route_result via the session module namespace.
    # The function uses `from file_index import find_relevant` at call time, so we
    # patch file_index and graph in sys.modules to intercept those imports.
    import sys
    from unittest.mock import MagicMock

    if find_relevant_return is not None:
        fake_fi = MagicMock()
        fake_fi.find_relevant = lambda *a, **kw: find_relevant_return
        sys.modules["file_index"] = fake_fi

    if get_all_tasks_return is not None or next_task_return is not None:
        fake_graph = MagicMock()
        fake_graph.get_all_tasks = lambda: (get_all_tasks_return or [])
        fake_graph.next_task = lambda: (next_task_return or {"found": False, "task": None})
        sys.modules["graph"] = fake_graph

    try:
        result: dict = {}
        _session_mod.enrich_route_result(result, task)
        return result
    finally:
        # Restore real modules — avoid polluting other tests
        for mod_name in ("file_index", "graph"):
            sys.modules.pop(mod_name, None)
            # Re-import the real module if it was replaced
            try:
                import importlib
                importlib.import_module(mod_name)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# file_context
# ---------------------------------------------------------------------------

class TestFileContext:
    def test_returns_hits_above_threshold(self, monkeypatch, tmp_path):
        """Hits with score < -0.5 appear in file_context."""
        fc = {"results": [
            {"file_path": "src/session.py", "project_slug": "youk", "score": -1.2},
            {"file_path": "src/server.py",  "project_slug": "youk", "score": -0.8},
        ]}
        result = _enrich(monkeypatch, tmp_path, find_relevant_return=fc, get_all_tasks_return=[])
        assert len(result["file_context"]) == 2
        assert result["file_context"][0]["file"] == "src/session.py"

    def test_filters_weak_matches(self, monkeypatch, tmp_path):
        """Hits with score >= -0.5 are excluded."""
        fc = {"results": [
            {"file_path": "src/session.py", "project_slug": "youk", "score": -1.0},
            {"file_path": "README.md",       "project_slug": "youk", "score": -0.1},
        ]}
        result = _enrich(monkeypatch, tmp_path, find_relevant_return=fc, get_all_tasks_return=[])
        assert len(result["file_context"]) == 1
        assert result["file_context"][0]["file"] == "src/session.py"

    def test_empty_when_no_results(self, monkeypatch, tmp_path):
        result = _enrich(monkeypatch, tmp_path,
                         find_relevant_return={"results": []}, get_all_tasks_return=[])
        assert result["file_context"] == []

    def test_fallback_to_longest_word(self, monkeypatch, tmp_path):
        """When full-task query returns 0 hits, falls back to longest word."""
        calls = []

        def _mock_find(query, **kw):
            calls.append(query)
            if len(calls) == 1:
                return {"results": [], "total": 0}
            return {"results": [{"file_path": "src/session.py", "project_slug": "p", "score": -3.0}], "total": 1}

        import sys
        from unittest.mock import MagicMock
        fake_fi = MagicMock()
        fake_fi.find_relevant = _mock_find
        fake_graph = MagicMock()
        fake_graph.get_all_tasks = lambda: []
        sys.modules["file_index"] = fake_fi
        sys.modules["graph"] = fake_graph

        monkeypatch.setattr(_session_mod, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        _make_session_open(state_dir)

        try:
            result: dict = {}
            _session_mod.enrich_route_result(result, "fix bug in session_start")
            assert len(calls) == 2
            assert calls[1] == "session_start"  # longest word
            assert len(result["file_context"]) == 1
        finally:
            for m in ("file_index", "graph"):
                sys.modules.pop(m, None)

    def test_silent_fail_on_exception(self, monkeypatch, tmp_path):
        """Exception in find_relevant → file_context defaults to [], never raises."""
        import sys
        from unittest.mock import MagicMock
        fake_fi = MagicMock()
        fake_fi.find_relevant = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        fake_graph = MagicMock()
        fake_graph.get_all_tasks = lambda: []
        sys.modules["file_index"] = fake_fi
        sys.modules["graph"] = fake_graph

        monkeypatch.setattr(_session_mod, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        _make_session_open(state_dir)

        try:
            result: dict = {}
            _session_mod.enrich_route_result(result, "any task")
            assert result["file_context"] == []
        finally:
            for m in ("file_index", "graph"):
                sys.modules.pop(m, None)

    def test_result_shape(self, monkeypatch, tmp_path):
        """Each file_context entry has exactly: file, project, score."""
        fc = {"results": [{"file_path": "a.py", "project_slug": "p", "score": -2.0}]}
        result = _enrich(monkeypatch, tmp_path, find_relevant_return=fc, get_all_tasks_return=[])
        assert set(result["file_context"][0].keys()) == {"file", "project", "score"}
        assert result["file_context"][0]["score"] == -2.0


# ---------------------------------------------------------------------------
# graph_state
# ---------------------------------------------------------------------------

class TestGraphState:
    def test_empty_when_zero_tasks(self, monkeypatch, tmp_path):
        """Key is always present. RouteTaskResult is total=False, so an omitted field is
        default-filled with null by the output validator and fails its non-nullable
        "type": "object" check. Empty dict is the empty signal."""
        result = _enrich(monkeypatch, tmp_path,
                         find_relevant_return={"results": []}, get_all_tasks_return=[])
        assert result["graph_state"] == {}

    def test_empty_when_one_task(self, monkeypatch, tmp_path):
        """Single-task sessions: no graph_state computation, but the key still exists."""
        result = _enrich(monkeypatch, tmp_path,
                         find_relevant_return={"results": []},
                         get_all_tasks_return=[{"id": "t1", "unblocked": True}])
        assert result["graph_state"] == {}

    def test_present_when_multiple_tasks(self, monkeypatch, tmp_path):
        tasks = [
            {"id": "t1", "unblocked": True},
            {"id": "t2", "unblocked": False},
            {"id": "t3", "unblocked": False},
        ]
        next_t = {"found": True, "task": {"id": "t1", "label": "first task"}}
        result = _enrich(monkeypatch, tmp_path,
                         find_relevant_return={"results": []},
                         get_all_tasks_return=tasks,
                         next_task_return=next_t)
        assert "graph_state" in result
        gs = result["graph_state"]
        assert gs["total_tasks"] == 3
        assert gs["blocked_count"] == 2
        assert gs["next_task"] == {"id": "t1", "label": "first task"}

    def test_blocked_count_accuracy(self, monkeypatch, tmp_path):
        """blocked_count counts all tasks where unblocked is falsy."""
        tasks = [
            {"id": "t1", "unblocked": True},
            {"id": "t2", "unblocked": False},
            {"id": "t3", "unblocked": 0},    # falsy int
            {"id": "t4", "unblocked": True},
        ]
        result = _enrich(monkeypatch, tmp_path,
                         find_relevant_return={"results": []},
                         get_all_tasks_return=tasks,
                         next_task_return={"found": False, "task": None})
        assert result["graph_state"]["blocked_count"] == 2

    def test_silent_fail_on_exception(self, monkeypatch, tmp_path):
        """Exception in get_all_tasks → graph_state stays {}, never raises."""
        import sys
        from unittest.mock import MagicMock
        fake_fi = MagicMock()
        fake_fi.find_relevant = lambda *a, **kw: {"results": []}
        fake_graph = MagicMock()
        fake_graph.get_all_tasks = lambda: (_ for _ in ()).throw(RuntimeError("graph gone"))
        sys.modules["file_index"] = fake_fi
        sys.modules["graph"] = fake_graph

        monkeypatch.setattr(_session_mod, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        _make_session_open(state_dir)

        try:
            result: dict = {}
            _session_mod.enrich_route_result(result, "any task")
            assert result["graph_state"] == {}
        finally:
            for m in ("file_index", "graph"):
                sys.modules.pop(m, None)
