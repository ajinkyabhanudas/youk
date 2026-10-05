#!/usr/bin/env python3
"""Sort contracts into mechanical (a machine can check) and judgment.

Mechanical ones are candidates to compile into hook checks instead of prose the model has to
remember. The rule is conservative (servers/shared/contracts.classify_contract), and the list
this prints is for a person to review. Nothing here enforces anything.

    python3 scripts/classify_contracts.py [--root DIR] [--write]

--write saves state/contracts-classified.json under the root, for the gates card to read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "servers" / "shared"))

import contracts  # noqa: E402


def collect(root: Path) -> list[dict]:
    rows = [{"scope": "global", "text": t} for t in contracts.global_contracts(root, 10_000)]
    projects = root / "knowledge" / "projects"
    for project in sorted(p.name for p in projects.glob("*") if p.is_dir()) if projects.is_dir() else []:
        rows += [{"scope": project, "text": t} for t in contracts.project_contracts(root, project)]
    seen, unique = set(), []
    for row in rows:
        if row["text"] not in seen:
            seen.add(row["text"])
            unique.append({**row, "class": contracts.classify_contract(row["text"])})
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows = collect(args.root)
    mech = [r for r in rows if r["class"] == "mechanical"]
    print(f"{len(rows)} contracts: {len(mech)} mechanical, {len(rows) - len(mech)} judgment")
    for row in mech:
        print(f"  [{row['scope']}] {row['text'][:110]}")
    if args.write:
        out = args.root / "state" / "contracts-classified.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
