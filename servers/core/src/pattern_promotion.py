"""Cross-project promotion to the global pattern store: Phase D of
docs/pattern-learning-architecture-design.md -- read that document's
"Phase D, precisely" section first; this module implements only its three
mechanical pieces (1, 3, 4). Piece 2 (choosing which abstracted statement
represents a group with more than one distinct wording) is a required
skill-content judgment call -- see
skills/self-heal/references/pattern-promotion.md -- same reasoning as Phase
C's domain/sub_domain naming step, not a Python heuristic.

Two real design decisions this module enforces rather than re-litigates
(see the design doc section for the full reasoning):
  - `abstract_claim()` (servers/core/src/verification_research.py) is
    reused completely unmodified. `confident: False` is a hard refusal to
    promote the whole group it belongs to -- no glossary expansion, no
    second abstraction path, no partial promotion of a group with one
    unconfident member.
  - Cross-project matching is exact equality on (domain, sub_domain) --
    the same two judgment-call fields Phase C's skill-content step already
    requires naming for every confirmed entry. No invented text similarity.

One real new file: state/global-patterns.jsonl, the promoted-only sibling
of Phase C's state/confirmed-patterns.jsonl. Deliberately not wired into
DomainBrief's own dataclass, and not wired into nfr-check's live
candidate-surfacing flow -- both explicitly deferred, named here rather
than silently built or silently skipped (same honesty precedent as Phase
C naming its own deferred MCP-tool wiring).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from domain_brief import REPO_ROOT
from pattern_entry import PatternEntry, promote_pattern
from reversal_check import confirmed_patterns_path
from verification_research import abstract_claim


def global_patterns_path(root: Path) -> Path:
    return root / "state" / "global-patterns.jsonl"


def _load_confirmed_entries(path: Path) -> list[PatternEntry]:
    """Real PatternEntry rows from state/confirmed-patterns.jsonl. A missing
    file contributes zero entries, same resilience discipline as
    reversal_check._load_dismissed_events. A line that fails to parse as
    JSON is skipped (same precedent); a line that parses but fails
    PatternEntry's own validation raises -- that is real corruption of a
    file nothing but confirm_reversed_pattern/promote_group ever writes to,
    not a case to silently swallow."""
    if not path.exists():
        return []
    entries: list[PatternEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(PatternEntry.from_dict(row))
    return entries


def find_promotion_candidates(root: Path) -> list[dict]:
    """Group status=confirmed PatternEntry rows by (domain, sub_domain),
    keep only groups whose provenance spans >=2 distinct project values,
    and run abstract_claim() on every entry's statement in a surviving
    group -- dropping the whole group if any result has confident=False.

    Returns real groups:
      {"domain": str, "sub_domain": str, "entries": list[PatternEntry],
       "projects": set[str], "abstracted_statements": list[str]}
    "abstracted_statements" is aligned index-for-index with "entries", not
    deduplicated -- the skill-content step decides whether there is one
    distinct wording (trivial) or more than one (a real judgment call).
    Returns [] when nothing qualifies, never a forced/partial group.
    """
    confirmed = [e for e in _load_confirmed_entries(confirmed_patterns_path(root)) if e.status == "confirmed"]

    groups: dict[tuple[str, str], list[PatternEntry]] = {}
    for entry in confirmed:
        groups.setdefault((entry.domain, entry.sub_domain), []).append(entry)

    candidates: list[dict] = []
    for (domain, sub_domain), group_entries in groups.items():
        projects = {row["project"] for e in group_entries for row in e.provenance}
        if len(projects) < 2:
            continue

        abstractions = [abstract_claim(e.statement) for e in group_entries]
        if any(not a.confident for a in abstractions):
            continue

        candidates.append(
            {
                "domain": domain,
                "sub_domain": sub_domain,
                "entries": group_entries,
                "projects": projects,
                "abstracted_statements": [a.abstracted for a in abstractions],
            }
        )

    return candidates


def _compute_promoted_id(domain: str, sub_domain: str, entries: list[PatternEntry]) -> str:
    """Deterministic, derived from the real group -- NOT a random uuid, same
    precedent as reversal_check._compute_pattern_id, so promoting the same
    real group twice never produces two different PatternEntry ids."""
    digest_input = "\x1f".join([domain, sub_domain, *sorted(e.id for e in entries)])
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]


def promote_group(group: dict, chosen_statement: str, *, root: Path | None = None) -> PatternEntry:
    """Build the provenance list for a real promotion candidate group
    (every real entry's real provenance rows, each row's abstracted set to
    True -- legitimately true now, confirmed via abstract_claim() in
    find_promotion_candidates), then call Phase A's existing
    promote_pattern() to get the >=2-distinct-project guardrail enforcement
    for free. Appends the result to state/global-patterns.jsonl.

    chosen_statement is never picked here -- see the skill-content step
    this function is called from.
    """
    resolved_root = root if root is not None else REPO_ROOT
    entries: list[PatternEntry] = group["entries"]
    projects: set[str] = set(group["projects"])

    provenance = [
        {
            "project": row["project"],
            "source_file": row.get("source_file", ""),
            "source_id": row.get("source_id", ""),
            "abstracted": True,
        }
        for entry in entries
        for row in entry.provenance
    ]

    base_entry = PatternEntry(
        id=_compute_promoted_id(group["domain"], group["sub_domain"], entries),
        scope="local",
        domain=group["domain"],
        sub_domain=group["sub_domain"],
        statement=chosen_statement,
        evidence_level=entries[0].evidence_level,
        provenance=provenance,
        status="confirmed",
        created_at=datetime.now(UTC).isoformat(),
    )

    promoted = promote_pattern(base_entry, confirmed_in_projects=projects)

    path = global_patterns_path(resolved_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(promoted.to_dict()) + "\n")

    return promoted


def query_global_patterns(
    root: Path, domain: str | None = None, sub_domain: str | None = None
) -> list[PatternEntry]:
    """Real PatternEntry rows from state/global-patterns.jsonl, optionally
    filtered by domain and/or sub_domain. A missing file returns [].
    Deliberately a plain list a caller receives -- never merged into
    DomainBrief's own dataclass or any project's own bounded_contexts; see
    the module docstring for why that wiring is out of scope here."""
    path = global_patterns_path(root)
    if not path.exists():
        return []
    entries: list[PatternEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry = PatternEntry.from_dict(row)
        if domain is not None and entry.domain != domain:
            continue
        if sub_domain is not None and entry.sub_domain != sub_domain:
            continue
        entries.append(entry)
    return entries
