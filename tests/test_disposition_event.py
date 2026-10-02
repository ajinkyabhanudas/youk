"""Tests for DispositionEvent (Phase B of pattern-learning-architecture-design.md).

Governed by ADR-009: no Pydantic, raise-on-malformed, no coercion -- same
discipline as test_pattern_entry.py (Phase A). These tests prove:
  - a real candidate (the actual Langfuse trace fixture from
    test_domain_edge_cases.py) logged with each of the three real
    disposition values produces exactly those lines, on disk, in a real
    (tmp_path-scoped) disposition log -- read back after writing, not mocked.
  - candidate_id is deterministic: the same (project, bounded_context,
    source_id, task) always produces the same id, and changing any one of
    the four changes it.
  - a malformed disposition value raises, as does a missing/empty required
    field.
"""
from __future__ import annotations

import json

import pytest

from disposition_event import (
    DispositionEvent,
    DispositionValidationError,
    append_disposition_event,
    compute_candidate_id,
)

# The real Langfuse trace candidate from domain_brief's own DECISIONS.md-derived
# fixture (test_domain_edge_cases.py), not a synthetic example.
_PROJECT = "youk"
_TASK = "Add a new Langfuse trace field to capture retry latency across repairs."
_BOUNDED_CONTEXT = "Langfuse trace granularity"
_SOURCE_FILE = "DECISIONS.md"
_SOURCE_ID = "2026-08-27 [Langfuse trace granularity]"


def _valid_kwargs(**overrides) -> dict:
    kwargs = dict(
        candidate_id="cid-1",
        project=_PROJECT,
        task=_TASK,
        bounded_context=_BOUNDED_CONTEXT,
        source_file=_SOURCE_FILE,
        source_id=_SOURCE_ID,
        disposition="accepted",
        timestamp="2026-10-02T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return kwargs


# --- valid construction --------------------------------------------------


def test_valid_event_constructs():
    event = DispositionEvent(**_valid_kwargs())
    assert event.disposition == "accepted"


@pytest.mark.parametrize("disposition", ["accepted", "dismissed", "ignored"])
def test_all_three_real_disposition_values_construct(disposition):
    event = DispositionEvent(**_valid_kwargs(disposition=disposition))
    assert event.disposition == disposition


# --- guardrail: malformed disposition raises ------------------------------


def test_malformed_disposition_raises():
    with pytest.raises(DispositionValidationError, match="disposition"):
        DispositionEvent(**_valid_kwargs(disposition="maybe"))


# --- guardrail: missing/empty required field raises ------------------------


def test_missing_bounded_context_raises():
    with pytest.raises(DispositionValidationError, match="bounded_context"):
        DispositionEvent(**_valid_kwargs(bounded_context=""))


def test_wrong_type_raises():
    with pytest.raises(DispositionValidationError, match="project"):
        DispositionEvent(**_valid_kwargs(project=123))


# --- no Pydantic -----------------------------------------------------------


def test_module_does_not_import_pydantic():
    import ast

    import disposition_event

    with open(disposition_event.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported_names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "pydantic" not in imported_names


# --- deterministic candidate_id --------------------------------------------


def test_candidate_id_is_deterministic():
    id_1 = compute_candidate_id(_PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK)
    id_2 = compute_candidate_id(_PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK)
    assert id_1 == id_2


def test_candidate_id_is_not_a_random_uuid():
    import uuid

    cid = compute_candidate_id(_PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK)
    with pytest.raises(ValueError):
        uuid.UUID(cid)


@pytest.mark.parametrize(
    "changed_field",
    ["project", "bounded_context", "source_id", "task"],
)
def test_candidate_id_changes_when_any_input_changes(changed_field):
    base = compute_candidate_id(_PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK)
    kwargs = {
        "project": _PROJECT,
        "bounded_context": _BOUNDED_CONTEXT,
        "source_id": _SOURCE_ID,
        "task": _TASK,
    }
    kwargs[changed_field] = kwargs[changed_field] + "-different"
    changed = compute_candidate_id(**kwargs)
    assert changed != base


# --- real append + read-back, tmp_path-scoped ------------------------------


def test_append_disposition_event_writes_real_line_and_reads_back(tmp_path):
    log_path = tmp_path / "disposition-log.jsonl"

    event = append_disposition_event(
        project=_PROJECT,
        task=_TASK,
        bounded_context=_BOUNDED_CONTEXT,
        source_file=_SOURCE_FILE,
        source_id=_SOURCE_ID,
        disposition="accepted",
        log_path=log_path,
    )

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    written = json.loads(lines[0])
    expected_candidate_id = compute_candidate_id(
        _PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK
    )
    assert written["candidate_id"] == expected_candidate_id
    assert event.candidate_id == expected_candidate_id
    assert written["project"] == _PROJECT
    assert written["task"] == _TASK
    assert written["bounded_context"] == _BOUNDED_CONTEXT
    assert written["source_file"] == _SOURCE_FILE
    assert written["source_id"] == _SOURCE_ID
    assert written["disposition"] == "accepted"
    assert "timestamp" in written


def test_logging_all_three_dispositions_for_the_same_candidate_produces_three_real_lines(
    tmp_path,
):
    """The same real candidate reviewed three separate times (once per
    disposition value) must produce three distinct, correctly-ordered real
    lines -- same candidate_id each time (it is derived from the candidate's
    identity, not the disposition), all on disk, read back for real."""
    log_path = tmp_path / "disposition-log.jsonl"
    expected_candidate_id = compute_candidate_id(
        _PROJECT, _BOUNDED_CONTEXT, _SOURCE_ID, _TASK
    )

    for disposition in ["accepted", "dismissed", "ignored"]:
        append_disposition_event(
            project=_PROJECT,
            task=_TASK,
            bounded_context=_BOUNDED_CONTEXT,
            source_file=_SOURCE_FILE,
            source_id=_SOURCE_ID,
            disposition=disposition,
            log_path=log_path,
        )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    rows = [json.loads(line) for line in lines]
    assert [r["disposition"] for r in rows] == ["accepted", "dismissed", "ignored"]
    for row in rows:
        assert row["candidate_id"] == expected_candidate_id


def test_append_disposition_event_raises_before_writing_on_malformed_disposition(tmp_path):
    log_path = tmp_path / "disposition-log.jsonl"

    with pytest.raises(DispositionValidationError):
        append_disposition_event(
            project=_PROJECT,
            task=_TASK,
            bounded_context=_BOUNDED_CONTEXT,
            source_file=_SOURCE_FILE,
            source_id=_SOURCE_ID,
            disposition="maybe",
            log_path=log_path,
        )

    assert not log_path.exists()
