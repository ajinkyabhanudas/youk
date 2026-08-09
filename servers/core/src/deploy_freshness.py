"""Deployment-freshness gate — never trust 'merged' as 'in effect'.

The blind spot this closes (observed live, session 74): a fix merged to main is NOT
automatically in force. There is a gap between MERGED (in git), DEPLOYED (the running MCP
server is on that code), and REFLECTED (the DB/state migrated to match). A session that calls
next_task and trusts the answer can silently point at the wrong task because the migration the
answer depends on never ran in the live server yet.

This gate makes that gap LOUD instead of silent. At session_start it asks: since the HEAD this
project was last at, have commits merged that touch server / schema / routing / gate code? If
so, the running server may be stale — warn before next_task is trusted.

HONEST LIMIT (why this WARNS, never says 'verified fresh'): git tells us what MERGED. It does
NOT tell us whether the running container restarted onto that code — a matching image SHA can
still front a stale in-memory process. So a false 'verified' would be the wiring_pulse
false-green disease. This gate only ever raises risk; proving liveness (image SHA / a server
/version endpoint) is a heavier follow-up, deliberately out of scope. Surfacing what it cannot
prove is the point.

Pure functions + git subprocess. No API.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

# Path prefixes whose change means the running server's behavior may have moved. A merged commit
# touching ONLY docs/tests/knowledge does not risk stale runtime behavior; one touching these
# does. Self-revising judgment-set — grow when a new stale-risk surface is found.
_RUNTIME_SENSITIVE_PREFIXES: tuple[str, ...] = (
    "servers/",              # the MCP server code itself
    "skills/",               # skill files the routing loop loads
)

# Substrings marking the HIGHEST-risk changes — schema/migration/gate logic. A merge touching
# these is exactly the class that bit us (a done-column migration that hadn't run live).
_HIGH_RISK_MARKERS: tuple[str, ...] = (
    "migrat", "schema", "_gate", "graph.py", "routing.py", "session.py",
)


@dataclass(frozen=True)
class FreshnessVerdict:
    """Result of the gate. `stale_risk` True means WARN before trusting next_task."""
    last_head: str | None          # the HEAD recorded at last session_end, or None (first run)
    current_head: str | None
    commits_since: int
    runtime_files_changed: list[str]
    high_risk: bool                # a schema/gate/migration file is among the changes
    stale_risk: bool               # runtime-sensitive files changed since last session
    reason: str

    def warning(self) -> str | None:
        """The one-line warning for session_plan, or None when there's nothing to flag.
        Never claims 'verified fresh' — it either warns or stays silent (honest limit)."""
        if not self.stale_risk:
            return None
        # Unknown case: HEAD moved but git couldn't diff (rebased/bogus last_head). We warn
        # without a file list because we genuinely don't know what changed — honest, not silent.
        if not self.runtime_files_changed:
            return (
                f"⚠ deployment-freshness: {self.reason}. Restart/rebuild the MCP server and "
                f"re-verify task state before trusting next_task (merged ≠ in effect)."
            )
        tag = "⚠ HIGH-RISK" if self.high_risk else "⚠"
        n = len(self.runtime_files_changed)
        sample = ", ".join(self.runtime_files_changed[:3])
        more = f" (+{n - 3} more)" if n > 3 else ""
        return (
            f"{tag} deployment-freshness: {self.commits_since} commit(s) merged since last "
            f"session touch runtime code — {sample}{more}. Restart/rebuild the MCP server "
            f"before trusting next_task or task state (merged ≠ in effect)."
        )


def _git(resolved_dir: str, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", resolved_dir, *args],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout.strip()
        return out if r.returncode == 0 else None
    except Exception:
        return None


def current_head(resolved_dir: str) -> str | None:
    """The project's current HEAD sha. session_end persists this; session_start diffs it."""
    return _git(resolved_dir, "rev-parse", "HEAD")


def _changed_files_since(resolved_dir: str, since_hash: str) -> list[str] | None:
    """Files changed in commits after since_hash.

    Returns None when git could NOT answer (bad/rebased since_hash, not a repo) — distinct
    from an empty list (git answered: genuinely zero files). Collapsing these two was a
    false-green: a rebased history whose old HEAD no longer exists made git fail, which read
    as 'nothing merged' and stayed silent — the exact disease this module exists to prevent.
    """
    out = _git(resolved_dir, "diff", "--name-only", f"{since_hash}..HEAD")
    if out is None:
        return None  # git failed — we do NOT know; caller must treat as stale-risk, not safe
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _is_runtime_sensitive(path: str) -> bool:
    return path.startswith(_RUNTIME_SENSITIVE_PREFIXES)


def _is_high_risk(path: str) -> bool:
    return any(marker in path for marker in _HIGH_RISK_MARKERS)


def check_freshness(resolved_dir: str, last_head: str | None) -> FreshnessVerdict:
    """The gate. Compare last-session HEAD to current; classify what changed.

    First run (last_head is None) → no baseline, no warning (nothing to compare, and a warning
    on every fresh clone would cry wolf). Same HEAD → nothing merged, silent. Otherwise:
    classify changed files; stale_risk if any touch runtime-sensitive paths.
    """
    cur = current_head(resolved_dir)

    if last_head is None:
        return FreshnessVerdict(None, cur, 0, [], False, False,
                                "no baseline HEAD recorded (first run) — nothing to compare")
    if cur is None:
        return FreshnessVerdict(last_head, None, 0, [], False, False,
                                "current HEAD unreadable (not a git repo?) — cannot check")
    if cur == last_head:
        return FreshnessVerdict(last_head, cur, 0, [], False, False,
                                "HEAD unchanged since last session — nothing merged")

    changed = _changed_files_since(resolved_dir, last_head)
    if changed is None:
        # HEAD moved (cur != last_head) but git can't diff the range — last_head is bogus or
        # history was rebased/force-pushed. We CANNOT prove what changed, so we must NOT go
        # silent. Treat as stale-risk: something changed, contents unknown → warn.
        return FreshnessVerdict(
            last_head=last_head, current_head=cur, commits_since=0,
            runtime_files_changed=[], high_risk=False, stale_risk=True,
            reason=("HEAD changed but git could not diff from last_head (rebased/bogus SHA) "
                    "— cannot verify what merged; treating as stale-risk"),
        )

    runtime = [p for p in changed if _is_runtime_sensitive(p)]
    high = any(_is_high_risk(p) for p in runtime)
    count_out = _git(resolved_dir, "rev-list", "--count", f"{last_head}..HEAD")
    commits = int(count_out) if count_out and count_out.isdigit() else 0

    return FreshnessVerdict(
        last_head=last_head,
        current_head=cur,
        commits_since=commits,
        runtime_files_changed=runtime,
        high_risk=high,
        stale_risk=bool(runtime),
        reason=(
            f"{len(runtime)} runtime-sensitive file(s) changed across {commits} commit(s)"
            if runtime else
            f"{commits} commit(s) merged but none touch runtime code — safe"
        ),
    )
