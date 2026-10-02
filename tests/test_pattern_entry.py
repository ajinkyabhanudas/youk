"""Tests for PatternEntry (Phase A of pattern-learning-architecture-design.md).

Governed by ADR-009: no Pydantic, raise-on-malformed, no coercion. These tests
prove each guardrail from the design doc actually RAISES on the real bad input
it exists to catch, not just that valid data passes:
  - a malformed global entry (missing/false abstracted on a provenance row)
  - a promotion attempt with only 1 confirmed project
  - construction with schema_version != "1.0"
  - Pydantic is not imported anywhere in the module
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pattern_entry import (
    PatternEntry,
    PatternValidationError,
    promote_pattern,
)

_MODULE_PATH = Path(__file__).parent.parent / "servers" / "shared" / "pattern_entry.py"


def _valid_kwargs(**overrides) -> dict:
    kwargs = dict(
        id="pat-1",
        scope="local",
        domain="testing",
        sub_domain="flaky-tests",
        statement="Retrying a flaky test without root-causing it hides a real bug.",
        evidence_level="asserted",
        provenance=[{"project": "youk", "abstracted": False}],
        status="candidate",
        created_at="2026-10-02T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return kwargs


# --- valid construction --------------------------------------------------


def test_valid_local_candidate_constructs():
    entry = PatternEntry(**_valid_kwargs())
    assert entry.scope == "local"
    assert entry.schema_version == "1.0"


def test_valid_global_entry_requires_abstracted_true():
    entry = PatternEntry(
        **_valid_kwargs(
            scope="global",
            status="promoted",
            provenance=[
                {"project": "youk", "abstracted": True},
                {"project": "other-project", "abstracted": True},
            ],
        )
    )
    assert entry.scope == "global"


# --- guardrail: no un-abstracted global entry ----------------------------


def test_global_scope_with_unabstracted_provenance_raises():
    with pytest.raises(PatternValidationError, match="abstracted"):
        PatternEntry(
            **_valid_kwargs(
                scope="global",
                status="promoted",
                provenance=[{"project": "youk", "abstracted": False}],
            )
        )


def test_global_scope_with_missing_abstracted_field_raises():
    with pytest.raises(PatternValidationError, match="abstracted"):
        PatternEntry(
            **_valid_kwargs(
                scope="global",
                status="promoted",
                provenance=[{"project": "youk"}],
            )
        )


# --- guardrail: enums must raise, never silently coerce ------------------


def test_invalid_scope_raises():
    with pytest.raises(PatternValidationError, match="scope"):
        PatternEntry(**_valid_kwargs(scope="galactic"))


def test_invalid_evidence_level_raises():
    with pytest.raises(PatternValidationError, match="evidence_level"):
        PatternEntry(**_valid_kwargs(evidence_level="vibes"))


def test_invalid_status_raises():
    with pytest.raises(PatternValidationError, match="status"):
        PatternEntry(**_valid_kwargs(status="vibing"))


# --- guardrail: schema_version pinned to 1.0 ------------------------------


def test_schema_version_mismatch_raises():
    with pytest.raises(PatternValidationError, match="schema_version"):
        PatternEntry(**_valid_kwargs(schema_version="2.0"))


# --- guardrail: promotion requires >=2 distinct confirmed projects --------


def test_promote_with_one_project_raises():
    entry = PatternEntry(
        **_valid_kwargs(
            scope="local",
            status="confirmed",
            provenance=[{"project": "youk", "abstracted": True}],
        )
    )
    with pytest.raises(PatternValidationError, match="2"):
        promote_pattern(entry, confirmed_in_projects={"youk"})


def test_promote_with_two_projects_succeeds():
    entry = PatternEntry(
        **_valid_kwargs(
            scope="local",
            status="confirmed",
            provenance=[
                {"project": "youk", "abstracted": True},
                {"project": "other-project", "abstracted": True},
            ],
        )
    )
    promoted = promote_pattern(entry, confirmed_in_projects={"youk", "other-project"})
    assert promoted.scope == "global"
    assert promoted.status == "promoted"
    assert promoted.confirmed_count == 2


def test_promote_result_still_enforces_abstraction_guardrail():
    """Promoting an entry whose provenance isn't abstracted must still raise --
    promotion cannot be used to smuggle an un-abstracted entry into global scope."""
    entry = PatternEntry(
        **_valid_kwargs(
            scope="local",
            status="confirmed",
            provenance=[
                {"project": "youk", "abstracted": False},
                {"project": "other-project", "abstracted": True},
            ],
        )
    )
    with pytest.raises(PatternValidationError, match="abstracted"):
        promote_pattern(entry, confirmed_in_projects={"youk", "other-project"})


# --- no coercion: wrong types RAISE, never silently convert ---------------


def test_no_coercion_on_wrong_type():
    with pytest.raises(PatternValidationError):
        PatternEntry(**_valid_kwargs(domain=123))


def test_confirmed_count_rejects_negative():
    with pytest.raises(PatternValidationError, match="confirmed_count"):
        PatternEntry(**_valid_kwargs(confirmed_count=-1))


def test_confirmed_count_rejects_bool():
    with pytest.raises(PatternValidationError, match="confirmed_count"):
        PatternEntry(**_valid_kwargs(confirmed_count=True))


# --- validated against the committed JSON Schema file too, not just the --
# --- dataclass's own checks -----------------------------------------------


def test_committed_json_schema_file_exists():
    schema_path = Path(__file__).parent.parent / "schemas" / "pattern-entry.schema.json"
    assert schema_path.exists()


def test_valid_entry_passes_json_schema_validation():
    """The dataclass's own __post_init__ re-validates against the committed
    schema file; a valid entry must not raise during that step."""
    PatternEntry(**_valid_kwargs())  # would raise if schema validation failed


# --- no Pydantic anywhere in the module -----------------------------------


def test_module_does_not_import_pydantic():
    """ADR-009 rejected Pydantic; the module docstring explains why by name,
    so check for an actual import, not any mention of the word."""
    source = _MODULE_PATH.read_text().lower()
    assert "import pydantic" not in source
    assert "from pydantic" not in source
