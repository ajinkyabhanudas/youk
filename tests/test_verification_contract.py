"""Tests for servers/core/src/verification_contract.py (CIR-154 items 2-4)."""
from __future__ import annotations

import json

import pytest
from host_inventory import scan as scan_host_graph
from verification_contract import (
    FORWARD_EDGES,
    MAX_REWORK_ROUNDS,
    REWORK_EDGES,
    Claim,
    InvalidStageTransition,
    Stage,
    SubClaim,
    _walk_forward_to,
    advance,
    append_pattern_library_entries,
    build_claim,
    claims_dir,
    gate_all_claims,
    gate_claim_done,
    generate_sub_claims,
    mark_externally_verified,
    mark_founder_confirmed,
    migrate_claim_file_add_verification_level,
    migrate_claims_dir,
    pattern_library_path,
    retrieve_similar_patterns,
    rework,
    run_checker,
    run_rework_loop,
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


class TestPatternLibraryRetrieval:
    """CIR-160 (Phase 3): lightweight stdlib retrieval over the pattern
    library -- difflib.SequenceMatcher token-level similarity, no
    embeddings or vector DB (see retrieve_similar_patterns' own docstring
    for why nothing heavier is warranted at this corpus's real size)."""

    def test_retrieves_the_real_entry_for_a_structurally_similar_new_claim(self, tmp_path):
        # Seed the library the same way a real run does: build a claim,
        # let append_pattern_library_entries write its one real failure.
        seed_claim = build_claim("youk is agnostic across host", "host", _FAKE_GRAPH)
        append_pattern_library_entries(tmp_path, seed_claim, "test run")

        hits = retrieve_similar_patterns(
            tmp_path, "youk is agnostic across every host", "host",
        )
        assert len(hits) == 1
        assert hits[0]["missed_sub_claim"] == "pre_tool_guard:codex"
        assert hits[0]["claim_shape"] == "host-dimension: youk is agnostic across host"
        assert hits[0]["similarity"] >= 0.6

    def test_genuinely_dissimilar_claim_returns_nothing(self, tmp_path):
        seed_claim = build_claim("youk is agnostic across host", "host", _FAKE_GRAPH)
        append_pattern_library_entries(tmp_path, seed_claim, "test run")

        hits = retrieve_similar_patterns(
            tmp_path, "the deploy pipeline retries failed jobs three times", "host",
        )
        assert hits == []

    def test_no_pattern_library_file_on_disk_returns_nothing(self, tmp_path):
        assert retrieve_similar_patterns(tmp_path, "anything at all", "host") == []

    def test_generate_sub_claims_surfaces_the_hint_on_only_the_matching_sub_claim(self, tmp_path):
        seed_claim = build_claim("youk is agnostic across host", "host", _FAKE_GRAPH)
        append_pattern_library_entries(tmp_path, seed_claim, "first run")

        sub_claims = generate_sub_claims(
            "host", _FAKE_GRAPH,
            claim_statement="youk is agnostic across every host",
            root=tmp_path,
        )
        hints = {sc.id: sc.pattern_hint for sc in sub_claims}
        assert hints["pre_tool_guard:codex"] is not None
        assert "youk is agnostic across host" in hints["pre_tool_guard:codex"]
        # Only the sub_claim the pattern library actually named gets a hint.
        assert hints["pre_tool_guard:claude-code"] is None
        assert hints["compaction_context:claude-code"] is None
        assert hints["compaction_context:codex"] is None

    def test_generate_sub_claims_without_root_or_statement_has_no_hints(self):
        """Backward compat: every pre-CIR-160 caller (including the other
        tests in this file) omits claim_statement/root and must see no
        behavior change."""
        sub_claims = generate_sub_claims("host", _FAKE_GRAPH)
        assert all(sc.pattern_hint is None for sc in sub_claims)

    def test_build_claim_wires_root_through_to_surface_hints_end_to_end(self, tmp_path):
        seed_claim = build_claim("youk is agnostic across host", "host", _FAKE_GRAPH)
        append_pattern_library_entries(tmp_path, seed_claim, "first run")

        claim = build_claim(
            "youk is agnostic across every host", "host", _FAKE_GRAPH, root=tmp_path,
        )
        hinted = next(sc for sc in claim.sub_claims if sc.id == "pre_tool_guard:codex")
        assert hinted.pattern_hint is not None


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

    def test_agent_agnostic_claim_through_the_generalized_stage_model_is_still_8_of_8(self, tmp_path):
        """CIR-156 regression: re-running the exact same real claim, this
        time through run_rework_loop's stage-aware machinery instead of a
        single bare run_checker call, must still produce the same real,
        correct result -- the generalization must not change the answer."""
        outcome = run_rework_loop(
            tmp_path,
            "youk is agent-agnostic",
            "host",
            graph_fn=scan_host_graph,
            how_found="CIR-156 stage-model regression",
        )

        assert outcome.dry is True
        assert outcome.cap_hit is False
        assert outcome.message is None
        assert outcome.claim.all_verified() is True
        assert len(outcome.claim.sub_claims) == 8
        assert outcome.rounds[0].round_number == 1
        assert outcome.rounds[0].unresolved == []
        # Fully verified on round 1 -- no rework transition should have
        # fired at all for the real, already-fixed codebase.
        assert outcome.claim.rework_rounds == 0
        assert outcome.claim.stage == Stage.VERIFY

        verdict = gate_all_claims(tmp_path)
        assert verdict is None


class TestStageGraph:
    def test_every_stage_is_reserved(self):
        expected = {
            "intake", "abstract", "bound", "research", "diff",
            "decompose", "verify", "pattern_capture", "gate", "retrieve",
        }
        assert {s.value for s in Stage} == expected

    def test_forward_chain_reaches_gate_from_intake(self):
        claim = Claim(statement="x", dimension="host")
        for target in [
            Stage.ABSTRACT, Stage.BOUND, Stage.RESEARCH, Stage.DIFF, Stage.DECOMPOSE,
            Stage.VERIFY, Stage.PATTERN_CAPTURE, Stage.GATE,
        ]:
            advance(claim, target)
        assert claim.stage == Stage.GATE
        assert claim.stage_history == [
            "intake", "abstract", "bound", "research", "diff", "decompose", "verify",
            "pattern_capture",
        ]

    def test_advance_rejects_an_edge_not_in_forward_edges(self):
        claim = Claim(statement="x", dimension="host")
        with pytest.raises(InvalidStageTransition):
            advance(claim, Stage.GATE)

    def test_verify_rework_to_bound_is_valid(self):
        claim = Claim(statement="x", dimension="host", stage=Stage.VERIFY)
        rework(claim, Stage.BOUND, reason="domain incomplete")
        assert claim.stage == Stage.BOUND
        assert claim.rework_rounds == 1
        assert claim.rework_log[0] == {
            "from": "verify", "to": "bound", "reason": "domain incomplete", "round": 1,
        }

    def test_verify_rework_to_decompose_is_valid(self):
        """Both BOUND and DECOMPOSE must be valid rework targets from
        VERIFY -- the caller's choice, not a fixed single target."""
        claim = Claim(statement="x", dimension="host", stage=Stage.VERIFY)
        rework(claim, Stage.DECOMPOSE, reason="decomposition missed it")
        assert claim.stage == Stage.DECOMPOSE

    def test_verify_rework_to_an_undeclared_target_is_rejected(self):
        claim = Claim(statement="x", dimension="host", stage=Stage.VERIFY)
        with pytest.raises(InvalidStageTransition):
            rework(claim, Stage.RESEARCH, reason="not a declared VERIFY rework edge")

    def test_diff_rework_edge_back_to_research_is_live(self):
        """CIR-157: DIFF's rework edge (reserved since CIR-156) is now driven
        for real by diff_stage_outcome in verification_research.py."""
        claim = Claim(statement="x", dimension="host", stage=Stage.DIFF)
        rework(claim, Stage.RESEARCH, reason="diff disagreement")
        assert claim.stage == Stage.RESEARCH

    def test_diff_forward_edge_to_decompose_is_live(self):
        """CIR-157: a dual-pass diff with no disagreement continues the
        pipeline from DIFF to DECOMPOSE, not DIFF staying a dead end."""
        claim = Claim(statement="x", dimension="host", stage=Stage.DIFF)
        advance(claim, Stage.DECOMPOSE)
        assert claim.stage == Stage.DECOMPOSE

    def test_gate_reserves_rework_edges_mirroring_verify(self):
        assert REWORK_EDGES[Stage.GATE] == REWORK_EDGES[Stage.VERIFY] == frozenset(
            {Stage.BOUND, Stage.DECOMPOSE}
        )

    def test_retrieve_is_still_reserved_with_no_forward_edge_yet(self):
        """RETRIEVE (Phase 3, RAG over the pattern library) is the only
        stage still with no real wiring — DIFF got its forward edge in
        CIR-157."""
        assert FORWARD_EDGES[Stage.RETRIEVE] == frozenset()

    def test_walk_forward_to_retraverses_every_intervening_stage(self):
        """CIR-157: RESEARCH now feeds DIFF before DECOMPOSE, so the walk
        from BOUND to VERIFY passes through one more real stage than before
        DIFF had forward wiring."""
        claim = Claim(statement="x", dimension="host", stage=Stage.BOUND)
        _walk_forward_to(claim, Stage.VERIFY)
        assert claim.stage == Stage.VERIFY
        assert claim.stage_history == ["bound", "research", "diff", "decompose"]

    def test_walk_forward_to_from_decompose_is_a_single_hop(self):
        claim = Claim(statement="x", dimension="host", stage=Stage.DECOMPOSE)
        _walk_forward_to(claim, Stage.VERIFY)
        assert claim.stage == Stage.VERIFY
        assert claim.stage_history == ["decompose"]

    def test_gate_claim_done_names_the_stage_it_routes_back_to(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        path = write_claim(tmp_path, claim)
        verdict = gate_claim_done(path)
        assert verdict["stage"] == "gate"
        assert verdict["routed_to"] == "decompose"
        assert "Routing back to decompose" in verdict["message"]

    def test_gate_claim_done_honors_a_preferred_rework_stage(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        path = write_claim(tmp_path, claim)
        verdict = gate_claim_done(path, preferred_rework_stage=Stage.BOUND)
        assert verdict["routed_to"] == "bound"

    def test_gate_claim_done_rejects_a_preferred_stage_outside_its_rework_edges(self, tmp_path):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        path = write_claim(tmp_path, claim)
        with pytest.raises(InvalidStageTransition):
            gate_claim_done(path, preferred_rework_stage=Stage.RESEARCH)


class TestReworkLoop:
    def test_fully_verified_on_first_round_exits_dry_with_no_rework(self, tmp_path):
        graph = {"compaction_context": _FAKE_GRAPH["compaction_context"]}
        outcome = run_rework_loop(
            tmp_path, "compaction works everywhere", "host",
            graph_fn=lambda: graph, how_found="test",
        )
        assert outcome.dry is True
        assert outcome.cap_hit is False
        assert outcome.message is None
        assert outcome.claim.all_verified() is True
        assert outcome.claim.rework_rounds == 0
        assert len(outcome.rounds) == 1

    def test_stabilizing_without_full_resolution_exits_dry_and_lets_gate_block(self, tmp_path):
        """A round that reproduces the same unresolved set as the round
        before it has stabilized -- the loop exits (zero NEW findings),
        even though the claim is not fully verified. GATE still blocks
        "done" normally; the rework loop's job is only to stop churning."""
        outcome = run_rework_loop(
            tmp_path, "youk is agent-agnostic", "host",
            graph_fn=lambda: _FAKE_GRAPH, how_found="test",
        )
        assert outcome.dry is True
        assert outcome.cap_hit is False
        assert outcome.claim.all_verified() is False
        assert outcome.rounds[0].unresolved == ["pre_tool_guard:codex"]
        assert outcome.rounds[0].new_findings == ["pre_tool_guard:codex"]
        # Round 2 reproduces the identical unresolved set -> zero new findings -> exit.
        assert len(outcome.rounds) == 2
        assert outcome.rounds[1].new_findings == []
        assert outcome.claim.rework_rounds == 1

    def test_cap_hit_surfaces_explicit_message_and_never_declares_done(self, tmp_path):
        """A domain that keeps producing a genuinely new failing sub_claim
        every round never stabilizes -- the hard cap must stop the loop
        with an explicit message, not loop silently or claim success."""
        call_count = {"n": 0}

        def ever_growing_graph():
            call_count["n"] += 1
            hosts = {f"host-{i}": {"wired": False, "evidence": None} for i in range(call_count["n"])}
            return {"mechanism_x": {"mechanism": "mechanism_x", "hosts": hosts}}

        outcome = run_rework_loop(
            tmp_path, "ever growing claim", "host",
            graph_fn=ever_growing_graph, how_found="test",
            max_rounds=MAX_REWORK_ROUNDS,
        )

        assert outcome.cap_hit is True
        assert outcome.dry is False
        assert outcome.message is not None
        assert outcome.message.startswith(f"still unresolved after {MAX_REWORK_ROUNDS} rounds:")
        assert len(outcome.rounds) == MAX_REWORK_ROUNDS
        assert outcome.claim.all_verified() is False

    def test_rework_target_is_the_callers_choice(self, tmp_path):
        """A caller who believes the domain itself is incomplete (not just
        decomposition) can route rework to BOUND instead of the default
        DECOMPOSE -- both are valid per REWORK_EDGES[Stage.VERIFY]."""
        outcome = run_rework_loop(
            tmp_path, "youk is agent-agnostic", "host",
            graph_fn=lambda: _FAKE_GRAPH, how_found="test",
            rework_target=Stage.BOUND,
        )
        assert outcome.claim.rework_log[0]["to"] == "bound"

    def test_cap_hit_message_names_the_actual_unresolved_specifics(self, tmp_path):
        round_counter = {"n": 0}

        def graph_fn():
            round_counter["n"] += 1
            return {
                "mechanism_x": {
                    "mechanism": "mechanism_x",
                    "hosts": {
                        f"host-{round_counter['n']}": {"wired": False, "evidence": None},
                    },
                }
            }

        outcome = run_rework_loop(
            tmp_path, "distinct new failure claim", "host",
            graph_fn=graph_fn, how_found="test", max_rounds=2,
        )
        assert outcome.cap_hit is True
        assert outcome.message == "still unresolved after 2 rounds: mechanism_x:host-2"


class TestVerificationLevel:
    def test_generate_sub_claims_sets_internally_checked_not_asserted(self):
        """The scanner's grep/AST evidence is real but never leaves the
        codebase -- internally_checked, not the dataclass's own asserted
        floor and not externally_verified (CIR-157)."""
        sub_claims = generate_sub_claims("host", _FAKE_GRAPH)
        assert all(sc.verification_level == "internally_checked" for sc in sub_claims)

    def test_bare_sub_claim_defaults_to_asserted(self):
        """A SubClaim constructed with no mechanical check behind it at all
        gets the dataclass's own conservative floor."""
        sub = SubClaim(id="x:y", mechanism="x", host="y", status="unverified")
        assert sub.verification_level == "asserted"

    def test_mark_externally_verified_promotes_without_touching_status(self):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        target = next(sc for sc in claim.sub_claims if sc.id == "pre_tool_guard:codex")
        assert target.verification_level == "internally_checked"
        assert target.status == "failed"

        mark_externally_verified(claim, "pre_tool_guard:codex")

        assert target.verification_level == "externally_verified"
        assert target.status == "failed"  # status is orthogonal, untouched

    def test_mark_externally_verified_raises_for_unknown_sub_claim_id(self):
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        with pytest.raises(KeyError):
            mark_externally_verified(claim, "no-such-id")

    def test_mark_founder_confirmed_also_promotes_to_externally_verified(self):
        """A founder stating a fact directly is independent of the codebase,
        same as two external research sources agreeing -- external, not
        internal (CIR-157 DONE-MEANS)."""
        claim = build_claim("youk is agent-agnostic", "host", _FAKE_GRAPH)
        mark_founder_confirmed(claim, "pre_tool_guard:codex")
        target = next(sc for sc in claim.sub_claims if sc.id == "pre_tool_guard:codex")
        assert target.verification_level == "externally_verified"


class TestVerificationLevelMigration:
    def _write_legacy_claim_file(self, tmp_path) -> "Path":
        """A claim file shaped exactly like CIR-154/155/156's real claim
        files on disk before verification_level existed -- no key at all on
        any sub_claim."""
        claim = build_claim("compaction works everywhere", "host",
                             {"compaction_context": _FAKE_GRAPH["compaction_context"]})
        path = write_claim(tmp_path, claim)
        data = json.loads(path.read_text())
        for sc in data["sub_claims"]:
            del sc["verification_level"]
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        return path

    def test_migrate_adds_internally_checked_to_every_legacy_sub_claim(self, tmp_path):
        path = self._write_legacy_claim_file(tmp_path)
        changed = migrate_claim_file_add_verification_level(path)
        assert changed is True

        data = json.loads(path.read_text())
        assert all(sc["verification_level"] == "internally_checked" for sc in data["sub_claims"])

    def test_migrate_is_idempotent(self, tmp_path):
        path = self._write_legacy_claim_file(tmp_path)
        migrate_claim_file_add_verification_level(path)
        changed_again = migrate_claim_file_add_verification_level(path)
        assert changed_again is False

    def test_migrate_claims_dir_migrates_every_file_and_returns_the_changed_paths(self, tmp_path):
        legacy_path = self._write_legacy_claim_file(tmp_path)
        already_current = write_claim(
            tmp_path, build_claim("other claim", "host", _FAKE_GRAPH)
        )

        migrated = migrate_claims_dir(tmp_path)

        assert legacy_path in migrated
        assert already_current not in migrated

    def test_migrate_claims_dir_none_when_no_claims_directory_exists(self, tmp_path):
        assert migrate_claims_dir(tmp_path) == []
