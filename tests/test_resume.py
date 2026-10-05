"""Where a project stopped is derived from facts, never stored as a note.

The old design kept a prose line (resume-from: in context.md) written by six code paths where
the last writer won and a stale line beat everything fresher. These tests pin the replacement:
the answer comes from the task graph and git, is scoped to one project, follows the task
lifecycle, and cannot be corrupted because nothing about it is written.
"""
from __future__ import annotations

import subprocess

import pytest

import graph
import resume


@pytest.fixture
def db(tmp_path):
    return tmp_path / "graph.db"


def _git_repo(path, files=("a.py",), commit=True):
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    for name in files:
        (path / name).write_text("x\n")
    if commit:
        run("add", "-A")
        run("commit", "-q", "-m", "first commit")
    return path


class TestTaskLifecycle:
    def test_start_task_tags_the_project_and_marks_it_in_flight(self, db):
        graph.start_task("t1", "build the thing", "youk", "youk-4", db_path=db)
        opened = graph.open_tasks("youk", db_path=db)
        assert [t["label"] for t in opened["in_flight"]] == ["build the thing"]
        assert opened["in_flight"][0]["session_id"] == "youk-4"

    def test_mark_done_closes_it(self, db):
        graph.start_task("t1", "build the thing", "youk", "youk-4", db_path=db)
        graph.mark_done("t1", db_path=db)
        assert graph.open_tasks("youk", db_path=db) == {"in_flight": [], "open_count": 0}

    def test_routing_a_finished_task_again_reopens_it(self, db):
        graph.start_task("t1", "same words", "youk", "youk-4", db_path=db)
        graph.mark_done("t1", db_path=db)
        graph.start_task("t1", "same words", "youk", "youk-9", db_path=db)
        assert len(graph.open_tasks("youk", db_path=db)["in_flight"]) == 1

    def test_creating_a_task_with_a_project_adopts_an_ownerless_row(self, db):
        graph.create_task_graph([{"id": "t1", "label": "seeded"}], db_path=db)
        graph.create_task_graph([{"id": "t1", "label": "seeded", "project": "youk"}], db_path=db)
        assert graph.open_tasks("youk", db_path=db)["open_count"] == 1


class TestScopedToOneProject:
    def test_another_projects_tasks_never_appear(self, db):
        graph.start_task("a", "canopy work", "canopy", "canopy-1", db_path=db)
        state = resume.where_stopped("youk", "/nowhere", db_path=db, git={})
        assert state["in_flight"] == [] and state["next"] is None and state["open_count"] == 0

    def test_ownerless_tasks_never_appear(self, db):
        graph.create_task_graph([{"id": "orphan", "label": "who owns me"}], db_path=db)
        graph.set_gate("orphan", "unblocked", True, db_path=db)
        state = resume.where_stopped("youk", "/nowhere", db_path=db, git={})
        assert state["next"] is None


class TestDerivation:
    def test_next_and_in_flight_are_reported_separately(self, db):
        graph.start_task("t1", "half done", "youk", "youk-4", db_path=db)
        graph.create_task_graph(
            [{"id": "t2", "label": "do this next", "project": "youk"}], db_path=db)
        graph.set_gate("t2", "unblocked", True, db_path=db)
        state = resume.where_stopped("youk", "/nowhere", db_path=db, git={})
        assert [t["label"] for t in state["in_flight"]] == ["half done"]
        assert state["next"]["label"] == "do this next"

    def test_same_inputs_give_the_same_answer(self, db):
        graph.start_task("t1", "half done", "youk", "youk-4", db_path=db)
        first = resume.render(resume.where_stopped("youk", "/x", db_path=db, git={}))
        second = resume.render(resume.where_stopped("youk", "/x", db_path=db, git={}))
        assert first == second and first

    def test_a_broken_database_costs_only_its_part(self, tmp_path):
        bad = tmp_path  # a directory, not a database file
        state = resume.where_stopped("youk", "/x", db_path=bad,
                                     git={"branch": "main", "head": "abc", "subject": "s",
                                          "age": "1 hour ago", "dirty": 0})
        assert state["in_flight"] == [] and state["git"]["branch"] == "main"
        assert "git: main" in resume.render(state)


class TestRender:
    GIT = {"branch": "feat/x", "head": "abc1234", "subject": "add the parser", "age": "2 hours ago",
           "dirty": 3}

    def test_mid_task_next_and_git_in_one_line(self, db):
        graph.start_task("t1", "wire the report", "youk", "youk-4", db_path=db)
        graph.create_task_graph([{"id": "t2", "label": "write the docs", "project": "youk"}], db_path=db)
        graph.set_gate("t2", "unblocked", True, db_path=db)
        line = resume.render(resume.where_stopped("youk", "/x", db_path=db, git=self.GIT))
        assert line.startswith("Resume: STOPPED MID-TASK: wire the report")
        assert "NEXT: write the docs" in line
        assert "git: feat/x, 3 uncommitted file(s), last commit abc1234 add the parser" in line

    def test_nothing_known_renders_nothing(self, db):
        assert resume.render(resume.where_stopped("youk", "/x", db_path=db, git=None)) == ""

    def test_the_projects_own_note_follows_the_facts_and_never_replaces_them(self, db):
        graph.start_task("t1", "wire the report", "youk", "youk-4", db_path=db)
        line = resume.render(resume.where_stopped("youk", "/x", db_path=db, git=None),
                             authored_note="finish the PRD review")
        assert line.index("STOPPED MID-TASK") < line.index("project note: finish the PRD review")

    def test_a_note_alone_still_shows(self, db):
        line = resume.render(resume.where_stopped("youk", "/x", db_path=db, git=None),
                             authored_note="finish the PRD review")
        assert line == "Resume: project note: finish the PRD review"

    def test_line_is_bounded(self, db):
        for i in range(5):
            graph.start_task(f"t{i}", "very long label " * 10, "youk", "youk-1", db_path=db)
        assert len(resume.render(resume.where_stopped("youk", "/x", db_path=db, git=self.GIT))) <= 300


class TestGitState:
    def test_branch_last_commit_and_uncommitted_files(self, tmp_path):
        repo = _git_repo(tmp_path / "repo")
        (repo / "b.py").write_text("new\n")
        (repo / "a.py").write_text("changed\n")
        state = resume.git_state(str(repo))
        assert state["branch"] == "main" and state["subject"] == "first commit"
        assert state["dirty"] == 2 and len(state["head"]) >= 7

    def test_a_directory_that_is_not_a_repo_gives_none(self, tmp_path):
        assert resume.git_state(str(tmp_path)) is None


class TestWiredIntoSessionStart:
    @pytest.fixture(autouse=True)
    def host(self, tmp_path, monkeypatch, youk_root):
        import session
        host_root = tmp_path / "claude"
        (host_root / "audit").mkdir(parents=True)
        monkeypatch.setattr(session, "HOST_ROOT", host_root)

    def test_a_task_started_and_never_finished_is_reported_at_the_next_start(self, tmp_path):
        import session
        repo = _git_repo(tmp_path / "proj-a")
        graph.start_task("t1", "migrate the billing table", "proj-a", "proj-a-3")
        state = session.start_session(str(repo))
        assert "STOPPED MID-TASK: migrate the billing table" in state.resume_point
        assert "git: main" in state.resume_point

    def test_after_the_task_is_finished_it_is_no_longer_reported(self, tmp_path):
        import session
        repo = _git_repo(tmp_path / "proj-b")
        graph.start_task("t1", "migrate the billing table", "proj-b", "proj-b-3")
        graph.mark_done("t1")
        state = session.start_session(str(repo))
        assert "STOPPED MID-TASK" not in state.resume_point

    def test_no_resume_line_is_written_to_context_md(self, youk_root, tmp_path):
        import session
        repo = _git_repo(tmp_path / "proj-c")
        session.start_session(str(repo))
        ctx = (youk_root / "knowledge" / "projects" / "proj-c" / "context.md").read_text()
        assert "resume-from" not in ctx

    def test_a_stale_resume_line_from_an_older_version_is_ignored_and_dropped(self, youk_root, tmp_path):
        import session
        repo = _git_repo(tmp_path / "proj-d")
        ctx_dir = youk_root / "knowledge" / "projects" / "proj-d"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "context.md").write_text(
            "# Project context: proj-d\n\nfirst-seen: 2026-01-01\nlast-seen: 2026-01-01\n"
            "resume-from: NEXT (from task graph): a stale note that must not win\n")
        state = session.start_session(str(repo))
        assert "stale note" not in state.resume_point
        assert "resume-from" not in (ctx_dir / "context.md").read_text()

    def test_the_old_writers_are_gone(self):
        import session
        for name in ("_update_resume_point", "_strip_resume_wrapping", "_resolve_youk_root"):
            assert not hasattr(session, name), f"{name} reintroduces a stored resume pointer"


class TestTaskCheckpointFinishesTheRoutedTask:
    def test_checkpoint_marks_the_task_route_task_started_as_done(self, tmp_path, monkeypatch):
        import json

        import session
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        monkeypatch.setattr("session.YOUK_ROOT", tmp_path)
        monkeypatch.setattr("session._build_brief", lambda _: {"brief": "B"})
        monkeypatch.setattr("session._load_state", lambda: {"last_project": "test", "session_counter": 1})
        monkeypatch.setattr("session._write_session_stub", lambda *a: None)
        monkeypatch.setattr("session._check_session_goal", lambda _: None)
        monkeypatch.setattr(graph, "_DB_PATH", tmp_path / "state" / "g.db")
        graph.start_task("abc123", "implement feature", "test", "test-1")
        (state_dir / "routing-breadcrumb.json").write_text(json.dumps(
            {"task": "implement feature", "task_id": "abc123", "size": "M"}))

        session.task_checkpoint(str(tmp_path), "implement feature", size="M")

        assert graph.open_tasks("test")["in_flight"] == []
