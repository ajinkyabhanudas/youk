"""Coverage tree — the completeness surface. Cheap concept-check before expensive code-review.

The blind spot this closes: review currently means reading a diff to find what's wrong. But
the costliest miss is a CONCEPT never considered (no secrets handling, no idempotency) — and
a diff cannot show you what isn't there. The tree makes that miss surface at the TOP, at near-
zero cost: you check the tree's concept nodes first ('did it even think about X?'), and only
descend into code for branches that pass the concept check. A miss at the top is cheap to find
because you never descend for it (the user's core requirement).

STRUCTURE (BUILD-SPEC D7 — the load-bearing design choice):
  - A BUILDER populates the tree: which template concepts did this task cover?
  - An ADVERSARY (stripped context — task + template only, NOT the builder's reasoning)
    attacks the tree for missed/contested nodes. A single agent building AND judging its own
    tree can only mark nodes it thought of; its blind spot IS the tree's blind spot. Real
    independence needs a separate context, not a prompt saying 'now critique yourself'.
  - The adversary RAISES, it does not RULE: a contested node surfaces to the HUMAN at
    Level-1. Turning a contested node into a forced human glance is the germane-load moment.
  - Human-caught misses UPDATE the template (self-revising set) — the accumulator that stops
    a class of miss recurring. Only mechanical/safety nodes are frozen.

NAMED ANTI-PATTERN (wiring_pulse false-green): when the adversary cannot run (no API), the
tree MUST NOT render a clean all-covered result it never verified. It renders adversary
status = NOT_RUN and a completeness=UNVERIFIED banner. This degraded path is first-class and
tested — it was built API-down on purpose so the fail-safe cannot be an afterthought.

The builder/adversary are injected callables (Populator / Adversary protocols) so this module
is fully testable offline; the live LLM-subagent implementations swap in without touching the
tree logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Coverage(StrEnum):
    COVERED = "covered"           # concept was handled
    PARTIAL = "partial"          # touched but incomplete
    MISSING = "missing"          # concept not considered — the costly, cheap-to-find miss
    NA = "n/a"                   # concept legitimately doesn't apply to this task


class AdversaryStatus(StrEnum):
    CLEAN = "clean"              # adversary ran, found nothing to add/contest
    FOUND_GAPS = "found_gaps"    # adversary added/contested nodes
    NOT_RUN = "not_run"          # could not run (no API) — completeness UNVERIFIED


@dataclass
class Node:
    """One concept in the tree. `covered` is the builder's claim; `contested_by_adversary`
    is set when the adversary disputes it or adds it as a missing concept the builder omitted.
    """
    concept: str
    covered: Coverage
    detail: str = ""
    contested_by_adversary: bool = False
    added_by_adversary: bool = False  # a concept the builder never listed at all


@dataclass
class Branch:
    """A top-level domain (security, correctness, data, nfr) and its concept nodes. MECE is
    checked against the template: nodes must not overlap and must exhaust the template's set.
    """
    domain: str
    nodes: list[Node] = field(default_factory=list)

    def gaps(self) -> list[Node]:
        return [n for n in self.nodes if n.covered is Coverage.MISSING]

    def partials(self) -> list[Node]:
        return [n for n in self.nodes if n.covered is Coverage.PARTIAL]

    def contested(self) -> list[Node]:
        return [n for n in self.nodes if n.contested_by_adversary]


# --- templates: the MECE concept sets per task domain -------------------------------------
# Self-revising (BUILD-SPEC anti-pattern #3): grows when a human catches a missing concept.
# Seeded conservatively; each set is a claim of 'these are the concepts this domain requires'.
# Only these are the frozen safety/mechanical core — everything else is added by revision.

TEMPLATES: dict[str, list[str]] = {
    "security": [
        "authn / identity",
        "authz / access control",
        "input validation",
        "secrets handling",
        "injection (sql/cmd/path)",
        "rate-limit / dos",
    ],
    "correctness": [
        "happy path",
        "edge cases",
        "error states",
        "concurrency / races",
    ],
    "data": [
        "schema change",
        "migration / revert",
        "data volume / scale",
    ],
    "nfr": [
        "idempotency",
        "retry / timeout",
        "observability",
        "caching",
    ],
}


def add_concept_to_template(domain: str, concept: str) -> bool:
    """Self-revision entry point: a human-caught miss adds a concept so the class can't recur.
    Returns True if newly added. Idempotent. This is the accumulator (BUILD-SPEC D7)."""
    bucket = TEMPLATES.setdefault(domain, [])
    if concept in bucket:
        return False
    bucket.append(concept)
    return True


# --- injected agent roles -----------------------------------------------------------------

class Populator(Protocol):
    """Fills a branch's nodes from the task. Live impl = an LLM subagent; test impl = a stub.
    Returns a list of Nodes covering (at least) the template concepts for the domain."""
    def __call__(self, task: str, domain: str, template: list[str]) -> list[Node]: ...


class Adversary(Protocol):
    """Attacks a populated branch for missed/contested concepts. Live impl = a STRIPPED
    subagent (task + template only). Returns nodes to add/contest, or raises to signal it
    could not run (caught → NOT_RUN degraded path). Never returns a rubber-stamp silently."""
    def __call__(self, task: str, branch: Branch, template: list[str]) -> list[Node]: ...


# --- the tree -----------------------------------------------------------------------------

@dataclass
class CoverageTree:
    task: str
    branches: list[Branch] = field(default_factory=list)
    adversary_status: AdversaryStatus = AdversaryStatus.NOT_RUN

    @property
    def unverified(self) -> bool:
        """True when the adversary never ran — completeness is a builder self-claim only."""
        return self.adversary_status is AdversaryStatus.NOT_RUN

    def all_gaps(self) -> list[tuple[str, Node]]:
        return [(b.domain, n) for b in self.branches for n in b.gaps()]

    def all_contested(self) -> list[tuple[str, Node]]:
        return [(b.domain, n) for b in self.branches for n in b.contested()]

    def review_order(self) -> list[str]:
        """Level-1 priority (BUILD-SPEC goal): gaps first (a missed concept is cheapest to
        find, costliest to miss), then contested (adversary disputed — human rules), then
        partials (ask). Full code descent only after these clear. Ordered by domain risk:
        security/data (safety) ahead of correctness/nfr when severity ties."""
        risk_rank = {"security": 0, "data": 1, "correctness": 2, "nfr": 3}

        def rank(domain: str) -> int:
            return risk_rank.get(domain, 99)

        lines: list[str] = []
        for domain, node in sorted(self.all_gaps(), key=lambda x: rank(x[0])):
            lines.append(f"GAP  [{domain}] {node.concept} — concept not considered")
        for domain, node in sorted(self.all_contested(), key=lambda x: rank(x[0])):
            tag = "adversary-added" if node.added_by_adversary else "adversary-contested"
            lines.append(f"?    [{domain}] {node.concept} — {tag}, you rule")
        for b in self.branches:
            for n in b.partials():
                lines.append(f"~    [{b.domain}] {n.concept} — partial, ask")
        return lines

    def render(self) -> str:
        """The glanceable tree. Leads with the honesty banner if unverified, then gaps/
        contested up top (cheap to find), then the branch tree, then the review order."""
        out: list[str] = [f"COVERAGE · {self.task}"]
        if self.unverified:
            out.append("⚠ completeness UNVERIFIED — adversary did not run (no API); "
                       "builder self-claim only")
        elif self.adversary_status is AdversaryStatus.FOUND_GAPS:
            out.append("adversary: found gaps (below)")
        else:
            out.append("adversary: clean")

        mark = {
            Coverage.COVERED: "●", Coverage.PARTIAL: "◐",
            Coverage.MISSING: "○", Coverage.NA: "·",
        }
        for b in self.branches:
            out.append(f"├─ {b.domain}")
            for n in b.nodes:
                flag = ""
                if n.covered is Coverage.MISSING:
                    flag = "  ⚠ GAP"
                elif n.contested_by_adversary:
                    flag = "  ? contested"
                out.append(f"│  {mark[n.covered]} {n.concept}{flag}")
        order = self.review_order()
        if order:
            out.append("— review order (top = cheapest to check) —")
            out.extend(order)
        return "\n".join(out)


def check_mece(branch: Branch, template: list[str]) -> tuple[bool, list[str]]:
    """MECE check against the template: exhaustive (every template concept present) and
    non-overlapping (no duplicate concepts). Returns (ok, problems). This is what makes
    'complete' a checkable claim rather than a vibe."""
    problems: list[str] = []
    concepts = [n.concept for n in branch.nodes]
    # mutually exclusive: no duplicates
    dupes = {c for c in concepts if concepts.count(c) > 1}
    if dupes:
        problems.append(f"overlap: {sorted(dupes)}")
    # collectively exhaustive: every template concept represented
    missing = [c for c in template if c not in concepts]
    if missing:
        problems.append(f"not exhaustive: missing {missing}")
    return (not problems, problems)


def build_tree(
    task: str,
    domains: list[str],
    populate: Populator,
    adversary: Adversary | None,
) -> CoverageTree:
    """Build the tree: populate each domain, then run the adversary if available.

    The degraded path (BUILD-SPEC no-API section) is the DEFAULT posture, not an exception:
    if adversary is None OR raises, adversary_status stays NOT_RUN and the tree renders
    UNVERIFIED — never a false-green clean result. This is the fail-safe made structural.
    """
    tree = CoverageTree(task=task)
    for domain in domains:
        template = TEMPLATES.get(domain, [])
        branch = Branch(domain=domain, nodes=populate(task, domain, template))
        tree.branches.append(branch)

    if adversary is None:
        tree.adversary_status = AdversaryStatus.NOT_RUN
        return tree

    found_any = False
    for branch in tree.branches:
        template = TEMPLATES.get(branch.domain, [])
        try:
            additions = adversary(task, branch, template)
        except Exception:
            # Adversary could not run for this branch → do NOT claim verification.
            # Fail-safe per contract: no silent rubber-stamp, no false-green.
            tree.adversary_status = AdversaryStatus.NOT_RUN
            return tree
        for node in additions:
            found_any = True
            existing = next((n for n in branch.nodes if n.concept == node.concept), None)
            if existing is None:
                node.added_by_adversary = True
                node.contested_by_adversary = True
                branch.nodes.append(node)
            else:
                existing.contested_by_adversary = True
                if node.detail:
                    existing.detail = node.detail
    tree.adversary_status = (
        AdversaryStatus.FOUND_GAPS if found_any else AdversaryStatus.CLEAN
    )
    return tree
