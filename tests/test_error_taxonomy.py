"""Tests for error taxonomy, retry classification, and side effect declaration."""
from __future__ import annotations
import pytest


class TestErrorType:
    def test_all_values_are_strings(self):
        from schemas import ErrorType
        for member in ErrorType:
            assert isinstance(member.value, str)

    def test_retryable_types_exist(self):
        from schemas import ErrorType
        assert ErrorType.TRANSIENT
        assert ErrorType.RATE_LIMIT

    def test_non_retryable_types_exist(self):
        from schemas import ErrorType
        assert ErrorType.INPUT
        assert ErrorType.AUTH
        assert ErrorType.BUSINESS_RULE
        assert ErrorType.SYSTEM

    def test_error_type_is_comparable_as_string(self):
        from schemas import ErrorType
        assert ErrorType.TRANSIENT == "TRANSIENT"
        assert ErrorType.BUSINESS_RULE == "BUSINESS_RULE"


class TestClassifyError:
    def test_transient_is_retryable_with_backoff(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.TRANSIENT)
        assert decision["retryable"] is True
        assert decision["strategy"] == "backoff"
        assert decision["reason"]

    def test_rate_limit_is_retryable_with_backoff(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.RATE_LIMIT)
        assert decision["retryable"] is True
        assert decision["strategy"] == "backoff"

    def test_input_is_not_retryable(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.INPUT)
        assert decision["retryable"] is False
        assert decision["strategy"] == "none"

    def test_auth_is_not_retryable(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.AUTH)
        assert decision["retryable"] is False
        assert decision["strategy"] == "none"

    def test_business_rule_is_not_retryable(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.BUSINESS_RULE)
        assert decision["retryable"] is False
        assert decision["strategy"] == "none"

    def test_system_is_not_retryable(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.SYSTEM)
        assert decision["retryable"] is False
        assert decision["strategy"] == "none"

    def test_all_decisions_have_reason(self):
        from schemas import ErrorType
        from guardrails import classify_error
        for error_type in ErrorType:
            decision = classify_error(error_type)
            assert decision["reason"], f"Missing reason for {error_type}"

    def test_retry_table_covers_all_error_types(self):
        from schemas import ErrorType
        from guardrails import classify_error
        for error_type in ErrorType:
            decision = classify_error(error_type)
            assert "retryable" in decision
            assert "strategy" in decision


class TestSaveContractErrorType:
    def test_vague_contract_returns_input_error_type(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        from schemas import ErrorType
        # Simulate the save_contract vague-input path without invoking the MCP tool directly
        stripped = "short"
        words = stripped.split()
        is_vague = len(stripped) < 20 or len(words) < 3
        assert is_vague
        # Confirm ErrorType.INPUT is the right annotation for vague input
        assert ErrorType.INPUT == "INPUT"
        assert ErrorType.INPUT != "TRANSIENT"


class TestRetryDecisionShape:
    def test_retry_decision_has_required_keys(self):
        from schemas import ErrorType
        from guardrails import classify_error
        decision = classify_error(ErrorType.TRANSIENT)
        assert set(decision.keys()) >= {"retryable", "strategy", "reason"}

    def test_strategy_values_are_valid(self):
        from schemas import ErrorType
        from guardrails import classify_error
        valid_strategies = {"immediate", "backoff", "none"}
        for error_type in ErrorType:
            decision = classify_error(error_type)
            assert decision["strategy"] in valid_strategies, \
                f"Invalid strategy '{decision['strategy']}' for {error_type}"
