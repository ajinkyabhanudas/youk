#!/usr/bin/env python3
"""
revert_checkpoint.py — restore a working tree from a pre-destructive-command
checkpoint written by the PreToolUse hook (plugin/scripts/pre_tool_use.py).

Usage:
  python3 scripts/revert_checkpoint.py                 # list recent checkpoints
  python3 scripts/revert_checkpoint.py latest           # restore the most recent one
  python3 scripts/revert_checkpoint.py <checkpoint-id>  # restore a specific one

What restore does, precisely:
  1. Resets the working tree to the checkpoint's head_sha (git reset --hard).
  2. Applies the checkpoint's working_tree.patch (git diff HEAD, captured before the
     destructive command ran) — restores file CONTENT exactly as it was, including
     conflict markers if a merge was mid-conflict.
  3. Restores untracked files that existed at checkpoint time.

Honest limit: if a merge was in progress at checkpoint time, this restores file
content but not git's internal merge-index bookkeeping (which files git considers
"resolved"). Re-running the original merge command after restore recreates the
correct conflict state; the restored file content is already right for that.

Cross-platform: pure Python + git subprocess calls, no shell-specific syntax —
runs identically on macOS, Linux, and Windows (Git Bash / WSL / PowerShell + Python).
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path


def _run(args: list[str], cwd: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout


def _checkpoints_dir(repo_root: str) -> Path | None:
    rc, git_dir = _run(["rev-parse", "--git-dir"], repo_root)
    if rc != 0:
        return None
    d = Path(git_dir.strip())
    if not d.is_absolute():
        d = Path(repo_root) / d
    return d / "youk-checkpoints"


def _load_checkpoints(checkpoints_dir: Path) -> list[dict]:
    if not checkpoints_dir.is_dir():
        return []
    entries = []
    for d in sorted(checkpoints_dir.iterdir()):
        manifest = d / "manifest.json"
        if manifest.exists():
            try:
                entries.append(json.loads(manifest.read_text()) | {"_dir": str(d)})
            except Exception:
                continue
    return entries


def list_checkpoints(checkpoints_dir: Path) -> None:
    entries = _load_checkpoints(checkpoints_dir)
    if not entries:
        print("No checkpoints found.")
        return
    print(f"{len(entries)} checkpoint(s), newest last:\n")
    for e in entries:
        merge_note = " [was mid-merge]" if e.get("merge_in_progress") else ""
        print(f"  {e['id']}  branch={e['branch']}  {e['triggering_command'][:60]}{merge_note}")
    print("\nRestore: python3 scripts/revert_checkpoint.py <id>")
    print("     or: python3 scripts/revert_checkpoint.py latest")


def restore(checkpoints_dir: Path, checkpoint_id: str, repo_root: str) -> int:
    entries = _load_checkpoints(checkpoints_dir)
    if not entries:
        print("No checkpoints found.")
        return 1

    if checkpoint_id == "latest":
        entry = entries[-1]
    else:
        matches = [e for e in entries if e["id"] == checkpoint_id]
        if not matches:
            print(f"No checkpoint with id '{checkpoint_id}'. Run with no arguments to list.")
            return 1
        entry = matches[0]

    entry_dir = Path(entry["_dir"])
    print(f"Restoring checkpoint {entry['id']}")
    print(f"  branch:  {entry['branch']}")
    print(f"  head:    {entry['head_sha']}")
    print(f"  before:  {entry['triggering_command']}")
    if entry.get("merge_in_progress"):
        print("  note: a merge was in progress at checkpoint time — this restores file")
        print("        content, not git's merge-index bookkeeping. Re-run the original")
        print("        merge command after restore to recreate the conflict state.")

    confirm = input("\nProceed? This will git reset --hard to the checkpoint's commit. [y/N] ")
    if confirm.strip().lower() != "y":
        print("Aborted.")
        return 1

    rc, out = _run(["reset", "--hard", entry["head_sha"]], repo_root)
    if rc != 0:
        print(f"git reset --hard failed:\n{out}")
        return 1
    print(f"  reset to {entry['head_sha']}")

    patch = entry_dir / "working_tree.patch"
    if entry.get("has_patch") and patch.exists():
        rc, out = _run(["apply", str(patch)], repo_root)
        if rc != 0:
            print(f"  warning: patch did not apply cleanly:\n{out}")
            print(f"  the raw patch is saved at {patch} — apply manually with `git apply`")
        else:
            print("  working tree patch applied")

    untracked_root = entry_dir / "untracked"
    if untracked_root.is_dir():
        restored = 0
        for f in untracked_root.rglob("*"):
            if f.is_file():
                rel = f.relative_to(untracked_root)
                dst = Path(repo_root) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(f.read_bytes())
                restored += 1
        if restored:
            print(f"  restored {restored} untracked file(s)")

    print("\nDone.")
    return 0


def main() -> int:
    repo_root = str(Path.cwd())
    checkpoints_dir = _checkpoints_dir(repo_root)
    if checkpoints_dir is None:
        print("Not inside a git repository.")
        return 1

    args = sys.argv[1:]
    if not args:
        list_checkpoints(checkpoints_dir)
        return 0

    return restore(checkpoints_dir, args[0], repo_root)


if __name__ == "__main__":
    sys.exit(main())
