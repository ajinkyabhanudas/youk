"""Tests for _extract_implicit_assumptions in servers/core/src/intent.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from intent import _extract_implicit_assumptions


def test_no_domain_keywords_returns_empty():
    result = _extract_implicit_assumptions("refactor the controller layer for clarity")
    assert result == []


def test_retry_returns_transience_assumption():
    result = _extract_implicit_assumptions("add retry logic to the LLM client")
    assert any("transient" in a for a in result), f"Expected transience assumption, got: {result}"


def test_cache_returns_ttl_assumption():
    result = _extract_implicit_assumptions("cache the API responses")
    assert any("TTL" in a or "cacheable" in a for a in result), f"Expected TTL/cacheability assumption, got: {result}"


def test_explicit_if_clause_suppresses_assumption():
    result = _extract_implicit_assumptions("add retry if the failure is transient")
    assert result == [], f"Expected no assumption when 'if' clause present, got: {result}"


def test_multiple_keywords_return_multiple_assumptions():
    result = _extract_implicit_assumptions("add retry logic and cache the results")
    assert len(result) >= 2, f"Expected at least 2 assumptions, got: {result}"
    combined = " ".join(result)
    assert "transient" in combined
    assert "TTL" in combined or "cacheable" in combined


def test_case_insensitive_matching():
    result_upper = _extract_implicit_assumptions("implement RETRY for failed requests")
    result_mixed = _extract_implicit_assumptions("add Caching to the endpoint")
    assert any("transient" in a for a in result_upper), f"RETRY not detected: {result_upper}"
    assert any("TTL" in a or "cacheable" in a for a in result_mixed), f"Caching not detected: {result_mixed}"
