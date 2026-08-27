#!/usr/bin/env python3
"""Pre-commit gate for commit messages.

Two checks, in order:
1. Voice gate — blocks commits with hard AI-tells (check_text BLOCKED).
   Soft tells print a warning but do not block.
2. Behavioral hint — if humanize:commit hint is active (learned from audit history),
   surface a reminder to run humanize before committing.

Silent-exits 0 if voice_fingerprint or behavioral_profile are not importable.
"""
import pathlib
import sys

root = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(root / "servers" / "core" / "src"))

try:
    from voice_fingerprint import check_text
except ImportError:
    sys.exit(0)

def _resolve_msg_path() -> pathlib.Path | None:
    """Locate the commit message file.

    git passes it as argv[1] to a commit-msg hook. The previous version ignored that
    and guessed at root/".git"/"COMMIT_EDITMSG", which does not exist in a worktree:
    there .git is a FILE containing a gitdir pointer, so the guess missed and the gate
    exited 0. It had been silently passing every commit made from a worktree.
    """
    if len(sys.argv) > 1 and sys.argv[1]:
        candidate = pathlib.Path(sys.argv[1])
        if candidate.exists():
            return candidate

    # Asking git works for worktrees, submodules and plain clones alike.
    try:
        import subprocess
        out = subprocess.run(
            ["git", "rev-parse", "--git-path", "COMMIT_EDITMSG"],
            capture_output=True, text=True, timeout=5, cwd=str(root),
        )
        if out.returncode == 0:
            candidate = pathlib.Path(out.stdout.strip())
            if not candidate.is_absolute():
                candidate = root / candidate
            if candidate.exists():
                return candidate
    except Exception:
        pass

    guess = root / ".git" / "COMMIT_EDITMSG"
    return guess if guess.exists() else None


msg_path = _resolve_msg_path()
if msg_path is None:
    # Loud, not silent. A gate that exits 0 when it cannot find its input is
    # indistinguishable from a gate that found nothing wrong, which is exactly how this
    # one passed every worktree commit for an entire session. Blocking on an unreadable
    # message is recoverable in one command; passing silently is not detectable at all.
    print("[youk BLOCKED] Voice gate could not locate the commit message.")
    print("  Tried: argv[1], `git rev-parse --git-path COMMIT_EDITMSG`, .git/COMMIT_EDITMSG")
    print("  The gate refuses to pass work it did not inspect.")
    print("  Re-run `python scripts/generate_commitmsg_hook.py` to reinstall the hook.")
    sys.exit(1)

msg = "\n".join(
    line for line in msg_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not line.startswith("#")
).strip()
if not msg:
    sys.exit(0)

# ── Voice gate ────────────────────────────────────────────────────────────────
result = check_text(msg)
if result["gate"] == "BLOCKED":
    print("[youk BLOCKED] Voice gate: commit message has hard AI-tells:")
    for t in result["tells_hard"]:
        print(f"  {t}")
    print("Rewrite and retry.")
    sys.exit(1)
elif result["gate"] == "REVIEW":
    print("[youk REVIEW] Voice gate: commit message has soft AI-tells (not blocking):")
    for t in result["tells_soft"]:
        print(f"  {t}")

# ── Behavioral hint: humanize at commit ───────────────────────────────────────
try:
    from behavioral_profile import is_hint_active
    if is_hint_active("humanize", "commit"):
        print("[youk HINT] humanize:commit active — run humanize on this message before shipping.")
except Exception:
    pass
