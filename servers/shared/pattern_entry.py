"""PatternEntry: the one schema serving all three pattern-learning lifecycle
points (local Domain Brief candidate, confirmed reactive-pattern-library hit,
promoted cross-project global pattern). Phase A of
docs/pattern-learning-architecture-design.md -- read that document first; this
module implements only its "Schema" section plus the promotion guardrail.

Governed by ADR-009, same as state_schema.py: a stdlib dataclass with
__post_init__ validation that RAISES on malformed input, never coerces.
No Pydantic -- ADR-009 rejected it specifically because its default coercion
silently accepts a malformed value instead of raising, and that failure mode
is exactly what this module exists to close off.

The dataclass's own checks run first (cheap, dependency-free). The instance
is then independently re-validated against the committed JSON Schema file
(schemas/pattern-entry.schema.json) via the `jsonschema` package, so the
schema file -- the portable, language-neutral contract a future non-Python
consumer validates against -- can never silently drift from what this
dataclass actually enforces.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "pattern-entry.schema.json"

_VALID_SCOPES = frozenset({"local", "global"})
_VALID_EVIDENCE_LEVELS = frozenset({"asserted", "internally_checked", "externally_verified"})
_VALID_STATUSES = frozenset({"candidate", "confirmed", "promoted", "retired"})
_SCHEMA_VERSION = "1.0"


class PatternValidationError(ValueError):
    """Raised when a PatternEntry fails validation, on construction or promotion.

    Subclass of ValueError (same precedent as state_schema.StateValidationError)
    so existing broad `except ValueError` handlers still catch it, while callers
    that care can catch this specifically.
    """


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _require_str(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise PatternValidationError(f"{field_name} must be str, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise PatternValidationError(f"{field_name} must be a non-empty string")
    return value


def _require_enum(value: Any, field_name: str, valid: frozenset) -> str:
    if value not in valid:
        raise PatternValidationError(
            f"{field_name} must be one of {sorted(valid)}, got {value!r}"
        )
    return value


@dataclass
class PatternEntry:
    """schemas/pattern-entry.schema.json, enforced. See module docstring."""

    id: str
    scope: str
    domain: str
    sub_domain: str
    statement: str
    evidence_level: str
    provenance: list[dict]
    status: str
    created_at: str
    schema_version: str = _SCHEMA_VERSION
    constraint_set: list[str] = field(default_factory=list)
    confirmed_count: int = 0
    updated_at: str = ""
    related_pattern_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise PatternValidationError(
                f"schema_version must be {_SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        _require_str(self.id, "id", allow_empty=False)
        _require_enum(self.scope, "scope", _VALID_SCOPES)
        _require_str(self.domain, "domain", allow_empty=False)
        _require_str(self.sub_domain, "sub_domain", allow_empty=False)
        _require_str(self.statement, "statement", allow_empty=False)
        _require_enum(self.evidence_level, "evidence_level", _VALID_EVIDENCE_LEVELS)
        _require_enum(self.status, "status", _VALID_STATUSES)
        _require_str(self.created_at, "created_at", allow_empty=False)

        if not isinstance(self.provenance, list) or not all(
            isinstance(p, dict) for p in self.provenance
        ):
            raise PatternValidationError("provenance must be a list of objects")
        for i, row in enumerate(self.provenance):
            if "project" not in row or "abstracted" not in row:
                raise PatternValidationError(
                    f"provenance[{i}] missing required field(s): "
                    f"needs 'project' and 'abstracted'"
                )
            if not isinstance(row["abstracted"], bool):
                raise PatternValidationError(
                    f"provenance[{i}].abstracted must be bool, got "
                    f"{type(row['abstracted']).__name__}"
                )

        if self.scope == "global":
            unabstracted = [i for i, row in enumerate(self.provenance) if not row["abstracted"]]
            if unabstracted:
                raise PatternValidationError(
                    f"scope=global requires abstracted=true on every provenance row; "
                    f"row(s) {unabstracted} are not abstracted"
                )

        if not isinstance(self.constraint_set, list) or not all(
            isinstance(c, str) for c in self.constraint_set
        ):
            raise PatternValidationError("constraint_set must be a list of str")

        if not isinstance(self.related_pattern_ids, list) or not all(
            isinstance(p, str) for p in self.related_pattern_ids
        ):
            raise PatternValidationError("related_pattern_ids must be a list of str")

        if not isinstance(self.confirmed_count, int) or isinstance(self.confirmed_count, bool):
            raise PatternValidationError("confirmed_count must be an int")
        if self.confirmed_count < 0:
            raise PatternValidationError("confirmed_count must be >= 0")

        self._validate_against_json_schema()

    def _validate_against_json_schema(self) -> None:
        try:
            jsonschema.validate(instance=self.to_dict(), schema=_load_schema())
        except jsonschema.exceptions.ValidationError as e:
            raise PatternValidationError(f"failed committed JSON Schema validation: {e.message}") from e

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "schema_version": self.schema_version,
            "scope": self.scope,
            "domain": self.domain,
            "sub_domain": self.sub_domain,
            "constraint_set": self.constraint_set,
            "statement": self.statement,
            "evidence_level": self.evidence_level,
            "provenance": self.provenance,
            "confirmed_count": self.confirmed_count,
            "status": self.status,
            "created_at": self.created_at,
            "related_pattern_ids": self.related_pattern_ids,
        }
        if self.updated_at:
            d["updated_at"] = self.updated_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PatternEntry:
        if not isinstance(d, dict):
            raise PatternValidationError("pattern entry must be a JSON object")
        return cls(
            id=d.get("id", ""),
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            scope=d.get("scope", ""),
            domain=d.get("domain", ""),
            sub_domain=d.get("sub_domain", ""),
            constraint_set=d.get("constraint_set", []),
            statement=d.get("statement", ""),
            evidence_level=d.get("evidence_level", ""),
            provenance=d.get("provenance", []),
            confirmed_count=d.get("confirmed_count", 0),
            status=d.get("status", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            related_pattern_ids=d.get("related_pattern_ids", []),
        )


def promote_pattern(entry: PatternEntry, confirmed_in_projects: set[str]) -> PatternEntry:
    """Enforce the design doc's >=2-distinct-project promotion guardrail.

    Phases B-D wire real confirmed-project data into `confirmed_in_projects`;
    this function only enforces the guardrail and returns the promoted entry.
    Raises PatternValidationError if fewer than 2 distinct projects confirmed
    the pattern, or if the resulting global-scope entry has any
    un-abstracted provenance row (surfaced via the dataclass's own
    __post_init__ validation on the replacement instance).
    """
    if len(confirmed_in_projects) < 2:
        raise PatternValidationError(
            f"promotion requires >=2 distinct confirmed projects, got "
            f"{len(confirmed_in_projects)}: {sorted(confirmed_in_projects)}"
        )
    return replace(
        entry,
        scope="global",
        status="promoted",
        confirmed_count=len(confirmed_in_projects),
        updated_at=datetime.now(UTC).isoformat(),
    )
