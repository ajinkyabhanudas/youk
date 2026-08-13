#!/usr/bin/env python3
"""
PostToolUse hook — fires after Bash, Read, Write, Edit tool calls.

Job: maintain state/active_task.json with current working context so
that after any /compact or tab-close, the next session (or the next
UserPromptSubmit hook) can inject "what we were doing" accurately.

Also extracts a signal from large tool outputs so Claude doesn't need
to re-read them — the signal lives in active_task.json and surfaces
in the next UserPromptSubmit brief.

Signal extraction rules:
  - Bash: last non-empty line of stdout (usually the meaningful output)
  - Read/Write/Edit: the file path being worked on
  - Large outputs (>2000 chars): extract first 200 chars as signal snippet

Does NOT write to the knowledge store. That's MCP tools' job.
This hook only writes to state/ (ephemeral, session-scoped).
"""
from __future__ import annotations
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from youk_hook_utils import (
    read_stdin,
    youk_root,
    slug_from_cwd,
    ok_no_output,
)

# Output size above which we extract a signal snippet
LARGE_OUTPUT_THRESHOLD = 2000

# Max files to track in active_task.json
MAX_FILES = 10


def extract_signal(tool_name: str, tool_input: dict, tool_result: str) -> str:
    """Extract a meaningful signal from a tool result."""
    result_str = str(tool_result or "")

    if tool_name == "Bash":
        # Last meaningful line of bash output
        lines = [ln.strip() for ln in result_str.splitlines() if ln.strip()]
        if lines:
            return lines[-1][:200]
        return ""

    if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
        file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
        if file_path:
            return f"edited {file_path}"
        return ""

    if len(result_str) > LARGE_OUTPUT_THRESHOLD:
        return result_str[:200]

    return ""


def get_touched_file(tool_name: str, tool_input: dict) -> str | None:
    """Return the file path being touched, if applicable."""
    if tool_name in ("Read", "Write", "Edit", "MultiEdit"):
        return tool_input.get("file_path") or tool_input.get("path")
    return None


def infer_task_label(tool_name: str, tool_input: dict, existing_task: str, routing_task: str = "") -> str:
    """
    Infer a human-readable task label from tool activity.
    Prefers routing_context.task (semantic intent) over file-derived labels.
    """
    if routing_task:
        return routing_task  # routing_context.task is always the authoritative semantic label

    if existing_task and not existing_task.startswith(("unknown", "editing ", "running:")):
        return existing_task  # existing label already semantic (set by a prior routing_context write)

    file_path = get_touched_file(tool_name, tool_input)
    if file_path:
        return f"editing {Path(file_path).name}"

    cmd = tool_input.get("command", "")
    if cmd:
        return f"running: {cmd[:60]}"

    return existing_task or "active"


def main() -> None:
    data = read_stdin()
    cwd = data.get("cwd", "")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_result = data.get("tool_result", "")

    root = youk_root()
    if root is None:
        ok_no_output()
        return

    state_dir = root / "state"
    if not state_dir.exists():
        ok_no_output()
        return

    slug = slug_from_cwd(cwd)
    slug_dir = root / "state" / "sessions" / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    active_task_file = slug_dir / "active_task.json"

    # Load existing state
    existing: dict = {}
    if active_task_file.exists():
        try:
            existing = json.loads(active_task_file.read_text())
        except Exception:
            existing = {}
    elif (state_dir / "active_task.json").exists():
        # Migrate from legacy flat path on first write for this slug
        try:
            legacy = json.loads((state_dir / "active_task.json").read_text())
            if legacy.get("cwd", "") == cwd:
                existing = legacy
        except Exception:
            pass

    # Update files_touched
    files_touched: list[str] = existing.get("files_touched", [])
    touched = get_touched_file(tool_name, tool_input)
    if touched and touched not in files_touched:
        files_touched.append(touched)
        if len(files_touched) > MAX_FILES:
            files_touched = files_touched[-MAX_FILES:]

    # Extract signal from this tool call
    signal = extract_signal(tool_name, tool_input, str(tool_result))

    # Prefer semantic label from routing_context if present
    _routing_ctx = existing.get("routing_context", {})
    _routing_task = _routing_ctx.get("task", "") if isinstance(_routing_ctx, dict) else ""

    # Infer task label
    task_label = infer_task_label(tool_name, tool_input, existing.get("task", ""), _routing_task)

    updated = {
        "task": task_label,
        "cwd": cwd,
        "slug": slug,
        "files_touched": files_touched,
        "last_signal": signal or existing.get("last_signal", ""),
        "last_tool": tool_name,
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        active_task_file.write_text(json.dumps(updated, indent=2))
    except Exception:
        pass  # never block tool use for state write failures

    ok_no_output()


if __name__ == "__main__":
    main()
