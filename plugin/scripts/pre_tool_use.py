#!/usr/bin/env python3
"""
PreToolUse hook — fires before every Bash, Edit, or Write tool call, before it runs.

Two independent jobs:

1. Bash: when the command matches a destructive pattern (git reset --hard, git
   checkout <ref> -- <path>, rm -rf, git clean -f, etc.), write a restorable
   checkpoint of the current git working tree BEFORE the command executes. Never
   blocks — this is a safety net, not a permission gate. The command always
   proceeds; only the ability to recover from it changes.

   Why this exists: a mid-merge `git checkout <ref> -- .` clobbered in-progress
   conflict resolution in a real session. `git stash`, the obvious manual recovery
   tool, failed at exactly that moment ("could not write index") because a merge
   was active — recovery took several manual diagnostic steps instead of one
   command. This makes the safety net automatic and independent of the operator
   noticing the risk in advance.

   See youk_hook_utils.write_pre_destructive_checkpoint for the checkpoint
   mechanism (uses `git diff`, not `git stash` — diff works correctly mid-merge,
   stash does not) and scripts/revert_checkpoint.py for the restore path.

2. Edit/Write: this IS a permission gate. CIR-150 (youk vs. its stated end-goal)
   found that every M+ enforcement rule in CLAUDE.md was prose the model could
   skip under time pressure, with zero technical backstop — a model that never
   called route_task could Edit/Write freely. See
   youk_hook_utils.check_m_plus_write_gate for the actual gate logic; this hook
   denies the call outright when it returns non-None.

3. Any mcp__youk-core__* / mcp__youk-code__* tool call: the deploy-freshness
   consequence gate (CIR-153). session_start's own freshness check (see
   deploy_freshness.py) only ever produces a warning a session can scroll past
   — CIR-152 found one such warning sat live, correct, and ignored for a full
   week while the running youk-core container kept serving pre-fix code. This
   reuses the same PreToolUse boundary as the M+ write gate above, but for a
   signal a session cannot silently satisfy: server_freshness.py compares the
   running container's actual boot time (Docker) to the latest commit touching
   runtime-sensitive paths, and auto-restarts (or denies) when it's stale —
   see server_freshness.enforce.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from youk_hook_utils import (
    read_stdin,
    is_destructive_command,
    write_pre_destructive_checkpoint,
    check_m_plus_write_gate,
    slug_from_cwd,
    youk_root,
    ok,
    ok_no_output,
    deny,
)
from server_freshness import enforce as enforce_deploy_freshness

_MCP_YOUK_TOOL_RE = re.compile(r"^mcp__(youk-core|youk-code)__")


def main() -> None:
    data = read_stdin()
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "")

    mcp_match = _MCP_YOUK_TOOL_RE.match(tool_name)
    if mcp_match:
        root = youk_root()
        if root is not None:
            verdict = enforce_deploy_freshness(root, mcp_match.group(1))
            if verdict["action"] == "deny":
                deny(verdict["message"])
                return
            message = verdict.get("message")
            if message:
                ok(system_message=message)
                return
        ok_no_output()
        return

    if tool_name in ("Edit", "Write"):
        root = youk_root()
        if root is not None:
            slug = slug_from_cwd(cwd)
            verdict = check_m_plus_write_gate(root, slug)
            if verdict is not None:
                deny(verdict["message"])
                return
        ok_no_output()
        return

    if tool_name != "Bash":
        ok_no_output()
        return

    command = tool_input.get("command", "")
    if not command or not is_destructive_command(command):
        ok_no_output()
        return

    checkpoint_id = write_pre_destructive_checkpoint(cwd, command)
    if checkpoint_id:
        ok(system_message=(
            f"[youk checkpoint {checkpoint_id}] Working tree snapshotted before a "
            "destructive command. If this goes wrong: "
            f"python3 scripts/revert_checkpoint.py {checkpoint_id}"
        ))
    else:
        ok_no_output()


if __name__ == "__main__":
    main()
