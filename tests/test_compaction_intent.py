"""Tests for compaction by intent and skill handoff verification."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_brief(youk_root: Path, tmp_path: Path, slug: str = "testproj") -> None:
    """Minimal state needed for build_brief() to run without error."""
    proj_dir = youk_root / "knowledge" / "projects" / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "contracts.md").write_text("- always run ruff\n")
    (youk_root / "state" / "session-plan.json").write_text(
        json.dumps({"plan": ["build the thing"], "slug": slug})
    )
    (youk_root / "state" / "session.json").write_text(
        json.dumps({"last_project": slug, "session_counter": 5})
    )


# ---------------------------------------------------------------------------
# Part A — Compaction by intent (session-goal.json → DECISION tier in brief)
# ---------------------------------------------------------------------------

class TestCompactionIntent:
    def test_goal_present_appears_in_brief(self, youk_root, tmp_path):
        _seed_brief(youk_root, tmp_path)
        (youk_root / "state" / "session-goal.json").write_text(json.dumps({
            "success_criteria": "skill_reentry wired and tested",
            "observable_outcome": "write_skill_handoff returns reentry_suggestion",
        }))

        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "skill_reentry wired and tested" in result["brief"]

    def test_goal_absent_no_section(self, youk_root, tmp_path):
        _seed_brief(youk_root, tmp_path)
        # No session-goal.json written

        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "Session goal" not in result["brief"]

    def test_goal_uses_decision_tier_marker(self, youk_root, tmp_path):
        _seed_brief(youk_root, tmp_path)
        (youk_root / "state" / "session-goal.json").write_text(json.dumps({
            "success_criteria": "all 5 L9 PRs merged",
        }))

        from compaction import build_brief
        from compaction import TIER_DECISION
        result = build_brief(str(tmp_path / "testproj"))
        assert TIER_DECISION in result["brief"]
        # Confirm goal section uses the DECISION tier tag
        brief = result["brief"]
        goal_idx = brief.find("Session goal")
        tier_idx = brief.find(TIER_DECISION, goal_idx)
        assert goal_idx != -1 and tier_idx != -1 and tier_idx < goal_idx + 80

    def test_observable_outcome_included_when_present(self, youk_root, tmp_path):
        _seed_brief(youk_root, tmp_path)
        (youk_root / "state" / "session-goal.json").write_text(json.dumps({
            "success_criteria": "PR-5 merged",
            "observable_outcome": "full suite passes at 79%+",
        }))

        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "full suite passes at 79%+" in result["brief"]

    def test_empty_success_criteria_omits_section(self, youk_root, tmp_path):
        _seed_brief(youk_root, tmp_path)
        (youk_root / "state" / "session-goal.json").write_text(json.dumps({
            "success_criteria": "",
        }))

        from compaction import build_brief
        result = build_brief(str(tmp_path / "testproj"))
        assert "Session goal" not in result["brief"]


# ---------------------------------------------------------------------------
# Part B — Skill handoff end-to-end: nfr-check → dev-loop
# ---------------------------------------------------------------------------

class TestSkillHandoffFlow:
    """
    Verifies that write_skill_handoff("nfr-check", content) correctly flows
    into route_to_skill("dev-loop") via _read_and_clear_pending_handoff.

    These tests call the functions directly against a temp session.json to avoid
    requiring the MCP server or skill-graph.yaml at /youk/knowledge/.
    """

    def _make_graph(self, tmp_path: Path) -> Path:
        """Write a minimal skill-graph.yaml where nfr-check precedes dev-loop."""
        graph = {
            "skills": {
                "nfr-check": {"precedes": ["dev-loop"], "follows": []},
                "dev-loop": {"precedes": [], "follows": ["nfr-check"]},
            }
        }
        f = tmp_path / "skill-graph.yaml"
        f.write_text(yaml.dump(graph))
        return f

    def test_handoff_flows_from_nfr_to_dev_loop(self, tmp_path, monkeypatch):
        import skills

        session_file = tmp_path / "session.json"
        graph_file = self._make_graph(tmp_path)

        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)
        monkeypatch.setattr(skills, "_SKILL_GRAPH", graph_file)

        # Write handoff from nfr-check
        result = skills.write_skill_handoff("nfr-check", "RETRY: max 3, idempotent=yes")
        assert result["saved"] is True

        # Read and clear — simulates what route_to_skill("dev-loop") does internally
        handoff = skills._read_and_clear_pending_handoff("dev-loop")
        assert handoff is not None
        assert "nfr-check" in handoff
        assert "RETRY" in handoff

    def test_handoff_cleared_after_consumption(self, tmp_path, monkeypatch):
        import skills

        session_file = tmp_path / "session.json"
        graph_file = self._make_graph(tmp_path)

        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)
        monkeypatch.setattr(skills, "_SKILL_GRAPH", graph_file)

        skills.write_skill_handoff("nfr-check", "NFR block content")
        # First read consumes it
        skills._read_and_clear_pending_handoff("dev-loop")
        # Second read returns None
        second = skills._read_and_clear_pending_handoff("dev-loop")
        assert second is None

    def test_unrelated_skill_does_not_receive_handoff(self, tmp_path, monkeypatch):
        import skills

        session_file = tmp_path / "session.json"
        graph_file = self._make_graph(tmp_path)

        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)
        monkeypatch.setattr(skills, "_SKILL_GRAPH", graph_file)

        skills.write_skill_handoff("nfr-check", "NFR block content")
        # code-review does not follow nfr-check in this graph
        handoff = skills._read_and_clear_pending_handoff("code-review")
        assert handoff is None
        # And nfr-check handoff is still present (not consumed)
        state = json.loads(session_file.read_text())
        assert "nfr-check" in state.get("pending_handoff", {})
