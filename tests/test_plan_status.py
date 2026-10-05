"""The plan's status lives in the task graph, and routing work that names a plan task uses its node."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graph
import plan_status

REPO = Path(__file__).parent.parent
PLAN = REPO / "docs" / "value-plan" / "tasks.json"


@pytest.fixture
def db(tmp_path):
    return tmp_path / "g.db"


def _task(db, task_id, project="youk"):
    graph.create_task_graph([{"id": task_id, "label": task_id, "project": project}], db_path=db)


class TestFindMentionedTask:
    def test_full_id_and_short_form_both_match(self, db):
        _task(db, "VP-S08")
        assert graph.find_mentioned_task("youk", "please do VP-S08 now", db_path=db) == "VP-S08"
        assert graph.find_mentioned_task("youk", "build S08 replay battery", db_path=db) == "VP-S08"
        assert graph.find_mentioned_task("youk", "build s08", db_path=db) == "VP-S08"

    def test_only_whole_tokens_match(self, db):
        _task(db, "VP-S08")
        assert graph.find_mentioned_task("youk", "S080 is something else", db_path=db) is None
        assert graph.find_mentioned_task("youk", "the MIS08 file", db_path=db) is None

    def test_two_candidates_is_ambiguous(self, db):
        _task(db, "VP-S08")
        _task(db, "OTHER-S08")
        assert graph.find_mentioned_task("youk", "do S08", db_path=db) is None

    def test_finished_and_foreign_tasks_are_not_matched(self, db):
        _task(db, "VP-S08")
        graph.mark_done("VP-S08", db_path=db)
        assert graph.find_mentioned_task("youk", "S08", db_path=db) is None
        _task(db, "VP-S09", project="canopy")
        assert graph.find_mentioned_task("youk", "S09", db_path=db) is None


class TestRoutingUsesThePlanNode:
    def test_the_breadcrumb_carries_the_plan_nodes_id(self, tmp_path, monkeypatch, db):
        import routing
        monkeypatch.setattr(graph, "_DB_PATH", db)
        monkeypatch.setattr(routing, "YOUK_ROOT", tmp_path)
        _task(db, "VP-S08")
        routing._write_routing_breadcrumb("build S08 replay battery", "M", slug="youk")
        crumb = json.loads((tmp_path / "state" / "sessions" / "youk" / "routing-breadcrumb.json").read_text())
        assert crumb["task_id"] == "VP-S08"

    def test_unrelated_work_still_gets_a_hashed_id(self, tmp_path, monkeypatch, db):
        import routing
        monkeypatch.setattr(graph, "_DB_PATH", db)
        monkeypatch.setattr(routing, "YOUK_ROOT", tmp_path)
        _task(db, "VP-S08")
        routing._write_routing_breadcrumb("fix a typo in the readme", "M", slug="youk")
        crumb = json.loads((tmp_path / "state" / "sessions" / "youk" / "routing-breadcrumb.json").read_text())
        assert len(crumb["task_id"]) == 12 and crumb["task_id"] != "VP-S08"

    def test_start_then_checkpoint_closes_the_plan_node(self, tmp_path, monkeypatch, db):
        import routing
        import session
        monkeypatch.setattr(graph, "_DB_PATH", db)
        monkeypatch.setattr(routing, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr("session.YOUK_ROOT", tmp_path)
        monkeypatch.setattr("session._build_brief", lambda _: {"brief": "B"})
        monkeypatch.setattr("session._load_state", lambda: {"last_project": "youk", "session_counter": 1})
        monkeypatch.setattr("session._write_session_stub", lambda *a: None)
        monkeypatch.setattr("session._check_session_goal", lambda _: None)
        _task(db, "VP-S08")
        routing._write_routing_breadcrumb("build S08 replay battery", "M", slug="youk")
        graph.start_task("VP-S08", "x", "youk", "youk-1", db_path=db)
        assert graph.open_tasks("youk", db_path=db)["in_flight"][0]["id"] == "VP-S08"
        session.task_checkpoint(str(tmp_path), "S08 done", size="M")
        assert graph.open_tasks("youk", db_path=db)["in_flight"] == []
        assert "VP-S08" in [t["id"] for t in graph.get_all_tasks(db_path=db) if t["done"]]


class TestPlanStatus:
    def test_load_creates_every_plan_task_and_is_safe_to_repeat(self, db):
        plan = json.loads(PLAN.read_text())
        first = plan_status.load_plan(db, "youk", PLAN)
        assert first["created"] == len(plan["tasks"])
        graph.mark_done("VP-S00", db_path=db)
        graph.start_task("VP-S01", "x", "youk", "youk-2", db_path=db)
        again = plan_status.load_plan(db, "youk", PLAN)
        assert again["created"] == 0
        s = plan_status.status(db, "youk", PLAN)
        assert "VP-S00" in s["done"] and "VP-S01" in s["in_flight"]

    def test_next_follows_the_dependencies(self, db):
        plan_status.load_plan(db, "youk", PLAN)
        for done in ("VP-S00", "VP-S01", "VP-S02", "VP-S03", "VP-S04", "VP-S05", "VP-S06", "VP-S07"):
            graph.mark_done(done, db_path=db)
        assert plan_status.status(db, "youk", PLAN)["next"] == "VP-S08"
        graph.mark_done("VP-S08", db_path=db)
        assert plan_status.status(db, "youk", PLAN)["next"] == "VP-S09"
        graph.mark_done("VP-S09", db_path=db)
        # S10 needs S05, S08 and S09, all done now; the decision gate G1 still waits on S10.
        assert plan_status.status(db, "youk", PLAN)["next"] == "VP-S10"

    def test_a_blocked_gate_is_never_next(self, db):
        plan_status.load_plan(db, "youk", PLAN)
        assert plan_status.status(db, "youk", PLAN)["next"] != "VP-G1"

    def test_render_names_the_stopped_task_and_the_next_one(self, db):
        plan_status.load_plan(db, "youk", PLAN)
        graph.mark_done("VP-S00", db_path=db)
        graph.start_task("VP-S02", "x", "youk", "youk-2", db_path=db)
        labels = {t["id"]: t["label"] for t in json.loads(PLAN.read_text())["tasks"]}
        text = plan_status.render(plan_status.status(db, "youk", PLAN), labels)
        assert "STOPPED MID-TASK  VP-S02" in text and "1 of" in text


class TestDefaultDatabase:
    def test_youk_home_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YOUK_HOME", str(tmp_path))
        assert plan_status.default_db() == tmp_path / "state" / "task-graph.db"

    def test_a_worktree_reads_the_live_install_not_its_own_empty_state(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUK_HOME", raising=False)
        live = tmp_path / ".claude" / "youk" / "state"
        live.mkdir(parents=True)
        (live / "task-graph.db").write_text("")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert plan_status.default_db() == live / "task-graph.db"
