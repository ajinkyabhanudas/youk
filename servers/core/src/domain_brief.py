"""
Domain Brief: structured per-project domain model (CIR-162, Phase 1 of 4).

Phase 1 only: schema + a real extractor that populates it from this
project's own real decision records. Edge-case elicitation (Phase 2) and
bias-resistant review (Phase 3) are not built here -- see
state/problem-space-modeling/design.md for the full phased design and why
they are deliberately sequenced after this one is proven against real data.

Two real sources, two different structural dialects:
  - DECISIONS.md (repo root, committed): one decision per heading, followed
    by a block of labeled fields. CIR-168 generalized this across three real,
    confirmed dialects (youk's own dated-bracket headers with
    Chose/Over/Because/Cost; circaid's `## ADR-Cxxx — Title` headers with
    bold-markdown Decided/Rejected/Why fields; canopy's `### Sx — Title`
    headers with bold-markdown Decision/Why/Alternatives-considered fields)
    via a header-shape registry (_HEADER_PATTERNS) and a field-label synonym
    map (_FIELD_SYNONYMS) -- a 4th real dialect is one more registry entry,
    not a rewrite of the parser.
  - knowledge/projects/youk/decisions.md (instance-local, gitignored --
    "personal intelligence, never universally applicable" per .gitignore):
    numbered ADR-NNN entries with Decision/Rejected alternatives/Encodes
    fields. Not present in every checkout (CI included) -- the extractor
    treats its absence as a normal, reportable condition, not an error.

Never-backfill discipline (same as verification_contract.py's events.jsonl):
an entry that doesn't cleanly match its source's expected structure is
skipped, not forced into a bounded_context/invariant shape. A missing
source contributes zero entries rather than a fabricated one. CIR-168 also
distinguishes, per source, "file absent" from "file present but unrecognized
format" (`sources[].format_recognized`: None = absent, False = present with
zero matches, True = present and parsed) -- the open-ended question of what
to actually do about an unrecognized format is deliberately NOT answered
here in code; see skills/nfr-check/SKILL.md's "Domain Brief fallback" step
for the codebase-examination fallback, which is a judgment call and belongs
in skill content, not a deterministic function.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_STOPWORDS = {"a", "an", "and", "for", "in", "not", "of", "on", "or", "the", "to", "vs"}


@dataclass
class Invariant:
    statement: str
    source_file: str
    source_id: str


@dataclass
class BoundedContext:
    name: str
    ubiquitous_language: list[str] = field(default_factory=list)
    invariants: list[Invariant] = field(default_factory=list)


@dataclass
class DomainBrief:
    project: str
    generated_at: str
    sources: list[dict]
    bounded_contexts: list[BoundedContext] = field(default_factory=list)
    explicit_non_goals: list[Invariant] = field(default_factory=list)
    known_boundaries: list[Invariant] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def domain_brief_path(root: Path) -> Path:
    return root / "state" / "domain-brief.json"


def _title_terms(title: str) -> list[str]:
    """Deterministic ubiquitous-language terms from a real title -- never
    invented vocabulary, just the title's own significant words, in order,
    de-duplicated case-insensitively."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]*", title)
    terms: list[str] = []
    seen: set[str] = set()
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS or lw in seen:
            continue
        seen.add(lw)
        terms.append(w)
    return terms


# --- Source 1: DECISIONS.md -------------------------------------------------
#
# Real structural dialects confirmed across three real projects (CIR-168):
# the heading shape and field-label spelling both vary, but every real file
# is still "a heading naming one decision, followed by a block of labeled
# fields." Each dialect below is one additive _HeaderPattern entry -- a 4th
# real format found later is a new list entry, not a change to the parsing
# logic that walks the list.


@dataclass(frozen=True)
class _HeaderPattern:
    name: str
    regex: re.Pattern[str]
    # (raw id, title) -> the source_id to cite. Kept per-pattern because each
    # real dialect names its own entries differently (a date, an ADR code, a
    # short section id) and the citation should read the way that project
    # itself refers to the decision.
    format_source_id: Callable[[str, str], str]


_HEADER_PATTERNS: list[_HeaderPattern] = [
    # youk's own DECISIONS.md: "## 2026-08-27  [Langfuse trace granularity]"
    _HeaderPattern(
        "dated-bracket",
        re.compile(r"^## (?P<id>\d{4}-\d{2}-\d{2})\s+\[(?P<title>[^\]]+)\]\s*$"),
        lambda entry_id, title: f"{entry_id} [{title}]",
    ),
    # circaid's DECISIONS.md: "## ADR-C001 — Circaid is private, ..."
    _HeaderPattern(
        "adr-dash",
        re.compile(r"^## (?P<id>ADR-[A-Za-z0-9]+)\s*[—-]\s*(?P<title>.+?)\s*$"),
        lambda entry_id, title: entry_id,
    ),
    # canopy's DECISIONS.md: "### S1 — Architecture boundary" (nested under
    # a non-decision "## Security & Privacy"-style section header, which
    # doesn't match this or any other pattern and is correctly ignored).
    _HeaderPattern(
        "section-id-dash",
        re.compile(r"^### (?P<id>[A-Z]{1,3}\d+)\s*[—-]\s*(?P<title>.+?)\s*$"),
        lambda entry_id, title: entry_id,
    ),
]

# Synonym map: the same concept is spelled differently per project. A 4th
# project's own spelling is one more entry in a set below, not a new code
# path -- the parser only ever looks up the canonical key.
_FIELD_SYNONYMS: dict[str, frozenset[str]] = {
    "DECIDED": frozenset({"decided", "decision", "chose"}),
    "REJECTED": frozenset({"rejected", "over", "alternatives considered"}),
    "WHY": frozenset({"why", "because", "rationale"}),
    "COST": frozenset({"cost", "tradeoff"}),
}
_LABEL_TO_CANON: dict[str, str] = {
    synonym: canon for canon, synonyms in _FIELD_SYNONYMS.items() for synonym in synonyms
}

# Two real field-writing styles: plain ("Chose:      One trace per run.") and
# bold-markdown ("**Decided:** ..."), the latter's body running until the
# next bold field, a "---" separator, or end of block.
_BOLD_FIELD = re.compile(
    r"^\*\*(?P<label>[^*:]+):\*\*(?P<body>.*?)(?=\n\*\*[^*:]+:\*\*|\n-{3,}\s*(?:\n|\Z)|\Z)",
    re.DOTALL | re.MULTILINE,
)
_PLAIN_FIELD = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ]*):\s*(?P<body>.*)$")


def _canonical_label(raw_label: str) -> str | None:
    return _LABEL_TO_CANON.get(raw_label.strip().lower())


def _match_header(line: str) -> tuple[_HeaderPattern, str, str] | None:
    """Try every known header shape against one line, in registry order.
    A line matching none of them (a section header like "## Security &
    Privacy" that merely groups real entries underneath it, say) is never
    forced into the decision-entry structure -- it's just not a boundary."""
    for pattern in _HEADER_PATTERNS:
        m = pattern.regex.match(line)
        if m:
            return pattern, m.group("id"), m.group("title").strip()
    return None


def _extract_fields(block_text: str) -> dict[str, str]:
    """Pull every recognized field out of one decision block, regardless of
    which real markdown style it's written in, normalized through the
    synonym map so callers only ever see the canonical key."""
    fields: dict[str, str] = {}
    for m in _BOLD_FIELD.finditer(block_text):
        canon = _canonical_label(m.group("label"))
        if canon:
            fields[canon] = m.group("body").strip()
    for line in block_text.splitlines():
        m = _PLAIN_FIELD.match(line)
        if m:
            canon = _canonical_label(m.group("label"))
            if canon:
                fields.setdefault(canon, m.group("body").strip())
    return fields


def _parse_decisions_md(text: str, source_file: str) -> list[BoundedContext]:
    lines = text.splitlines()
    headers: list[tuple[int, _HeaderPattern, str, str]] = []
    for idx, line in enumerate(lines):
        matched = _match_header(line)
        if matched:
            pattern, entry_id, title = matched
            headers.append((idx, pattern, entry_id, title))

    contexts: list[BoundedContext] = []
    for n, (start, pattern, entry_id, title) in enumerate(headers):
        end = headers[n + 1][0] if n + 1 < len(headers) else len(lines)
        block_text = "\n".join(lines[start + 1 : end])
        fields = _extract_fields(block_text)
        if "DECIDED" not in fields or "WHY" not in fields:
            # No clean decision to extract -- never force a fit.
            continue
        statement = f"{fields['DECIDED']} — because {fields['WHY']}"
        source_id = pattern.format_source_id(entry_id, title)
        contexts.append(
            BoundedContext(
                name=title,
                ubiquitous_language=_title_terms(title),
                invariants=[
                    Invariant(statement=statement, source_file=source_file, source_id=source_id)
                ],
            )
        )
    return contexts


def extract_decisions_md(root: Path) -> list[BoundedContext]:
    path = root / "DECISIONS.md"
    if not path.exists():
        return []
    return _parse_decisions_md(path.read_text(encoding="utf-8"), "DECISIONS.md")


# --- Source 2: knowledge/projects/youk/decisions.md (instance-local, optional) --

_ADR_HEADER = re.compile(r"^## (?P<id>ADR-\d+):\s*(?P<title>.+?)\s*$")
_ADR_FIELD = re.compile(
    r"\*\*(?P<label>[^*:]+):\*\*(?P<body>.*?)(?=\n\*\*[^*:]+:\*\*|\Z)", re.DOTALL
)


def _adr_blocks(text: str) -> list[tuple[str, str, str]]:
    """Split the ADR log into (adr_id, title, block_text) tuples, one per
    `## ADR-NNN: Title` header. Headers that don't match this exact shape
    (e.g. `## PENDING: ...`) are not ADRs and are skipped -- never forced
    into the ADR structure."""
    lines = text.splitlines()
    blocks: list[tuple[str, str, int]] = []
    for idx, line in enumerate(lines):
        m = _ADR_HEADER.match(line)
        if m:
            blocks.append((m.group("id"), m.group("title").strip(), idx))
    out: list[tuple[str, str, str]] = []
    for n, (adr_id, title, start) in enumerate(blocks):
        end = blocks[n + 1][2] if n + 1 < len(blocks) else len(lines)
        out.append((adr_id, title, "\n".join(lines[start + 1 : end])))
    return out


def _adr_fields(block_text: str) -> dict[str, str]:
    return {
        m.group("label").strip(): m.group("body").strip() for m in _ADR_FIELD.finditer(block_text)
    }


def _parse_adr_log(
    text: str, source_file: str
) -> tuple[list[BoundedContext], list[Invariant], list[Invariant]]:
    contexts: list[BoundedContext] = []
    non_goals: list[Invariant] = []
    boundaries: list[Invariant] = []

    for adr_id, title, block_text in _adr_blocks(text):
        fields = _adr_fields(block_text)
        decision = fields.get("Decision")
        if not decision:
            # No clean decision in this block (e.g. a status/pending entry
            # that happens to share the ADR-NNN header shape) -- skip it.
            continue
        why_label = next((label for label in fields if label.startswith("Why")), None)
        statement = decision.strip()
        if why_label:
            statement = f"{statement} — because {fields[why_label].strip()}"
        contexts.append(
            BoundedContext(
                name=title,
                ubiquitous_language=_title_terms(title),
                invariants=[
                    Invariant(statement=statement, source_file=source_file, source_id=adr_id)
                ],
            )
        )

        rejected = fields.get("Rejected alternatives")
        if rejected:
            for bullet in re.findall(r"^- (.+(?:\n  .+)*)", rejected, re.MULTILINE):
                non_goals.append(
                    Invariant(
                        statement=" ".join(bullet.split()),
                        source_file=source_file,
                        source_id=adr_id,
                    )
                )

        encodes = fields.get("Encodes")
        if encodes:
            boundaries.append(
                Invariant(
                    statement=" ".join(encodes.split()), source_file=source_file, source_id=adr_id
                )
            )

    return contexts, non_goals, boundaries


def extract_adr_log(root: Path) -> tuple[list[BoundedContext], list[Invariant], list[Invariant]]:
    path = root / "knowledge" / "projects" / "youk" / "decisions.md"
    if not path.exists():
        return [], [], []
    return _parse_adr_log(path.read_text(encoding="utf-8"), "knowledge/projects/youk/decisions.md")


# --- Build + persist ---------------------------------------------------------


def _format_recognized(present: bool, entries_parsed: int) -> bool | None:
    """Distinguishes "file absent" (None) from "file present but no known
    pattern matched it" (False) from "file present and parsed" (True). A
    caller that sees False knows a real file is sitting there unread -- the
    right moment to fall back to something else (e.g. the codebase-
    examination step in skills/nfr-check/SKILL.md) rather than silently
    treating it the same as "there was nothing to read."""
    if not present:
        return None
    return entries_parsed > 0


def build_domain_brief(root: Path, *, project: str = "youk") -> DomainBrief:
    decisions_path = root / "DECISIONS.md"
    adr_path = root / "knowledge" / "projects" / "youk" / "decisions.md"

    decisions_contexts = extract_decisions_md(root)
    adr_contexts, adr_non_goals, adr_boundaries = extract_adr_log(root)

    decisions_present = decisions_path.exists()
    adr_present = adr_path.exists()

    sources = [
        {
            "path": "DECISIONS.md",
            "present": decisions_present,
            "entries_parsed": len(decisions_contexts),
            "format_recognized": _format_recognized(decisions_present, len(decisions_contexts)),
        },
        {
            "path": "knowledge/projects/youk/decisions.md",
            "present": adr_present,
            "entries_parsed": len(adr_contexts),
            "format_recognized": _format_recognized(adr_present, len(adr_contexts)),
        },
    ]

    return DomainBrief(
        project=project,
        generated_at=datetime.now(UTC).isoformat(),
        sources=sources,
        bounded_contexts=decisions_contexts + adr_contexts,
        explicit_non_goals=adr_non_goals,
        known_boundaries=adr_boundaries,
    )


def write_domain_brief(root: Path, brief: DomainBrief) -> Path:
    path = domain_brief_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    _brief = build_domain_brief(REPO_ROOT)
    _path = write_domain_brief(REPO_ROOT, _brief)
    print(f"wrote {_path} ({len(_brief.bounded_contexts)} bounded contexts)")
