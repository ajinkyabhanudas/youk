"""End-to-end integration test for the complete pattern-learning architecture
(Phases A-E of docs/pattern-learning-architecture-design.md -- see its
"Phase E, precisely" section). Every function exercised here already exists
and already has its own unit tests (test_pattern_entry.py,
test_disposition_event.py, test_reversal_check.py, test_pattern_promotion.py);
this file's only job is proving the full chain actually composes on real
data, using the real deployment shape, not one isolated unit test per
function.

Real deployment shape, per the design doc: one youk installation tracks
multiple projects' confirmed/global patterns in the SAME root's state/
directory -- confirmed_patterns_path(root) and global_patterns_path(root) are
per-ROOT, not per-project; the `project` field on each row is what
distinguishes them. `build_domain_brief` itself always reads `root /
"DECISIONS.md"` though, so a shared root running two projects means writing
one project's real DECISIONS.md, running that project's full reversal chain,
then overwriting DECISIONS.md with the other real project's file and running
its chain -- the shared `state/` directory (ledgers, confirmed-patterns,
global-patterns) persists across that swap exactly as it would across two
real sessions against the same youk installation.

Real projects used, same real-data discipline and skip-when-absent precedent
as test_domain_brief.py's CIR-168 cross-project tests: this repo's own
DECISIONS.md (project "youk") and circaid's real DECISIONS.md at its real,
absolute, read-only location on this machine (project "circaid") -- the
exact pairing the design doc's own "Phase E, precisely" section names as an
example. Two real bounded contexts are used per project (one per promotion
group below), copied/extended, never fabricated prose.

Three real scenarios (design doc's full numbered chain, 1-8):
  - test_full_chain_promotes_across_two_real_projects: the happy path,
    steps 1-6 -- a real dismissal, a real reversal, a real cross-project
    confirmation, a real promotion, a real read-back.
  - test_adversarial_group_with_proprietary_identifier_is_refused: step 7,
    non-optional per the design doc -- a second, parallel pair of confirmed
    entries for the same two projects, where one reversing decision contains
    a real proprietary-shaped identifier (same PascalCase style the
    verification_research.py module docstring names as the real leak CIR-175
    found and fixed). The whole group must be refused, while the happy group
    above is unaffected.
  - test_identical_chain_run_twice_produces_no_duplicate_rows: step 8 --
    re-running confirm_reversed_pattern and promote_group against the same
    real, already-processed data must not grow confirmed-patterns.jsonl or
    global-patterns.jsonl. Building this test surfaced a real bug (see the
    fix in reversal_check.py / pattern_promotion.py, same commit as this
    test): both functions appended unconditionally on every call, so calling
    either twice with the same deterministic id produced two rows with that
    id, not one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from disposition_event import append_disposition_event
from domain_brief import build_domain_brief
from domain_edge_cases import find_domain_edge_case_candidates
from pattern_entry import PatternEntry
from pattern_promotion import (
    find_promotion_candidates,
    global_patterns_path,
    promote_group,
    query_global_patterns,
)
from reversal_check import (
    confirm_reversed_pattern,
    confirmed_patterns_path,
    detect_reversals,
    disposition_log_path,
    known_sources_path,
)

_YOUK_DECISIONS = (Path(__file__).parent.parent / "DECISIONS.md").read_text(encoding="utf-8")

_CIRCAID_DECISIONS_PATH = Path("/Users/ajinkya/Desktop/circaid/DECISIONS.md")
_CIRCAID_DECISIONS = (
    _CIRCAID_DECISIONS_PATH.read_text(encoding="utf-8") if _CIRCAID_DECISIONS_PATH.exists() else ""
)

pytestmark = pytest.mark.skipif(
    not _CIRCAID_DECISIONS_PATH.exists(),
    reason="circaid repo not present on this machine -- same skip precedent as "
    "test_domain_brief.py's CIR-168 cross-project tests",
)

# --- Group 1 (happy path): domain=observability, sub_domain=tracing --------
#
# youk's half is the real fixture test_reversal_check.py already proved --
# same real dismissed bounded context, same real-shaped reversing entry,
# reused verbatim rather than inventing a parallel one.

_YOUK_TRACING_TASK = "Add a new Langfuse trace field to capture retry latency across repairs."
_YOUK_TRACING_BOUNDED_CONTEXT = "Langfuse trace granularity"
_YOUK_TRACING_REVERSING_ENTRY = """

## 2026-10-03 [Langfuse trace granularity revisited]
Chose:      Per-repair trace granularity after all.
Over:       One trace per run.
Because:    A real incident showed aggregating cost/latency across a run masked
            which specific repair caused a cost spike; per-repair traces were
            required to debug it.
Cost:       Loses the single-run frame for normal aggregation; needs a join to
            see whole-run cost again.
"""

_CIRCAID_SCOPE_TASK = "Decide whether a client scope boundary should extend across a shared session slug."
_CIRCAID_SCOPE_BOUNDED_CONTEXT = "Client scope is a path level above session slug"
_CIRCAID_SCOPE_REVERSING_ENTRY = """

## ADR-C099 — Client scope is a path level above session slug, revisited

**Decided:** client scope moves one level up again, to the organization, after a real
incident showed two sibling clients under one organization needed to share a promoted
read without re-deriving it per client.

**Why:** a later real incident showed the original per-client boundary blocked a
legitimate shared read that should have been allowed; organization-level scope
restores that without widening isolation elsewhere.
"""

_DOMAIN_HAPPY = "observability"
_SUB_DOMAIN_HAPPY = "tracing"

# --- Group 2 (adversarial): domain=payments, sub_domain=retry-handling -----
#
# youk's side stays clean (confident abstraction); circaid's reversing
# decision carries a real proprietary-shaped PascalCase identifier, same
# style as the PaymentGatewayRetryHandlerV3 case verification_research.py's
# module docstring names as the real leak this initiative already found and
# fixed (CIR-175) -- find_promotion_candidates must refuse the WHOLE group.

_YOUK_PROXY_TASK = "Change how the proxy score weights repair attempts in run_health_check."
_YOUK_PROXY_BOUNDED_CONTEXT = "Proxy score definition"
_YOUK_PROXY_REVERSING_ENTRY = """

## 2026-10-03 [Proxy score definition revisited]
Chose:      Weight repair attempts by how costly each one was, not a flat ratio.
Over:       A simple ratio of repaired candidates to total candidates.
Because:    A real run showed one expensive repair outweighed five cheap ones, and
            the flat ratio made an expensive run look identical to a cheap one.
Cost:       Needs a cost figure for every candidate, not just a pass or fail flag.
"""

_CIRCAID_PROMOTION_TASK = (
    "Decide whether the promotion boundary that binds reads should extend to internal tooling."
)
_CIRCAID_PROMOTION_BOUNDED_CONTEXT = "Promotion boundary binds both promotion and reads"
_CIRCAID_PROMOTION_REVERSING_ENTRY_POISONED = """

## ADR-C098 — Promotion boundary binds both promotion and reads, revisited

**Decided:** the promotion boundary is relaxed for internal tooling after a real
incident where PaymentGatewayRetryHandlerV3 silently retried a promoted read three
times before the duplicate was caught.

**Why:** the retry handler needed a shared read across the promotion boundary to
detect its own duplicate, which the original rule made impossible.
"""

_DOMAIN_ADVERSARIAL = "payments"
_SUB_DOMAIN_ADVERSARIAL = "retry-handling"


def _run_project_reversal_chain(
    *,
    root: Path,
    project: str,
    decisions_text: str,
    task: str,
    bounded_context: str,
    reversing_entry: str,
    domain: str,
    sub_domain: str,
) -> PatternEntry:
    """The real per-project half of the full chain (design doc steps 1-5):
    write this project's real DECISIONS.md into the shared root, surface a
    real candidate via the real Domain Brief + edge-case pipeline, dismiss
    it, add a real-shaped reversing decision, detect the real reversal, and
    confirm it. Returns the real, appended PatternEntry.
    """
    (root / "DECISIONS.md").write_text(decisions_text, encoding="utf-8")
    brief = build_domain_brief(root, project=project).to_dict()
    candidates = find_domain_edge_case_candidates(task, brief, top_n=1000)
    candidate = next(c for c in candidates if c["bounded_context"] == bounded_context)

    # Seed the ledger before dismissing -- same cold-start discipline as
    # test_reversal_check.py: a dismissal logged before detect_reversals has
    # ever run for this project must not self-match on the next call.
    detect_reversals(project, root)
    append_disposition_event(
        project=project,
        task=task,
        bounded_context=candidate["bounded_context"],
        source_file=candidate["source_file"],
        source_id=candidate["source_id"],
        disposition="dismissed",
        log_path=disposition_log_path(root),
    )

    (root / "DECISIONS.md").write_text(decisions_text + reversing_entry, encoding="utf-8")
    reversals = detect_reversals(project, root)
    assert len(reversals) == 1, f"{project}/{bounded_context}: expected exactly one real reversal"

    return confirm_reversed_pattern(
        reversals[0], domain=domain, sub_domain=sub_domain, project=project, root=root
    )


def _run_happy_group(root: Path) -> tuple[PatternEntry, PatternEntry]:
    youk_entry = _run_project_reversal_chain(
        root=root,
        project="youk",
        decisions_text=_YOUK_DECISIONS,
        task=_YOUK_TRACING_TASK,
        bounded_context=_YOUK_TRACING_BOUNDED_CONTEXT,
        reversing_entry=_YOUK_TRACING_REVERSING_ENTRY,
        domain=_DOMAIN_HAPPY,
        sub_domain=_SUB_DOMAIN_HAPPY,
    )
    circaid_entry = _run_project_reversal_chain(
        root=root,
        project="circaid",
        decisions_text=_CIRCAID_DECISIONS,
        task=_CIRCAID_SCOPE_TASK,
        bounded_context=_CIRCAID_SCOPE_BOUNDED_CONTEXT,
        reversing_entry=_CIRCAID_SCOPE_REVERSING_ENTRY,
        domain=_DOMAIN_HAPPY,
        sub_domain=_SUB_DOMAIN_HAPPY,
    )
    return youk_entry, circaid_entry


def _run_adversarial_group(root: Path) -> tuple[PatternEntry, PatternEntry]:
    youk_entry = _run_project_reversal_chain(
        root=root,
        project="youk",
        decisions_text=_YOUK_DECISIONS,
        task=_YOUK_PROXY_TASK,
        bounded_context=_YOUK_PROXY_BOUNDED_CONTEXT,
        reversing_entry=_YOUK_PROXY_REVERSING_ENTRY,
        domain=_DOMAIN_ADVERSARIAL,
        sub_domain=_SUB_DOMAIN_ADVERSARIAL,
    )
    circaid_entry = _run_project_reversal_chain(
        root=root,
        project="circaid",
        decisions_text=_CIRCAID_DECISIONS,
        task=_CIRCAID_PROMOTION_TASK,
        bounded_context=_CIRCAID_PROMOTION_BOUNDED_CONTEXT,
        reversing_entry=_CIRCAID_PROMOTION_REVERSING_ENTRY_POISONED,
        domain=_DOMAIN_ADVERSARIAL,
        sub_domain=_SUB_DOMAIN_ADVERSARIAL,
    )
    return youk_entry, circaid_entry


# --- The real chain: steps 1-6 ----------------------------------------------


def test_full_chain_promotes_across_two_real_projects(tmp_path):
    youk_entry, circaid_entry = _run_happy_group(tmp_path)

    # Step 5: both land in the ONE shared confirmed-patterns.jsonl.
    assert youk_entry.status == "confirmed"
    assert circaid_entry.status == "confirmed"
    assert youk_entry.domain == circaid_entry.domain == _DOMAIN_HAPPY
    assert youk_entry.sub_domain == circaid_entry.sub_domain == _SUB_DOMAIN_HAPPY
    confirmed_lines = confirmed_patterns_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(confirmed_lines) == 2

    # Step 6: find_promotion_candidates finds the real 2-project group.
    candidates = find_promotion_candidates(tmp_path)
    assert len(candidates) == 1
    group = candidates[0]
    assert (group["domain"], group["sub_domain"]) == (_DOMAIN_HAPPY, _SUB_DOMAIN_HAPPY)
    assert group["projects"] == {"youk", "circaid"}
    assert len(group["entries"]) == 2

    # promote_group writes a real PatternEntry to global-patterns.jsonl.
    promoted = promote_group(group, group["abstracted_statements"][0], root=tmp_path)
    assert promoted.scope == "global"
    assert promoted.status == "promoted"
    assert promoted.confirmed_count == 2
    assert {row["project"] for row in promoted.provenance} == {"youk", "circaid"}
    assert all(row["abstracted"] is True for row in promoted.provenance)

    # query_global_patterns reads it back.
    read_back = query_global_patterns(tmp_path)
    assert len(read_back) == 1
    assert read_back[0].id == promoted.id
    assert read_back[0].to_dict() == promoted.to_dict()


# --- The adversarial half: step 7, non-optional -----------------------------


def test_adversarial_group_with_proprietary_identifier_is_refused(tmp_path):
    _run_happy_group(tmp_path)
    _run_adversarial_group(tmp_path)

    # Both groups are real, confirmed, cross-project pairs in the one shared
    # confirmed-patterns.jsonl -- four rows, two distinct (domain, sub_domain)
    # groups, each spanning both real projects.
    confirmed_lines = confirmed_patterns_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(confirmed_lines) == 4

    candidates = find_promotion_candidates(tmp_path)
    group_keys = {(c["domain"], c["sub_domain"]) for c in candidates}

    # The happy group still promotes...
    assert (_DOMAIN_HAPPY, _SUB_DOMAIN_HAPPY) in group_keys
    # ...but the adversarial group is refused WHOLE -- not partially promoted,
    # not promoted with the poisoned entry silently dropped.
    assert (_DOMAIN_ADVERSARIAL, _SUB_DOMAIN_ADVERSARIAL) not in group_keys

    happy_group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN_HAPPY, _SUB_DOMAIN_HAPPY))
    promote_group(happy_group, happy_group["abstracted_statements"][0], root=tmp_path)

    # Nothing from the adversarial run ever reaches global-patterns.jsonl.
    global_lines = global_patterns_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(global_lines) == 1
    assert query_global_patterns(tmp_path, domain=_DOMAIN_ADVERSARIAL) == []


# --- Idempotency: step 8, running the identical chain twice ----------------


def test_identical_chain_run_twice_produces_no_duplicate_rows(tmp_path):
    youk_entry, _circaid_entry = _run_happy_group(tmp_path)
    candidates = find_promotion_candidates(tmp_path)
    group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN_HAPPY, _SUB_DOMAIN_HAPPY))
    promoted = promote_group(group, group["abstracted_statements"][0], root=tmp_path)

    # Re-running detect_reversals for both projects against the identical,
    # already-seen real decisions must find nothing new -- the ledger already
    # knows every real source_id involved.
    assert detect_reversals("youk", tmp_path) == []
    assert detect_reversals("circaid", tmp_path) == []
    youk_known = known_sources_path(tmp_path, "youk").read_text(encoding="utf-8")
    circaid_known = known_sources_path(tmp_path, "circaid").read_text(encoding="utf-8")

    # A retried confirm step against the SAME already-detected real pairs
    # (e.g. a resumed session that re-runs confirm_reversed_pattern without
    # re-deriving the reversal from scratch) must not grow
    # confirmed-patterns.jsonl -- same deterministic id, same real pair.
    youk_pair = {
        "dismissed_event": {
            "project": "youk",
            "bounded_context": _YOUK_TRACING_BOUNDED_CONTEXT,
            "source_file": "DECISIONS.md",
            "source_id": "2026-08-27 [Langfuse trace granularity]",
        },
        "new_invariant": {
            "bounded_context": _YOUK_TRACING_BOUNDED_CONTEXT,
            "source_file": "DECISIONS.md",
            "source_id": "2026-10-03 [Langfuse trace granularity revisited]",
            "statement": (
                "Per-repair trace granularity after all. — because A real incident showed "
                "aggregating cost/latency across a run masked\nwhich specific repair caused a "
                "cost spike; per-repair traces were\nrequired to debug it."
            ),
        },
    }
    first_repeat = confirm_reversed_pattern(
        youk_pair, domain=_DOMAIN_HAPPY, sub_domain=_SUB_DOMAIN_HAPPY, project="youk", root=tmp_path
    )
    second_repeat = confirm_reversed_pattern(
        youk_pair, domain=_DOMAIN_HAPPY, sub_domain=_SUB_DOMAIN_HAPPY, project="youk", root=tmp_path
    )
    assert first_repeat.id == youk_entry.id
    assert second_repeat.id == youk_entry.id
    confirmed_lines = confirmed_patterns_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(confirmed_lines) == 2, "re-confirming the same real pair must not duplicate it"

    # Re-running find_promotion_candidates + promote_group against the same
    # already-promoted real group -- find_promotion_candidates has no
    # "already promoted" filter by design (confirmed-patterns.jsonl entries
    # never change status in place), so promote_group itself must be the one
    # idempotency boundary.
    candidates_again = find_promotion_candidates(tmp_path)
    group_again = next(
        c for c in candidates_again if (c["domain"], c["sub_domain"]) == (_DOMAIN_HAPPY, _SUB_DOMAIN_HAPPY)
    )
    promoted_again = promote_group(group_again, group_again["abstracted_statements"][0], root=tmp_path)
    assert promoted_again.id == promoted.id
    global_lines = global_patterns_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(global_lines) == 1, "re-promoting the same real group must not duplicate it"

    # The ledger itself never grows on a no-op re-run.
    assert known_sources_path(tmp_path, "youk").read_text(encoding="utf-8") == youk_known
    assert known_sources_path(tmp_path, "circaid").read_text(encoding="utf-8") == circaid_known

    # query_global_patterns still reads back exactly one real entry.
    assert len(query_global_patterns(tmp_path)) == 1
