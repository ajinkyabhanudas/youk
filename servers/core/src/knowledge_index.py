"""
Tiered Knowledge Index — CAP-10

HOT index at knowledge/INDEX.md: one row per entry across knowledge/.
Usage tracking via state/knowledge-usage.jsonl (raw log) folded into INDEX.md at session_end.
Lifecycle: HOT→COLD (auto, use-count==0 across 15 sessions or >45d), COLD→ARCHIVE (proposed only).
Never delete. Archival moves file to knowledge/archive/, never unlinks.
Human-readable throughout.
"""
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, "/shared")

YOUK_ROOT = Path("/youk")
_INDEX_FILE = YOUK_ROOT / "knowledge" / "INDEX.md"
_USAGE_LOG = YOUK_ROOT / "state" / "knowledge-usage.jsonl"
_ARCHIVE_DIR = YOUK_ROOT / "knowledge" / "archive"

# Directories and files to scan for index entries
_SCAN_ROOTS: list[tuple[str, str]] = [
    ("domain", "domain"),
    ("domain/knowledge", "domain/symlink"),  # symlinked learn knowledge
    ("interpretation", "interpretation"),
    ("clarifications", "clarifications"),
    ("global", "global"),
    ("stacks", "stacks"),
    ("projects", "project"),
]
# Paths to skip during scan
_SKIP_NAMES = {"gaps.md", "INDEX.md", "PENDING.md", "_README.md", ".gitkeep"}
_SKIP_DIRS = {"archive", "proposals", "research-inbox"}

# Lifecycle thresholds
_HOT_TO_COLD_DAYS = 45
_HOT_TO_COLD_SESSIONS = 15
_COLD_TO_ARCHIVE_DAYS = 90


def _path_to_id(rel_path: str) -> str:
    """Deterministic id from relative path within knowledge/."""
    return re.sub(r"[^\w/]", "-", rel_path.lower()).replace("/", "--").strip("-")


def _one_line_summary(path: Path) -> str:
    """Extract one-line summary from a knowledge file (first non-empty, non-header line)."""
    try:
        for line in path.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                return stripped[:100]
    except Exception:
        pass
    return path.stem.replace("-", " ")


def _scan_knowledge_entries(root: Path) -> list[dict]:
    """
    Walk knowledge/ and return a list of entry dicts (without usage data).
    Skips archive/, proposals/, research-inbox/, and _README/.gitkeep files.
    """
    entries: list[dict] = []
    knowledge_dir = root / "knowledge"
    if not knowledge_dir.exists():
        return entries

    def _walk(dirpath: Path, prefix: str) -> None:
        try:
            items = sorted(dirpath.iterdir())
        except PermissionError:
            return
        for item in items:
            if item.name in _SKIP_DIRS:
                continue
            if item.is_symlink():
                # Follow symlinks one level — they point to another knowledge store
                target = item.resolve()
                if target.is_dir():
                    _walk(target, f"{prefix}/{item.name}")
                continue
            if item.is_dir():
                _walk(item, f"{prefix}/{item.name}")
            elif item.is_file() and item.suffix == ".md" and item.name not in _SKIP_NAMES:
                rel = str(item.relative_to(knowledge_dir))
                entry_id = _path_to_id(rel)
                entries.append({
                    "id": entry_id,
                    "tier": "HOT",
                    "summary": _one_line_summary(item),
                    "path": f"knowledge/{rel}",
                    "last_used": "",
                    "use_count": 0,
                })

    _walk(knowledge_dir, "")
    return entries


def _parse_index(index_text: str) -> tuple[list[dict], list[str]]:
    """
    Parse INDEX.md into (entry_rows, archive_ids).
    Preserves usage columns (last_used, use_count) from existing rows.
    Returns list of row dicts and list of archived ids.
    """
    rows: list[dict] = []
    archive_ids: list[str] = []
    in_table = False
    in_archive = False

    for line in index_text.splitlines():
        # Archive section
        if line.startswith("## Archive"):
            in_archive = True
            in_table = False
            continue
        if in_archive:
            m = re.match(r"\|\s*([^\|]+)\s*\|", line)
            if m and m.group(1).strip() not in ("id", "---"):
                archive_ids.append(m.group(1).strip())
            continue

        # Main table
        if line.startswith("| id ") or line.startswith("| id|"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 6 and cells[0] and cells[0] != "id":
                rows.append({
                    "id": cells[0],
                    "tier": cells[1] if cells[1] in ("HOT", "COLD") else "HOT",
                    "summary": cells[2],
                    "path": cells[3],
                    "last_used": cells[4],
                    "use_count": int(cells[5]) if cells[5].isdigit() else 0,
                })
        elif in_table and not line.startswith("|"):
            in_table = False

    return rows, archive_ids


def _render_index(rows: list[dict], archive_ids: list[str], generated_at: str) -> str:
    """Render INDEX.md from rows and archive ids."""
    hot = [r for r in rows if r["tier"] == "HOT"]
    cold = [r for r in rows if r["tier"] == "COLD"]

    lines = [
        "# knowledge/INDEX.md",
        f"*Managed by youk-core. Rebuilt: {generated_at}.*",
        "*One row per knowledge entry. Edit tier/summary inline — rebuild preserves usage columns.*",
        "",
        "## HOT entries (loaded as summaries at session_start)",
        "",
        "| id | tier | summary | path | last-used | use-count |",
        "|----|------|---------|------|-----------|-----------|",
    ]
    for r in sorted(hot, key=lambda x: x["id"]):
        lines.append(
            f"| {r['id']} | {r['tier']} | {r['summary'][:80]} | {r['path']} "
            f"| {r['last_used']} | {r['use_count']} |"
        )
    if cold:
        lines += [
            "",
            "## COLD entries (surfaced on demand only)",
            "",
            "| id | tier | summary | path | last-used | use-count |",
            "|----|------|---------|------|-----------|-----------|",
        ]
        for r in sorted(cold, key=lambda x: x["id"]):
            lines.append(
                f"| {r['id']} | {r['tier']} | {r['summary'][:80]} | {r['path']} "
                f"| {r['last_used']} | {r['use_count']} |"
            )
    if archive_ids:
        lines += ["", "## Archive (moved to knowledge/archive/ — never deleted)", ""]
        for aid in archive_ids:
            lines.append(f"- {aid}")

    return "\n".join(lines) + "\n"


def rebuild_knowledge_index(root: Path | None = None) -> dict:
    """
    Scan knowledge/ and rebuild INDEX.md.
    Idempotent: preserves existing usage columns on rebuild.
    Appends new entries with tier=HOT, use-count=0.
    Returns {entries_total, hot, cold, archived, index_bytes}.
    """
    root = root or YOUK_ROOT
    index_file = root / "knowledge" / "INDEX.md"

    # Load existing usage data to preserve it
    existing_by_id: dict[str, dict] = {}
    archive_ids: list[str] = []
    if index_file.exists():
        existing_rows, archive_ids = _parse_index(index_file.read_text())
        existing_by_id = {r["id"]: r for r in existing_rows}

    # Scan current knowledge entries
    fresh_entries = _scan_knowledge_entries(root)

    # Merge: preserve usage from existing rows; new entries get HOT/0
    merged: list[dict] = []
    for entry in fresh_entries:
        if entry["id"] in existing_by_id:
            existing = existing_by_id[entry["id"]]
            entry["tier"] = existing["tier"]
            entry["last_used"] = existing["last_used"]
            entry["use_count"] = existing["use_count"]
        merged.append(entry)

    generated_at = date.today().isoformat()
    index_text = _render_index(merged, archive_ids, generated_at)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(index_text)

    hot_count = sum(1 for r in merged if r["tier"] == "HOT")
    cold_count = sum(1 for r in merged if r["tier"] == "COLD")
    return {
        "entries_total": len(merged),
        "hot": hot_count,
        "cold": cold_count,
        "archived": len(archive_ids),
        "index_bytes": len(index_text.encode()),
    }


def append_knowledge_usage(entry_id: str, root: Path | None = None) -> None:
    """
    Append a usage event to state/knowledge-usage.jsonl.
    Called when a knowledge entry is read during session flow.
    """
    root = root or YOUK_ROOT
    log_file = root / "state" / "knowledge-usage.jsonl"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        event = {"id": entry_id, "date": date.today().isoformat()}
        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def fold_usage_into_index(root: Path | None = None) -> dict:
    """
    Read state/knowledge-usage.jsonl and update last-used/use-count in INDEX.md.
    Called by session_end. Keeps JSONL as raw log; INDEX carries folded state.
    Returns {entries_updated, events_processed}.
    """
    root = root or YOUK_ROOT
    log_file = root / "state" / "knowledge-usage.jsonl"
    index_file = root / "knowledge" / "INDEX.md"

    if not log_file.exists() or not index_file.exists():
        return {"entries_updated": 0, "events_processed": 0}

    # Read usage events
    events: list[dict] = []
    try:
        for line in log_file.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))
    except Exception:
        return {"entries_updated": 0, "events_processed": 0}

    if not events:
        return {"entries_updated": 0, "events_processed": 0}

    # Aggregate: last_used date and increment counts per id
    counts: dict[str, int] = {}
    last_dates: dict[str, str] = {}
    for ev in events:
        eid = ev.get("id", "")
        if not eid:
            continue
        counts[eid] = counts.get(eid, 0) + 1
        d = ev.get("date", "")
        if d > last_dates.get(eid, ""):
            last_dates[eid] = d

    # Update INDEX.md rows in place
    index_text = index_file.read_text()
    existing_rows, archive_ids = _parse_index(index_text)
    updated = 0
    for row in existing_rows:
        eid = row["id"]
        if eid in counts:
            row["use_count"] += counts[eid]
            if last_dates[eid] > row.get("last_used", ""):
                row["last_used"] = last_dates[eid]
            updated += 1

    generated_at = date.today().isoformat()
    index_file.write_text(_render_index(existing_rows, archive_ids, generated_at))
    return {"entries_updated": updated, "events_processed": len(events)}


def _session_count_since(last_used_date: str, sessions: list[dict]) -> int:
    """Count sessions that occurred after last_used_date in the parsed audit sessions."""
    if not last_used_date:
        return len(sessions)
    count = 0
    for s in sessions:
        # sessions don't have explicit date fields; estimate from raw block header
        m = re.search(r"### Session — (\d{4}-\d{2}-\d{2})", s.get("raw", ""))
        if m and m.group(1) > last_used_date:
            count += 1
    return count


def apply_lifecycle_rules(
    root: Path | None = None,
    sessions: list[dict] | None = None,
) -> dict:
    """
    Apply HOT→COLD transitions in INDEX.md.
    COLDâ†'ARCHIVE: emit proposals only — never move without approval.
    Returns {demoted_to_cold, archive_proposals}.
    """
    root = root or YOUK_ROOT
    index_file = root / "knowledge" / "INDEX.md"
    if not index_file.exists():
        return {"demoted_to_cold": 0, "archive_proposals": []}

    rows, archive_ids = _parse_index(index_file.read_text())
    sessions = sessions or []
    today = date.today().isoformat()

    demoted = 0
    archive_proposals: list[dict] = []

    for row in rows:
        last_used = row.get("last_used", "")
        use_count = row.get("use_count", 0)

        # Compute days since last used
        days_unused = 0
        if last_used:
            try:
                lu = date.fromisoformat(last_used)
                days_unused = (date.today() - lu).days
            except ValueError:
                days_unused = 0
        else:
            # Never used — count from first availability (conservative: 0)
            days_unused = 0

        # Sessions since last use
        sessions_unused = _session_count_since(last_used, sessions)

        if row["tier"] == "HOT":
            # HOT→COLD: use_count==0 across last 15 sessions OR >45 days unused
            if use_count == 0 and (sessions_unused >= _HOT_TO_COLD_SESSIONS or days_unused > _HOT_TO_COLD_DAYS):
                row["tier"] = "COLD"
                demoted += 1

        elif row["tier"] == "COLD":
            # COLD→ARCHIVE: propose only, never auto-apply
            if days_unused > _COLD_TO_ARCHIVE_DAYS:
                archive_proposals.append({
                    "id": row["id"],
                    "path": row["path"],
                    "last_used": last_used,
                    "days_unused": days_unused,
                    "reason": f"COLD for {days_unused}d (>{_COLD_TO_ARCHIVE_DAYS}d threshold)",
                })

    if demoted > 0:
        generated_at = today
        index_file.write_text(_render_index(rows, archive_ids, generated_at))

    return {"demoted_to_cold": demoted, "archive_proposals": archive_proposals}


def archive_entry(entry_id: str, root: Path | None = None) -> dict:
    """
    Move a COLD knowledge entry to knowledge/archive/.
    Called only after apply_proposal(confirmed=True) — never auto-invoked.
    NEVER DELETES: moves the file; file count is conserved.
    Updates INDEX.md to list entry_id in archive section.
    Returns {archived, from_path, to_path, file_count_before, file_count_after}.
    """
    root = root or YOUK_ROOT
    index_file = root / "knowledge" / "INDEX.md"
    archive_dir = root / "knowledge" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    if not index_file.exists():
        return {"archived": False, "error": "INDEX.md not found"}

    rows, archive_ids = _parse_index(index_file.read_text())
    target = next((r for r in rows if r["id"] == entry_id), None)
    if not target:
        return {"archived": False, "error": f"entry {entry_id} not found in index"}

    # Resolve source path
    src = root / target["path"].lstrip("/")
    if not src.exists():
        return {"archived": False, "error": f"source file not found: {src}"}

    # Count files before
    file_count_before = sum(1 for _ in (root / "knowledge").rglob("*.md"))

    # Move (never unlink)
    dst = archive_dir / src.name
    src.rename(dst)

    # Count files after — must equal before
    file_count_after = sum(1 for _ in (root / "knowledge").rglob("*.md"))

    # Update INDEX: remove from rows, add to archive_ids
    rows = [r for r in rows if r["id"] != entry_id]
    if entry_id not in archive_ids:
        archive_ids.append(entry_id)

    index_file.write_text(_render_index(rows, archive_ids, date.today().isoformat()))

    return {
        "archived": True,
        "entry_id": entry_id,
        "from_path": str(src),
        "to_path": str(dst),
        "file_count_before": file_count_before,
        "file_count_after": file_count_after,
        "conserved": file_count_before == file_count_after,
    }


def resurrect_entry(entry_id: str, root: Path | None = None) -> dict:
    """
    Restore a COLD or archived entry to HOT tier and reset the clock.
    For archived entries: moves file back from knowledge/archive/ to its original path.
    """
    root = root or YOUK_ROOT
    index_file = root / "knowledge" / "INDEX.md"
    if not index_file.exists():
        return {"resurrected": False, "error": "INDEX.md not found"}

    rows, archive_ids = _parse_index(index_file.read_text())
    today = date.today().isoformat()

    # Check if in active rows (COLD)
    for row in rows:
        if row["id"] == entry_id:
            row["tier"] = "HOT"
            row["last_used"] = today
            index_file.write_text(_render_index(rows, archive_ids, today))
            return {"resurrected": True, "from_tier": "COLD", "entry_id": entry_id}

    # Check if in archive
    if entry_id in archive_ids:
        # Find file in archive dir
        archive_dir = root / "knowledge" / "archive"
        archived_files = list(archive_dir.glob("*.md"))
        # Match by id slug
        match = next(
            (f for f in archived_files if _path_to_id(f.name) in entry_id or entry_id in _path_to_id(f.name)),
            None,
        )
        if match:
            # Move back — restore to knowledge/ root (original sub-path unknown after archive)
            dst = root / "knowledge" / match.name
            match.rename(dst)
            rel = str(dst.relative_to(root / "knowledge"))
            archive_ids.remove(entry_id)
            rows.append({
                "id": entry_id,
                "tier": "HOT",
                "summary": _one_line_summary(dst),
                "path": f"knowledge/{rel}",
                "last_used": today,
                "use_count": 1,
            })
            index_file.write_text(_render_index(rows, archive_ids, today))
            return {"resurrected": True, "from_tier": "ARCHIVE", "entry_id": entry_id}

    return {"resurrected": False, "error": f"entry {entry_id} not found in index or archive"}


def load_index_summaries(root: Path | None = None) -> dict:
    """
    Load HOT entry summaries from INDEX.md for session_start brief.
    Returns only id + summary lines for HOT entries — never entry bodies.
    R10-labeled: includes total/hot/cold/archived counts and byte size.
    """
    root = root or YOUK_ROOT
    index_file = root / "knowledge" / "INDEX.md"
    if not index_file.exists():
        return {
            "summaries": [],
            "r10_line": "knowledge: 0 entries (0 hot, 0 cold, 0 archived); loaded 0 summaries (0B)",
            "index_exists": False,
        }

    rows, archive_ids = _parse_index(index_file.read_text())
    hot = [r for r in rows if r["tier"] == "HOT"]
    cold = [r for r in rows if r["tier"] == "COLD"]

    summaries = [f"{r['id']}: {r['summary']}" for r in hot]
    summary_bytes = sum(len(s.encode()) for s in summaries)

    r10_line = (
        f"knowledge: {len(rows) + len(archive_ids)} entries "
        f"({len(hot)} hot, {len(cold)} cold, {len(archive_ids)} archived); "
        f"loaded {len(hot)} summaries ({summary_bytes}B)"
    )

    return {
        "summaries": summaries,
        "r10_line": r10_line,
        "index_exists": True,
        "hot_count": len(hot),
        "cold_count": len(cold),
        "archived_count": len(archive_ids),
        "summary_bytes": summary_bytes,
    }
