"""
Tests for _routed_task_id — the reader half of the routing-breadcrumb handoff.

The bug this guards: routing._write_routing_breadcrumb writes to
state/sessions/{slug}/routing-breadcrumb.json, while the gate mirrors in server.py
read state/routing-breadcrumb.json (root only). The paths never agreed once a slug
existed, so every gate mirror fell through to a task[:40] fallback and created a
phantom task row keyed on a truncated label instead of route_task's sha1 id.

test_writer_reader_agree_on_path is the data-flow contract test — it is the one that
fails on the pre-fix code, because it exercises the writer and the reader together
rather than either one alone.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

# server.py imports mcp.server.fastmcp specifically — guard the exact module, not the
# parent package, since mcp 2.x installs cleanly but renames FastMCP to MCPServer.
pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp<2 with the FastMCP API not installed — CI installs it",
)


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    """Point server, state_paths and routing at a temp YOUK_ROOT."""
    import server
    import state_paths
    import routing

    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    monkeypatch.setattr(state_paths, "YOUK_ROOT", tmp_path)
    monkeypatch.setattr(routing, "YOUK_ROOT", tmp_path)
    return tmp_path


def _write_breadcrumb(path: Path, task_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task": "t", "task_id": task_id, "size": "M"}))


class TestRoutedTaskId:
    def test_reads_slug_scoped_breadcrumb(self, rooted, monkeypatch):
        """The slug-scoped path is where route_task actually writes."""
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        _write_breadcrumb(
            rooted / "state" / "sessions" / "youk-99" / "routing-breadcrumb.json",
            "abc123def456",
        )
        assert server._routed_task_id() == "abc123def456"

    def test_slug_scoped_wins_over_root(self, rooted, monkeypatch):
        """A stale root breadcrumb must not shadow the current session's."""
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        _write_breadcrumb(
            rooted / "state" / "sessions" / "youk-99" / "routing-breadcrumb.json", "current"
        )
        _write_breadcrumb(rooted / "state" / "routing-breadcrumb.json", "stale")
        assert server._routed_task_id() == "current"

    def test_falls_back_to_root_for_slugless_session(self, rooted, monkeypatch):
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "")
        _write_breadcrumb(rooted / "state" / "routing-breadcrumb.json", "rootid")
        assert server._routed_task_id() == "rootid"

    def test_returns_none_when_absent(self, rooted, monkeypatch):
        """No breadcrumb means no id — never a value derived from the task text."""
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        assert server._routed_task_id() is None

    def test_returns_none_on_malformed_json(self, rooted, monkeypatch):
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        bad = rooted / "state" / "sessions" / "youk-99" / "routing-breadcrumb.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json")
        assert server._routed_task_id() is None

    def test_returns_none_when_task_id_key_missing(self, rooted, monkeypatch):
        """An older breadcrumb without task_id yields None, not a synthesised id."""
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        p = rooted / "state" / "sessions" / "youk-99" / "routing-breadcrumb.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"task": "t", "size": "M"}))
        assert server._routed_task_id() is None

    def test_read_does_not_create_session_dir(self, rooted, monkeypatch):
        """Path resolution must not mkdir — _sp.slug_state_dir does, so it is not used here."""
        import server
        monkeypatch.setattr(server, "_get_session_slug", lambda: "youk-99")
        server._routed_task_id()
        assert not (rooted / "state" / "sessions" / "youk-99").exists()

    def test_slug_lookup_failure_falls_back_to_root(self, rooted, monkeypatch):
        import server

        def _boom():
            raise RuntimeError("no session")

        monkeypatch.setattr(server, "_get_session_slug", _boom)
        _write_breadcrumb(rooted / "state" / "routing-breadcrumb.json", "rootid")
        assert server._routed_task_id() == "rootid"


class TestWriterReaderContract:
    def test_writer_reader_agree_on_path(self, rooted, monkeypatch):
        """route_task's write must be visible to the gate mirrors' read.

        This is the regression: before the fix the reader looked only at the root
        path while the writer used the slug-scoped one, so this returned None (and
        the caller then invented an id from the task text).
        """
        import server
        import routing

        slug = "youk-101"
        task = "reconcile the task graph against the shipped codebase"
        monkeypatch.setattr(server, "_get_session_slug", lambda: slug)

        routing._write_routing_breadcrumb(task, "M", slug=slug)

        import hashlib
        expected = hashlib.sha1(task.encode()).hexdigest()[:12]
        assert server._routed_task_id() == expected

    def test_read_id_is_not_derived_from_task_text(self, rooted, monkeypatch):
        """Guards the specific defect: a 40-char truncation of the task is not an id."""
        import server
        import routing

        slug = "youk-102"
        task = "a" * 120
        monkeypatch.setattr(server, "_get_session_slug", lambda: slug)
        routing._write_routing_breadcrumb(task, "M", slug=slug)

        got = server._routed_task_id()
        assert got != task[:40]
        assert len(got) == 12
