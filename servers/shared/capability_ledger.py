"""Declaration-completeness ledger for agent-host capabilities (CIR-156).

CIR-155 found PROMPT_CONTEXT absent from CodexHost's declared set entirely —
not declared-and-unwired the way PRE_TOOL_GUARD once was, but never
investigated at all, which meant the structural scanner never even generated
a row for it. Silence on a (host, capability) pair in agent_host.py's
HostCapabilities declarations is indistinguishable from "doesn't apply" --
this ledger makes "nobody has checked" a real, flaggable, append-only record
instead.

Every (host, capability) pair the current codebase declares must have at
least one ledger entry. tests/test_capability_ledger.py's
TestLedgerCoversTheRealCodebase asserts this against the real repo, which is
the CI check CIR-156's DONE-MEANS asks for: add a HostCapability member or a
host without adding a matching ledger line, and that test fails.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent_host import HostCapability, all_host_ids

REPO_ROOT = Path(__file__).resolve().parents[2]


def ledger_path(root: Path) -> Path:
    return root / "state" / "capability-investigation-ledger.jsonl"


@dataclass(frozen=True)
class LedgerEntry:
    host: str
    capability: str
    date: str
    how_found: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "capability": self.capability,
            "date": self.date,
            "how_found": self.how_found,
            "note": self.note,
        }


def record_investigation(
    root: Path,
    host: str,
    capability: HostCapability | str,
    how_found: str,
    note: str = "",
) -> LedgerEntry:
    """Append one investigation record. Append-only like the pattern library
    (verification_contract.py's append_pattern_library_entries) — a
    (host, capability) pair can legitimately be re-checked later (e.g. after
    a host's hook surface changes); every real check is worth keeping, not
    just the latest one."""
    entry = LedgerEntry(
        host=host,
        capability=str(capability),
        date=date.today().isoformat(),
        how_found=how_found,
        note=note,
    )
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
    return entry


def load_ledger(root: Path) -> list[dict]:
    path = ledger_path(root)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def investigated_pairs(root: Path) -> set[tuple[str, str]]:
    return {(row["host"], row["capability"]) for row in load_ledger(root)}


def missing_investigations(
    root: Path,
    host_ids: frozenset[str] | None = None,
    capabilities: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Every (host, capability) pair with no ledger entry at all.

    host_ids/capabilities default to every host and HostCapability member
    currently registered in agent_host.py — never a hardcoded list, so a
    newly added host or capability is covered automatically. The parameters
    exist so a test can simulate "a new HostCapability value was added"
    without needing to monkeypatch the StrEnum itself: pass a capabilities
    list that includes a value absent from the ledger and assert it comes
    back as missing for every host."""
    hosts = sorted(host_ids if host_ids is not None else all_host_ids())
    caps = capabilities if capabilities is not None else [c.value for c in HostCapability]
    recorded = investigated_pairs(root)
    return [
        (host, capability)
        for host in hosts
        for capability in caps
        if (host, capability) not in recorded
    ]


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    missing = missing_investigations(args.root)
    if missing:
        print("UNINVESTIGATED (host, capability) pairs:", file=sys.stderr)
        for host, capability in missing:
            print(f"  {host}:{capability}", file=sys.stderr)
        return 1
    print("every declared (host, capability) pair has a ledger entry.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
