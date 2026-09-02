#!/usr/bin/env python3
"""
PreToolUse hook — fires before every Bash tool call, before the command runs.

Job: when the command matches a destructive pattern (git reset --hard, git checkout
<ref> -- <path>, rm -rf, git clean -f, etc.), write a restorable checkpoint of the
current git working tree BEFORE the command executes. Never blocks — this is a safety
net, not a permission gate. The command always proceeds; only the ability to recover
from it changes.

Why this exists: a mid-merge `git checkout <ref> -- .` clobbered in-progress conflict
resolution in a real session. `git stash`, the obvious manual recovery tool, failed at
exactly that moment ("could not write index") because a merge was active — recovery
took several manual diagnostic steps instead of one command. This makes the safety net
automatic and independent of the operator noticing the risk in advance.

See youk_hook_utils.write_pre_destructive_checkpoint for the checkpoint mechanism
(uses `git diff`, not `git stash` — diff works correctly mid-merge, stash does not)
and scripts/revert_checkpoint.py for the restore path.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from youk_hook_utils import (
    read_stdin,
    is_destructive_command,
    write_pre_destructive_checkpoint,
    ok,
    ok_no_output,
)


def main() -> None:
    data = read_stdin()
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "")

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
