"""Tests for servers/core/src/verification_contract.py (CIR-154 items 2-4)."""
from __future__ import annotations

import json

import pytest
from host_inventory import scan as scan_host_graph
from verification_contract import (
    append_pattern_library_entries,
    build_claim,
    claims_dir,
    gate_all_claims,
    gate_claim_done,
    generate_sub_claims,
    pattern_library_path,
    run_checker,
    write_claim,
)

_FAKE_GRAPH = {
    "pre_tool_guard": {
        "mechanism": "pre_tool_guard",
        "hosts": {
            "claude-code": {"wired": True, "evidence": "plugin/hooks/hooks.json:26"},
            "codex": {"wired": False, "evidence": None},
        },
    },
    "compaction_context": {
        "mechanism": "compaction_context",
        "hosts": {
            "claude-code": {"wired": True, "evidence": "plugin/hooks/hooks.json:4"},
            "codex": {"wired": True, "evidence": "servers/core/src/compaction.py:248"},
        },
    },
}


class TestSubClaimGeneration:
    def test_one_sub_claim_per_mechanism_host_pair_in_the_graph(self):
        sub_claims = generate_sub_claims("host", _FAKE_GRAPH)
        ids = {sc.id for sc in sub_claims}
        assert ids == {
            "pre_tool_guard:claude-code", "pre_tool_guard:codex",
            "compaction_context:claude-code", "compaction_context:codex",
        }

    def test_wired_true_maps_to_verified(self):
        sub_claims = generate_sub_claims("host", _FAKE_GRAPH)
        by_id = {sc.id: sc for sc in sub_claims}
        assert by_id["pre_tool_guard:claude-code"].status == "verified"
        assert by_id["pre_tool_guard:claude-code"].evidence == "plugin/hooks/hooks.json:26"

    def test_wired_false_maps_to_failed_not_unverified(self):
        """A scanner that actually looked and found nothing is a positive
        finding of absence, not an open question -- "failed" communicates
        that a check ran and came back negative, distinct from "unverified"
        (never checked at all)."""
        sub_claims = generate_sub_claims("host", _FAKE_GRAPH)
        by_id = {sc.id: sc for sc in sub_claims}
        assert by_id["pre_tool_guard:codex"].status == "failed"

    def test_unsupported_dimension_raises(self):
        with pytest.raises(ValueError):
            generate_sub_claims("vendor", _FAKE_GRAPH)

    def test_domain_comes_from_the_graph_not_a_fixed_list(self):
        """Adding a mechanism to the graph adds sub_claims automatically --
        the checker never hardcodes which mechanisms exist."""
        graph = dict(_FAKE_GRAPH)
        graph["new_mechanism"] = {
            "mechanism": "new_mechanism",
            "hosts": {"claude-code": {"wired": True, "evidence": "x:1"}},
        }
        sub_claims = generate_sub_claims("host", graph)
        assert any(sc.id == "new_mechanism:claude-code" for sc in sub_claims)


class TestClaimPersistenceAndGate:
    def test_claim_with_all_verified_sub_claims_passes_the_gate(self, tmp_path):
        graph = {"compaction_context": _FAKE_GRAPH["compaction_context"]}
        claim = build_claim("compaction works everywhere", "host", graph)
        path = write_claim(tmp_path, claim)
        assert path.exists()
        assert gate_claim_done(path) is None

    def test_claim_with_a_failed_sub_claim_blocks_the_gate(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        path = write_claim(tmp_path, claim)
        verdict = gate_claim_done(path)
        assert verdict is not None
        assert "pre_tool_guard:codex" in verdict["message"]
        assert "failed" in verdict["message"]

    def test_gate_all_claims_none_when_no_claims_directory_exists(self, tmp_path):
        assert gate_all_claims(tmp_path) is None

    def test_gate_all_claims_none_when_every_claim_on_disk_is_fully_verified(self, tmp_path):
        graph = {"compaction_context": _FAKE_GRAPH["compaction_context"]}
        write_claim(tmp_path, build_claim("compaction works everywhere", "host", graph))
        assert gate_all_claims(tmp_path) is None

    def test_gate_all_claims_blocks_when_any_claim_on_disk_has_a_failure(self, tmp_path):
        write_claim(tmp_path, build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH))
        verdict = gate_all_claims(tmp_path)
        assert verdict is not None
        assert "pre_tool_guard:codex" in verdict["message"]

    def test_missing_claim_file_does_not_block(self, tmp_path):
        assert gate_claim_done(tmp_path / "does-not-exist.json") is None


class TestPatternLibrary:
    def test_appends_one_entry_per_failed_sub_claim(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        entries = append_pattern_library_entries(tmp_path, claim, "test run")
        assert len(entries) == 1
        assert entries[0]["missed_sub_claim"] == "pre_tool_guard:codex"
        assert entries[0]["how_found"] == "test run"

        lib = pattern_library_path(tmp_path)
        lines = [json.loads(ln) for ln in lib.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_rerunning_against_the_same_failure_does_not_duplicate(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        append_pattern_library_entries(tmp_path, claim, "first run")
        second = append_pattern_library_entries(tmp_path, claim, "second run")
        assert second == []

        lib = pattern_library_path(tmp_path)
        lines = [ln for ln in lib.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_fully_verified_claim_appends_nothing(self, tmp_path):
        graph = {"compaction_context": _FAKE_GRAPH["compaction_context"]}
        claim = build_claim("compaction works everywhere", "host", graph)
        entries = append_pattern_library_entries(tmp_path, claim, "test run")
        assert entries == []
        assert not pattern_library_path(tmp_path).exists()


class TestRunChecker:
    def test_run_checker_writes_claim_and_appends_pattern_library_in_one_call(self, tmp_path):
        claim = run_checker(tmp_path, "youk is agent-agnostic", "host", _FAKE_GRAPH, "test run")
        assert not claim.all_verified()
        assert (claims_dir(tmp_path) / "youk-is-agent-agnostic.json").exists()
        assert pattern_library_path(tmp_path).exists()


class TestRealAgentAgnosticClaimAgainstTheRealScanner:
    """The concrete demonstration CIR-154's DONE-MEANS requires: re-running
    the checker today, against the real scanner's output for the real
    codebase, must surface the enforcement-layer gap automatically -- with
    nobody having to think to ask about it.

    CIR-155 closed the two gaps CIR-154 found live (pre_tool_guard:codex and
    session_context:claude-code) -- see plugin/scripts/pre_tool_use.py's
    apply_patch handling and plugin/scripts/session_start.py respectively.
    This test now asserts the claim is fully verified -- the updated live
    proof CIR-155's own DONE-MEANS requires."""

    def test_agent_agnostic_claim_is_now_fully_verified_after_cir_155(self, tmp_path):
        graph = scan_host_graph()
        claim = run_checker(tmp_path, "youk is agent-agnostic", "host", graph,
                             "CIR-155 automated regression")

        assert claim.all_verified() is True

        by_id = {sc.id: sc for sc in claim.sub_claims}
        assert by_id["pre_tool_guard:codex"].status == "verified"
        assert by_id["pre_tool_guard:claude-code"].status == "verified"
        assert by_id["session_context:claude-code"].status == "verified"

        verdict = gate_all_claims(tmp_path)
        assert verdict is None
