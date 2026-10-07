#!/usr/bin/env python3
"""Register youk's hooks in Claude Code's settings.json, or remove them.

Why this exists: the installer used to symlink plugin/ into ~/.claude/plugins and hope Claude Code
discovered it. Current Claude Code does not (a probe run found 0 plugins and 0 hooks), so none of
youk's hooks ran: no voice capture, no event ledger, no contract guard, no session brief.

The hook scripts import from servers/shared relative to their own location, so they have to run in
place. A marketplace install copies them into a cache and breaks that. Entries in settings.json
point at the scripts where they live instead.

Idempotent: youk's own entries are found by their script path and replaced, other hooks are left
alone, and a backup is written before the first change.

    python3 scripts/install_hooks.py              register
    python3 scripts/install_hooks.py --remove     unregister
    python3 scripts/install_hooks.py --dry-run    show what would change
    python3 scripts/install_hooks.py --settings PATH --plugin-dir DIR
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
BACKUP_SUFFIX = ".bak-youk-hooks"


def load_hooks(plugin_dir: Path) -> dict:
    """The plugin's hooks.json with the plugin root path filled in."""
    raw = (plugin_dir / "hooks" / "hooks.json").read_text()
    return json.loads(raw.replace(PLACEHOLDER, str(plugin_dir)))["hooks"]


def _is_youk(group: dict, scripts_dir: str) -> bool:
    return any(scripts_dir in (h.get("command") or "") for h in group.get("hooks", []))


def merge(settings: dict, hooks: dict, plugin_dir: Path, remove: bool = False) -> dict:
    """settings with youk's hook groups replaced by `hooks`, or removed. Others are untouched."""
    scripts_dir = str(plugin_dir / "scripts")
    out = dict(settings)
    current = {ev: list(groups) for ev, groups in (out.get("hooks") or {}).items()}
    for event in set(current) | set(hooks):
        kept = [g for g in current.get(event, []) if not _is_youk(g, scripts_dir)]
        added = [] if remove else hooks.get(event, [])
        merged = kept + added
        if merged:
            current[event] = merged
        else:
            current.pop(event, None)
    if current:
        out["hooks"] = current
    else:
        out.pop("hooks", None)
    return out


def summarize(before: dict, after: dict) -> str:
    def count(s: dict) -> int:
        return sum(len(g.get("hooks", [])) for gs in (s.get("hooks") or {}).values() for g in gs)
    return f"hook commands in settings: {count(before)} -> {count(after)}"


def write_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--plugin-dir", type=Path, default=REPO / "plugin")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    plugin_dir = args.plugin_dir.resolve()
    if not (plugin_dir / "hooks" / "hooks.json").is_file():
        print(f"no hooks.json under {plugin_dir}", file=sys.stderr)
        return 1
    settings: dict = {}
    if args.settings.exists():
        try:
            settings = json.loads(args.settings.read_text())
        except json.JSONDecodeError as exc:
            print(f"{args.settings} is not valid JSON ({exc}); not touching it", file=sys.stderr)
            return 1
    updated = merge(settings, load_hooks(plugin_dir), plugin_dir, args.remove)
    print(summarize(settings, updated))
    if updated == settings:
        print("already up to date")
        return 0
    if args.dry_run:
        return 0
    args.settings.parent.mkdir(parents=True, exist_ok=True)
    backup = args.settings.with_name(args.settings.name + BACKUP_SUFFIX)
    if args.settings.exists() and not backup.exists():
        shutil.copy2(args.settings, backup)
        print(f"backup: {backup}")
    write_atomic(args.settings, updated)
    print(("removed from " if args.remove else "registered in ") + str(args.settings))
    print("restart Claude Code sessions for the hooks to take effect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
