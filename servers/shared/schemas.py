"""Typed output schemas for the youk routing pipeline.

All schemas are TypedDict (stdlib only, no Pydantic). They describe the
return shapes of the five core routing functions in servers/core/src/server.py.
Functions return dict; callers can cast via TypedDict for static analysis.
"""
from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


# ── Error taxonomy ────────────────────────────────────────────────────────────

class ErrorType(StrEnum):
    """Machine-readable error category. Determines retry and escalation behaviour.

    Retryable:
        TRANSIENT  — temporary network failure, service unavailable, transient timeout
        RATE_LIMIT — rate limit hit; retry after back-off

    Not retryable:
        INPUT         — invalid argument, missing required field, schema violation
        AUTH          — unauthorized or forbidden
        BUSINESS_RULE — gate blocked, contract violated, hard rule triggered
        SYSTEM        — unexpected internal error; surface to operator
    """
    TRANSIENT = "TRANSIENT"
    RATE_LIMIT = "RATE_LIMIT"
    INPUT = "INPUT"
    AUTH = "AUTH"
    BUSINESS_RULE = "BUSINESS_RULE"
    SYSTEM = "SYSTEM"


class RetryDecision(TypedDict):
    """Returned by classify_error() in guardrails.py."""
    retryable: bool
    strategy: str    # "immediate" | "backoff" | "none"
    reason: str      # human-readable guidance for the agent


# ── optimize_intent ──────────────────────────────────────────────────────────

class GoalTranslation(TypedDict):
    stated_as: str
    interpreted_as: str
    observable_outcome: str
    translation_risk: str          # "none" | "low" | "medium" | "high"
    translation_question: str | None


class OptimizeIntentResult(TypedDict, total=False):
    problem: str
    success_criteria: str
    constraints: list[str]
    architecture_recommendation: str
    anti_patterns: list[str]
    out_of_scope: list[str]
    ambiguity_detected: bool
    clarifying_questions: list[str]
    estimated_size: str            # "XS" | "S" | "M" | "L" | "XL"
    token_efficiency_gain: str
    mode: str                      # "fast_pattern_match" | "api_optimized" | "fallback_no_api"
    raw_input: str
    goal_translation: GoalTranslation
    intake_required: bool
    implicit_assumptions: list[str]


# ── route_task ───────────────────────────────────────────────────────────────

class RoutingWarning(TypedDict):
    rule_id: str
    name: str
    message: str


class SteeringBehavior(TypedDict, total=False):
    label: str
    behaviors: list[str]
    learned: bool
    confidence: str


class RouteTaskResult(TypedDict, total=False):
    task: str
    size: str                      # "XS" | "S" | "M" | "L" | "XL"
    ceremony: str
    skills: list[str]
    nfr_mode: str
    token_budget: int
    warnings: list[RoutingWarning]
    plan_hook: str
    blocked: bool
    collapsing_question: str
    file_context: list[dict[str, object]]
    graph_state: dict[str, object]  # present when blocked_count > 0
    calls_since_compact: int
    steering_context: list[SteeringBehavior]


# ── task_contract ─────────────────────────────────────────────────────────────

class TaskContractResult(TypedDict, total=False):
    contract_required: bool
    reason: str                    # present when contract_required=False
    contract_id: str
    path: str
    contract: str                  # markdown body to present to developer
    size: str
    calls_since_compact: int


# ── check_nfr_gate ────────────────────────────────────────────────────────────

class CheckNfrGateResult(TypedDict):
    blocked: bool
    reason: str


# ── check_challenge_gate ──────────────────────────────────────────────────────

class CheckChallengeGateResult(TypedDict):
    blocked: bool
    reason: str


# ── failure_pattern_detector ──────────────────────────────────────────────────

class FailurePatternAlert(TypedDict):
    domain: str
    count: int
    sessions_scanned: int
    message: str
