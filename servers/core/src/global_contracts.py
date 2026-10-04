"""Global contracts storage — no MCP dependency, importable in tests.

Stores each contract as a tagged PatternEntry in state/global-patterns.jsonl
(query via query_global_patterns). contracts.md is generated from that store
by render_contracts_md, not edited directly.
"""
from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path


def _projects_with_lesson(contract: str, youk_root: Path) -> list[str]:
    """Names of the projects whose contracts.md holds this lesson, matched by
    meaning (same threshold as cross-project detection). Returns [] when no
    project file matches or the embedding model cannot run -- the caller then
    records the source as unknown rather than inventing one."""
    from semantic_similarity import _SIMILARITY_THRESHOLD, rank_by_similarity

    projects_dir = youk_root / "knowledge" / "projects"
    if not projects_dir.exists():
        return []
    found: list[str] = []
    try:
        for d in sorted(projects_dir.iterdir()):
            f = d / "contracts.md"
            if not f.is_file():
                continue
            lines = [
                ln.strip().lstrip("- ").strip()
                for ln in f.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")
            ]
            if lines and rank_by_similarity(contract, lines, min_score=_SIMILARITY_THRESHOLD, limit=1):
                found.append(d.name)
    except Exception:
        return []
    return found


def promote_to_global_contracts(
    contracts: list[str],
    youk_root: Path,
    domain: str,
    sub_domain: str,
) -> dict:
    """Write each contract as a tagged PatternEntry to state/global-patterns.jsonl
    and regenerate contracts.md from the full store.

    Caller passes domain/sub_domain explicitly per batch; split batches that
    span different topics.

    Returns {promoted: N, skipped: N, conflicts: [], leak_blocked: [{contract, reason}]}.
    """
    from jsonl_lock import locked_jsonl_append, locked_jsonl_read_all
    from pattern_entry import PatternEntry
    from semantic_similarity import is_same_lesson
    from verification_research import abstract_claim
    import hashlib
    import json
    import re

    patterns_path = youk_root / "state" / "global-patterns.jsonl"
    existing = locked_jsonl_read_all(patterns_path)

    def _opposite_polarity(a: str, b: str) -> bool:
        return ("always" in a and "never" in b) or ("never" in a and "always" in b)

    promoted, skipped, conflicts = 0, 0, []
    leak_blocked: list[dict] = []
    for c in contracts:
        normalized = c.strip().lower()

        # A genuine contradiction ("always X" vs "never X") shares almost
        # every token with its opposite, so embedding similarity alone
        # cannot tell "same lesson, reworded" from "opposite claim, same
        # words" -- negation is a known blind spot for this class of model.
        # Polarity is checked first and wins: an opposite-polarity match is
        # never treated as a duplicate, only ever as a conflict below.
        duplicate = any(
            is_same_lesson(c, e.get("statement", ""))
            and not _opposite_polarity(normalized, e.get("statement", "").lower())
            for e in existing
        )
        if duplicate:
            skipped += 1
            continue

        result = abstract_claim(c)
        if not result.confident:
            leak_blocked.append({"contract": c, "reason": result.flagged_reason})
            continue

        topic = re.sub(r"\b(always|never)\b", "", normalized, count=1).strip()
        for existing_row in existing:
            existing_stmt = existing_row.get("statement", "")
            existing_lower = existing_stmt.lower()
            if _opposite_polarity(normalized, existing_lower):
                existing_topic = re.sub(r"\b(always|never)\b", "", existing_lower, count=1).strip()
                if is_same_lesson(topic, existing_topic, threshold=0.5):
                    conflicts.append(f"Conflict: new '{c}' vs existing '{existing_stmt}'")

        source_projects = _projects_with_lesson(c, youk_root)
        pattern_id = hashlib.sha256(
            f"{domain}\x1f{sub_domain}\x1f{result.abstracted.strip().lower()}".encode()
        ).hexdigest()[:16]
        entry = PatternEntry(
            id=pattern_id,
            scope="global",
            domain=domain,
            sub_domain=sub_domain,
            statement=result.abstracted.strip(),
            evidence_level="internally_checked",
            provenance=[{"project": name, "abstracted": True} for name in source_projects]
            or [{"project": "unknown", "abstracted": True}],
            status="promoted",
            created_at=datetime.now(UTC).isoformat(),
            confirmed_count=len(source_projects),
        )
        locked_jsonl_append(patterns_path, json.dumps(entry.to_dict()))
        existing.append(entry.to_dict())
        promoted += 1

    if promoted:
        render_contracts_md(youk_root)

    return {
        "promoted": promoted,
        "skipped": skipped,
        "conflicts": conflicts,
        "leak_blocked": leak_blocked,
    }


def render_contracts_md(youk_root: Path) -> None:
    """Regenerate knowledge/global/contracts.md as a human-readable view of
    the real structured store (state/global-patterns.jsonl), grouped by
    domain. Never hand-edited -- always regenerated from the source of truth.
    Atomic temp-file rename — safe under concurrent calls.
    """
    from jsonl_lock import locked_jsonl_read_all

    patterns_path = youk_root / "state" / "global-patterns.jsonl"
    entries = locked_jsonl_read_all(patterns_path)

    by_domain: dict[str, list[dict]] = {}
    for e in entries:
        by_domain.setdefault(e.get("domain", "unclassified"), []).append(e)

    lines = [
        "# Global behavioral contracts — applies to every project\n",
        "# GENERATED from state/global-patterns.jsonl — do not hand-edit.\n",
        "# Regenerated by promote_to_global_contracts(); the JSONL file is the source of truth.\n",
        "# Never committed to the repo — personal intelligence, local only\n",
        "\n",
    ]
    for domain in sorted(by_domain):
        lines.append(f"## {domain}\n")
        for e in sorted(by_domain[domain], key=lambda x: x.get("sub_domain", "")):
            lines.append(f"- [{e.get('sub_domain', 'general')}] {e['statement']}\n")
        lines.append("\n")

    global_file = youk_root / "knowledge" / "global" / "contracts.md"
    global_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = global_file.with_suffix(".tmp")
    tmp.write_text("".join(lines))
    tmp.replace(global_file)
