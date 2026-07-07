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
