#!/usr/bin/env python3
"""The value plan's status, read from the task graph. Nothing else holds it.

docs/value-plan/tasks.json defines the plan (ids, labels, dependencies). Whether a task is done,
in flight or next is state, and state lives in one place: state/task-graph.db. A status table in
a document would be a second copy that drifts, so there is none.

    python3 scripts/plan_status.py            show done, in flight, next and what is left
    python3 scripts/plan_status.py --load     add any plan tasks the graph does not have yet
                                              (safe to repeat; never changes done or in-flight)
    --db PATH  --project NAME  --plan FILE

A task is started when work that names it is routed (route_task) and finished by task_checkpoint.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "servers" / "shared"))
sys.path.insert(0, str(REPO / "servers" / "core" / "src"))

import graph  # noqa: E402
from youk_paths import locate_install  # noqa: E402


def default_db() -> Path:
    """The live install's graph. A worktree has its own empty state/, so the script's own
    location is the wrong place to look: use YOUK_HOME, else ~/.claude/youk, else this repo."""
    env = os.environ.get("YOUK_HOME")
    if env:
        return Path(env) / "state" / "task-graph.db"
    home = Path.home() / ".claude" / "youk"
    if (home / "state" / "task-graph.db").exists():
        return home / "state" / "task-graph.db"
    youk_dir, _, _ = locate_install(__file__)
    return youk_dir / "state" / "task-graph.db"


def load_plan(db: Path, project: str, plan_file: Path) -> dict:
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    tasks = [{"id": t["id"], "label": t["label"], "project": project} for t in plan["tasks"]]
    result = graph.create_task_graph(tasks, [tuple(e) for e in plan["edges"]], db_path=db)
    # Ready means "its parents are done", which next_task already checks through the edges, so
    # every plan task is marked unblocked. Re-running leaves done and in_flight alone.
    for t in tasks:
        graph.set_gate(t["id"], "unblocked", True, db_path=db)
    return result


def status(db: Path, project: str, plan_file: Path) -> dict:
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    ids = [t["id"] for t in plan["tasks"]]
    rows = {r["id"]: r for r in graph.get_all_tasks(db_path=db)}
    known = [i for i in ids if i in rows]
    done = [i for i in known if rows[i]["done"]]
    flying = [i for i in known if rows[i]["in_flight"] and not rows[i]["done"]]
    nxt = graph.next_task(project=project, db_path=db)
    return {
        "plan_tasks": len(ids),
        "not_loaded": [i for i in ids if i not in rows],
        "done": done,
        "in_flight": flying,
        "next": nxt["task"]["id"] if nxt.get("found") else None,
        "left": [i for i in known if i not in done],
    }


def render(s: dict, labels: dict[str, str]) -> str:
    lines = [f"plan: {len(s['done'])} of {s['plan_tasks']} done"]
    if s["not_loaded"]:
        lines.append(f"  {len(s['not_loaded'])} plan task(s) not in the graph yet: run with --load")
    for i in s["in_flight"]:
        lines.append(f"  STOPPED MID-TASK  {i}  {labels.get(i, '')}")
    if s["next"]:
        lines.append(f"  NEXT              {s['next']}  {labels.get(s['next'], '')}")
    elif not s["not_loaded"]:
        lines.append("  nothing is ready (the remaining tasks wait on a dependency or a decision)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--project", default="youk")
    parser.add_argument("--plan", type=Path, default=REPO / "docs" / "value-plan" / "tasks.json")
    args = parser.parse_args()
    db = args.db or default_db()
    if args.load:
        print("loaded:", load_plan(db, args.project, args.plan))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    print(render(status(db, args.project, args.plan), {t["id"]: t["label"] for t in plan["tasks"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
