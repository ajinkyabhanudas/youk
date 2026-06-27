from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import SessionState

CLAUDE_ROOT = Path("/claude")
YOUK_ROOT = Path("/youk")
STATE_FILE = YOUK_ROOT / "state" / "session.json"
SKILLS_DIR = CLAUDE_ROOT / "skills"


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"session_counter": 0, "last_project": "", "last_session": ""}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _detect_project(project_dir: str) -> str:
    """Infer project name from directory path."""
    p = Path(project_dir)
    return p.name if p.name else "unknown"


def _load_l2_context(project_dir: str) -> tuple[str, str]:
    """
    Returns (resume_point, context_health).
    Looks for .claude/*-context.md and .claude/prd-status.md.
    """
    p = Path(project_dir)
    claude_dir = p / ".claude"
    resume_point = "No prior context found — fresh session."
    context_health = "NONE"

    if not claude_dir.exists():
        return resume_point, context_health

    # Look for prd-status.md first (most specific resume point)
    prd_status = claude_dir / "prd-status.md"
    if prd_status.exists():
        content = prd_status.read_text()
        for line in content.split("\n"):
            if "Resume from" in line or "resume from" in line:
                # Grab the next non-empty line
                lines = content.split("\n")
                idx = lines.index(line)
                for next_line in lines[idx + 1:]:
                    if next_line.strip():
                        resume_point = next_line.strip()
                        break
                break
        context_health = "L3"

    # Look for project context file
    for f in claude_dir.iterdir():
        if f.suffix == ".md" and "context" in f.name.lower():
            context_health = "L2+L3" if context_health == "L3" else "L2"
            break

    return resume_point, context_health


def _count_pending_proposals() -> int:
    pending_file = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"
    if not pending_file.exists():
        return 0
    content = pending_file.read_text()
    return content.count("## PENDING-")


def start_session(project_dir: str) -> SessionState:
    state = _load_state()
    state["session_counter"] = state.get("session_counter", 0) + 1
    state["last_project"] = project_dir
    state["last_session"] = datetime.utcnow().isoformat()
    _save_state(state)

    project = _detect_project(project_dir)
    resume_point, context_health = _load_l2_context(project_dir)
    pending = _count_pending_proposals()
    counter = state["session_counter"]
    health_check_due = counter % 3 == 0

    return SessionState(
        project=project,
        resume_point=resume_point,
        context_health=context_health,
        pending_proposals_count=pending,
        session_counter=counter,
        health_check_due=health_check_due,
    )


def end_session(summary: str, commits_made: bool) -> dict:
    """Write audit log entry, validate summary structure."""
    from guardrails import check_knowledge_write
    check_knowledge_write(summary)

    # Write audit entry
    audit_dir = CLAUDE_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    month = datetime.utcnow().strftime("%Y-%m")
    audit_file = audit_dir / f"{month}.md"

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n### Session — {timestamp}\n{summary}\n"
    if commits_made:
        entry += "Commits made: yes\n"

    with open(audit_file, "a") as f:
        f.write(entry)

    session_close_detected = any(
        marker in summary
        for marker in ["FLUSHED", "[MENTAL MODEL UPDATE", "context-sync end", "learn complete"]
    )

    return {
        "knowledge_extracted": summary.count("##"),
        "proposals_added": 0,
        "audit_written": True,
        "session_close_cluster_detected": session_close_detected,
    }
