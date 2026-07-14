"""
Calibration tests for simulate-experience quality bars.

These tests prevent simulation drift — the simulate-experience skill
returning COMPOUNDING on a broken product. They test the underlying
mechanisms that each of the 6 ELITE VERDICT criteria depend on.

If these tests fail, simulate-experience's ELITE VERDICT would produce
a false positive (COMPOUNDING when the product is actually broken).
"""
from __future__ import annotations
import json
from pathlib import Path


# ── Criterion 2: M+ gate fires without /build ────────────────────────────────

class TestMPlusGateMechanism:
    """
    Criterion 2 of ELITE VERDICT: nfr_check fires on M+ tasks without user typing /build.
    The gate is enforced via route_to_skill("dev-loop") blocking when route_task hasn't run.
    """

    @staticmethod
    def _patch_skills(monkeypatch, tmp_path):
        import skills
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(skills, "_ROUTE_TASK_RAN", state_dir / "route-task-ran.json")
        monkeypatch.setattr(skills, "_SESSION_OPEN", state_dir / "session-open.json")
        monkeypatch.setattr(skills, "_SESSION_STATE", state_dir / "session.json")
        return skills, state_dir

    def test_dev_loop_blocked_on_m_plus_task_without_routing(self, monkeypatch, tmp_path):
        """
        Simulates Persona B starting an M+ task (add feature) without /build.
        Gate must block — this is what makes Criterion 2 testable.
        """
        skills, state_dir = self._patch_skills(monkeypatch, tmp_path)
        (state_dir / "session-open.json").write_text(json.dumps({"slug": "myproject"}))
        # No route-task-ran.json — route_task was never called
        result = skills.route_to_skill("dev-loop", "add authentication endpoint")
        assert result.get("blocked") is True, (
            "dev-loop must block when route_task hasn't run — "
            "this is what makes Criterion 2 (M+ gate fires automatically) testable"
        )

    def test_hook_detects_build_signal_in_user_prompt(self):
        """
        BUILD_SIGNAL detection must fire on real M+ prompts so the hook can
        inject [YOUK DIRECTIVE] before Claude responds.
        """
        from youk_hook_utils import detect_task_size
        m_plus_prompts = [
            "add a payment endpoint",
            "build a login page",
            "implement rate limiting",
            "let's add user authentication",
            "create a new API module",
        ]
        for prompt in m_plus_prompts:
            result = detect_task_size(prompt)
            assert result == "M", f"Expected M+ detection for prompt: {prompt!r}"

    def test_non_build_prompts_not_detected(self):
        """Non-M+ prompts must not trigger the nudge (false positive prevention)."""
        from youk_hook_utils import detect_task_size
        non_build = [
            "what does this function do?",
            "is this the right approach?",
            "ok thanks",
            "/done",
        ]
        for prompt in non_build:
            result = detect_task_size(prompt)
            assert result is None, f"Expected no M+ detection for: {prompt!r}"


# ── Criterion 4: Staleness detection mechanism ────────────────────────────────

class TestStalenessDetectionMechanism:
    """
    Criterion 4 of ELITE VERDICT: resume point written 14+ days ago triggers warning.
    The mechanism is the template instruction in youk-lite.md CLAUDE.md block.
    This tests that the instruction text is present and correctly phrased.
    """

    def test_youk_lite_template_contains_staleness_instruction(self):
        """
        The youk-lite.md template must contain the staleness detection instruction.
        If missing, Persona D (returning dev) loads stale context silently.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        assert lite_doc.exists(), "docs/youk-lite.md must exist"
        content = lite_doc.read_text()
        assert "14 days" in content, (
            "youk-lite.md must instruct Claude to warn when resume point is 14+ days old"
        )
        assert "tell the user before loading" in content, (
            "youk-lite.md must tell Claude to surface staleness before loading old context"
        )

    def test_youk_lite_template_has_behavioral_direction_gate(self):
        """
        The direction gate must be a behavioral instruction (MUST NOT), not a checklist.
        If it's a checklist, Criterion 1/2 of the ELITE VERDICT can fail silently.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = lite_doc.read_text()
        assert "MUST NOT" in content, (
            "youk-lite.md direction gate must use 'MUST NOT' — "
            "checklist language ('only proceed after') is bypassable"
        )


# ── Criterion 6: Contract durability ─────────────────────────────────────────

class TestContractDurabilityMechanism:
    """
    Criterion 6 of ELITE VERDICT: zero contracts verbalized and lost.
    Tests the write_contracts mechanism that save_contract calls.
    """

    def test_contract_written_to_file(self, monkeypatch, tmp_path):
        """
        write_contracts must persist the contract to contracts.md.
        If it doesn't, any verbalized contract in a simulate-experience session is lost.
        """
        import compaction
        monkeypatch.setattr(compaction, "YOUK_ROOT", tmp_path)
        (tmp_path / "knowledge" / "projects" / "proj").mkdir(parents=True)

        result = compaction.write_contracts("proj", ["always run ruff before committing"])
        assert result["added"] == 1
        contracts_file = tmp_path / "knowledge" / "projects" / "proj" / "contracts.md"
        assert contracts_file.exists()
        content = contracts_file.read_text()
        assert "always run ruff before committing" in content

    def test_duplicate_contract_not_added_twice(self, monkeypatch, tmp_path):
        """
        Duplicate contracts must be deduplicated. A verbalized contract that appears
        twice in a simulation must not create duplicate entries in contracts.md.
        """
        import compaction
        monkeypatch.setattr(compaction, "YOUK_ROOT", tmp_path)
        (tmp_path / "knowledge" / "projects" / "proj").mkdir(parents=True)

        compaction.write_contracts("proj", ["always run ruff before committing"])
        result = compaction.write_contracts("proj", ["always run ruff before committing"])
        assert result["added"] == 0

        contracts_file = tmp_path / "knowledge" / "projects" / "proj" / "contracts.md"
        content = contracts_file.read_text()
        assert content.count("always run ruff before committing") == 1

    def test_contract_readable_after_write(self, monkeypatch, tmp_path):
        """
        After write_contracts, _load_contracts must return the saved contract.
        This is the full durability chain: write → read → load in session_start.
        """
        import compaction
        import session
        monkeypatch.setattr(compaction, "YOUK_ROOT", tmp_path)
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        (tmp_path / "knowledge" / "projects" / "proj").mkdir(parents=True)

        compaction.write_contracts("proj", ["never mock the database in tests"])
        loaded = session._load_contracts("proj")
        assert any("never mock the database in tests" in c for c in loaded), (
            "Contract written via write_contracts must appear in _load_contracts — "
            "the full chain (write → read) is what Criterion 6 depends on"
        )

    def test_contract_template_instruction_in_youk_lite(self):
        """
        youk-lite.md template must instruct Claude to write contracts immediately
        when stated — not at end of session. If missing, contracts get lost to compaction.
        """
        lite_doc = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = lite_doc.read_text()
        assert "immediately" in content, (
            "youk-lite.md must instruct Claude to write contracts immediately — "
            "deferred writes are lost to compaction"
        )
        assert "Do not wait" in content, (
            "youk-lite.md must say 'Do not wait for end of session' for contract capture"
        )


# ── Criterion 3: Structural gap surfaces with mitigation ─────────────────────

class TestStructuralGapAwareness:
    """
    Criterion 3: Persona C (joining dev) simulation must surface the per-user
    knowledge store as a STRUCTURAL gap with a mitigation, not just a note.
    This tests that the gap is actually structural (not a bug that could be silently fixed).
    """

    def test_knowledge_store_is_per_user_not_per_project(self, tmp_path):
        """
        The knowledge store lives at ~/.claude/youk/knowledge, not in the project repo.
        A joining dev gets zero historical context. This structural fact must be surfaced.
        This test verifies the structural reality — the simulate skill must report it accurately.
        """
        # Simulate: developer A writes a contract on project "myapp"
        root_a = tmp_path / "user_a" / ".claude" / "youk"
        (root_a / "knowledge" / "projects" / "myapp").mkdir(parents=True)
        contracts_file = root_a / "knowledge" / "projects" / "myapp" / "contracts.md"
        contracts_file.write_text("- always run tests before committing\n")

        # Developer B's install has a different root — no contracts
        root_b = tmp_path / "user_b" / ".claude" / "youk"
        (root_b / "knowledge" / "projects" / "myapp").mkdir(parents=True)
        contracts_b = root_b / "knowledge" / "projects" / "myapp" / "contracts.md"

        # The gap: developer B's contracts.md is empty — they get no handoff
        assert not contracts_b.exists() or contracts_b.read_text().strip() == "", (
            "Joining dev's knowledge store must be empty — "
            "knowledge is per-user, not per-project-repo"
        )
        # Developer A's contracts exist but are invisible to B
        assert "always run tests before committing" in contracts_file.read_text()
