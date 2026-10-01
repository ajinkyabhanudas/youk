"""Tests for servers/core/src/domain_brief.py (CIR-162, Phase 1).

The DECISIONS.md tests run against the real, committed file in this repo --
not a mock -- so a passing test is proof the extractor works against actual
data. knowledge/projects/youk/decisions.md is instance-local and gitignored
(see .gitignore: "Instance-local knowledge -- personal intelligence, never
universally applicable"), so it is never present in this checkout or in CI;
its parser (_parse_adr_log) is instead exercised against a verbatim fixture
copied from the real file, so the parsing logic is still proven against
real ADR text rather than an invented shape.
"""

from __future__ import annotations


from domain_brief import (
    REPO_ROOT,
    build_domain_brief,
    extract_adr_log,
    extract_decisions_md,
    _parse_adr_log,
    _parse_decisions_md,
)

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

    assert len(contexts) == 3
    names = {c.name for c in contexts}
    assert names == {
        "Langfuse trace granularity",
        "Langfuse data handling",
        "Proxy score definition",
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
    assert by_path["DECISIONS.md"]["entries_parsed"] == 3
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
