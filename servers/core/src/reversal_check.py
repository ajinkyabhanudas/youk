"""The periodic reversal check: Phase C of
docs/pattern-learning-architecture-design.md -- read that document's
"Phase C, precisely" section first; this module implements only its three
real mechanical pieces.

A DispositionEvent with disposition="dismissed" recorded that a Domain
Brief candidate was explicitly judged irrelevant to some task. This module
detects when a LATER, genuinely new Domain Brief entry (a new decision or
post-mortem Domain Brief's own extractor picks up on a later run) proves
that dismissal wrong, and constructs the real PatternEntry that records it.

Two real new files (deliberately not reusing existing ones -- see the
design doc's "Phase C, precisely" section for why):
  - state/domain-brief-known-sources/{project}.json: every source_id Domain
    Brief has ever produced for that project, so a later run can tell a
    genuinely NEW entry from one that was always there.
  - state/confirmed-patterns.jsonl: every real PatternEntry Phase C (or
    later Phase D) actually writes. state/verification-pattern-library.jsonl
    stays exactly as it is -- a read-only historical record in its own,
    incompatible {claim_shape, missed_sub_claim, how_found, date} shape.

Container boundary (ADR-001): domain_brief.py (this module's sibling, same
youk-core container) is imported directly -- `build_domain_brief` is reused,
never reimplemented. domain_edge_cases.py runs in the separate youk-code
container and is never imported from here; instead, `_words` below
reproduces its exact term-matching style (same regex, same lowercase-and-
intersect approach) rather than inventing a second matcher, per the task's
explicit instruction to reuse that style without crossing the container
boundary.

domain/sub_domain are never inferred here -- see
skills/self-heal/references/reversal-confirmation.md for why that is a
required skill-content judgment call, not a Python heuristic.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from domain_brief import DomainBrief, REPO_ROOT, build_domain_brief
from pattern_entry import PatternEntry

# Same regex + lowercase-and-intersect style as
# servers/code/src/domain_edge_cases.py's _words() -- reused deliberately,
# not reimported (container boundary, see module docstring).
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def known_sources_path(root: Path, project: str) -> Path:
    return root / "state" / "domain-brief-known-sources" / f"{project}.json"


def disposition_log_path(root: Path) -> Path:
    return root / "state" / "disposition-log.jsonl"


def confirmed_patterns_path(root: Path) -> Path:
    return root / "state" / "confirmed-patterns.jsonl"


def _jsonl_has_id(path: Path, entry_id: str) -> bool:
    """True if an append-only JSONL file already has a row with this real,
    deterministic id. Re-confirming the same real reversal (or re-promoting
    the same real group) must never grow the file -- deterministic ids exist
    precisely so a repeat run can be recognized as the same real event, not
    appended as a duplicate. A line that fails to parse is skipped, same
    resilience discipline as every other reader of these files."""
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == entry_id:
            return True
    return False


def _load_known_source_ids(root: Path, project: str) -> set[str]:
    path = known_sources_path(root, project)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return set(data.get("known_source_ids", []))


def _write_known_source_ids(root: Path, project: str, source_ids: set[str]) -> None:
    path = known_sources_path(root, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "project": project,
                "known_source_ids": sorted(source_ids),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _brief_invariant_rows(brief: DomainBrief) -> list[dict]:
    """Every (bounded_context, invariant) pair in a fresh Domain Brief,
    flattened -- never forced, one real row per real invariant already in
    the brief."""
    rows: list[dict] = []
    for ctx in brief.bounded_contexts:
        for inv in ctx.invariants:
            rows.append(
                {
                    "bounded_context": ctx.name,
                    "ubiquitous_language": ctx.ubiquitous_language,
                    "statement": inv.statement,
                    "source_file": inv.source_file,
                    "source_id": inv.source_id,
                }
            )
    return rows


def _load_dismissed_events(root: Path, project: str) -> list[dict]:
    """Real dismissed rows for this project from state/disposition-log.jsonl.
    Never backfilled, never fabricated -- a missing log contributes zero
    events, same resilience discipline as domain_edge_cases.load_domain_brief."""
    path = disposition_log_path(root)
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("project") == project and row.get("disposition") == "dismissed":
            events.append(row)
    return events


def _matched_terms(dismissed_bounded_context: str, row: dict) -> list[str]:
    event_words = _words(dismissed_bounded_context)
    row_words = {t.lower() for t in row["ubiquitous_language"]} | _words(row["bounded_context"])
    return sorted(event_words & row_words)


def detect_reversals(project: str, root: Path) -> list[dict]:
    """Rebuild this project's Domain Brief fresh, diff it against the
    known-sources ledger for genuinely NEW entries, and cross-reference
    those against real dismissed DispositionEvents for this project by
    bounded_context keyword overlap.

    Returns a list of real {"dismissed_event": ..., "new_invariant": ...}
    pairs -- [] when nothing real changed (no new source_ids, or no
    dismissed event's bounded_context overlaps a new entry's vocabulary).
    Never a forced match. Updates the ledger after running, regardless of
    whether any reversal was found, so the next run's diff is against
    everything seen so far.
    """
    brief = build_domain_brief(root, project=project)
    rows = _brief_invariant_rows(brief)

    known_source_ids = _load_known_source_ids(root, project)
    is_first_ever_run = not known_source_ids
    new_rows = [r for r in rows if r["source_id"] not in known_source_ids]

    dismissed_events = _load_dismissed_events(root, project)

    reversals: list[dict] = []
    # On a genuinely first-ever run there is no real prior baseline: every
    # entry in the brief is trivially "new" relative to an empty ledger, so
    # "new" carries no real signal yet -- any dismissed event's own
    # still-unchanged entry (or an unrelated entry sharing one keyword)
    # would be reported as a false reversal. Seed the ledger below and
    # report nothing until a real second run has something genuine to diff
    # against.
    if not is_first_ever_run:
        for row in new_rows:
            for event in dismissed_events:
                matched = _matched_terms(event["bounded_context"], row)
                if not matched:
                    continue
                reversals.append(
                    {
                        "dismissed_event": event,
                        "new_invariant": {
                            "bounded_context": row["bounded_context"],
                            "statement": row["statement"],
                            "source_file": row["source_file"],
                            "source_id": row["source_id"],
                            "matched_terms": matched,
                        },
                    }
                )

    all_source_ids = known_source_ids | {r["source_id"] for r in rows}
    _write_known_source_ids(root, project, all_source_ids)

    return reversals


def _compute_pattern_id(project: str, dismissed_source_id: str, new_source_id: str) -> str:
    """Deterministic, derived from the real pair -- NOT a random uuid, same
    precedent as disposition_event.compute_candidate_id, so confirming the
    same real reversal twice never produces two different PatternEntry ids."""
    digest_input = "\x1f".join([project, dismissed_source_id, new_source_id])
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]


def confirm_reversed_pattern(
    reversal: dict,
    domain: str,
    sub_domain: str,
    *,
    project: str | None = None,
    root: Path | None = None,
) -> PatternEntry:
    """Construct the real PatternEntry a confirmed reversal earns, and
    append it to state/confirmed-patterns.jsonl.

    domain/sub_domain are passed in, never inferred here -- see
    skills/self-heal/references/reversal-confirmation.md for the required
    judgment-call step that names them before this function is ever called.
    A bad (empty) domain/sub_domain raises via PatternEntry's own
    __post_init__ validation, not a second check here.
    """
    dismissed_event = reversal["dismissed_event"]
    new_invariant = reversal["new_invariant"]
    resolved_project = project if project is not None else dismissed_event.get("project", "")
    resolved_root = root if root is not None else REPO_ROOT

    statement = (
        f"Dismissed decision for '{dismissed_event['bounded_context']}' "
        f"({dismissed_event['source_id']}) was reversed by a new decision "
        f"({new_invariant['source_id']}): {new_invariant['statement']}"
    )

    entry = PatternEntry(
        id=_compute_pattern_id(
            resolved_project, dismissed_event["source_id"], new_invariant["source_id"]
        ),
        scope="local",
        domain=domain,
        sub_domain=sub_domain,
        statement=statement,
        evidence_level="internally_checked",
        provenance=[
            {
                "project": resolved_project,
                "source_file": dismissed_event["source_file"],
                "source_id": dismissed_event["source_id"],
                "abstracted": False,
            },
            {
                "project": resolved_project,
                "source_file": new_invariant["source_file"],
                "source_id": new_invariant["source_id"],
                "abstracted": False,
            },
        ],
        status="confirmed",
        created_at=datetime.now(UTC).isoformat(),
        confirmed_count=1,
    )

    path = confirmed_patterns_path(resolved_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _jsonl_has_id(path, entry.id):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    return entry
