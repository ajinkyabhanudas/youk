"""
Claim schema + constraint checker (CIR-154 item 2; stage graph + rework
loop added CIR-156).

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

CIR-156 generalizes Claim.stage from an implicit linear string
(scanning -> decomposing -> checking -> done) to a real graph with named
backward (rework) edges — see Stage/FORWARD_EDGES/REWORK_EDGES below.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

SubClaimStatus = Literal["unverified", "verified", "failed"]

REPO_ROOT = Path(__file__).resolve().parents[3]


class Stage(StrEnum):
    """Every stage the verification pipeline knows about. All ten are
    reserved now (CIR-156 Phase 1) even though ABSTRACT/RESEARCH/DIFF/
    RETRIEVE have no real logic behind them yet — Phase 2/3 wire those in
    without needing another rename of this enum."""

    INTAKE = "intake"
    ABSTRACT = "abstract"
    BOUND = "bound"
    RESEARCH = "research"
    DIFF = "diff"
    DECOMPOSE = "decompose"
    VERIFY = "verify"
    PATTERN_CAPTURE = "pattern_capture"
    GATE = "gate"
    RETRIEVE = "retrieve"


# Forward (happy-path) edges. Linear today by construction — a stage with
# more than one declared forward edge would make _walk_forward_to's
# single-successor assumption below ambiguous.
FORWARD_EDGES: dict[Stage, frozenset[Stage]] = {
    Stage.INTAKE: frozenset({Stage.ABSTRACT}),
    Stage.ABSTRACT: frozenset({Stage.BOUND}),
    Stage.BOUND: frozenset({Stage.RESEARCH}),
    Stage.RESEARCH: frozenset({Stage.DECOMPOSE}),
    Stage.DECOMPOSE: frozenset({Stage.VERIFY}),
    Stage.VERIFY: frozenset({Stage.PATTERN_CAPTURE}),
    Stage.PATTERN_CAPTURE: frozenset({Stage.GATE}),
    Stage.GATE: frozenset(),
    # Reserved, no forward wiring yet: Phase 2 inserts DIFF after a dual-pass
    # RESEARCH; Phase 3 wires RETRIEVE in ahead of BOUND/RESEARCH as RAG over
    # the pattern library. Naming the states now means Phase 2/3 only add
    # edges, never rename or re-plumb what Phase 1 already shipped.
    Stage.DIFF: frozenset(),
    Stage.RETRIEVE: frozenset(),
}

# Backward (rework) edges — the real generalization CIR-156 asks for.
REWORK_EDGES: dict[Stage, frozenset[Stage]] = {
    # VERIFY finding a failed/undeclared sub_claim: the caller's call on
    # which gap it is — the domain the scanner enumerated was incomplete
    # (BOUND), or the domain was fine but decomposition missed it
    # (DECOMPOSE). Both are valid rework targets; nothing here picks for
    # the caller.
    Stage.VERIFY: frozenset({Stage.BOUND, Stage.DECOMPOSE}),
    # DIFF (Phase 2, not yet built) disagreeing routes back to RESEARCH.
    # Edge reserved now so Phase 2 only has to make DIFF reachable, not
    # invent its rework behavior.
    Stage.DIFF: frozenset({Stage.RESEARCH}),
    # GATE blocking "done" is the same shape of gap VERIFY would have
    # found — mirrors VERIFY's own rework targets so a gate denial can
    # always name a real stage instead of a bare refusal.
    Stage.GATE: frozenset({Stage.BOUND, Stage.DECOMPOSE}),
}

MAX_REWORK_ROUNDS = 5


class InvalidStageTransition(ValueError):
    """Raised when a transition is not a declared edge in FORWARD_EDGES or
    REWORK_EDGES for the claim's current stage."""


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
    stage: Stage = Stage.INTAKE
    stage_history: list[str] = field(default_factory=list)
    rework_rounds: int = 0
    rework_log: list[dict] = field(default_factory=list)

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
            "stage": self.stage.value,
            "stage_history": list(self.stage_history),
            "rework_rounds": self.rework_rounds,
            "rework_log": list(self.rework_log),
        }


def advance(claim: Claim, to_stage: Stage) -> Claim:
    """Forward transition. Raises InvalidStageTransition if `to_stage` is not
    a declared forward edge from the claim's current stage."""
    if to_stage not in FORWARD_EDGES.get(claim.stage, frozenset()):
        raise InvalidStageTransition(
            f"{claim.stage.value} -> {to_stage.value} is not a declared forward edge"
        )
    claim.stage_history.append(claim.stage.value)
    claim.stage = to_stage
    return claim


def rework(claim: Claim, to_stage: Stage, reason: str) -> Claim:
    """Backward transition triggered by VERIFY/DIFF/GATE finding a gap.
    Raises InvalidStageTransition if `to_stage` is not a declared rework
    edge from the claim's current stage."""
    if to_stage not in REWORK_EDGES.get(claim.stage, frozenset()):
        raise InvalidStageTransition(
            f"{claim.stage.value} -> {to_stage.value} is not a declared rework edge"
        )
    claim.rework_rounds += 1
    claim.stage_history.append(claim.stage.value)
    claim.rework_log.append({
        "from": claim.stage.value,
        "to": to_stage.value,
        "reason": reason,
        "round": claim.rework_rounds,
    })
    claim.stage = to_stage
    return claim


def _walk_forward_to(claim: Claim, target: Stage) -> Claim:
    """Advance claim forward, one declared edge at a time, from its current
    stage to `target`. Used after a rework edge sends a claim backward: the
    pipeline re-traverses every intervening stage rather than teleporting,
    even though Phase 1 has no real logic at BOUND/RESEARCH/DECOMPOSE beyond
    this transition bookkeeping. Raises InvalidStageTransition if any stage
    on the path has zero or more than one outgoing forward edge (today's
    chain is linear by construction; a future branch should fail loud here
    rather than guess which successor to take)."""
    guard = 0
    while claim.stage != target:
        guard += 1
        if guard > len(Stage):
            raise InvalidStageTransition(
                f"no forward path from {claim.stage.value} to {target.value}"
            )
        next_stages = FORWARD_EDGES.get(claim.stage, frozenset())
        if len(next_stages) != 1:
            raise InvalidStageTransition(
                f"cannot auto-walk forward from {claim.stage.value}: "
                f"{len(next_stages)} outgoing edges, not 1"
            )
        advance(claim, next(iter(next_stages)))
    return claim


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


def gate_claim_done(path: Path, *, preferred_rework_stage: Stage | None = None) -> dict | None:
    """Mirrors check_m_plus_write_gate's contract (plugin/scripts/
    youk_hook_utils.py, CIR-150 item 4): returns None to allow, or a deny
    dict ({"reason", "message", "stage", "routed_to"}) to block.

    CIR-154 item 4: a claim may not be reported done while any sub_claim the
    checker generated for it is not status=="verified".

    CIR-156: the denial now names which stage it is routing back to
    (`routed_to`) instead of a generic refusal — GATE's own rework edge
    (REWORK_EDGES[Stage.GATE]) allows either BOUND or DECOMPOSE, same as
    VERIFY's; a caller with a specific reason to prefer one can pass
    `preferred_rework_stage`, otherwise this defaults to DECOMPOSE (the gate
    itself has no signal to distinguish "domain incomplete" from
    "decomposition missed it" the way a human running VERIFY interactively
    would)."""
    if not path.exists():
        return None
    data = load_claim(path)
    unresolved = [sc for sc in data.get("sub_claims", []) if sc.get("status") != "verified"]
    if not unresolved:
        return None
    target = preferred_rework_stage or Stage.DECOMPOSE
    if target not in REWORK_EDGES[Stage.GATE]:
        raise InvalidStageTransition(
            f"gate -> {target.value} is not a declared rework edge"
        )
    detail = ", ".join(f"{sc['id']} ({sc['status']})" for sc in unresolved)
    return {
        "reason": "unverified_sub_claims",
        "stage": Stage.GATE.value,
        "routed_to": target.value,
        "message": (
            f"[YOUK] claim {data.get('statement')!r} has unresolved sub_claims: "
            f"{detail}. Routing back to {target.value} — every sub_claim the "
            "checker generated must be status=\"verified\" before this claim "
            "can be reported done."
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


@dataclass
class ReworkRound:
    round_number: int
    unresolved: list[str]
    new_findings: list[str]


@dataclass
class ReworkOutcome:
    claim: Claim
    rounds: list[ReworkRound]
    dry: bool
    cap_hit: bool
    message: str | None


def run_rework_loop(
    root: Path,
    statement: str,
    dimension: str,
    graph_fn: Callable[[], dict],
    how_found: str,
    rework_target: Stage = Stage.DECOMPOSE,
    max_rounds: int = MAX_REWORK_ROUNDS,
) -> ReworkOutcome:
    """Drive the claim through VERIFY repeatedly, re-scanning via `graph_fn`
    each round (a caller who fixed code between rounds sees the updated
    graph), until a round produces zero NEW findings compared to the round
    before it — the same "run to dry, not to round count" discipline
    stress-test/challenge already use (skills/stress-test/SKILL.md:248,
    skills/challenge/SKILL.md:313), reused here rather than reinvented.

    "Zero new findings" is the exit condition, not "zero findings" — a round
    that reproduces the same unresolved set as the last one has stabilized;
    the loop exits and lets GATE render its own (possibly blocking) verdict
    on what remains. Only a round that is still discovering new gaps keeps
    the loop going, via a rework() transition to `rework_target` (the
    caller's choice between BOUND and DECOMPOSE, same as VERIFY's own
    REWORK_EDGES) and a _walk_forward_to back to VERIFY for the next round.

    Hard cap: MAX_REWORK_ROUNDS (5), matching stress-test's own emergency
    brake. On cap hit, returns cap_hit=True with an explicit
    "still unresolved after 5 rounds: <specifics>" message — never loops
    silently and never declares the claim done anyway."""
    claim = Claim(statement=statement, dimension=dimension, stage=Stage.VERIFY)
    previous_unresolved: set[str] = set()
    rounds: list[ReworkRound] = []

    for round_number in range(1, max_rounds + 1):
        graph = graph_fn()
        checked = run_checker(root, statement, dimension, graph, how_found)
        claim.sub_claims = checked.sub_claims
        current_unresolved = {sc.id for sc in claim.unresolved()}
        new_findings = sorted(current_unresolved - previous_unresolved)
        rounds.append(ReworkRound(
            round_number=round_number,
            unresolved=sorted(current_unresolved),
            new_findings=new_findings,
        ))

        if not new_findings:
            return ReworkOutcome(claim=claim, rounds=rounds, dry=True, cap_hit=False, message=None)

        if round_number == max_rounds:
            break

        rework(claim, rework_target, reason=f"round {round_number} new findings: {new_findings}")
        _walk_forward_to(claim, Stage.VERIFY)
        previous_unresolved = current_unresolved

    specifics = ", ".join(sorted(current_unresolved)) or "no unresolved sub_claims recorded"
    message = f"still unresolved after {max_rounds} rounds: {specifics}"
    return ReworkOutcome(claim=claim, rounds=rounds, dry=False, cap_hit=True, message=message)


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
