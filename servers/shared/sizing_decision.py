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
    # What the intent call was actually shown when it estimated the size.
    # grounding_status: "" (no intent call), "grounded" (evidence was in the
    # prompt), "no_evidence" (looked, nothing relevant), "unavailable"
    # (retrieval could not run, so the estimate was made cold).
    grounding_status: str = ""
    precedent_count: int = 0
    domain_invariant_count: int = 0

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
        if self.grounding_status not in {"", "grounded", "no_evidence", "unavailable"}:
            raise SizingDecisionValidationError(f"grounding_status invalid: {self.grounding_status!r}")
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
            "grounding_status": self.grounding_status,
            "precedent_count": self.precedent_count,
            "domain_invariant_count": self.domain_invariant_count,
        }


def log_sizing_decision(
    task: str,
    deterministic_size: str,
    llm_estimated_size: str,
    resolved_size: str,
    mismatch_flag: bool,
    log_path: Path | None = None,
    grounding: dict[str, Any] | None = None,
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
        grounding_status=(grounding or {}).get("status", ""),
        precedent_count=int((grounding or {}).get("precedent_count", 0)),
        domain_invariant_count=int((grounding or {}).get("domain_invariant_count", 0)),
    )
    locked_jsonl_append(resolved_log_path, json.dumps(decision.to_dict()))
    return decision


def find_similar_sizing_precedents(
    task: str, limit: int = 3, log_path: Path | None = None
) -> list[dict[str, Any]]:
    """Real precedents for grounding a NEW sizing judgment -- the retrieval
    half of the research finding above. Returns up to `limit` past decisions
    whose task text clears TASK_RELEVANCE_FLOOR, most similar first, one per
    distinct task text (the most recent). Empty list when no history exists
    or nothing is relevant; never pads with an unrelated decision to fill the
    slots. Raises if the embedding model is unavailable, so the caller can
    tell "no precedent" from "could not look"."""
    from jsonl_lock import locked_jsonl_read_all
    from semantic_similarity import TASK_RELEVANCE_FLOOR, rank_by_similarity

    resolved_log_path = log_path or _DEFAULT_LOG_PATH
    latest_by_task: dict[str, dict[str, Any]] = {}
    for row in locked_jsonl_read_all(resolved_log_path):
        if isinstance(row.get("task"), str) and row["task"].strip():
            latest_by_task[row["task"]] = row
    history = list(latest_by_task.values())
    ranked = rank_by_similarity(
        task, [h["task"] for h in history], min_score=TASK_RELEVANCE_FLOOR, limit=limit
    )
    return [history[i] for i, _ in ranked]
