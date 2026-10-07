"""Tests for servers/core/src/domain_brief.py (CIR-162, Phase 1; CIR-168
generalized DECISIONS.md parsing across real dialects).

The DECISIONS.md tests run against the real, committed file in this repo --
not a mock -- so a passing test is proof the extractor works against actual
data. knowledge/projects/youk/decisions.md is instance-local and gitignored
(see .gitignore: "Instance-local knowledge -- personal intelligence, never
universally applicable"), so it is never present in this checkout or in CI;
its parser (_parse_adr_log) is instead exercised against a verbatim fixture
copied from the real file, so the parsing logic is still proven against
real ADR text rather than an invented shape.

CIR-168's cross-project tests below read two OTHER real, existing projects'
real DECISIONS.md files directly from their real, absolute location on this
machine -- never copied into this repo -- the same real-data discipline as
the in-repo test above, extended across projects. They are skipped (not
failed) on a machine/CI where those paths don't exist, same resilience
discipline as the instance-local ADR log test below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain_brief import (
    REPO_ROOT,
    build_domain_brief,
    extract_adr_log,
    extract_decisions_md,
    _parse_adr_log,
    _parse_decisions_md,
)

# Real, existing projects used to prove DECISIONS.md parsing generalizes
# beyond youk's own dialect (CIR-168) -- read-only, at their real location.
_CIRCAID_DECISIONS = Path("/Users/ajinkya/Desktop/circaid/DECISIONS.md")
_CANOPY_DECISIONS = Path("/Users/ajinkya/Desktop/Jocotoco/canopy/DECISIONS.md")

# Verbatim excerpt of knowledge/projects/youk/decisions.md (ADR-001, ADR-002's
# PENDING-shaped rejected alternative removed for brevity, and the PENDING
# section) -- copied exactly from the real, instance-local file so the ADR
# parser is tested against real decision text, not synthetic data.
_REAL_ADR_EXCERPT = """\
## ADR-001: MCP + Docker stdio transport (not network sockets)

**Date:** 2026-06-28 (session 1–5)
**Status:** Active

**Decision:** Two Docker containers (youk-core, youk-code) communicate with Claude Code
via stdio MCP transport. No network sockets, no port binding.

**Rejected alternatives:**
- Network socket MCP: port conflicts with developer tooling; connection-level failures
  add a reliability failure mode; requires firewall rules
- Direct Python import (no Docker): no isolation; youk code runs in Claude's process
  space; a crash kills the session
- Single container: youk-core needs `~/.claude` write access; youk-code is intentionally
  read-only. Two containers enforce the access boundary at the OS level, not just in code

**Why stdio:** Zero connection management. Claude Code opens the process; stdin/stdout
is the channel; process exit is the disconnect. No keepalive, no retry, no port.

**Encodes:** `well-architected.md` Security pillar — write access scoped at volume level.

---

## PENDING: Autonomy completeness — remaining 6 items (as of session 36)

**Date:** 2026-07-05 (session 36)
**Status:** In progress — full context in memory/youk-vision.md

One item complete: apply_proposal safe_types gate (health.py, 5 tests, session 36).

---
"""


def test_extract_decisions_md_against_real_file():
    """Real test against the actual committed DECISIONS.md -- not a mock."""
    contexts = extract_decisions_md(REPO_ROOT)

    assert len(contexts) == 4
    names = {c.name for c in contexts}
    assert names == {
        "Langfuse trace granularity",
        "Langfuse data handling",
        "Proxy score definition",
        "G1 baseline battery: no measured benefit from full over bare",
    }

    by_name = {c.name: c for c in contexts}
    trace = by_name["Langfuse trace granularity"]
    assert len(trace.invariants) == 1
    inv = trace.invariants[0]
    assert inv.source_file == "DECISIONS.md"
    assert inv.source_id == "2026-08-27 [Langfuse trace granularity]"
    assert "One trace per run" in inv.statement
    assert "atomic unit of user value" in inv.statement

    proxy = by_name["Proxy score definition"]
    assert "patch_cycle_rate" in proxy.invariants[0].statement


def test_decisions_md_ubiquitous_language_from_real_title():
    contexts = extract_decisions_md(REPO_ROOT)
    by_name = {c.name: c for c in contexts}
    assert by_name["Langfuse data handling"].ubiquitous_language == ["Langfuse", "data", "handling"]


def test_decisions_md_skips_entries_without_clean_fields():
    """Never fabricate: an entry missing Chose/Because is left out entirely."""
    text = """\
## 2026-09-01  [Incomplete entry]
Over:       Something else.
Cost:       Unclear.
"""
    assert _parse_decisions_md(text, "DECISIONS.md") == []


def test_adr_log_extracts_real_decision_rejected_and_encodes():
    contexts, non_goals, boundaries = _parse_adr_log(
        _REAL_ADR_EXCERPT, "knowledge/projects/youk/decisions.md"
    )

    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.name == "MCP + Docker stdio transport (not network sockets)"
    inv = ctx.invariants[0]
    assert inv.source_id == "ADR-001"
    assert "Two Docker containers" in inv.statement
    assert "because Zero connection management" in inv.statement

    assert len(non_goals) == 3
    assert all(n.source_id == "ADR-001" for n in non_goals)
    assert any("Network socket MCP" in n.statement for n in non_goals)
    assert any("Single container" in n.statement for n in non_goals)

    assert len(boundaries) == 1
    assert boundaries[0].source_id == "ADR-001"
    assert "well-architected.md" in boundaries[0].statement


def test_adr_log_skips_non_adr_pending_section():
    """`## PENDING: ...` does not match the `## ADR-NNN:` header shape --
    never forced into the ADR structure."""
    contexts, non_goals, boundaries = _parse_adr_log(
        _REAL_ADR_EXCERPT, "knowledge/projects/youk/decisions.md"
    )
    assert all("Autonomy completeness" not in c.name for c in contexts)


def test_extract_adr_log_handles_either_real_environment():
    """knowledge/projects/youk/decisions.md is gitignored instance-local
    state: absent in a fresh checkout or CI, genuinely present on a real
    working machine that has accumulated real ADRs. Both are real
    environments this must handle correctly -- hardcoding either one as
    "the" state is itself a fabrication. Absence must be handled, not
    forced; presence must parse real content, not fabricate it either."""
    adr_path = REPO_ROOT / "knowledge" / "projects" / "youk" / "decisions.md"
    contexts, non_goals, boundaries = extract_adr_log(REPO_ROOT)
    if not adr_path.exists():
        assert (contexts, non_goals, boundaries) == ([], [], [])
    else:
        # Present on this real machine -- must reflect real content, not
        # assert a fixed count (the file grows across real sessions).
        assert all(c.name for c in contexts)
        assert all(inv.source_file == "knowledge/projects/youk/decisions.md" for c in contexts for inv in c.invariants)


def test_build_domain_brief_reports_real_sources_honestly():
    brief = build_domain_brief(REPO_ROOT)

    by_path = {s["path"]: s for s in brief.sources}
    assert by_path["DECISIONS.md"]["present"] is True
    assert by_path["DECISIONS.md"]["entries_parsed"] == 4
    assert by_path["knowledge/projects/youk/decisions.md"]["present"] == (
        (REPO_ROOT / "knowledge" / "projects" / "youk" / "decisions.md").exists()
    )

    assert len(brief.bounded_contexts) >= 3
    assert brief.project == "youk"


def test_domain_brief_to_dict_round_trips_nested_dataclasses():
    brief = build_domain_brief(REPO_ROOT)
    d = brief.to_dict()
    assert isinstance(d["bounded_contexts"], list)
    assert isinstance(d["bounded_contexts"][0]["invariants"][0]["statement"], str)


# --- CIR-168: generalized parsing against real external dialects -----------


@pytest.mark.skipif(
    not _CIRCAID_DECISIONS.exists(), reason="circaid repo not present on this machine"
)
def test_extract_decisions_md_against_real_circaid_file():
    """circaid's real DECISIONS.md: `## ADR-Cxxx — Title` headers, bold-
    markdown `**Decided:**`/`**Rejected:**`/`**Why:**` fields -- a different
    dialect from youk's own dated-bracket/plain-field DECISIONS.md."""
    text = _CIRCAID_DECISIONS.read_text(encoding="utf-8")
    contexts = _parse_decisions_md(text, "DECISIONS.md")

    assert len(contexts) > 0
    by_name = {c.name: c for c in contexts}
    assert "Client scope is a path level above session slug" in by_name

    ctx = by_name["Client scope is a path level above session slug"]
    assert len(ctx.invariants) == 1
    inv = ctx.invariants[0]
    assert inv.source_file == "DECISIONS.md"
    assert inv.source_id == "ADR-C002"
    # Real content pulled from circaid's own **Decided:** / **Why:** fields.
    assert "state_paths.py" in inv.statement
    assert "task-graph.db" in inv.statement
    assert "dangerous to retrofit" in inv.statement


@pytest.mark.skipif(
    not _CANOPY_DECISIONS.exists(), reason="canopy repo not present on this machine"
)
def test_extract_decisions_md_against_real_canopy_file():
    """canopy's real DECISIONS.md: `### Sx — Title` headers nested under a
    `## Security & Privacy`-style section header (which must NOT itself be
    treated as a decision entry), bold-markdown `**Decision:**` (singular,
    a different synonym than circaid's `**Decided:**`) / `**Why:**` /
    `**Alternatives considered:**` (a different synonym than circaid's
    `**Rejected:**`) fields."""
    text = _CANOPY_DECISIONS.read_text(encoding="utf-8")
    contexts = _parse_decisions_md(text, "DECISIONS.md")

    assert len(contexts) > 0
    by_name = {c.name: c for c in contexts}
    assert "Architecture boundary" in by_name
    # The grouping section header above it must never become a fake entry.
    assert "Security & Privacy" not in by_name

    ctx = by_name["Architecture boundary"]
    assert len(ctx.invariants) == 1
    inv = ctx.invariants[0]
    assert inv.source_file == "DECISIONS.md"
    assert inv.source_id == "S1"
    # Real content pulled from canopy's own **Decision:** / **Why:** fields.
    assert "direct database access" in inv.statement
    assert "OWASP" in inv.statement


def test_decisions_md_recognizes_adr_dash_header_shape():
    """A minimal, synthetic circaid-shaped entry proves the `adr-dash`
    _HeaderPattern in isolation, independent of the real-file tests above
    (which prove it against actual production text)."""
    text = """\
## ADR-C099 — Example synthetic decision for header-shape coverage

**Decided:** Use approach X.

**Rejected:**
- Approach Y — too slow.

**Why:** X is faster and simpler.
"""
    contexts = _parse_decisions_md(text, "DECISIONS.md")
    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.name == "Example synthetic decision for header-shape coverage"
    assert ctx.invariants[0].source_id == "ADR-C099"
    assert "Use approach X" in ctx.invariants[0].statement
    assert "X is faster and simpler" in ctx.invariants[0].statement


def test_decisions_md_recognizes_section_id_dash_header_shape():
    """A minimal, synthetic canopy-shaped entry proves the
    `section-id-dash` _HeaderPattern in isolation, and that a non-matching
    `##` section header above it is correctly ignored rather than forced
    into an entry."""
    text = """\
## Security & Privacy

### S9 — Example synthetic decision for header-shape coverage

**Decision:** Use approach X.

**Why:** X is faster and simpler.

**Alternatives considered:** Approach Y, rejected as too slow.
"""
    contexts = _parse_decisions_md(text, "DECISIONS.md")
    names = {c.name for c in contexts}
    assert "Security & Privacy" not in names
    assert "Example synthetic decision for header-shape coverage" in names
    ctx = next(c for c in contexts if c.name == "Example synthetic decision for header-shape coverage")
    assert ctx.invariants[0].source_id == "S9"
    assert "Use approach X" in ctx.invariants[0].statement
    assert "X is faster and simpler" in ctx.invariants[0].statement


def test_sources_format_recognized_distinguishes_absent_from_unrecognized(tmp_path):
    """CIR-168 item 2: `sources[].format_recognized` must tell "no file
    there" (None) apart from "a real file is there and nothing matched it"
    (False) -- today's `present`/`entries_parsed` pair alone can't."""
    # Case 1: no DECISIONS.md at all.
    brief_absent = build_domain_brief(tmp_path, project="absent-case")
    by_path = {s["path"]: s for s in brief_absent.sources}
    decisions_source = by_path["DECISIONS.md"]
    assert decisions_source["present"] is False
    assert decisions_source["entries_parsed"] == 0
    assert decisions_source["format_recognized"] is None

    # Case 2: DECISIONS.md exists but matches none of the known header shapes.
    (tmp_path / "DECISIONS.md").write_text(
        "# Decision log\n\nJust some prose with no recognized heading shape at all.\n",
        encoding="utf-8",
    )
    brief_unrecognized = build_domain_brief(tmp_path, project="unrecognized-case")
    by_path = {s["path"]: s for s in brief_unrecognized.sources}
    decisions_source = by_path["DECISIONS.md"]
    assert decisions_source["present"] is True
    assert decisions_source["entries_parsed"] == 0
    assert decisions_source["format_recognized"] is False

    # Case 3 (regression guard): a real, recognized file still reports True.
    brief_real = build_domain_brief(REPO_ROOT)
    by_path = {s["path"]: s for s in brief_real.sources}
    assert by_path["DECISIONS.md"]["format_recognized"] is True
