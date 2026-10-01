"""
Domain Brief: structured per-project domain model (CIR-162, Phase 1 of 4).

Phase 1 only: schema + a real extractor that populates it from this
project's own real decision records. Edge-case elicitation (Phase 2) and
bias-resistant review (Phase 3) are not built here -- see
state/problem-space-modeling/design.md for the full phased design and why
they are deliberately sequenced after this one is proven against real data.

Two real sources, two different formats:
  - DECISIONS.md (repo root, committed): dated, bracketed-title entries with
    Chose/Over/Because/Cost fields.
  - knowledge/projects/youk/decisions.md (instance-local, gitignored --
    "personal intelligence, never universally applicable" per .gitignore):
    numbered ADR-NNN entries with Decision/Rejected alternatives/Encodes
    fields. Not present in every checkout (CI included) -- the extractor
    treats its absence as a normal, reportable condition, not an error.

Never-backfill discipline (same as verification_contract.py's events.jsonl):
an entry that doesn't cleanly match its source's expected structure is
skipped, not forced into a bounded_context/invariant shape. A missing
source contributes zero entries rather than a fabricated one.
"""

from __future__ import annotations

import json
import re
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

_DECISIONS_MD_HEADER = re.compile(r"^## (?P<date>\d{4}-\d{2}-\d{2})\s+\[(?P<title>[^\]]+)\]\s*$")
_DECISIONS_MD_FIELD = re.compile(r"^(Chose|Over|Because|Cost):\s*(.*)$")


def _parse_decisions_md(text: str, source_file: str) -> list[BoundedContext]:
    contexts: list[BoundedContext] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _DECISIONS_MD_HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        title = m.group("title").strip()
        date = m.group("date")
        fields: dict[str, str] = {}
        i += 1
        while (
            i < len(lines)
            and not _DECISIONS_MD_HEADER.match(lines[i])
            and not lines[i].startswith("# ")
        ):
            fm = _DECISIONS_MD_FIELD.match(lines[i])
            if fm:
                fields[fm.group(1)] = fm.group(2).strip()
            i += 1
        if "Chose" not in fields or "Because" not in fields:
            # No clean decision to extract -- never force a fit.
            continue
        statement = f"{fields['Chose']} — because {fields['Because']}"
        source_id = f"{date} [{title}]"
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


def build_domain_brief(root: Path, *, project: str = "youk") -> DomainBrief:
    decisions_path = root / "DECISIONS.md"
    adr_path = root / "knowledge" / "projects" / "youk" / "decisions.md"

    decisions_contexts = extract_decisions_md(root)
    adr_contexts, adr_non_goals, adr_boundaries = extract_adr_log(root)

    sources = [
        {
            "path": "DECISIONS.md",
            "present": decisions_path.exists(),
            "entries_parsed": len(decisions_contexts),
        },
        {
            "path": "knowledge/projects/youk/decisions.md",
            "present": adr_path.exists(),
            "entries_parsed": len(adr_contexts),
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
