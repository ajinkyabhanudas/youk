"""Tests for nfr_gate.py — check_nfr_gate blocks M+ without NFR block, passes otherwise."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from nfr_gate import check_nfr_gate


class TestNfrGateBlocked:
    """M/L/XL without an NFR block must return blocked=True."""

    def test_m_task_no_block_is_blocked(self):
        result = check_nfr_gate("add caching layer", "M", None)
        assert result["blocked"] is True
        assert "nfr-check" in result["reason"].lower() or "NFR" in result["reason"]

    def test_l_task_no_block_is_blocked(self):
        result = check_nfr_gate("redesign auth module", "L", None)
        assert result["blocked"] is True

    def test_xl_task_no_block_is_blocked(self):
        result = check_nfr_gate("platform rewrite", "XL", None)
        assert result["blocked"] is True

    def test_m_task_empty_string_is_blocked(self):
        result = check_nfr_gate("add caching layer", "M", "")
        assert result["blocked"] is True

    def test_m_task_whitespace_only_is_blocked(self):
        result = check_nfr_gate("add caching layer", "M", "   \n  ")
        assert result["blocked"] is True

    def test_reason_names_the_size(self):
        result = check_nfr_gate("build feature", "L", None)
        assert "L" in result["reason"]


class TestNfrGatePasses:
    """XS/S always pass; M+ with a non-empty block passes."""

    def test_xs_passes_without_block(self):
        result = check_nfr_gate("fix typo", "XS", None)
        assert result["blocked"] is False

    def test_s_passes_without_block(self):
        result = check_nfr_gate("fix login bug", "S", None)
        assert result["blocked"] is False

    def test_m_passes_with_nfr_block(self):
        nfr = "[NFR — QUICK_4Q]\nTask: add caching\nDecisions:\n  - use in-memory LRU"
        result = check_nfr_gate("add caching layer", "M", nfr)
        assert result["blocked"] is False
        assert result["reason"] == ""

    def test_l_passes_with_nfr_block(self):
        nfr = "[NFR — FULL]\nTask: redesign auth"
        result = check_nfr_gate("redesign auth module", "L", nfr)
        assert result["blocked"] is False

    def test_xl_passes_with_nfr_block(self):
        nfr = "[NFR — FULL]\nTask: platform rewrite"
        result = check_nfr_gate("platform rewrite", "XL", nfr)
        assert result["blocked"] is False

    def test_xs_passes_even_with_block_provided(self):
        result = check_nfr_gate("rename variable", "XS", "[NFR — QUICK_4Q]")
        assert result["blocked"] is False


class TestNfrGateEdgeCases:
    """Edge cases: unknown size, case sensitivity."""

    def test_unknown_size_passes(self):
        # Unknown sizes are not in the blocked set — gate passes rather than crashes
        result = check_nfr_gate("do something", "UNKNOWN", None)
        assert result["blocked"] is False

    def test_lowercase_size_passes(self):
        # Gate is case-sensitive — lowercase "m" is not a blocked size
        result = check_nfr_gate("add feature", "m", None)
        assert result["blocked"] is False

    def test_result_always_has_blocked_and_reason(self):
        for size in ("XS", "S", "M", "L", "XL"):
            result = check_nfr_gate("task", size, None)
            assert "blocked" in result
            assert "reason" in result
