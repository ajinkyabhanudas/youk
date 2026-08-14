"""Behavioral profile — learns skill-timing patterns from session audit history.

Wiring pulse catches orphaned tools; pipeline pulse catches broken handoffs. This
module catches a third failure mode: a tool that IS wired and DOES flow data, but
fires at the wrong moment in the developer's workflow.

The canonical example: humanize is wired into /done. But when a session makes commits
without /done running (multi-commit sessions), humanize never fires at commit time.
The audit records "Commits: yes, Skills: ...(no humanize)". After enough sessions,
this module infers: this developer commits without humanize — route humanize before
every git commit for this developer.

The profile is:
  - Developer-specific (one file per project slug)
  - Additive: evidence accumulates, never resets
  - Conservative: a hint fires only after HINT_THRESHOLD sessions of evidence
  - Transparent: session_start surfaces active hints so the developer can see what was learned

Profile file: state/dev-behavioral-profile.json
Schema:
  {
    "hints": {
      "{skill}:{event}": {
        "count": int,           # sessions where this pattern was observed
        "active": bool,         # True once count >= HINT_THRESHOLD
        "last_seen": str        # ISO date of last observation
      }
    },
    "version": 1
  }
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

YOUK_ROOT = Path("/youk")
_PROFILE_FILE = YOUK_ROOT / "state" / "dev-behavioral-profile.json"

# A hint becomes active (starts influencing routing) after this many sessions of evidence.
# Low enough to learn fast, high enough to avoid false positives from one-off sessions.
HINT_THRESHOLD = 2

# Skills that must fire at commit time (event=commit) — absence is observable from audit.
# Extend this list to catch more skill-timing gaps. Keep it narrow: only skills where
# firing at /done-only is a known inadequate substitute for firing at commit.
_COMMIT_SKILLS = {"humanize"}

# Maximum hints stored per skill — prevents unbounded growth if patterns multiply.
_MAX_HINTS = 50


def _load(path: Path = _PROFILE_FILE) -> dict:
    if not path.exists():
        return {"hints": {}, "version": 1}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"hints": {}, "version": 1}


def _save(profile: dict, path: Path = _PROFILE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2))


def _hint_key(skill: str, event: str) -> str:
    return f"{skill}:{event}"


def record_session_patterns(
    skills_used: list[str] | None,
    commits_made: bool,
    path: Path = _PROFILE_FILE,
) -> dict:
    """Observe session behavior and update the profile.

    Called at session_end. Checks whether any _COMMIT_SKILLS were absent
    despite commits_made=True — the primary observable timing gap.

    Returns {"hints_updated": [key, ...], "hints_activated": [key, ...]}.
    """
    skills = set(skills_used or [])
    profile = _load(path)
    hints = profile.setdefault("hints", {})
    now = datetime.now(UTC).date().isoformat()

    updated: list[str] = []
    activated: list[str] = []

    if commits_made:
        for skill in _COMMIT_SKILLS:
            if skill not in skills:
                key = _hint_key(skill, "commit")
                entry = hints.setdefault(key, {"count": 0, "active": False, "last_seen": now})
                entry["count"] += 1
                entry["last_seen"] = now
                was_active = entry["active"]
                entry["active"] = entry["count"] >= HINT_THRESHOLD
                updated.append(key)
                if not was_active and entry["active"]:
                    activated.append(key)

    # Trim if over max — remove least-recently-seen inactive hints first
    if len(hints) > _MAX_HINTS:
        inactive = [(k, v) for k, v in hints.items() if not v["active"]]
        inactive.sort(key=lambda x: x[1]["last_seen"])
        for key, _ in inactive[:len(hints) - _MAX_HINTS]:
            del hints[key]

    _save(profile, path)
    return {"hints_updated": updated, "hints_activated": activated}


def load_active_hints(path: Path = _PROFILE_FILE) -> list[dict]:
    """Return all active routing hints for this developer.

    Called at session_start. Each hint is {skill, event, count, last_seen}.
    Active hints have count >= HINT_THRESHOLD — enough evidence to influence routing.
    """
    profile = _load(path)
    active = []
    for key, entry in profile.get("hints", {}).items():
        if entry.get("active"):
            skill, _, event = key.partition(":")
            active.append({
                "skill": skill,
                "event": event,
                "count": entry["count"],
                "last_seen": entry["last_seen"],
            })
    return active


def format_hint_warnings(hints: list[dict]) -> list[str]:
    """Session-start lines surfacing active behavioral routing hints."""
    if not hints:
        return []
    lines = [f"[Behavioral] Learned routing hints active ({len(hints)}):"]
    for h in hints:
        lines.append(
            f"  · {h['skill']} → fire at {h['event']} "
            f"(learned from {h['count']} sessions, last: {h['last_seen']})"
        )
    return lines


def is_hint_active(skill: str, event: str, path: Path = _PROFILE_FILE) -> bool:
    """Return True if this skill:event hint is active for this developer."""
    profile = _load(path)
    key = _hint_key(skill, event)
    entry = profile.get("hints", {}).get(key, {})
    return bool(entry.get("active"))


def scan_audit_for_patterns(audit_path: Path, profile_path: Path = _PROFILE_FILE) -> dict:
    """Scan an existing audit markdown file and backfill the profile.

    Reads Sessions from the audit (Skills: ..., Commits: yes/no lines) and
    calls record_session_patterns for each. Used for bootstrapping the profile
    from historical audit data at first installation.

    Returns {"sessions_scanned": int, "patterns_found": int}.
    """
    if not audit_path.exists():
        return {"sessions_scanned": 0, "patterns_found": 0}

    text = audit_path.read_text()
    sessions_scanned = 0
    patterns_found = 0

    # Each session block starts with "### Session —"
    blocks = re.split(r"\n### Session —", text)
    for block in blocks[1:]:  # skip preamble before first session
        skills_match = re.search(r"^Skills:\s*(.+)$", block, re.MULTILINE)
        commits_match = re.search(r"^Commits:\s*(yes|no)", block, re.MULTILINE | re.IGNORECASE)
        if not skills_match or not commits_match:
            continue
        skills_raw = skills_match.group(1).strip()
        skills_used = [s.strip() for s in skills_raw.split(",") if s.strip() and s.strip() != "none"]
        commits_made = commits_match.group(1).lower() == "yes"
        result = record_session_patterns(skills_used, commits_made, path=profile_path)
        sessions_scanned += 1
        patterns_found += len(result["hints_updated"])

    return {"sessions_scanned": sessions_scanned, "patterns_found": patterns_found}
