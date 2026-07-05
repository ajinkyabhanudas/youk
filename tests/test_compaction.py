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
