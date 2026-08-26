"""Tests for skill_reentry.py — reentry edge detection from skill-graph.yaml."""
from __future__ import annotations
import json
from pathlib import Path

import pytest
import yaml

import skill_reentry as sr


@pytest.fixture
def graph_file(tmp_path) -> Path:
    """Write a minimal skill-graph.yaml with reentry_edges for testing."""
    data = {
        "reentry_edges": {
            "code-review": [
                {
                    "to": "nfr-check",
                    "trigger": "NFR gap found",
                    "severity": "HIGH",
                    "label": "code-review-nfr-reentry",
                }
            ],
            "adversary-loop": [
                {
                    "to": "challenge",
                    "trigger": "Structural direction flaw",
                    "severity": "BLOCKING",
                    "label": "adversary-challenge-reentry",
                }
            ],
        }
    }
    f = tmp_path / "skill-graph.yaml"
    f.write_text(yaml.dump(data))
    return f


class TestEdgeCases:
    def test_missing_graph_returns_none(self, tmp_path):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=tmp_path / "nonexistent.yaml")
        assert result is None

    def test_from_skill_with_no_edges_returns_none(self, graph_file):
        result = sr.check_reentry("security-review", "HIGH", skill_graph_path=graph_file)
        assert result is None

    def test_empty_skills_run_defaults_to_empty(self, graph_file):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=graph_file)
        assert result is not None
        assert result["already_ran"] is False


class TestSeverityThreshold:
    def test_high_severity_matches_high_edge(self, graph_file):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=graph_file)
        assert result is not None
        assert result["to_skill"] == "nfr-check"

    def test_blocking_severity_matches_high_edge(self, graph_file):
        result = sr.check_reentry("code-review", "BLOCKING", skill_graph_path=graph_file)
        assert result is not None
        assert result["to_skill"] == "nfr-check"

    def test_medium_severity_below_high_edge_returns_none(self, graph_file):
        result = sr.check_reentry("code-review", "MEDIUM", skill_graph_path=graph_file)
        assert result is None

    def test_low_severity_below_high_edge_returns_none(self, graph_file):
        result = sr.check_reentry("code-review", "LOW", skill_graph_path=graph_file)
        assert result is None

    def test_blocking_edge_requires_blocking_severity(self, graph_file):
        result = sr.check_reentry("adversary-loop", "HIGH", skill_graph_path=graph_file)
        assert result is None

    def test_blocking_edge_matches_blocking_severity(self, graph_file):
        result = sr.check_reentry("adversary-loop", "BLOCKING", skill_graph_path=graph_file)
        assert result is not None
        assert result["to_skill"] == "challenge"


class TestAlreadyRan:
    def test_already_ran_true_when_to_skill_in_session(self, graph_file):
        result = sr.check_reentry(
            "code-review", "HIGH",
            skills_run_this_session=["nfr-check", "dev-loop"],
            skill_graph_path=graph_file,
        )
        assert result is not None
        assert result["already_ran"] is True

    def test_already_ran_false_when_to_skill_not_in_session(self, graph_file):
        result = sr.check_reentry(
            "code-review", "HIGH",
            skills_run_this_session=["dev-loop"],
            skill_graph_path=graph_file,
        )
        assert result is not None
        assert result["already_ran"] is False


class TestResultFields:
    def test_result_has_all_required_fields(self, graph_file):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=graph_file)
        assert result is not None
        for field in ("to_skill", "label", "trigger", "already_ran", "message"):
            assert field in result, f"Missing field: {field}"

    def test_label_and_trigger_populated(self, graph_file):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=graph_file)
        assert result is not None
        assert result["label"] == "code-review-nfr-reentry"
        assert "NFR gap" in result["trigger"]

    def test_message_contains_to_skill(self, graph_file):
        result = sr.check_reentry("code-review", "HIGH", skill_graph_path=graph_file)
        assert result is not None
        assert "nfr-check" in result["message"]


class TestInferSeverity:
    def test_blocking_detected(self):
        import skills
        assert skills._infer_severity("BLOCKING: critical issue") == "BLOCKING"

    def test_high_detected(self):
        import skills
        assert skills._infer_severity("HIGH: missing error handling") == "HIGH"

    def test_medium_fallback(self):
        import skills
        assert skills._infer_severity("some findings here") == "MEDIUM"

    def test_blocking_takes_precedence_over_high(self):
        import skills
        assert skills._infer_severity("BLOCKING and HIGH") == "BLOCKING"


class TestWriteSkillHandoff:
    def test_handoff_with_high_content_adds_reentry(self, tmp_path, monkeypatch):
        import skills
        session_file = tmp_path / "session.json"
        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)

        graph = tmp_path / "skill-graph.yaml"
        graph.write_text(yaml.dump({
            "reentry_edges": {
                "code-review": [{
                    "to": "nfr-check",
                    "trigger": "NFR gap",
                    "severity": "HIGH",
                    "label": "code-review-nfr-reentry",
                }]
            }
        }))
        monkeypatch.setattr(sr, "_DEFAULT_GRAPH", graph)

        result = skills.write_skill_handoff("code-review", "HIGH: missing error handling")
        assert result["saved"] is True
        assert "reentry_suggestion" in result
        assert result["reentry_suggestion"]["to_skill"] == "nfr-check"

    def test_handoff_with_no_severity_no_reentry(self, tmp_path, monkeypatch):
        import skills
        session_file = tmp_path / "session.json"
        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)

        graph = tmp_path / "skill-graph.yaml"
        graph.write_text(yaml.dump({
            "reentry_edges": {
                "code-review": [{
                    "to": "nfr-check",
                    "trigger": "NFR gap",
                    "severity": "HIGH",
                    "label": "code-review-nfr-reentry",
                }]
            }
        }))
        monkeypatch.setattr(sr, "_DEFAULT_GRAPH", graph)

        result = skills.write_skill_handoff("code-review", "all looks good")
        assert result["saved"] is True
        assert "reentry_suggestion" not in result

    def test_handoff_save_succeeds_even_if_reentry_graph_missing(self, tmp_path, monkeypatch):
        import skills
        session_file = tmp_path / "session.json"
        monkeypatch.setattr(skills, "_SESSION_STATE", session_file)
        monkeypatch.setattr(skills, "_STATE_WRITABLE", True)
        monkeypatch.setattr(sr, "_DEFAULT_GRAPH", tmp_path / "nonexistent.yaml")

        result = skills.write_skill_handoff("code-review", "HIGH finding")
        assert result["saved"] is True
        assert "reentry_suggestion" not in result
