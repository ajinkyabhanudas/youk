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

2. Edit/Write (and Codex's equivalent, apply_patch): this IS a permission gate.
   CIR-150 (youk vs. its stated end-goal) found that every M+ enforcement rule
   in CLAUDE.md was prose the model could skip under time pressure, with zero
   technical backstop — a model that never called route_task could Edit/Write
   freely. See youk_hook_utils.check_m_plus_write_gate for the actual gate
   logic; this hook denies the call outright when it returns non-None.

   CIR-155: this same script is also the real Codex-reachable PreToolUse
   boundary agent_host.py's CodexHost declared but left unwired. Codex's own
   PreToolUse hook contract (confirmed against developers.openai.com/codex/hooks,
   2026) uses the identical stdin shape (tool_name, tool_input, cwd) and the
   identical deny envelope ({"hookSpecificOutput": {"hookEventName":
   "PreToolUse", "permissionDecision": "deny", ...}}) Claude Code uses — see
   deny() below — so no Codex-specific branch is needed here, only recognizing
   "apply_patch" (Codex's canonical file-edit tool name) alongside Edit/Write.
   Register this script as a Codex PreToolUse hook matching "apply_patch" in
   ~/.codex/hooks.json — see docs/getting-started.md's "Codex PreToolUse hook"
   section.

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

4. mcp__youk-core__session_end with close_cluster=True: the verification-
   contract gate. Reuses this same PreToolUse boundary and deny-outright
   precedent as the M+ write gate above, but for claims: any claim on record
   under state/verification-contracts/claims/ with an unresolved
   (non-"verified") sub_claim blocks the session from being reported done.
   See servers/core/src/verification_contract.gate_all_claims.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servers" / "core" / "src"))
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
from verification_contract import gate_all_claims

_MCP_YOUK_TOOL_RE = re.compile(r"^mcp__(youk-core|youk-code)__")


def _gates_on(root: Path, cwd: str) -> bool:
    """The `bare` arm runs without the blocking gates (servers/shared/arms.py). Freshness and
    checkpoints are infrastructure, not gates, and stay on for every arm."""
    from arms import current_arm, gates_active
    return gates_active(current_arm(root, slug_from_cwd(cwd)))


def _voice_tells(text: str) -> list[str]:
    """AI-tells in a text, hard and soft, empty when it passes the voice gate."""
    try:
        from voice_fingerprint import check_text
        result = check_text(text)
        return result["tells_hard"] + result["tells_soft"] if result["gate"] == "BLOCKED" else []
    except Exception:
        return []


def _contract_denial(command: str, cwd: str) -> bool:
    """Deny a Bash command that breaks a compiled contract (servers/shared/contract_guard.py).
    True when it denied. A guard failure never blocks: on any error the command goes through."""
    try:
        root = youk_root()
        if root is not None and not _gates_on(root, cwd):
            return False
        from contract_guard import first_violation
        violation = first_violation(command, cwd, _voice_tells)
        if violation is None:
            return False
        if root is not None:
            try:
                from arms import current_arm
                from events import emit
                emit(root, slug_from_cwd(cwd), kind="gate", name=f"contract.{violation.rule}",
                     status="block", src="hook", arm=current_arm(root, slug_from_cwd(cwd)))
            except Exception:
                pass
        deny(violation.text())
        return True
    except Exception:
        return False


def main() -> None:
    data = read_stdin()
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "")

    mcp_match = _MCP_YOUK_TOOL_RE.match(tool_name)
    if mcp_match:
        root = youk_root()
        if root is not None:
            if (tool_name.endswith("__session_end") and tool_input.get("close_cluster")
                    and _gates_on(root, cwd)):
                claim_verdict = gate_all_claims(root)
                if claim_verdict is not None:
                    deny(claim_verdict["message"])
                    return
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

    # "apply_patch" is Codex's canonical file-edit tool name (confirmed against
    # Codex's own PreToolUse hook contract) -- this is the real Codex-reachable
    # boundary for check_m_plus_write_gate once this script is registered as a
    # Codex PreToolUse hook (docs/getting-started.md, "Codex PreToolUse hook").
    if tool_name in ("Edit", "Write", "apply_patch"):
        root = youk_root()
        if root is not None:
            slug = slug_from_cwd(cwd)
            verdict = check_m_plus_write_gate(root, slug) if _gates_on(root, cwd) else None
            if verdict is not None:
                deny(verdict["message"])
                return
        ok_no_output()
        return

    if tool_name != "Bash":
        ok_no_output()
        return

    command = tool_input.get("command", "")
    if command and _contract_denial(command, cwd):
        return
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
