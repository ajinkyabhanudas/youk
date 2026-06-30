"""
Token tracking — accumulates usage across a session for audit and self_heal scoring.

Writes to state/current-session-tokens.json (gitignored, local only).
session_start resets it. track_tokens appends checkpoints. session_end reads
the total and writes a Tokens: line to the audit log, then clears the file.

Token counts are estimates from Claude's context window display — rough is fine.
The goal is trend detection across sessions, not per-call accounting.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

YOUK_ROOT = Path("/youk")
TOKEN_FILE = YOUK_ROOT / "state" / "current-session-tokens.json"


def init_token_tracker(session_id: str, task_size: str | None = None, token_budget: int = 0) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({
        "session_id": session_id,
        "task_size": task_size,
        "token_budget": token_budget,
        "checkpoints": [],
        "total_input": 0,
        "total_output": 0,
        "started_at": datetime.utcnow().isoformat(),
    }, indent=2))


def record_checkpoint(input_tokens: int, output_tokens: int, note: str = "") -> dict:
    if not TOKEN_FILE.exists():
        return {"error": "no active token tracker — call session_start first"}
    try:
        data = json.loads(TOKEN_FILE.read_text())
    except Exception:
        return {"error": "token tracker file corrupt"}

    data["total_input"] += input_tokens
    data["total_output"] += output_tokens
    data["checkpoints"].append({
        "ts": datetime.utcnow().isoformat(),
        "input": input_tokens,
        "output": output_tokens,
        "note": note,
    })

    TOKEN_FILE.write_text(json.dumps(data, indent=2))

    budget = data.get("token_budget", 0)
    total = data["total_input"] + data["total_output"]
    vs_budget_pct = round(total / budget * 100, 1) if budget else None

    return {
        "session_total_input": data["total_input"],
        "session_total_output": data["total_output"],
        "session_total": total,
        "vs_budget_pct": vs_budget_pct,
        "checkpoints_recorded": len(data["checkpoints"]),
    }


def read_and_clear() -> dict:
    """Read final totals for session_end, then clear the file."""
    if not TOKEN_FILE.exists():
        return {"total_input": 0, "total_output": 0, "token_budget": 0, "checkpoints": 0}
    try:
        data = json.loads(TOKEN_FILE.read_text())
        TOKEN_FILE.unlink()
        return {
            "total_input": data.get("total_input", 0),
            "total_output": data.get("total_output", 0),
            "token_budget": data.get("token_budget", 0),
            "checkpoints": len(data.get("checkpoints", [])),
        }
    except Exception:
        return {"total_input": 0, "total_output": 0, "token_budget": 0, "checkpoints": 0}
