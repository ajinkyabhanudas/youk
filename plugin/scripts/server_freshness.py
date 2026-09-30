"""Host-side deploy-freshness enforcement — the real-consequence half of CIR-153.

servers/core/src/deploy_freshness.py computes staleness from state/*.json's
`last_head`, a marker that session.start_session() unconditionally advances to
the current git HEAD on every single call (session.py, right after computing
the freshness verdict) — regardless of whether the running server ever
restarted onto that code. That means the warning fires exactly once, the
session where the commit lands, then a session that scrolls past it silently
retires the warning for good: the next session_start sees last_head already
equal to current HEAD and stays silent, even though the container is still
running the old code underneath it. That is the exact failure CIR-152 hit —
six runtime-touching commits landed over a week, undetected, because one
scrolled-past warning was enough to reset the marker forever.

This module asks a question no session can quietly satisfy by editing a state
file: does the SERVER PROCESS's actual boot time predate the last commit that
touched runtime-sensitive paths? A container's StartedAt comes from Docker,
not from anything a session writes — the only way to move it forward is an
actual restart. plugin/scripts/pre_tool_use.py uses this to gate every MCP
tool call to youk-core / youk-code until that is true, auto-restarting via the
same launchd kickstart `make update` already performs unattended after every
pull+rebuild when it is safe to do so.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

# Mirrors deploy_freshness.py's _RUNTIME_SENSITIVE_PREFIXES. Kept as its own
# constant rather than imported: that module lives on servers/core/src's path,
# which is the CONTAINER's import path, not the host's — this script runs on
# the host, outside the container, so it needs its own copy of the same
# classification. Two short tuples in sync by convention beats cross-wiring
# two independent runtimes for one list.
_RUNTIME_SENSITIVE_PREFIXES: tuple[str, ...] = ("servers/", "skills/")

# MCP server name (as registered with `claude mcp add`, and how tool_name
# arrives at the hook: mcp__<name>__<tool>) -> (docker container name, launchd
# label). See scripts/install.sh for the registration/container names and the
# com.youk.*.plist LaunchAgents `make update`'s `launchctl kickstart -k` already
# targets — this reuses that exact restart path, not a new one.
SERVERS: dict[str, tuple[str, str]] = {
    "youk-core": ("youk-core-server", "com.youk.core-server"),
    "youk-code": ("youk-code-server", "com.youk.code-server"),
}


def _run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def container_started_at(container: str) -> str | None:
    """RFC3339 boot time of `container`'s current process, or None if it can't
    be determined (not running, docker unreachable, mid-restart)."""
    r = _run(["docker", "inspect", container, "--format", "{{.State.StartedAt}}"])
    if r is None or r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


def latest_runtime_commit_since(root: Path, since_iso: str) -> str | None:
    """Short SHA of the most recent commit touching a runtime-sensitive path
    at/after `since_iso`, or None if there isn't one (or git could not answer,
    which we deliberately treat the same as "none" here — is_stale's caller
    already fails closed on the container-boot-time half of this check, so an
    unreadable git log degrades to "can't prove staleness from this signal"
    rather than a second independent unknown)."""
    r = _run([
        "git", "-C", str(root), "log", f"--since={since_iso}", "--format=%h",
        "--", *_RUNTIME_SENSITIVE_PREFIXES,
    ])
    if r is None or r.returncode != 0:
        return None
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return lines[0] if lines else None


def is_stale(root: Path, server: str) -> bool | None:
    """True: `server`'s running container predates a runtime-sensitive commit
    — it is serving stale code. False: confirmed fresh. None: could not be
    determined (unknown server, docker/container unreachable) — callers must
    not treat this as fresh; see enforce()'s fail-closed handling."""
    spec = SERVERS.get(server)
    if spec is None:
        return None
    container, _label = spec
    started = container_started_at(container)
    if started is None:
        return None
    return latest_runtime_commit_since(root, started) is not None


def restart(server: str, ready_timeout: float = 20.0, poll_interval: float = 1.0) -> bool:
    """Kick `server`'s launchd job — the same action `make update` already
    takes unattended after every pull+rebuild — and block until the container
    reports a new StartedAt, i.e. until the restart has actually taken effect,
    not just until the command returned.

    Safe to run unattended: server source is bind-mounted into the container,
    never baked into the image (see servers/core/Dockerfile's "Source is NOT
    baked in" comment) — a restart just re-execs the process against the
    already-current working tree. No rebuild, no image pull, no state loss
    (state/ lives on the same mount the process reads from).
    """
    spec = SERVERS.get(server)
    if spec is None:
        return False
    container, label = spec
    before = container_started_at(container)

    r = _run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], timeout=10.0)
    if r is None or r.returncode != 0:
        return False

    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        after = container_started_at(container)
        if after is not None and after != before:
            return True
    return False


def enforce(root: Path, server: str) -> dict:
    """The gate's full decision for one MCP call to `server`.

    {"action": "allow"}                 — confirmed fresh, nothing to do.
    {"action": "allow", "message": ...} — was stale; auto-restart fixed it;
                                           call proceeds against fresh code.
    {"action": "deny", "message": ...}  — stale (or undeterminable) and could
                                           not be confirmed fresh; call blocked.
    """
    stale = is_stale(root, server)
    if stale is False:
        return {"action": "allow"}

    container = SERVERS.get(server, (server, server))[0]
    label = SERVERS.get(server, (server, server))[1]

    if stale is None:
        return {
            "action": "deny",
            "message": (
                f"[YOUK] deploy-freshness for {server} could not be determined "
                f"(docker unreachable or container '{container}' not found) — "
                "failing closed rather than silently trusting a server that "
                f"might be stale. Check `docker ps` / `docker inspect {container}` "
                "and retry."
            ),
        }

    # stale is True — confirmed stale. Fix it, not just report it.
    if restart(server):
        return {
            "action": "allow",
            "message": (
                f"[YOUK] {server} was serving stale code — a merged commit "
                "touching servers/ or skills/ postdates the running "
                "container's boot (merged ≠ in effect). Auto-restarted via "
                "launchd and confirmed the container came back up on a fresh "
                "boot. Proceeding."
            ),
        }
    return {
        "action": "deny",
        "message": (
            f"[YOUK] {server} is serving stale code — a merged commit "
            "touching servers/ or skills/ postdates the running container's "
            "boot (merged ≠ in effect). Auto-restart via launchd failed "
            f"or timed out. Run `launchctl kickstart -k gui/$(id -u)/{label}` "
            "manually (or `make update`), then retry."
        ),
    }
