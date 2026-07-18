"""Tests for CAP-7: External-review organ.

Covers:
  - Bundle contents complete: MANIFEST.md, health.json, PENDING.md, audit-tail.md, RUBRIC.md
  - MANIFEST has denominators for every rate present (R10 labels)
  - org_score unchanged with/without recent review (no score effect)
  - rubric copy matches source (adversarial-planning/SKILL.md Discriminator section)
  - _get_last_external_review_date returns correct date / NEVER
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

YOUK_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(YOUK_ROOT / "servers" / "core" / "src"))


@pytest.fixture
def review_root(tmp_path):
    """Minimal youk-style root for external review tests."""
    root = tmp_path / "youk"
    (root / "state" / "relay").mkdir(parents=True)
    (root / "knowledge" / "proposals").mkdir(parents=True)
    (root / "audit").mkdir(parents=True)
    return root


@pytest.fixture
def ap_skill_root(tmp_path):
    """Fake claude root with adversarial-planning/SKILL.md that has the rubric section."""
    croot = tmp_path / "claude"
    ap_dir = croot / "skills" / "adversarial-planning"
    ap_dir.mkdir(parents=True)
    (ap_dir / "SKILL.md").write_text(
        "# adversarial-planning\n\n"
        "Some content before.\n\n"
        "### Discriminator Grading-Rubric Template\n\n"
        "GATE {N} GRADING MEMO\n\n"
        "STATUS: APPROVED | APPROVED WITH CORRECTIONS | REJECTED\n\n"
        "\n---\n"
        "More content after.\n"
    )
    return croot


_STUB_HEALTH = {
    "org_score": 7.5,
    "sessions_analyzed": 10,
    "findings": [],
    "proposals": [],
    "developer_autonomy_rate": 0.3,
    "contract_compliance_rate": 0.9,
    "decision_durability_rate": None,
}


class TestBundleContents:
    def test_bundle_creates_all_required_files(self, review_root, ap_skill_root):
        """_build_review_bundle creates MANIFEST.md, health.json, PENDING.md, audit-tail.md, RUBRIC.md."""
        from health import _build_review_bundle

        result = _build_review_bundle(
            scope="HEALTH",
            notes="test",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        assert result.get("blocked") is not True, f"Unexpected block: {result}"

        folder = Path(result["folder_path"])
        required = {"MANIFEST.md", "health.json", "PENDING.md", "audit-tail.md", "RUBRIC.md"}
        present = {f.name for f in folder.iterdir() if f.is_file()}
        missing = required - present
        assert not missing, f"Bundle files missing: {missing}"

    def test_invalid_scope_returns_blocked(self, review_root, ap_skill_root):
        """Invalid scope is rejected without creating any files."""
        from health import _build_review_bundle

        result = _build_review_bundle(
            scope="INVALID",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        assert result.get("blocked") is True
        assert "INVALID" in result["error"]


class TestManifestR10Labels:
    def test_manifest_has_r10_block_header(self, review_root, ap_skill_root):
        """MANIFEST.md contains '## R10 Metric Block' header."""
        from health import _build_review_bundle

        result = _build_review_bundle(
            scope="HEALTH",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        manifest = (Path(result["folder_path"]) / "MANIFEST.md").read_text()
        assert "## R10 Metric Block" in manifest

    def test_manifest_rates_have_denominator_labels(self, review_root, ap_skill_root):
        """MANIFEST.md includes denominator context for each rate (R10 compliance)."""
        from health import _build_review_bundle

        health_with_rates = {
            **_STUB_HEALTH,
            "developer_autonomy_rate": 0.4,
            "contract_compliance_rate": 0.9,
            "decision_durability_rate": 0.7,
        }
        result = _build_review_bundle(
            scope="HEALTH",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=health_with_rates,
        )
        manifest = (Path(result["folder_path"]) / "MANIFEST.md").read_text()
        # Each rate must include a parenthetical denominator label
        assert "sessions" in manifest, "MANIFEST.md lacks session denominator label"
        assert "autonomy sessions" in manifest
        assert "VALIDATED retrospectives" in manifest


class TestOrgScoreUnchanged:
    def test_build_review_bundle_does_not_call_score_org(self, review_root, ap_skill_root, monkeypatch):
        """_build_review_bundle does not invoke _score_org — no score feedback loop."""
        import health as h

        score_calls = []
        original = h._score_org

        def tracked(*a, **kw):
            score_calls.append(True)
            return original(*a, **kw)

        monkeypatch.setattr(h, "_score_org", tracked)

        before = len(score_calls)
        h._build_review_bundle(
            scope="HEALTH",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        assert len(score_calls) == before, (
            "_build_review_bundle called _score_org — self-scoring problem recreated"
        )


class TestRubricCopy:
    def test_rubric_content_extracted_from_skill_file(self, review_root, ap_skill_root):
        """RUBRIC.md contains the Discriminator Grading-Rubric Template section."""
        from health import _build_review_bundle

        result = _build_review_bundle(
            scope="HEALTH",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        rubric = (Path(result["folder_path"]) / "RUBRIC.md").read_text()
        assert "Discriminator Grading-Rubric Template" in rubric
        assert "GATE {N} GRADING MEMO" in rubric

    def test_rubric_stops_at_section_boundary(self, review_root, ap_skill_root):
        """RUBRIC.md does not include content from sections after the rubric template."""
        from health import _build_review_bundle

        result = _build_review_bundle(
            scope="HEALTH",
            youk_root=review_root,
            claude_root=ap_skill_root,
            health_data=_STUB_HEALTH,
        )
        rubric = (Path(result["folder_path"]) / "RUBRIC.md").read_text()
        assert "More content after" not in rubric

    def test_last_external_review_date_never(self, review_root):
        """_get_last_external_review_date returns NEVER when no review dirs exist."""
        import health as h

        assert h._get_last_external_review_date_for_root(review_root) == "NEVER"

    def test_last_external_review_date_found(self, review_root):
        """_get_last_external_review_date returns the most recent REVIEW- date."""
        import health as h

        (review_root / "state" / "relay" / "REVIEW-2026-06-01").mkdir(parents=True)
        (review_root / "state" / "relay" / "REVIEW-2026-05-15").mkdir(parents=True)
        assert h._get_last_external_review_date_for_root(review_root) == "2026-06-01"
