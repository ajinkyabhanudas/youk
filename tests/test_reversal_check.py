"""Tests for servers/core/src/reversal_check.py (Phase C of
pattern-learning-architecture-design.md -- see its "Phase C, precisely"
section).

Real scenario, not synthetic: this repo's own actual DECISIONS.md already
has a real entry -- "2026-08-27 [Langfuse trace granularity]", the same
fixture test_domain_edge_cases.py and test_disposition_event.py use -- that
chose "one trace per run" over "one trace per repair". These tests copy
that real file into a tmp_path (never the production file), log a real
dismissed DispositionEvent against that real bounded context, then add a
second, real-shaped decision entry that actually reverses it (chooses
per-repair granularity after all, citing a real-shaped incident reason) and
confirm detect_reversals finds that real pair -- and only that pair.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from disposition_event import append_disposition_event
from pattern_entry import PatternEntry, PatternValidationError
from reversal_check import (
    confirm_reversed_pattern,
    confirmed_patterns_path,
    detect_reversals,
    disposition_log_path,
    known_sources_path,
)

_PROJECT = "youk"
_REAL_DECISIONS_MD = (Path(__file__).parent.parent / "DECISIONS.md").read_text(encoding="utf-8")

_DISMISSED_BOUNDED_CONTEXT = "Langfuse trace granularity"
_DISMISSED_SOURCE_FILE = "DECISIONS.md"
_DISMISSED_SOURCE_ID = "2026-08-27 [Langfuse trace granularity]"
_DISMISSED_TASK = "Add a new Langfuse trace field to capture retry latency across repairs."

# A real-shaped reversing entry: a later incident proves the original
# "one trace per run" choice wrong, same markdown dialect as the real file.
_REVERSING_ENTRY = """

## 2026-10-03 [Langfuse trace granularity revisited]
Chose:      Per-repair trace granularity after all.
Over:       One trace per run.
Because:    A real incident showed aggregating cost/latency across a run masked
            which specific repair caused a cost spike; per-repair traces were
            required to debug it.
Cost:       Loses the single-run frame for normal aggregation; needs a join to
            see whole-run cost again.
"""

# An unrelated real-shaped entry -- a genuinely new source_id, but about a
# topic with zero vocabulary overlap with the dismissed candidate above.
_UNRELATED_ENTRY = """

## 2026-10-03 [Onboarding email palette]
Chose:      Use the brand neutral palette for onboarding emails.
Over:       A custom palette per campaign.
Because:    Consistency across every email matters more than per-campaign flair.
Cost:       Campaign designers lose some creative freedom.
"""


def _write_decisions_md(root: Path, extra: str = "") -> None:
    (root / "DECISIONS.md").write_text(_REAL_DECISIONS_MD + extra, encoding="utf-8")


def _log_dismissed_event(root: Path) -> dict:
    event = append_disposition_event(
        project=_PROJECT,
        task=_DISMISSED_TASK,
        bounded_context=_DISMISSED_BOUNDED_CONTEXT,
        source_file=_DISMISSED_SOURCE_FILE,
        source_id=_DISMISSED_SOURCE_ID,
        disposition="dismissed",
        log_path=disposition_log_path(root),
    )
    return event.to_dict()


# --- real non-match: nothing changed -----------------------------------


def test_detect_reversals_returns_empty_on_first_run_with_no_dismissals(tmp_path):
    """First run against a project with no disposition log at all: seeds
    the ledger, finds nothing -- never a forced match."""
    _write_decisions_md(tmp_path)

    reversals = detect_reversals(_PROJECT, tmp_path)

    assert reversals == []
    assert known_sources_path(tmp_path, _PROJECT).exists()


def test_detect_reversals_cold_start_does_not_self_match_the_dismissed_entry(tmp_path):
    """A dismissal gets logged BEFORE detect_reversals has ever run once for
    this project (the ledger is genuinely empty, not pre-seeded by a
    throwaway call) -- the dismissed event's own still-unchanged source
    entry is trivially "new" on this first real run and must never be
    reported as a reversal of itself."""
    _write_decisions_md(tmp_path)
    _log_dismissed_event(tmp_path)  # no detect_reversals call before this

    reversals = detect_reversals(_PROJECT, tmp_path)

    assert reversals == []


def test_detect_reversals_returns_empty_when_nothing_changed(tmp_path):
    """A real dismissed event exists, but no new Domain Brief entry has
    appeared since the ledger was last written -- [] is the correct answer,
    not a stale match against the same old entry."""
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)  # seed the ledger
    _log_dismissed_event(tmp_path)

    reversals = detect_reversals(_PROJECT, tmp_path)

    assert reversals == []


# --- real non-match: a new entry exists, but shares no vocabulary --------


def test_detect_reversals_returns_empty_when_new_entry_is_unrelated(tmp_path):
    """A genuinely NEW source_id appears (so the ledger diff is non-empty),
    and a real dismissed event exists for this project -- but the two share
    no bounded_context vocabulary. Must not be forced into a false match."""
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)  # seed the ledger
    _log_dismissed_event(tmp_path)

    _write_decisions_md(tmp_path, extra=_UNRELATED_ENTRY)
    reversals = detect_reversals(_PROJECT, tmp_path)

    assert reversals == []


# --- real match -----------------------------------------------------------


def test_detect_reversals_finds_the_real_reversal_pair(tmp_path):
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)  # seed the ledger with the original entry
    dismissed = _log_dismissed_event(tmp_path)

    _write_decisions_md(tmp_path, extra=_REVERSING_ENTRY)
    reversals = detect_reversals(_PROJECT, tmp_path)

    assert len(reversals) == 1
    pair = reversals[0]
    assert pair["dismissed_event"]["candidate_id"] == dismissed["candidate_id"]
    assert pair["dismissed_event"]["source_id"] == _DISMISSED_SOURCE_ID
    assert pair["new_invariant"]["source_id"] == "2026-10-03 [Langfuse trace granularity revisited]"
    assert pair["new_invariant"]["source_file"] == "DECISIONS.md"
    assert "Per-repair trace granularity after all" in pair["new_invariant"]["statement"]
    assert "langfuse" in pair["new_invariant"]["matched_terms"]
    assert "trace" in pair["new_invariant"]["matched_terms"]


def test_detect_reversals_updates_ledger_so_repeat_run_is_empty(tmp_path):
    """Once a reversal has been detected and the ledger updated, re-running
    with no further changes must not re-surface the same pair again."""
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)
    _log_dismissed_event(tmp_path)
    _write_decisions_md(tmp_path, extra=_REVERSING_ENTRY)

    first = detect_reversals(_PROJECT, tmp_path)
    second = detect_reversals(_PROJECT, tmp_path)

    assert len(first) == 1
    assert second == []


def test_detect_reversals_never_touches_production_pattern_library(tmp_path):
    """Phase C writes confirmed-patterns.jsonl, never
    state/verification-pattern-library.jsonl -- detect_reversals itself
    writes nothing but the ledger."""
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)

    assert not (tmp_path / "state" / "verification-pattern-library.jsonl").exists()
    assert not confirmed_patterns_path(tmp_path).exists()


# --- confirm_reversed_pattern ----------------------------------------------


def _real_reversal(tmp_path: Path) -> dict:
    _write_decisions_md(tmp_path)
    detect_reversals(_PROJECT, tmp_path)
    _log_dismissed_event(tmp_path)
    _write_decisions_md(tmp_path, extra=_REVERSING_ENTRY)
    reversals = detect_reversals(_PROJECT, tmp_path)
    assert len(reversals) == 1
    return reversals[0]


def test_confirm_reversed_pattern_builds_valid_entry_and_appends(tmp_path):
    reversal = _real_reversal(tmp_path)

    entry = confirm_reversed_pattern(
        reversal, domain="observability", sub_domain="tracing", root=tmp_path
    )

    assert isinstance(entry, PatternEntry)
    assert entry.scope == "local"
    assert entry.status == "confirmed"
    assert entry.evidence_level == "internally_checked"
    assert entry.domain == "observability"
    assert entry.sub_domain == "tracing"
    assert entry.confirmed_count == 1

    provenance_source_ids = {row["source_id"] for row in entry.provenance}
    assert _DISMISSED_SOURCE_ID in provenance_source_ids
    assert "2026-10-03 [Langfuse trace granularity revisited]" in provenance_source_ids
    assert all(row["abstracted"] is False for row in entry.provenance)

    path = confirmed_patterns_path(tmp_path)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["id"] == entry.id
    assert written["status"] == "confirmed"


def test_confirm_reversed_pattern_is_deterministic_for_the_same_real_pair(tmp_path):
    reversal = _real_reversal(tmp_path)

    first = confirm_reversed_pattern(reversal, domain="observability", sub_domain="tracing", root=tmp_path)
    second = confirm_reversed_pattern(reversal, domain="observability", sub_domain="tracing", root=tmp_path)

    assert first.id == second.id


def test_confirm_reversed_pattern_raises_on_bad_domain_via_pattern_entry_validation(tmp_path):
    """domain/sub_domain validity is enforced by PatternEntry's own
    __post_init__, not reimplemented here."""
    reversal = _real_reversal(tmp_path)

    with pytest.raises(PatternValidationError, match="domain"):
        confirm_reversed_pattern(reversal, domain="", sub_domain="tracing", root=tmp_path)

    assert not confirmed_patterns_path(tmp_path).exists()
