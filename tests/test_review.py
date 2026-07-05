"""Tests for review.py — doc-map ref staleness, commit quality scoring."""
from __future__ import annotations
from pathlib import Path
import yaml


def _write_doc_map(docs_dir: Path) -> None:
    data = {
        "mcp_tools": {"youk-core": []},
        "src_files": [
            {"file": "servers/core/src/session.py", "refs": ["README.md", "docs/guide.md"]},
            {"file": "servers/core/src/health.py", "refs": ["README.md"]},
        ],
        "skills": [
            {"skill": "code-review", "refs": ["README.md"]},
        ],
    }
    (docs_dir / "doc-map.yaml").write_text(yaml.dump(data))


class TestStaleDocRefs:
    def test_empty_when_no_doc_map(self, youk_root):
        from review import _stale_doc_refs
        assert _stale_doc_refs(["servers/core/src/session.py"]) == []

    def test_flags_unupdated_refs(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import _stale_doc_refs
        stale = _stale_doc_refs(["servers/core/src/session.py"])
        assert "README.md" in stale
        assert "docs/guide.md" in stale

    def test_no_flag_when_all_refs_also_committed(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import _stale_doc_refs
        stale = _stale_doc_refs(["servers/core/src/session.py", "README.md", "docs/guide.md"])
        assert stale == []

    def test_partial_refs_committed(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import _stale_doc_refs
        stale = _stale_doc_refs(["servers/core/src/session.py", "README.md"])
        assert "docs/guide.md" in stale
        assert "README.md" not in stale

    def test_unrelated_file_no_refs_flagged(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import _stale_doc_refs
        assert _stale_doc_refs(["scripts/unrelated.py"]) == []

    def test_skill_dir_change_flags_refs(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import _stale_doc_refs
        stale = _stale_doc_refs(["skills/code-review/SKILL.md"])
        assert "README.md" in stale

    def test_broken_doc_map_returns_empty(self, youk_root):
        (youk_root / "docs" / "doc-map.yaml").write_text("not: valid: yaml: [broken")
        from review import _stale_doc_refs
        assert _stale_doc_refs(["servers/core/src/session.py"]) == []


class TestCheckCommitQuality:
    def test_blocks_env_file(self):
        from review import check_commit_quality
        result = check_commit_quality("add config", [".env"])
        assert result.blocked is True
        assert result.score == 0

    def test_blocks_api_key_file(self):
        from review import check_commit_quality
        result = check_commit_quality("add keys", ["config/api_key.json"])
        assert result.blocked is True

    def test_good_message_passes(self):
        from review import check_commit_quality
        result = check_commit_quality("fix auth bug to prevent session hijacking")
        assert result.blocked is False
        assert result.score >= 70

    def test_message_with_why_gets_higher_score(self):
        from review import check_commit_quality
        with_why = check_commit_quality("remove duplicate check to fix flaky test")
        without_why = check_commit_quality("remove duplicate check")
        assert with_why.score >= without_why.score

    def test_em_dash_penalised(self):
        from review import check_commit_quality
        result = check_commit_quality("fix the auth bug — it was broken")
        assert any("em dash" in v for v in result.violations)

    def test_short_message_penalised(self):
        from review import check_commit_quality
        result = check_commit_quality("fix it")
        assert result.score < 100

    def test_surfaces_stale_doc_ref(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import check_commit_quality
        result = check_commit_quality(
            "fix session state bug to prevent context loss",
            ["servers/core/src/session.py"],
        )
        assert result.blocked is False
        doc_violations = [v for v in result.violations if "Doc sync" in v]
        assert doc_violations, f"Expected doc-sync violation. Violations: {result.violations}"

    def test_no_stale_doc_violation_when_refs_committed(self, youk_root):
        _write_doc_map(youk_root / "docs")
        from review import check_commit_quality
        result = check_commit_quality(
            "fix session state bug to prevent context loss",
            ["servers/core/src/session.py", "README.md", "docs/guide.md"],
        )
        doc_violations = [v for v in result.violations if "Doc sync" in v]
        assert not doc_violations
