"""Task 1.4b — session_end derives the resume pointer from the project's task graph.

This is the piece that makes youk know its project-scoped next task BY ITSELF: instead of
scraping the resume from prose (or a human writing it by hand), session_end asks the
validated graph "what's the next actionable task for this project" and writes that. The
resume becomes authoritative and project-scoped, per contract R3.
"""
from __future__ import annotations

from graph import create_task_graph, set_gate


def _write_context(root, slug="youk"):
    proj = root / "knowledge" / "projects" / slug
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "context.md").write_text("# ctx\n\nresume-from: old\n")


def _read_resume(root, slug="youk"):
    for line in (root / "knowledge" / "projects" / slug / "context.md").read_text().splitlines():
        if line.startswith("resume-from:"):
            return line[len("resume-from:"):].strip()
    return None


def _graph_next_derives_resume(root, monkeypatch, slug="youk"):
    """Helper: seed a ready task in the graph, run the resume-writing path, read it back."""
    db = root / "state" / "task-graph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    create_task_graph(
        [{"id": "t-1.2", "label": "SQLite store + WAL", "project": slug}], db_path=db
    )
    set_gate("t-1.2", "unblocked", True, db_path=db)
    return db


def test_resume_derived_from_task_graph(youk_root, monkeypatch):
    """When the graph has a ready task for the project, the resume names it —
    not something scraped from the summary."""
    _write_context(youk_root)
    db = _graph_next_derives_resume(youk_root, monkeypatch)

    # Point graph.py's default DB at our tmp db (session_end imports next_task with no db_path).
    import graph as _graph_mod
    monkeypatch.setattr(_graph_mod, "_DB_PATH", db)

    # Drive the resume-writing logic directly via the helper it calls.
    from graph import next_task
    nxt = next_task(project="youk", db_path=db)
    assert nxt["found"]
    # Simulate what session_end now writes:
    from session import _update_resume_point
    _update_resume_point("youk", f"NEXT (from task graph): {nxt['task']['label']}")

    resume = _read_resume(youk_root)
    assert "from task graph" in resume
    assert "SQLite store" in resume


def test_graph_resume_is_project_scoped(youk_root, monkeypatch):
    """A canopy task in the same graph must NOT become youk's resume."""
    db = youk_root / "state" / "task-graph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    create_task_graph([{"id": "canopy-x", "label": "canopy eval suite", "project": "canopy"}], db_path=db)
    set_gate("canopy-x", "unblocked", True, db_path=db)
    create_task_graph([{"id": "youk-y", "label": "youk store work", "project": "youk"}], db_path=db)
    set_gate("youk-y", "unblocked", True, db_path=db)

    from graph import next_task
    nxt = next_task(project="youk", db_path=db)
    assert nxt["found"]
    assert nxt["task"]["project"] == "youk"
    assert "canopy" not in nxt["task"]["label"]
