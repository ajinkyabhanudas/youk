#!/usr/bin/env python3
"""Real status-check over docs/system-map.yaml (Phase 3 of
docs/system-observability-design.md -- read that document first).

Loads the Stage Registry, reads the REAL file each entry's `real_log`
points to (never invents a status), and reports per stage whether it has
ever fired, how many real entries exist, and when the most recent one was.

Three real file shapes exist across the registry (see the module docstrings
of domain_brief.py, verification_contract.py, pattern_entry.py,
disposition_event.py, domain_scope_event.py, reversal_check.py and
pattern_promotion.py for how each one is actually written):
  - most real_log paths are JSONL, append-only, one event per line.
  - state/verification-contracts/claims/ is a DIRECTORY of per-claim JSON
    files (Claim.to_dict()). Claim's own dict carries no top-level
    timestamp field, so the only real signal of "most recent" is each
    file's own mtime.
  - state/domain-brief.json is a single JSON object (DomainBrief.to_dict()),
    not a log -- "has it ever fired" means "does it exist", and its one
    real timestamp is its own `generated_at` field.

A stage whose real_log is null is reported as "no real log exists for this
stage" -- a state the design doc requires never be collapsed into "never
fired" (one means unobservable by design, the other means untested).
Six registry stages are grounding=llm_judgment/hybrid AND have real,
scannable decision content behind them even though their own `real_log`
field is null -- the record is written by a separate, deterministic
logging stage immediately downstream (e.g. domain_scope_naming's own
real_log is null; append_domain_scope_event's triggers_on names
domain_scope_naming as the thing it logs right after). That pairing is
found generically, by searching every stage's `triggers_on` text for
another stage's exact name, rather than hardcoding the pair list -- see
`_find_paired_log_stage`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_MAP_PATH = REPO_ROOT / "docs" / "system-map.yaml"

NEVER_FIRED = "never fired"
NO_REAL_LOG = "no real log exists for this stage"
TRACED = "traced via the event ledger"
FIRED = "fired"

_JUDGMENT_GROUNDINGS = {"llm_judgment", "hybrid"}

# The two real_log shapes that are not plain append-only JSONL (see module
# docstring). Both paths are exactly as they appear in docs/system-map.yaml.
_CLAIMS_DIR_LOG = "state/verification-contracts/claims/"
_DOMAIN_BRIEF_LOG = "state/domain-brief.json"

# Priority order for picking "the" timestamp out of a real logged row --
# each real file uses exactly one of these keys consistently (see the
# module docstrings this file is read against), so there's never a
# collision between two of them on the same row.
_TIMESTAMP_KEYS = ("updated_at", "timestamp", "created_at", "date")


@dataclass
class StageReport:
    name: str
    subsystem: str
    grounding: str
    real_log: str | None
    state: str  # FIRED | NEVER_FIRED | NO_REAL_LOG
    entry_count: int = 0
    last_timestamp: str | None = None
    judgment_rows: list[dict] = field(default_factory=list)
    judgment_via: str | None = None  # paired stage name, if content came from one
    note: str | None = None  # emitted ledger kinds, or why the stage is untraced


def load_stages(path: Path = SYSTEM_MAP_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or []


def _row_timestamp(row: dict) -> str | None:
    for key in _TIMESTAMP_KEYS:
        value = row.get(key)
        if value:
            return value
    return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _read_claims_dir(path: Path) -> tuple[int, str | None]:
    if not path.is_dir():
        return 0, None
    files = sorted(path.glob("*.json"))
    if not files:
        return 0, None
    latest_mtime = max(f.stat().st_mtime for f in files)
    last = datetime.fromtimestamp(latest_mtime, tz=UTC).isoformat()
    return len(files), last


def _read_domain_brief(path: Path) -> tuple[int, str | None]:
    if not path.exists():
        return 0, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0, None
    if not isinstance(data, dict):
        return 0, None
    return 1, data.get("generated_at")


def read_real_log(root: Path, real_log_rel: str) -> tuple[int, str | None, list[dict]]:
    """Returns (entry_count, last_timestamp, rows). `rows` is only populated
    for JSONL-shaped logs (the directory and single-object shapes have no
    per-row content to scan)."""
    path = root / real_log_rel
    if real_log_rel == _CLAIMS_DIR_LOG:
        count, last = _read_claims_dir(path)
        return count, last, []
    if real_log_rel == _DOMAIN_BRIEF_LOG:
        count, last = _read_domain_brief(path)
        return count, last, []
    rows = _read_jsonl(path)
    timestamps = [t for t in (_row_timestamp(r) for r in rows) if t]
    last = max(timestamps) if timestamps else None
    return len(rows), last, rows


def _find_paired_log_stage(stage: dict, stages_by_name: dict[str, dict]) -> dict | None:
    """Generic name-mention search for the deterministic stage that actually
    logs a judgment stage's decision, when the judgment stage's own
    real_log is null. See module docstring."""
    name = stage["name"]
    own_triggers = stage.get("triggers_on", "") or ""
    for other_name, other in stages_by_name.items():
        if other_name == name or not other.get("real_log"):
            continue
        if re.search(rf"\b{re.escape(other_name)}\b", own_triggers):
            return other
    for other_name, other in stages_by_name.items():
        if other_name == name or not other.get("real_log"):
            continue
        if re.search(rf"\b{re.escape(name)}\b", other.get("triggers_on", "") or ""):
            return other
    return None


def build_report(root: Path, stages: list[dict]) -> list[StageReport]:
    stages_by_name = {s["name"]: s for s in stages}
    reports: list[StageReport] = []

    for stage in stages:
        real_log = stage.get("real_log")
        grounding = stage["grounding"]
        judgment_via: str | None = None
        effective_log = real_log

        if real_log is None and grounding in _JUDGMENT_GROUNDINGS:
            paired = _find_paired_log_stage(stage, stages_by_name)
            if paired is not None:
                effective_log = paired["real_log"]
                judgment_via = paired["name"]

        if effective_log is None:
            emits = stage.get("emits")
            reports.append(
                StageReport(
                    name=stage["name"],
                    subsystem=stage["subsystem"],
                    grounding=grounding,
                    real_log=None,
                    state=TRACED if emits else NO_REAL_LOG,
                    note=("kinds: " + ", ".join(emits)) if emits else stage.get("untraced_reason"),
                )
            )
            continue

        count, last, rows = read_real_log(root, effective_log)
        state = FIRED if count > 0 else NEVER_FIRED
        judgment_rows = rows if (grounding in _JUDGMENT_GROUNDINGS and count > 0) else []

        reports.append(
            StageReport(
                name=stage["name"],
                subsystem=stage["subsystem"],
                grounding=grounding,
                real_log=effective_log,
                state=state,
                entry_count=count,
                last_timestamp=last,
                judgment_rows=judgment_rows,
                judgment_via=judgment_via,
            )
        )

    return reports


def _format_judgment_row(row: dict) -> str:
    if "domains" in row and "task" in row:
        domains = ", ".join(f"{d.get('domain')} ({d.get('reason')})" for d in row.get("domains", []))
        return f"task={row['task']!r} domains=[{domains}]"
    if "disposition" in row:
        return (
            f"task={row.get('task')!r} bounded_context={row.get('bounded_context')!r} "
            f"disposition={row.get('disposition')!r} source={row.get('source_file')}#{row.get('source_id')}"
        )
    if "statement" in row and "domain" in row:
        return f"domain={row.get('domain')!r} sub_domain={row.get('sub_domain')!r} statement={row.get('statement')!r}"
    return json.dumps(row, sort_keys=True)


def render_report(reports: list[StageReport]) -> str:
    lines: list[str] = []
    by_subsystem: dict[str, list[StageReport]] = {}
    for r in reports:
        by_subsystem.setdefault(r.subsystem, []).append(r)

    fired = sum(1 for r in reports if r.state == FIRED)
    never = sum(1 for r in reports if r.state == NEVER_FIRED)
    traced = sum(1 for r in reports if r.state == TRACED)
    no_log = sum(1 for r in reports if r.state == NO_REAL_LOG)
    lines.append(
        f"system_status: {len(reports)} stages — {fired} fired, {never} never fired, "
        f"{traced} traced via ledger, {no_log} no real log"
    )
    lines.append("")

    for subsystem in sorted(by_subsystem):
        lines.append(f"== {subsystem} ==")
        for r in by_subsystem[subsystem]:
            tag = f"[{r.grounding}]"
            if r.state in (NO_REAL_LOG, TRACED):
                note = f" ({r.note[:90]})" if r.note else ""
                lines.append(f"  {r.name:<45} {tag:<16} {r.state}{note}")
                continue
            via = f" (via {r.judgment_via})" if r.judgment_via else ""
            lines.append(
                f"  {r.name:<45} {tag:<16} {r.state} — {r.entry_count} entries, "
                f"last: {r.last_timestamp or 'n/a'} — log: {r.real_log}{via}"
            )
            if r.judgment_rows:
                lines.append(f"    real logged decisions ({len(r.judgment_rows)}):")
                for row in r.judgment_rows:
                    lines.append(f"      - {_format_judgment_row(row)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="repo root (default: this repo)")
    ap.add_argument(
        "--system-map", type=Path, default=None, help="override docs/system-map.yaml path (default: --root/docs/system-map.yaml)"
    )
    args = ap.parse_args(argv)

    system_map_path = args.system_map or (args.root / "docs" / "system-map.yaml")
    if not system_map_path.exists():
        print(f"no system map at {system_map_path}", file=sys.stderr)
        return 1

    stages = load_stages(system_map_path)
    reports = build_report(args.root, stages)
    print(render_report(reports), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
