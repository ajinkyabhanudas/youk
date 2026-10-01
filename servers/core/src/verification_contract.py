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

CIR-157 (Phase 2) wires real logic behind two of the stages CIR-156 only
reserved: ABSTRACT (abstract_claim, verification_research.py -- strip
proprietary specifics before anything goes external) and RESEARCH/DIFF
(run_dual_pass_research + diff_fact_sets, same module -- two independent
research passes over the abstracted question, agreement promotes a fact to
externally_verified evidence, disagreement routes to Stage.DIFF named
explicitly rather than silently resolved). It also adds verification_level
to SubClaim (asserted / internally_checked / externally_verified) --
evidence strength, orthogonal to status (pass/fail). See
migrate_claim_file_add_verification_level for the on-disk migration path for
claim files CIR-154/155/156 wrote before this field existed.

CIR-160 (Phase 3) adds retrieve_similar_patterns: a lightweight, stdlib-only
(difflib.SequenceMatcher, no embeddings/vector DB) retrieval pass over the
real pattern library (pattern_library_path) that generate_sub_claims uses to
surface a `pattern_hint` on a sub_claim when a structurally similar past
claim previously missed that exact (mechanism, host) pair. A RAG-shaped
complement to the research agents elsewhere in this pipeline, not a
replacement -- see retrieve_similar_patterns' own docstring for why nothing
heavier is warranted at this corpus's real size.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from typing import Literal

SubClaimStatus = Literal["unverified", "verified", "failed"]

# Evidence strength, orthogonal to SubClaimStatus (pass/fail). "asserted" is
# the dataclass-level floor for a sub_claim constructed with no mechanical
# check behind it at all (reserved for a future bare-declaration path --
# nothing in this file produces one today). "internally_checked" is what
# generate_sub_claims actually produces: real grep/AST evidence against our
# own repo, but never leaving the codebase to confirm against anything
# external. "externally_verified" is earned only two ways (CIR-157
# DONE-MEANS): the dual-pass research+diff below confirming agreement across
# two independent external sources, or a human (the founder) stating the
# fact directly -- a founder statement is independent of the codebase, same
# as two external sources, so it counts as external, not internal.
VerificationLevel = Literal["asserted", "internally_checked", "externally_verified"]

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
    # CIR-157 (Phase 2): RESEARCH now runs the dual-pass research+diff below,
    # so it feeds DIFF, not DECOMPOSE, directly. DIFF only continues forward
    # to DECOMPOSE once diff_stage_outcome (verification_research.py) finds
    # no disagreement between the two passes; a disagreement reworks back to
    # RESEARCH instead (REWORK_EDGES[Stage.DIFF] below, reserved since
    # CIR-156).
    Stage.RESEARCH: frozenset({Stage.DIFF}),
    Stage.DIFF: frozenset({Stage.DECOMPOSE}),
    Stage.DECOMPOSE: frozenset({Stage.VERIFY}),
    Stage.VERIFY: frozenset({Stage.PATTERN_CAPTURE}),
    Stage.PATTERN_CAPTURE: frozenset({Stage.GATE}),
    Stage.GATE: frozenset(),
    # Reserved, no forward wiring yet: Phase 3 wires RETRIEVE in ahead of
    # BOUND/RESEARCH as RAG over the pattern library.
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
    # DIFF disagreeing routes back to RESEARCH -- live as of CIR-157 via
    # diff_stage_outcome (verification_research.py), which calls this edge
    # when diff_fact_sets finds a named disagreement between the two
    # independent research passes.
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
    verification_level: VerificationLevel = "asserted"
    # CIR-160 (Phase 3): set by generate_sub_claims when a real pattern-
    # library entry (retrieve_similar_patterns) names this exact sub_claim
    # id as one a structurally similar past claim previously missed. None
    # for every sub_claim with no genuinely similar precedent.
    pattern_hint: str | None = None


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


def generate_sub_claims(
    dimension: str,
    graph: dict,
    *,
    claim_statement: str | None = None,
    root: Path | None = None,
) -> list[SubClaim]:
    """One sub_claim per (mechanism, host) pair present in the scanner's
    graph for this dimension. The graph decides how many sub_claims exist —
    not the claim's author. wired=True -> "verified" (real evidence the
    mechanism reaches this host); wired=False -> "failed" (the scanner looked
    and found no such evidence, a positive finding of absence, not mere
    ignorance — hence "failed" rather than "unverified").

    CIR-160 (Phase 3): when `claim_statement` and `root` are both given,
    also checks the real pattern library (retrieve_similar_patterns) for
    structurally similar past claims that previously missed a sub_claim —
    and if this decomposition reproduces that exact (mechanism, host) pair,
    attaches a `pattern_hint` naming the precedent. Both default to None so
    every existing caller that only cares about the mechanical scan (no
    pattern-library lookup) is unaffected."""
    if dimension != "host":
        raise ValueError(f"unsupported claim dimension: {dimension!r}")

    hints_by_sub_claim_id: dict[str, dict] = {}
    if claim_statement is not None and root is not None:
        for hint in retrieve_similar_patterns(root, claim_statement, dimension):
            # First (highest-similarity) hit per id wins — retrieve_similar_
            # patterns already returns highest-similarity first.
            hints_by_sub_claim_id.setdefault(hint["missed_sub_claim"], hint)

    sub_claims: list[SubClaim] = []
    for mechanism, entry in sorted(graph.items()):
        for host, info in sorted(entry.get("hosts", {}).items()):
            wired = info.get("wired")
            status: SubClaimStatus = "verified" if wired else "failed"
            sub_claim_id = f"{mechanism}:{host}"
            hint = hints_by_sub_claim_id.get(sub_claim_id)
            pattern_hint = None
            if hint is not None:
                pattern_hint = (
                    f"pattern library: a structurally similar past claim "
                    f"({hint['claim_shape']!r}, similarity {hint['similarity']}) "
                    f"missed this exact sub_claim before — found via "
                    f"{hint.get('how_found', 'unknown')} on "
                    f"{hint.get('date', 'an unknown date')}."
                )
            sub_claims.append(SubClaim(
                id=sub_claim_id,
                mechanism=mechanism,
                host=host,
                status=status,
                evidence=info.get("evidence"),
                # grep/AST against our own repo is real evidence, but it
                # never leaves the codebase -- internally_checked, not
                # externally_verified (CIR-157).
                verification_level="internally_checked",
                pattern_hint=pattern_hint,
            ))
    return sub_claims


def build_claim(statement: str, dimension: str, graph: dict, root: Path | None = None) -> Claim:
    return Claim(statement=statement, dimension=dimension,
                 sub_claims=generate_sub_claims(
                     dimension, graph, claim_statement=statement, root=root,
                 ))


def _slug(statement: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in statement.lower()).strip("-")[:80] or "claim"


def claims_dir(root: Path) -> Path:
    return root / "state" / "verification-contracts" / "claims"


def pattern_library_path(root: Path) -> Path:
    return root / "state" / "verification-pattern-library.jsonl"


def retrieve_similar_patterns(
    root: Path,
    claim_statement: str,
    dimension: str,
    *,
    threshold: float = 0.6,
    top_n: int = 3,
) -> list[dict]:
    """Lightweight retrieval over the real pattern library (CIR-160, Phase
    3) -- no embeddings, no vector DB. The real corpus is a handful of rows
    (state/verification-pattern-library.jsonl); at that size a stdlib
    difflib.SequenceMatcher pass over each row's `claim_shape` string is the
    whole job, and standing up anything heavier would be infra built ahead
    of real need that sits unexercised (see append_pattern_library_entries,
    which already writes `claim_shape` as `f"{dimension}-dimension:
    {statement}"` -- this reuses that exact shape rather than inventing a
    second one).

    Only rows for the same `dimension` are considered (same claim_shape
    prefix) -- comparing claim shapes across dimensions isn't meaningful at
    this corpus size. Returns entries scoring >= `threshold` similarity,
    highest first, capped at `top_n`, each augmented with its `similarity`
    score. Empty list if the pattern library doesn't exist yet or nothing
    clears the threshold -- this is a hint source, never a hard gate."""
    library_path = pattern_library_path(root)
    if not library_path.exists():
        return []

    prefix = f"{dimension}-dimension: "
    new_shape = f"{prefix}{claim_statement}"

    scored: list[tuple[float, dict]] = []
    for line in library_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        past_shape = row.get("claim_shape", "")
        if not past_shape.startswith(prefix):
            continue
        ratio = SequenceMatcher(None, new_shape, past_shape).ratio()
        if ratio >= threshold:
            scored.append((ratio, {**row, "similarity": round(ratio, 3)}))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:top_n]]


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


def _find_sub_claim(claim: Claim, sub_claim_id: str) -> SubClaim:
    sub = next((sc for sc in claim.sub_claims if sc.id == sub_claim_id), None)
    if sub is None:
        raise KeyError(f"no sub_claim with id {sub_claim_id!r} on this claim")
    return sub


def mark_externally_verified(claim: Claim, sub_claim_id: str) -> SubClaim:
    """Promote one sub_claim's verification_level to externally_verified.
    Callers are the two real paths CIR-157's DONE-MEANS names: a diff that
    found agreement across two independent external research passes
    (verification_research.diff_fact_sets), or mark_founder_confirmed below.
    Never touches `status` — verification_level is evidence strength,
    orthogonal to pass/fail. Raises KeyError if sub_claim_id isn't on this
    claim."""
    sub = _find_sub_claim(claim, sub_claim_id)
    sub.verification_level = "externally_verified"
    return sub


def mark_founder_confirmed(claim: Claim, sub_claim_id: str) -> SubClaim:
    """A human (the founder) stating a fact directly counts as external
    verification, same as two independent external sources agreeing — both
    are independent of the codebase, which is what internally_checked never
    is (CIR-157 DONE-MEANS)."""
    return mark_externally_verified(claim, sub_claim_id)


def migrate_claim_file_add_verification_level(path: Path) -> bool:
    """One-off migration for claim files CIR-154/155/156 wrote to disk before
    verification_level existed. Every sub_claim already on disk came from
    generate_sub_claims' grep/AST scanner — real evidence, but never checked
    against anything external — so the sane default is internally_checked,
    the same value generate_sub_claims assigns going forward (not the
    dataclass's own conservative `asserted` floor, which is for a
    bare-declaration path nothing on disk actually used).

    Returns True if the file was rewritten (at least one sub_claim was
    missing the field), False if it already had it on every sub_claim
    (idempotent — safe to re-run)."""
    data = load_claim(path)
    changed = False
    for sub in data.get("sub_claims", []):
        if "verification_level" not in sub:
            sub["verification_level"] = "internally_checked"
            changed = True
    if changed:
        _atomic_write(path, json.dumps(data, indent=2, sort_keys=True))
    return changed


def migrate_claims_dir(root: Path) -> list[Path]:
    """Run migrate_claim_file_add_verification_level over every claim file
    under claims_dir(root). Returns the paths actually rewritten."""
    cdir = claims_dir(root)
    if not cdir.exists():
        return []
    return [p for p in sorted(cdir.glob("*.json")) if migrate_claim_file_add_verification_level(p)]


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
    claim = build_claim(statement, dimension, graph, root=root)
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
    parser.add_argument("statement", nargs="?", help='e.g. "youk is agent-agnostic"')
    parser.add_argument("--dimension", default="host")
    parser.add_argument("--how-found", default="verification_contract checker run")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--graph", type=Path,
        default=None,
        help="Path to a scanner graph JSON. Defaults to "
             "<root>/state/verification-contracts/host-inventory-graph.json.",
    )
    parser.add_argument(
        "--migrate-verification-level", action="store_true",
        help="One-off: add verification_level=internally_checked to every "
             "claim file on disk under --root that predates the field "
             "(CIR-157), then exit. Ignores `statement`.",
    )
    args = parser.parse_args()

    if args.migrate_verification_level:
        migrated = migrate_claims_dir(args.root)
        for path in migrated:
            print(f"migrated: {path}")
        print(f"{len(migrated)} claim file(s) migrated.")
        return 0

    if not args.statement:
        parser.error("statement is required unless --migrate-verification-level is passed")

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
