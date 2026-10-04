"""Real record of every task-sizing decision, for two real uses:

1. Retrieval-grounding: before judging a NEW task's size, find real past
   tasks that were semantically similar and show the LLM what they
   actually resolved to. A judgment grounded in real precedent is more
   reliable than one made cold. This is that retrieval's source.
2. Audit: a real, queryable history of every sizing call, not just the
   present-moment decision -- the raw material for checking whether
   sizing is actually accurate over time, once real outcome data exists
   to check it against (not yet built).

Governed by the same discipline as pattern_entry.py: a dataclass that
raises on malformed input, dual-validated against a committed JSON Schema.
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

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "sizing-decision.schema.json"
_DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "state" / "sizing-decisions.jsonl"
_VALID_SIZES = frozenset({"", "XS", "S", "M", "L", "XL"})


class SizingDecisionValidationError(ValueError):
    pass


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class SizingDecision:
    id: str
    task: str
    deterministic_size: str
    llm_estimated_size: str
    resolved_size: str
    mismatch_flag: bool
    timestamp: str

    def __post_init__(self) -> None:
        if not isinstance(self.task, str) or not self.task.strip():
            raise SizingDecisionValidationError("task must be a non-empty string")
        for field_name, value in (
            ("deterministic_size", self.deterministic_size),
            ("llm_estimated_size", self.llm_estimated_size),
            ("resolved_size", self.resolved_size),
        ):
            if value not in _VALID_SIZES:
                raise SizingDecisionValidationError(
                    f"{field_name} must be one of {sorted(_VALID_SIZES)}, got {value!r}"
                )
        if not isinstance(self.mismatch_flag, bool):
            raise SizingDecisionValidationError("mismatch_flag must be a bool")
        self._validate_against_json_schema()

    def _validate_against_json_schema(self) -> None:
        try:
            jsonschema.validate(instance=self.to_dict(), schema=_load_schema())
        except jsonschema.exceptions.ValidationError as e:
            raise SizingDecisionValidationError(f"failed committed JSON Schema validation: {e.message}") from e

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "deterministic_size": self.deterministic_size,
            "llm_estimated_size": self.llm_estimated_size,
            "resolved_size": self.resolved_size,
            "mismatch_flag": self.mismatch_flag,
            "timestamp": self.timestamp,
        }


def log_sizing_decision(
    task: str,
    deterministic_size: str,
    llm_estimated_size: str,
    resolved_size: str,
    mismatch_flag: bool,
    log_path: Path | None = None,
) -> SizingDecision:
    """Append one real sizing decision. Called from route_task itself,
    which already has every field computed -- never backfilled, never
    synthetic."""
    from jsonl_lock import locked_jsonl_append

    resolved_log_path = log_path or _DEFAULT_LOG_PATH
    decision_id = hashlib.sha256(
        f"{task}\x1f{datetime.now(UTC).isoformat()}".encode()
    ).hexdigest()[:16]
    decision = SizingDecision(
        id=decision_id,
        task=task,
        deterministic_size=deterministic_size,
        llm_estimated_size=llm_estimated_size,
        resolved_size=resolved_size,
        mismatch_flag=mismatch_flag,
        timestamp=datetime.now(UTC).isoformat(),
    )
    locked_jsonl_append(resolved_log_path, json.dumps(decision.to_dict()))
    return decision


def find_similar_sizing_precedents(
    task: str, limit: int = 3, log_path: Path | None = None
) -> list[dict[str, Any]]:
    """Real precedents for grounding a NEW sizing judgment -- the retrieval
    half of the research finding above. Returns the `limit` most similar
    past decisions (by semantic similarity on task text), most similar
    first. Empty list when no history exists yet; never invents a
    precedent."""
    from jsonl_lock import locked_jsonl_read_all
    from semantic_similarity import similarity

    resolved_log_path = log_path or _DEFAULT_LOG_PATH
    history = locked_jsonl_read_all(resolved_log_path)
    if not history:
        return []
    scored = sorted(
        (dict(h, _score=similarity(task, h["task"])) for h in history),
        key=lambda h: h["_score"],
        reverse=True,
    )
    return [{k: v for k, v in h.items() if k != "_score"} for h in scored[:limit]]
