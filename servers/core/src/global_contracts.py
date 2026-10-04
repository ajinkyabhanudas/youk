"""Global contracts storage — no MCP dependency, importable in tests."""
from __future__ import annotations
from pathlib import Path


def promote_to_global_contracts(contracts: list[str], youk_root: Path) -> dict:
    """Append confirmed cross-project contracts to knowledge/global/contracts.md.

    Deduplicates case-insensitively. Returns {promoted: N, skipped: N, conflicts: [],
    leak_blocked: [{contract, reason}]}. Uses atomic temp-file rename — safe under
    concurrent calls.

    2026-10-04: this promotion path had NO abstraction-leak protection -- raw
    contract text was written verbatim across project boundaries. Reuses
    abstract_claim() (verification_research.py, the same gate Phase D of
    docs/pattern-learning-architecture-design.md already requires before
    cross-project promotion elsewhere) rather than inventing a second check.
    A contract whose abstraction isn't confident is REFUSED (never silently
    dropped as a skip, and never promoted raw) -- the caller must abstract
    it manually or drop it, same as the Phase D guardrail's own contract.
    """
    from verification_research import abstract_claim

    global_file = youk_root / "knowledge" / "global" / "contracts.md"
    global_file.parent.mkdir(parents=True, exist_ok=True)

    existing_text = global_file.read_text() if global_file.exists() else ""
    existing_lines: list[str] = [
        line.strip().lstrip("- ")
        for line in existing_text.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    existing_normalized = {c.lower() for c in existing_lines}

    promoted, skipped, conflicts = 0, 0, []
    leak_blocked: list[dict] = []
    new_lines: list[str] = []
    for c in contracts:
        normalized = c.strip().lower()
        if normalized in existing_normalized:
            skipped += 1
            continue
        result = abstract_claim(c)
        if not result.confident:
            leak_blocked.append({"contract": c, "reason": result.flagged_reason})
            continue
        for existing in existing_lines:
            if (
                "always" in normalized
                and "never" in existing.lower()
                and normalized[7:20] in existing.lower()
            ) or (
                "never" in normalized
                and "always" in existing.lower()
                and normalized[6:20] in existing.lower()
            ):
                conflicts.append(f"Conflict: new '{c}' vs existing '{existing}'")
        new_lines.append(f"- {result.abstracted.strip()}\n")
        existing_normalized.add(normalized)
        promoted += 1

    if new_lines:
        tmp = global_file.with_suffix(".tmp")
        tmp.write_text(existing_text + "".join(new_lines))
        tmp.replace(global_file)

    return {
        "promoted": promoted,
        "skipped": skipped,
        "conflicts": conflicts,
        "leak_blocked": leak_blocked,
    }
