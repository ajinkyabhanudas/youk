"""DomainScopeEvent: the real log of nfr-check's "Domain scope" judgment call.

docs/system-observability-design.md's Phase 1 (CIR-177) -- read that
document's "Real gap found while scoping this" section first; this module
implements only that gap-close. `skills/nfr-check/SKILL.md`'s Domain scope
step (CIR-165) names 2-4 knowledge domains per M/L/XL task, with a
one-sentence justification each, fresh every time -- never cached or reused
from a prior task's answer. It is the single heaviest LLM judgment call in
the whole system, and until this module existed it wrote nothing durable:
the decision happened in-session and vanished, with no way to check later
for drift or bias in which domains get named and why.

Governed by ADR-009, same discipline as pattern_entry.py and
disposition_event.py: a stdlib dataclass with __post_init__ validation that
RAISES on malformed input, never coerces. No Pydantic.

Storage: state/domain-scope-log.jsonl, append-only, one real event per line,
never backfilled -- same precedent as every other JSONL file in this
initiative (disposition-log.jsonl, confirmed-patterns.jsonl).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "domain-scope-event.schema.json"
_DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "state" / "domain-scope-log.jsonl"


class DomainScopeValidationError(ValueError):
    """Raised when a DomainScopeEvent fails validation, on construction.

    Subclass of ValueError (same precedent as PatternValidationError /
    DispositionValidationError) so existing broad `except ValueError`
    handlers still catch it, while callers that care can catch this
    specifically.
    """


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise DomainScopeValidationError(f"{field_name} must be str, got {type(value).__name__}")
    if not value.strip():
        raise DomainScopeValidationError(f"{field_name} must be a non-empty string")
    return value


def _require_domains(value: Any) -> list[dict]:
    if not isinstance(value, list) or isinstance(value, (str, bytes)):
        raise DomainScopeValidationError(f"domains must be a list, got {type(value).__name__}")
    if not value:
        raise DomainScopeValidationError("domains must be a non-empty list (2-4 domains expected)")
    normalized = []
    for i, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise DomainScopeValidationError(f"domains[{i}] must be a dict, got {type(entry).__name__}")
        domain = entry.get("domain")
        reason = entry.get("reason")
        if not isinstance(domain, str) or not domain.strip():
            raise DomainScopeValidationError(f"domains[{i}].domain must be a non-empty string")
        if not isinstance(reason, str) or not reason.strip():
            raise DomainScopeValidationError(f"domains[{i}].reason must be a non-empty string")
        normalized.append({"domain": domain, "reason": reason})
    return normalized


@dataclass
class DomainScopeEvent:
    """schemas/domain-scope-event.schema.json, enforced. See module docstring."""

    task: str
    domains: list[dict] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        _require_str(self.task, "task")
        self.domains = _require_domains(self.domains)
        _require_str(self.timestamp, "timestamp")
        self._validate_against_json_schema()

    def _validate_against_json_schema(self) -> None:
        try:
            jsonschema.validate(instance=self.to_dict(), schema=_load_schema())
        except jsonschema.exceptions.ValidationError as e:
            raise DomainScopeValidationError(f"failed committed JSON Schema validation: {e.message}") from e

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "domains": self.domains,
            "timestamp": self.timestamp,
        }


def append_domain_scope_event(
    task: str,
    domains: list[dict],
    log_path: Path | None = None,
) -> DomainScopeEvent:
    """Construct a real DomainScopeEvent and append it as one line to
    log_path (default state/domain-scope-log.jsonl, resolved at call time so
    the path stays redirectable for tests). Only ever called right after the
    domains for THIS task were just named fresh -- never a cached/reused
    prior answer. Raises DomainScopeValidationError on malformed input before
    anything is written."""
    resolved_log_path = log_path or _DEFAULT_LOG_PATH
    event = DomainScopeEvent(
        task=task,
        domains=domains,
        timestamp=datetime.now(UTC).isoformat(),
    )
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict()) + "\n")
    return event
