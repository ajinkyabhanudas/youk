"""DispositionEvent: a deliberately separate, lighter schema from PatternEntry.

Phase B of docs/pattern-learning-architecture-design.md -- read that
document's "DispositionEvent -- a deliberately separate, lighter schema"
subsection first; this module implements only that subsection. A
DispositionEvent is NOT a PatternEntry: it is the raw material logged every
time a Domain Brief candidate gets shown and reacted to (accepted /
dismissed / ignored), before any of PatternEntry's confirmed-by-reversal or
promoted-across-projects bar has been cleared. Forcing it into PatternEntry's
shape would mean inventing fake domain/sub_domain/evidence_level/provenance
values for something that, at the moment it's logged, is just "a thing got
shown and something reacted to it."

Governed by ADR-009, same discipline as pattern_entry.py and state_schema.py:
a stdlib dataclass with __post_init__ validation that RAISES on malformed
input, never coerces. No Pydantic.

Storage: state/disposition-log.jsonl, append-only, one real event per line,
never backfilled -- same precedent as every other JSONL file in this
initiative (events.jsonl, the pattern-library itself).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "disposition-event.schema.json"
_DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "state" / "disposition-log.jsonl"

_VALID_DISPOSITIONS = frozenset({"accepted", "dismissed", "ignored"})


class DispositionValidationError(ValueError):
    """Raised when a DispositionEvent fails validation, on construction.

    Subclass of ValueError (same precedent as PatternValidationError /
    StateValidationError) so existing broad `except ValueError` handlers
    still catch it, while callers that care can catch this specifically.
    """


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise DispositionValidationError(f"{field_name} must be str, got {type(value).__name__}")
    if not value.strip():
        raise DispositionValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass
class DispositionEvent:
    """schemas/disposition-event.schema.json, enforced. See module docstring."""

    candidate_id: str
    project: str
    task: str
    bounded_context: str
    source_file: str
    source_id: str
    disposition: str
    timestamp: str

    def __post_init__(self) -> None:
        _require_str(self.candidate_id, "candidate_id")
        _require_str(self.project, "project")
        _require_str(self.task, "task")
        _require_str(self.bounded_context, "bounded_context")
        _require_str(self.source_file, "source_file")
        _require_str(self.source_id, "source_id")
        if self.disposition not in _VALID_DISPOSITIONS:
            raise DispositionValidationError(
                f"disposition must be one of {sorted(_VALID_DISPOSITIONS)}, got {self.disposition!r}"
            )
        _require_str(self.timestamp, "timestamp")
        self._validate_against_json_schema()

    def _validate_against_json_schema(self) -> None:
        try:
            jsonschema.validate(instance=self.to_dict(), schema=_load_schema())
        except jsonschema.exceptions.ValidationError as e:
            raise DispositionValidationError(f"failed committed JSON Schema validation: {e.message}") from e

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "project": self.project,
            "task": self.task,
            "bounded_context": self.bounded_context,
            "source_file": self.source_file,
            "source_id": self.source_id,
            "disposition": self.disposition,
            "timestamp": self.timestamp,
        }


def compute_candidate_id(project: str, bounded_context: str, source_id: str, task: str) -> str:
    """Deterministic candidate_id -- the same (project, bounded_context,
    source_id, task) always hashes to the same id, so the same real candidate
    surfaced again for a similar task can be correlated without a lookup
    table. NOT a random uuid. Unit-separator-joined before hashing so a value
    containing the plain join character can't collide with a different
    four-tuple."""
    digest_input = "\x1f".join([project, bounded_context, source_id, task])
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]


def append_disposition_event(
    *,
    project: str,
    task: str,
    bounded_context: str,
    source_file: str,
    source_id: str,
    disposition: str,
    log_path: Path | None = None,
) -> DispositionEvent:
    """Construct a real DispositionEvent and append it as one line to
    log_path (default state/disposition-log.jsonl, resolved at call time so
    the path stays redirectable for tests). Only ever called at the moment a
    disposition is actually decided -- never backfilled, never synthetic.
    Raises DispositionValidationError on malformed input before anything is
    written."""
    resolved_log_path = log_path or _DEFAULT_LOG_PATH
    event = DispositionEvent(
        candidate_id=compute_candidate_id(project, bounded_context, source_id, task),
        project=project,
        task=task,
        bounded_context=bounded_context,
        source_file=source_file,
        source_id=source_id,
        disposition=disposition,
        timestamp=datetime.now(UTC).isoformat(),
    )
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict()) + "\n")
    return event
