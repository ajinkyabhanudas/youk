"""
Claim schema + constraint checker (CIR-154 item 2).

A Claim states something across a dimension (today: "host"). Its sub_claims
are never hand-picked by whoever writes the claim — generate_sub_claims
derives exactly one sub_claim per (mechanism, host) pair straight from the
structural scanner's graph (scripts/host_inventory.py), so the domain a claim
gets checked against can never be narrower than what the codebase actually
contains.

This is the mechanism CIR-152's post-mortem named as missing: "youk is
agent-agnostic" was verified by testing context handoff only, because nothing
enumerated the domain before the claim was decomposed by hand. Re-running
run_checker against that exact statement today must surface a failed
{pre_tool_guard, codex} sub_claim automatically — see
tests/test_verification_contract.py's
test_agent_agnostic_claim_surfaces_the_real_pre_tool_guard_codex_gap for the
live proof.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

SubClaimStatus = Literal["unverified", "verified", "failed"]

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class SubClaim:
    id: str
    mechanism: str
    host: str
    status: SubClaimStatus
    evidence: str | None = None


@dataclass
class Claim:
    statement: str
    dimension: str
    sub_claims: list[SubClaim] = field(default_factory=list)

    def all_verified(self) -> bool:
        return all(sc.status == "verified" for sc in self.sub_claims)

    def unresolved(self) -> list[SubClaim]:
        return [sc for sc in self.sub_claims if sc.status != "verified"]

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "dimension": self.dimension,
            "sub_claims": [asdict(sc) for sc in self.sub_claims],
            "all_verified": self.all_verified(),
        }


def generate_sub_claims(dimension: str, graph: dict) -> list[SubClaim]:
    """One sub_claim per (mechanism, host) pair present in the scanner's
    graph for this dimension. The graph decides how many sub_claims exist —
    not the claim's author. wired=True -> "verified" (real evidence the
    mechanism reaches this host); wired=False -> "failed" (the scanner looked
    and found no such evidence, a positive finding of absence, not mere
    ignorance — hence "failed" rather than "unverified")."""
    if dimension != "host":
        raise ValueError(f"unsupported claim dimension: {dimension!r}")
    sub_claims: list[SubClaim] = []
    for mechanism, entry in sorted(graph.items()):
        for host, info in sorted(entry.get("hosts", {}).items()):
            wired = info.get("wired")
            status: SubClaimStatus = "verified" if wired else "failed"
            sub_claims.append(SubClaim(
                id=f"{mechanism}:{host}",
                mechanism=mechanism,
                host=host,
                status=status,
                evidence=info.get("evidence"),
            ))
    return sub_claims


def build_claim(statement: str, dimension: str, graph: dict) -> Claim:
    return Claim(statement=statement, dimension=dimension,
                 sub_claims=generate_sub_claims(dimension, graph))


def _slug(statement: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in statement.lower()).strip("-")[:80] or "claim"


def claims_dir(root: Path) -> Path:
    return root / "state" / "verification-contracts" / "claims"


def pattern_library_path(root: Path) -> Path:
    return root / "state" / "verification-pattern-library.jsonl"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".tmp")
    staged.write_text(text, encoding="utf-8")
    staged.replace(path)


def write_claim(root: Path, claim: Claim) -> Path:
    path = claims_dir(root) / f"{_slug(claim.statement)}.json"
    _atomic_write(path, json.dumps(claim.to_dict(), indent=2, sort_keys=True))
    return path


def load_claim(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gate_claim_done(path: Path) -> dict | None:
    """Mirrors check_m_plus_write_gate's contract (plugin/scripts/
    youk_hook_utils.py, CIR-150 item 4): returns None to allow, or a deny
    dict ({"reason", "message"}) to block.

    CIR-154 item 4: a claim may not be reported done while any sub_claim the
    checker generated for it is not status=="verified"."""
    if not path.exists():
        return None
    data = load_claim(path)
    unresolved = [sc for sc in data.get("sub_claims", []) if sc.get("status") != "verified"]
    if not unresolved:
        return None
    detail = ", ".join(f"{sc['id']} ({sc['status']})" for sc in unresolved)
    return {
        "reason": "unverified_sub_claims",
        "message": (
            f"[YOUK] claim {data.get('statement')!r} has unresolved sub_claims: "
            f"{detail}. Every sub_claim the checker generated must be "
            "status=\"verified\" before this claim can be reported done."
        ),
    }


def gate_all_claims(root: Path) -> dict | None:
    """Same contract as gate_claim_done, aggregated across every claim on
    record under this YOUK_ROOT. Wired into plugin/scripts/pre_tool_use.py's
    existing mcp__youk-core__ PreToolUse boundary (CIR-150 item 4's own
    precedent) for the session_end(close_cluster=True) call — the real
    boundary in this codebase for declaring a session's work done."""
    cdir = claims_dir(root)
    if not cdir.exists():
        return None
    messages = []
    for path in sorted(cdir.glob("*.json")):
        verdict = gate_claim_done(path)
        if verdict is not None:
            messages.append(verdict["message"])
    if not messages:
        return None
    return {
        "reason": "unverified_sub_claims",
        "message": "[YOUK] cannot report done — unresolved verification claims:\n" + "\n".join(messages),
    }


def append_pattern_library_entries(root: Path, claim: Claim, how_found: str) -> list[dict]:
    """Append one pattern-library entry per newly-seen failed/unverified
    sub_claim (CIR-154 item 3), deduped against what's already on record by
    (claim_shape, missed_sub_claim). Returns only the entries actually
    appended this call (empty list if nothing new)."""
    library_path = pattern_library_path(root)
    existing: set[tuple[str, str]] = set()
    if library_path.exists():
        for line in library_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            existing.add((row.get("claim_shape"), row.get("missed_sub_claim")))

    claim_shape = f"{claim.dimension}-dimension: {claim.statement}"
    new_entries: list[dict] = []
    for sc in claim.sub_claims:
        if sc.status == "verified":
            continue
        key = (claim_shape, sc.id)
        if key in existing:
            continue
        entry = {
            "claim_shape": claim_shape,
            "missed_sub_claim": sc.id,
            "how_found": how_found,
            "date": date.today().isoformat(),
        }
        new_entries.append(entry)
        existing.add(key)

    if new_entries:
        library_path.parent.mkdir(parents=True, exist_ok=True)
        with library_path.open("a", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
    return new_entries


def run_checker(root: Path, statement: str, dimension: str, graph: dict, how_found: str) -> Claim:
    """Build a claim against the scanner's graph, persist it immediately
    (WRITE PATH requirement: live, not buffered to a final report), and
    record any newly-found failure in the pattern library. The single
    entrypoint meant for real use."""
    claim = build_claim(statement, dimension, graph)
    write_claim(root, claim)
    append_pattern_library_entries(root, claim, how_found)
    return claim


def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statement", help='e.g. "youk is agent-agnostic"')
    parser.add_argument("--dimension", default="host")
    parser.add_argument("--how-found", default="verification_contract checker run")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--graph", type=Path,
        default=None,
        help="Path to a scanner graph JSON. Defaults to "
             "<root>/state/verification-contracts/host-inventory-graph.json.",
    )
    args = parser.parse_args()

    graph_path = args.graph or (args.root / "state" / "verification-contracts" / "host-inventory-graph.json")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    claim = run_checker(args.root, args.statement, args.dimension, graph, args.how_found)
    print(json.dumps(claim.to_dict(), indent=2, sort_keys=True))

    if not claim.all_verified():
        unresolved = ", ".join(sc.id for sc in claim.unresolved())
        print(f"\nUNRESOLVED sub_claims: {unresolved} — cannot be reported done.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
