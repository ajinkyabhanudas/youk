"""Where a project stopped, computed from facts every time it is asked.

Why this exists: "where did we stop" used to be a prose line (resume-from: in context.md)
written by six different code paths, each with its own wording, where the last writer won and
a stale line beat every fresher source. It silently did nothing when context.md was missing,
and it could not tell a finished task from an abandoned one.

Now nothing about it is stored. It is derived on read from two things that cannot go stale
because they record events, not summaries:

  the task graph   a task is started by route_task (tagged to its project, in flight) and
                   finished by task_checkpoint. In flight and not done means it stopped partway.
  git              branch, last commit, uncommitted files. The work as it actually is.

Same inputs, same answer, no write path to corrupt.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from graph import next_task, open_tasks
from state_paths import resolve_project_path

_MAX_LEN = 300


def _git(path: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", path, "-c", "safe.directory=*", *args],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def git_state(project_dir: str) -> dict | None:
    """Branch, last commit and uncommitted file count, or None when this is not a git repo."""
    path = str(resolve_project_path(project_dir))
    status = _git(path, "status", "--porcelain=v2", "--branch")
    if status is None:
        return None
    branch, dirty = "", 0
    for line in status.splitlines():
        if line.startswith("# branch.head "):
            branch = line.split(" ", 2)[2]
        elif line and not line.startswith("#"):
            dirty += 1
    last = _git(path, "log", "-1", "--format=%h%x1f%s%x1f%cr")
    head = subject = age = ""
    if last and last.strip():
        head, subject, age = (last.strip().split("\x1f") + ["", "", ""])[:3]
    return {"branch": branch, "head": head, "subject": subject, "age": age, "dirty": dirty}


def where_stopped(slug: str, project_dir: str, db_path: Path | None = None,
                  git: dict | None = None) -> dict:
    """The structured answer. `git` may be passed in so a caller that already has it (or a test)
    does not shell out again."""
    kwargs = {"db_path": db_path} if db_path is not None else {}
    # Each source is read on its own so one that fails (a missing or locked database, git absent)
    # costs only its own part of the answer. Session start must never fail because of this.
    try:
        opened = open_tasks(slug, **kwargs)
        nxt = next_task(project=slug, **kwargs)
    except Exception:
        opened, nxt = {"in_flight": [], "open_count": 0}, {"found": False}
    try:
        repo = git if git is not None else git_state(project_dir)
    except Exception:
        repo = None
    return {
        "project": slug,
        "in_flight": opened["in_flight"],
        "next": nxt["task"] if nxt.get("found") else None,
        "open_count": opened["open_count"],
        "git": repo,
    }


def render(state: dict, authored_note: str = "") -> str:
    """One line, or "" when there is nothing to say (a project with no tasks and no git).

    `authored_note` is a line the project's own author wrote (its prd-status "Resume from"). It is
    shown after the facts and never replaces them."""
    parts = []
    flying = state["in_flight"]
    if flying:
        names = "; ".join(t["label"][:70] for t in flying[:2])
        more = f" (+{len(flying) - 2} more)" if len(flying) > 2 else ""
        parts.append(f"STOPPED MID-TASK: {names}{more}")
    nxt = state["next"]
    if nxt:
        parts.append(f"NEXT: {nxt['label'][:90]}")
    elif state["open_count"] and not flying:
        parts.append(f"{state['open_count']} open task(s), none ready")
    git = state["git"]
    if git and git.get("branch"):
        bits = [git["branch"]]
        if git["dirty"]:
            bits.append(f"{git['dirty']} uncommitted file(s)")
        if git.get("head"):
            bits.append(f"last commit {git['head']} {git['subject'][:50]} ({git['age']})")
        parts.append("git: " + ", ".join(bits))
    if authored_note:
        parts.append(f"project note: {authored_note[:80]}")
    return ("Resume: " + " | ".join(parts))[:_MAX_LEN] if parts else ""
