"""Which project a directory belongs to.

A project's identity used to be the directory's basename, computed separately in seven places.
That made a git worktree its own project: a session in /work/youk-vp, a worktree of /work/youk,
had a different slug, so its tasks, events and "where I stopped" never met the main checkout's.

The rule now: a worktree belongs to the repository it was made from. Everything else keeps its
basename, so existing slugs do not change. Pure path logic on the one-line `.git` file a
worktree contains ("gitdir: <repo>/.git/worktrees/<name>"), no subprocess, so hooks can import
it without cost and it works the same inside a container.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def project_root(project_dir: str, resolve: Callable[[str], Path] | None = None) -> str:
    """The directory that identifies the project: the main repository for a worktree, else the
    directory itself. `resolve` maps a host path to one readable here (a container mounts the
    host home at a different prefix); the returned root stays in the caller's own path form."""
    if not project_dir:
        return project_dir
    readable = resolve(project_dir) if resolve else Path(project_dir)
    marker = Path(readable) / ".git"
    try:
        if marker.is_file():
            first = marker.read_text(encoding="utf-8").splitlines()[0]
            if first.startswith("gitdir:"):
                gitdir = Path(first.split(":", 1)[1].strip())
                # <repo>/.git/worktrees/<name>
                if gitdir.parent.name == "worktrees" and gitdir.parents[1].name == ".git":
                    return str(gitdir.parents[2])
    except (OSError, IndexError):
        pass
    return project_dir


def project_slug(project_dir: str, resolve: Callable[[str], Path] | None = None) -> str:
    return Path(project_root(project_dir, resolve)).name or "unknown"
