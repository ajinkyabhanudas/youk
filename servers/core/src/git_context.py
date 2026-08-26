"""git_context — git log and HEAD inspection helpers.

Extracted from session.py. All functions are subprocess calls — no API, no tokens.
Imported by session.py; session.py callers need no changes.
"""
from __future__ import annotations

import subprocess

from state_paths import resolve_project_path as _resolve_project_path


def _read_git_log(project_dir: str, n: int = 5) -> str:
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _read_git_log_since_days(project_dir: str, days: int) -> tuple[int, list[str]]:
    """Return (commit_count, [subject_lines]) for commits in the last `days` days."""
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "log", "--oneline", f"--since={days} days ago"],
            capture_output=True, text=True, timeout=5
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        subjects = [ln.split(" ", 1)[1] if " " in ln else ln for ln in lines[:5]]
        return len(lines), subjects
    except Exception:
        return 0, []


def _latest_commit_iso(project_dir: str) -> str | None:
    """Return the ISO 8601 author-date of the most recent commit, or None on failure."""
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "log", "-1", "--format=%aI"],
            capture_output=True, text=True, timeout=5
        )
        ts = result.stdout.strip()
        return ts if ts else None
    except Exception:
        return None


def _current_project_head(project_dir: str) -> str | None:
    """Current HEAD sha of the project, for the deployment-freshness baseline."""
    try:
        import deploy_freshness
        return deploy_freshness.current_head(str(_resolve_project_path(project_dir)))
    except Exception:
        return None


def _check_deploy_freshness(project_dir: str, last_head: str | None):
    """Run the deployment-freshness gate. Returns a FreshnessVerdict (or None on error).

    Never raises into session_start — a freshness-check failure must not block a session.
    """
    try:
        import deploy_freshness
        return deploy_freshness.check_freshness(
            str(_resolve_project_path(project_dir)), last_head
        )
    except Exception:
        return None


def _count_commits_since(project_dir: str, since_hash: str) -> int:
    """Count commits in project_dir that came after since_hash."""
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "rev-list", "--count", f"{since_hash}..HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    except Exception:
        return 0
