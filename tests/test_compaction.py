"""Tests for compaction.py — write_contracts dedup, build_brief, checkpoint."""
from __future__ import annotations
import json
from pathlib import Path


class TestWriteContracts:
    def test_creates_file_and_returns_count(self, youk_root):
        from compaction import write_contracts
        result = write_contracts("myproj", ["always run ruff before committing"])
        f = youk_root / "knowledge" / "projects" / "myproj" / "contracts.md"
        assert result["added"] == 1
        assert f.exists()
        assert "always run ruff" in f.read_text()

    def test_deduplicates_exact_match(self, youk_root):
        from compaction import write_contracts
        write_contracts("myproj", ["never skip tests"])
        result = write_contracts("myproj", ["never skip tests"])
        assert result["added"] == 0

    def test_deduplicates_with_dash_prefix(self, youk_root):
        """Contracts stored as '- rule' must deduplicate against 'rule'."""
        from compaction import write_contracts
        write_contracts("myproj", ["always use ruff"])
        result = write_contracts("myproj", ["- always use ruff"])
        assert result["added"] == 0

    def test_adds_only_new_entries(self, youk_root):
        from compaction import write_contracts
        write_contracts("myproj", ["rule A"])
        result = write_contracts("myproj", ["rule A", "rule B"])
        assert result["added"] == 1
        text = (youk_root / "knowledge" / "projects" / "myproj" / "contracts.md").read_text()
        assert "rule A" in text
        assert "rule B" in text

    def test_multiple_contracts_at_once(self, youk_root):
        from compaction import write_contracts
        result = write_contracts("myproj", ["rule X", "rule Y", "rule Z"])
        assert result["added"] == 3

    def test_detects_contradictory_contracts(self, youk_root):
        """New contract with keyword overlap triggers conflict detection."""
        from compaction import write_contracts
        write_contracts("myproj", ["always use class components for React"])
        result = write_contracts("myproj", ["prefer hook components for React"])
        # "components" and "react" overlap — should surface conflict
        assert result["conflicts"], "Expected conflict for contradicting component style"
        assert any("class components" in c for c in result["conflicts"])

    def test_no_conflicts_for_distinct_contracts(self, youk_root):
        """Unrelated contracts must not trigger conflicts."""
        from compaction import write_contracts
        write_contracts("myproj", ["always run tests before committing"])
        result = write_contracts("myproj", ["prefer short commit messages"])
        assert result["conflicts"] == []


class TestLoadSessionPlanSlugValidation:
    """_load_session_plan must reject plans from a different project slug."""

    def test_returns_plan_when_slug_matches(self, youk_root):
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["do the thing"], "slug": "myproj"})
        )
        from compaction import _load_session_plan
        result = _load_session_plan(slug="myproj")
        assert result == ["do the thing"]

    def test_returns_empty_when_slug_mismatches(self, youk_root):
        """Stale plan from a different project must be silently excluded."""
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["canopy resume point"], "slug": "canopy"})
        )
        from compaction import _load_session_plan
        result = _load_session_plan(slug="youk")
        assert result == [], "Stale slug should return empty plan, not canopy's context"

    def test_returns_plan_when_no_slug_passed(self, youk_root):
        """No-arg call (backward compat) must still return the plan."""
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["anything"], "slug": "proj"})
        )
        from compaction import _load_session_plan
        result = _load_session_plan()
        assert result == ["anything"]

    def test_build_brief_excludes_stale_slug_plan(self, youk_root, tmp_path):
        """build_brief for 'youk' must not include a plan stored for 'canopy'."""
        # Seed canopy plan
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["canopy: fix the billing flow"], "slug": "canopy"})
        )
        (youk_root / "state" / "session.json").write_text(
            json.dumps({"last_project": "canopy", "session_counter": 38})
        )
        # Seed youk contracts
        youk_proj = youk_root / "knowledge" / "projects" / "youk"
        youk_proj.mkdir(parents=True, exist_ok=True)
        (youk_proj / "contracts.md").write_text("- always run ruff before committing\n")

        from compaction import build_brief
        result = build_brief(str(tmp_path / "youk"))
        assert "canopy: fix the billing flow" not in result["brief"], (
            "Stale canopy plan must not appear in youk brief"
        )
        assert "always run ruff before committing" in result["brief"]


class TestBuildBrief:
    def _seed(self, youk_root: Path, slug: str, contracts: list[str]) -> None:
        proj_dir = youk_root / "knowledge" / "projects" / slug
        proj_dir.mkdir(parents=True, exist_ok=True)
        if contracts:
            (proj_dir / "contracts.md").write_text(
                "\n".join(f"- {c}" for c in contracts) + "\n"
            )
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["work on X"], "slug": slug})
        )
        (youk_root / "state" / "session.json").write_text(
            json.dumps({"last_project": slug, "session_counter": 3})
        )

    def test_contracts_appear_in_brief(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", ["commit format: type: why"])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "commit format: type: why" in result["brief"]
        assert result["contracts_count"] == 1

    def test_brief_has_verbatim_label(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", ["always run tests"])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "Pinned Contracts" in result["brief"]
        assert "verbatim" in result["brief"].lower() or "never summarize" in result["brief"].lower()

    def test_no_contracts_shows_placeholder(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", [])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert result["contracts_count"] == 0
        assert "none" in result["brief"].lower()

    def test_instruction_field_present(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", [])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "instruction" in result
        assert "VERBATIM" in result["instruction"] or "verbatim" in result["instruction"].lower()

    def test_writes_checkpoint(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", ["rule A"])
        from compaction import build_brief
        build_brief(str(tmp_path / "testproj"))
        checkpoint = youk_root / "state" / "session-checkpoint.json"
        assert checkpoint.exists()
        data = json.loads(checkpoint.read_text())
        assert data["slug"] == "testproj"
        assert "timestamp" in data

    def test_checkpoint_has_correct_contracts_count(self, youk_root, tmp_path):
        self._seed(youk_root, "testproj", ["rule A", "rule B"])
        from compaction import build_brief
        build_brief(str(tmp_path / "testproj"))
        data = json.loads((youk_root / "state" / "session-checkpoint.json").read_text())
        assert data["contracts_count"] == 2

    def test_checkpoint_failure_does_not_raise(self, youk_root, tmp_path, monkeypatch):
        """build_brief must never raise even if checkpoint write fails."""
        self._seed(youk_root, "testproj", [])
        import compaction
        monkeypatch.setattr(compaction, "YOUK_ROOT", Path("/nonexistent/path"))
        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "brief" in result


class TestCompactionFaithfulness:
    """Ground-truth faithfulness: contracts written must appear verbatim in the brief.

    These tests verify youk's core value prop — silent information loss during
    compaction would be undetectable by the unit tests above and catastrophic
    for the product guarantee.
    """

    def _seed(self, youk_root: Path, slug: str, contracts: list[str]) -> None:
        import json
        proj_dir = youk_root / "knowledge" / "projects" / slug
        proj_dir.mkdir(parents=True, exist_ok=True)
        if contracts:
            (proj_dir / "contracts.md").write_text(
                "\n".join(f"- {c}" for c in contracts) + "\n"
            )
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["work on X"], "slug": slug})
        )
        (youk_root / "state" / "session.json").write_text(
            json.dumps({"last_project": slug, "session_counter": 3})
        )

    def test_contracts_survive_verbatim(self, youk_root, tmp_path):
        """Every written contract must appear verbatim in the compacted brief."""
        contracts = [
            "always use TypeScript for new files",
            "never mock the database in integration tests",
            "commit format: feat/fix/chore: description",
        ]
        self._seed(youk_root, "proj", contracts)
        from compaction import build_brief
        result = build_brief(str(tmp_path / "proj"))
        brief = result["brief"]
        for contract in contracts:
            assert contract in brief, f"Contract lost in compaction: {contract!r}"

    def test_contracts_with_special_chars_survive(self, youk_root, tmp_path):
        """Contracts with quotes, colons, and braces must not be mangled."""
        contract = 'always wrap errors: raise ValueError(f"context: {e}")'
        self._seed(youk_root, "proj", [contract])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "proj"))
        assert contract in result["brief"], f"Special-char contract lost: {contract!r}"

    def test_ten_contracts_all_survive(self, youk_root, tmp_path):
        """None of 10 contracts may be silently dropped."""
        contracts = [f"rule {i}: always do thing {i}" for i in range(10)]
        self._seed(youk_root, "proj", contracts)
        from compaction import build_brief
        result = build_brief(str(tmp_path / "proj"))
        brief = result["brief"]
        missing = [c for c in contracts if c not in brief]
        assert not missing, f"Contracts silently lost in compaction: {missing}"

    def test_contracts_count_matches_actual(self, youk_root, tmp_path):
        """contracts_count in result must equal the number of lines in contracts.md."""
        contracts = ["rule A", "rule B", "rule C"]
        self._seed(youk_root, "proj", contracts)
        from compaction import build_brief
        result = build_brief(str(tmp_path / "proj"))
        assert result["contracts_count"] == 3

    def test_golden_file(self, youk_root, tmp_path):
        """Fixed input must always produce output containing these exact strings.

        This is a regression guard — if compaction.py is refactored, this test
        catches any silent change to what survives in the brief.
        """
        self._seed(youk_root, "proj", [
            "always run ruff before committing",
            "never use print() for debugging — use logging",
        ])
        from compaction import build_brief
        result = build_brief(str(tmp_path / "proj"))
        brief = result["brief"]
        assert "always run ruff before committing" in brief
        assert "never use print() for debugging" in brief
        assert "Pinned Contracts" in brief


class TestTierTags:
    """Tier tags in build_brief() output — compaction-by-intent enforcement.

    Each section must carry its tier tag so Claude's auto-compaction can honor
    CONTRACT > DECISION > EXPLORATION > CLARIFICATION without needing to infer
    importance from content alone.
    """

    def _seed(self, youk_root: Path, slug: str, contracts: list[str]) -> None:
        proj_dir = youk_root / "knowledge" / "projects" / slug
        proj_dir.mkdir(parents=True, exist_ok=True)
        if contracts:
            (proj_dir / "contracts.md").write_text(
                "\n".join(f"- {c}" for c in contracts) + "\n"
            )
        (youk_root / "state" / "session-plan.json").write_text(
            json.dumps({"plan": ["work on auth"], "slug": slug})
        )
        (youk_root / "state" / "session.json").write_text(
            json.dumps({"last_project": slug, "session_counter": 1})
        )

    def test_contract_section_has_tier_tag(self, youk_root, tmp_path):
        self._seed(youk_root, "p", ["always test before commit"])
        from compaction import build_brief, TIER_CONTRACT
        brief = build_brief(str(tmp_path / "p"))["brief"]
        assert TIER_CONTRACT in brief

    def test_tier_contract_tag_on_pinned_contracts_header(self, youk_root, tmp_path):
        self._seed(youk_root, "p", ["never skip NFR check"])
        from compaction import build_brief
        brief = build_brief(str(tmp_path / "p"))["brief"]
        # Tag must appear adjacent to the Pinned Contracts section header
        idx_header = brief.find("Pinned Contracts")
        idx_tag = brief.find("[TIER:CONTRACT")
        assert idx_header != -1 and idx_tag != -1
        # Tag must be within 120 chars of the header (same line/section)
        assert abs(idx_tag - idx_header) < 120

    def test_session_state_has_decision_tier_tag(self, youk_root, tmp_path):
        self._seed(youk_root, "p", [])
        from compaction import build_brief, TIER_DECISION
        brief = build_brief(str(tmp_path / "p"))["brief"]
        assert TIER_DECISION in brief

    def test_session_plan_has_exploration_tier_tag(self, youk_root, tmp_path):
        self._seed(youk_root, "p", [])
        from compaction import build_brief, TIER_EXPLORATION
        brief = build_brief(str(tmp_path / "p"))["brief"]
        assert TIER_EXPLORATION in brief

    def test_contract_tier_tag_says_preserve_verbatim(self, youk_root, tmp_path):
        self._seed(youk_root, "p", ["always run ruff"])
        from compaction import build_brief
        brief = build_brief(str(tmp_path / "p"))["brief"]
        assert "PRESERVE VERBATIM" in brief

    def test_tier_constants_exported(self, youk_root, tmp_path):
        from compaction import TIER_CONTRACT, TIER_DECISION, TIER_EXPLORATION, TIER_CLARIFICATION
        assert "[TIER:CONTRACT" in TIER_CONTRACT
        assert "[TIER:DECISION" in TIER_DECISION
        assert "[TIER:EXPLORATION" in TIER_EXPLORATION
        assert "[TIER:CLARIFICATION" in TIER_CLARIFICATION

    def test_contract_content_still_verbatim_with_tags(self, youk_root, tmp_path):
        contract = "never mutate global state in tests — use parameter threading"
        self._seed(youk_root, "p", [contract])
        from compaction import build_brief
        brief = build_brief(str(tmp_path / "p"))["brief"]
        # The contract text must survive verbatim even after tier tags added
        assert contract in brief

    def test_no_contract_section_still_has_tier_tag(self, youk_root, tmp_path):
        """Even when no contracts exist the section header must carry the CONTRACT tag."""
        self._seed(youk_root, "p", [])
        from compaction import build_brief, TIER_CONTRACT
        brief = build_brief(str(tmp_path / "p"))["brief"]
        assert TIER_CONTRACT in brief


class TestSkillHandoff:
    """Skill handoff roundtrip: write → route_to_skill reads handoff for successor.

    skills.py uses a module-level _SESSION_STATE path constant pointing to /youk/...
    We patch it to the tmp youk_root so tests remain isolated.
    """

    @staticmethod
    def _patch(monkeypatch, youk_root: Path):
        import skills
        monkeypatch.setattr(skills, "_SESSION_STATE", youk_root / "state" / "session.json")
        # skill-graph.yaml also referenced — point to real repo graph
        graph_path = Path(__file__).parent.parent / "knowledge" / "skill-graph.yaml"
        monkeypatch.setattr(skills, "_SKILL_GRAPH", graph_path)

    def test_write_handoff_saves_to_session_json(self, youk_root, monkeypatch):
        import json as _json
        self._patch(monkeypatch, youk_root)
        from skills import write_skill_handoff
        result = write_skill_handoff("nfr-check", "NFR block content here")
        assert result["saved"] is True
        state = _json.loads((youk_root / "state" / "session.json").read_text())
        assert state["pending_handoff"]["nfr-check"] == "NFR block content here"

    def test_read_and_clear_handoff_returns_content(self, youk_root, monkeypatch):
        self._patch(monkeypatch, youk_root)
        from skills import write_skill_handoff, _read_and_clear_pending_handoff
        write_skill_handoff("nfr-check", "CACHING: key=sha256, TTL=24h")
        content = _read_and_clear_pending_handoff("dev-loop")
        assert content is not None
        assert "CACHING" in content
        assert "## Handoff from nfr-check" in content

    def test_handoff_cleared_after_read(self, youk_root, monkeypatch):
        self._patch(monkeypatch, youk_root)
        from skills import write_skill_handoff, _read_and_clear_pending_handoff
        write_skill_handoff("nfr-check", "some NFR decision")
        _read_and_clear_pending_handoff("dev-loop")
        # Second read must return None — consumed once
        second = _read_and_clear_pending_handoff("dev-loop")
        assert second is None

    def test_no_handoff_returns_none(self, youk_root, monkeypatch):
        self._patch(monkeypatch, youk_root)
        from skills import _read_and_clear_pending_handoff
        result = _read_and_clear_pending_handoff("dev-loop")
        assert result is None

    def test_handoff_only_consumed_by_correct_successor(self, youk_root, monkeypatch):
        """code-review handoff must not appear for a skill that doesn't follow it."""
        self._patch(monkeypatch, youk_root)
        from skills import write_skill_handoff, _read_and_clear_pending_handoff
        write_skill_handoff("code-review", "CRITICAL: missing tenant filter")
        # nfr-check is not a successor of code-review in the graph
        result = _read_and_clear_pending_handoff("nfr-check")
        assert result is None

    def test_write_handoff_missing_session_json(self, youk_root, monkeypatch):
        """write_skill_handoff must create session.json if absent."""
        import json as _json
        self._patch(monkeypatch, youk_root)
        (youk_root / "state" / "session.json").unlink(missing_ok=True)
        from skills import write_skill_handoff
        result = write_skill_handoff("code-review", "findings block")
        assert result["saved"] is True
        state = _json.loads((youk_root / "state" / "session.json").read_text())
        assert "code-review" in state["pending_handoff"]


class TestSkillGraph:
    """Skill graph edge validation — the wiring that makes handoffs flow correctly."""

    GRAPH = Path(__file__).parent.parent / "knowledge" / "skill-graph.yaml"

    def _load_graph(self) -> dict:
        import yaml
        return yaml.safe_load(self.GRAPH.read_text())

    def test_graph_file_exists(self):
        assert self.GRAPH.exists()

    def test_nfr_check_precedes_dev_loop(self):
        g = self._load_graph()
        assert "dev-loop" in g["skills"]["nfr-check"]["precedes"]

    def test_dev_loop_precedes_code_review(self):
        g = self._load_graph()
        assert "code-review" in g["skills"]["dev-loop"]["precedes"]

    def test_code_review_precedes_security_review(self):
        g = self._load_graph()
        assert "security-review" in g["skills"]["code-review"]["precedes"]

    def test_code_review_precedes_verify(self):
        g = self._load_graph()
        assert "verify" in g["skills"]["code-review"]["precedes"]

    def test_verify_precedes_learn(self):
        g = self._load_graph()
        assert "learn" in g["skills"]["verify"]["precedes"]

    def test_all_precedes_targets_are_known_skills(self):
        """No dangling edge — every target in precedes must be a defined skill or a known lifecycle endpoint."""
        # session_end is a server MCP call, not a skill — it's a valid terminal node
        lifecycle_endpoints = {"session_end"}
        g = self._load_graph()
        known = set(g["skills"].keys()) | lifecycle_endpoints
        for skill, meta in g["skills"].items():
            for target in meta.get("precedes", []):
                assert target in known, (
                    f"skill '{skill}' precedes '{target}' which is not defined in skill-graph.yaml"
                )
