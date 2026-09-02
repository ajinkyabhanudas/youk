"""Tests for the experiment-gap detector (Phase 3 of the reaction-classifier plan).

Two layers: the pure candidate-generation function (detect_experiment_gaps, no DB,
no MCP), and the scan_experiment_gaps MCP tool that persists what it returns. The
load-bearing guard across both: every generated proposal is change_type
"EXPERIMENT_PROPOSAL" with review_required=True — the thing that keeps this detector
from ever being able to auto-apply what it finds, since apply_proposal blocks any
review_required=True proposal without an explicit human review_required_override=True
regardless of safe_types.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from experiment_gap_detector import (
    EXPERIMENT_GAP_CANDIDATES,
    detect_experiment_gaps,
)

# server.py imports mcp.server.fastmcp specifically. Checked here (not via a
# module-level importorskip, which would also skip the pure detect_experiment_gaps
# tests above that have no mcp dependency at all) so only TestScanExperimentGapsTool
# below is conditional on it.
try:
    import mcp.server.fastmcp  # noqa: F401
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def _import_core_server():
    """Load servers/core/src/server.py by explicit path, not bare `import server`.

    servers/code/src/server.py is also importable as top-level `server` (both dirs
    are on sys.path via conftest.py, code/src last-inserted so highest priority) and
    whichever one gets imported first wins the sys.modules['server'] cache for the
    rest of the pytest session. This file needs the core server specifically and
    must not depend on collection order to get it.
    """
    path = Path(__file__).parent.parent / "servers" / "core" / "src" / "server.py"
    spec = importlib.util.spec_from_file_location("youk_core_server_under_test", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDetectExperimentGapsNoExisting:
    def test_returns_one_result_per_candidate(self):
        results = detect_experiment_gaps(existing_proposal_ids=set())
        assert len(results) == len(EXPERIMENT_GAP_CANDIDATES)

    def test_all_are_added_when_nothing_exists(self):
        results = detect_experiment_gaps(existing_proposal_ids=set())
        assert all(r["status"] == "added" for r in results)

    def test_proposal_ids_are_stable_and_unique(self):
        r1 = detect_experiment_gaps(existing_proposal_ids=set())
        r2 = detect_experiment_gaps(existing_proposal_ids=set())
        ids1 = [r["proposal_id"] for r in r1]
        ids2 = [r["proposal_id"] for r in r2]
        assert ids1 == ids2
        assert len(set(ids1)) == len(ids1)

    def test_content_forces_a_disposition(self):
        for r in detect_experiment_gaps(existing_proposal_ids=set()):
            assert "IN-SCOPE" in r["content"]
            assert "DEFER" in r["content"]
            assert "ACCEPT-RISK" in r["content"]
            assert "N/A" in r["content"]

    def test_content_never_says_deploy_or_apply(self):
        """Guards the plan's own boundary: this proposes, it never deploys."""
        banned = ("auto-deploy", "auto-apply", "deploys automatically")
        for r in detect_experiment_gaps(existing_proposal_ids=set()):
            lowered = r["content"].lower()
            assert not any(b in lowered for b in banned)


class TestDetectExperimentGapsWithExisting:
    def test_already_proposed_candidate_is_skipped(self):
        one_id = f"EXPGAP-{EXPERIMENT_GAP_CANDIDATES[0]['key']}"
        results = detect_experiment_gaps(existing_proposal_ids={one_id})
        matched = next(r for r in results if r["proposal_id"] == one_id)
        assert matched["status"] == "already_proposed"
        assert "content" not in matched

    def test_all_existing_yields_no_added(self):
        all_ids = {f"EXPGAP-{c['key']}" for c in EXPERIMENT_GAP_CANDIDATES}
        results = detect_experiment_gaps(existing_proposal_ids=all_ids)
        assert all(r["status"] == "already_proposed" for r in results)

    def test_unrelated_existing_id_does_not_affect_others(self):
        results = detect_experiment_gaps(existing_proposal_ids={"EXPGAP-not-a-real-candidate"})
        assert all(r["status"] == "added" for r in results)


@pytest.mark.skipif(not _MCP_AVAILABLE, reason="mcp<2 with FastMCP API not installed — CI installs it")
class TestScanExperimentGapsTool:
    def test_first_scan_adds_all_and_persists_review_required(self, youk_root, claude_root):
        server = _import_core_server()
        import health

        tool = server.mcp._tool_manager.get_tool("scan_experiment_gaps")
        result = tool.fn()

        assert result["scanned"] == len(EXPERIMENT_GAP_CANDIDATES)
        assert result["added"] == len(EXPERIMENT_GAP_CANDIDATES)
        assert result["already_proposed"] == 0

        stored = health._load_pending_proposals("youk")
        exp_proposals = [p for p in stored if p.change_type == "EXPERIMENT_PROPOSAL"]
        assert len(exp_proposals) == len(EXPERIMENT_GAP_CANDIDATES)
        assert all(p.review_required is True for p in exp_proposals)

    def test_second_scan_is_idempotent(self, youk_root, claude_root):
        server = _import_core_server()
        import health

        tool = server.mcp._tool_manager.get_tool("scan_experiment_gaps")
        tool.fn()
        result = tool.fn()

        assert result["added"] == 0
        assert result["already_proposed"] == len(EXPERIMENT_GAP_CANDIDATES)

        stored = health._load_pending_proposals("youk")
        exp_proposals = [p for p in stored if p.change_type == "EXPERIMENT_PROPOSAL"]
        assert len(exp_proposals) == len(EXPERIMENT_GAP_CANDIDATES)

    def test_apply_proposal_blocks_without_review_override(self, youk_root, claude_root):
        """The safety property this whole phase depends on: even an explicit apply
        call, with no safe_types restriction at all, cannot land an experiment
        proposal without a human passing review_required_override=True."""
        server = _import_core_server()

        scan_tool = server.mcp._tool_manager.get_tool("scan_experiment_gaps")
        scan_tool.fn()

        one_id = f"EXPGAP-{EXPERIMENT_GAP_CANDIDATES[0]['key']}"
        apply_tool = server.mcp._tool_manager.get_tool("apply_proposal")
        result = apply_tool.fn(proposal_id=one_id, confirmed=True)

        assert result["applied"] is False
        assert result["blocked"] is True
        assert result["review_required"] is True

    def test_experiment_proposal_type_is_never_in_a_safe_types_call_site(self):
        """Static guard matching the plan's own verification step: grep every
        apply_proposal(...safe_types=...) call site in the codebase and confirm
        none of them include EXPERIMENT_PROPOSAL."""
        import re
        from pathlib import Path

        repo = Path(__file__).parent.parent
        pattern = re.compile(r"safe_types\s*=\s*\[[^\]]*\]")
        offenders = []
        for path in repo.rglob("*.py"):
            if "/.git/" in str(path) or "/tests/" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for match in pattern.finditer(text):
                if "EXPERIMENT_PROPOSAL" in match.group(0):
                    offenders.append(f"{path}: {match.group(0)}")
        assert offenders == [], f"EXPERIMENT_PROPOSAL reachable via safe_types: {offenders}"
