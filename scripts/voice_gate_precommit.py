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

msg_path = root / ".git" / "COMMIT_EDITMSG"
if not msg_path.exists():
    sys.exit(0)

msg = "\n".join(
    l for l in msg_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not l.startswith("#")
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
