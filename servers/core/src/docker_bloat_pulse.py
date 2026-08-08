"""Docker bloat pulse — surface accumulating youk containers/images, never delete them.

The gap: youk spawns a youk-core + youk-code container pair per session. Closed sessions
can leave stopped containers, and every rebuild can leave an old-SHA or dangling image.
Over time this bloats. Cleanup tools exist (make prune / prune-idle / cleanup.sh), but
NOTHING fires them automatically — the user only learns about the bloat if they remember to
run doctor.sh. That is the same "gated behind human discipline" failure the wiring and
personal-data pulses fix: the signal must autorun.

But — unlike those pulses — cleanup is DESTRUCTIVE and IRREVERSIBLE. A challenge pass rejected
"autorun the prune": youk cannot reliably tell an orphaned container from one another live Claude
tab is using mid-task, so an autorun delete could stop that session's container. So this pulse
DETECTS and SURFACES only. Deletion stays a human action (make prune), because only the human
knows which tabs are live. Detection autoruns (safe); deletion never does.

Thresholds mirror scripts/doctor.sh (<=2 running normal, <=4 warn, >4 likely orphaned) so the
two never disagree. Pure `docker` reads; degrades to silent if docker is unavailable.
"""
from __future__ import annotations

import subprocess


def _docker(args: list[str]) -> str | None:
    try:
        out = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=8,
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def check_docker_bloat() -> dict:
    """Read-only scan of youk's Docker footprint. Never mutates anything.

    Returns {"available": bool, "running": int, "stopped": int, "images": int,
    "dangling": int, "severity": "ok"|"warn"|"high"|"none"}. severity="none" when docker
    isn't reachable (pulse stays silent).
    """
    ps = _docker(["ps", "--format", "{{.Image}}"])
    if ps is None:
        return {"available": False, "severity": "none", "running": 0,
                "stopped": 0, "images": 0, "dangling": 0}

    running = sum(1 for line in ps.splitlines() if "youk-" in line)

    stopped_out = _docker(["ps", "-a", "--filter", "status=exited",
                           "--format", "{{.Image}}"]) or ""
    stopped = sum(1 for line in stopped_out.splitlines() if "youk-" in line)

    img_out = _docker(["images", "--filter", "reference=youk-*", "--format", "{{.ID}}"]) or ""
    images = len([x for x in img_out.splitlines() if x.strip()])

    dang_out = _docker(["images", "-f", "dangling=true", "-q"]) or ""
    dangling = len([x for x in dang_out.splitlines() if x.strip()])

    # Thresholds mirror doctor.sh so the two signals never contradict.
    if running > 4 or stopped > 4 or dangling > 5:
        severity = "high"
    elif running > 2 or stopped > 0 or dangling > 0:
        severity = "warn"
    else:
        severity = "ok"

    return {"available": True, "severity": severity, "running": running,
            "stopped": stopped, "images": images, "dangling": dangling}


def format_bloat_warnings(result: dict) -> list[str]:
    """Session-start lines. Surfaces the bloat + the exact fix command — never runs it.

    ok / none → silent. The one-command fix (make prune / prune-idle) is human-triggered
    because only the developer knows which Claude tabs are still live."""
    sev = result.get("severity")
    if sev in ("ok", "none"):
        return []
    parts = []
    if result["running"] > 2:
        parts.append(f"{result['running']} running")
    if result["stopped"] > 0:
        parts.append(f"{result['stopped']} stopped")
    if result["dangling"] > 0:
        parts.append(f"{result['dangling']} dangling image(s)")
    detail = ", ".join(parts) or f"{result['images']} images"
    icon = "⚠" if sev == "warn" else "⚠⚠"
    return [
        f"{icon} DOCKER BLOAT: youk containers/images accumulating ({detail}). "
        f"Fix when your other Claude tabs are closed: `make prune-idle` (or `make prune`). "
        f"Not auto-run — deletion is destructive and youk can't tell which tabs are live."
    ]
