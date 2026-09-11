"""Tests for the one-way Paperclip -> youk evidence feed (CIR-49).

Mocks the docker/MCP call boundary (_mcp_call) so these run without Docker.
Covers: the confirmed-by gate, dedup against an existing proposal, and the
exact arguments passed to add_proposal.
"""
from __future__ import annotations

import pytest

import paperclip_evidence_feed as feed


def _args(**overrides):
    base = dict(
        issue="CIR-39",
        skill="dev-loop",
        confirmed_by="shipped-gate",
        finding="PR claimed done with no matching commit",
        reason="dev-loop never states a commit is required before /done",
        proposed_change="Add a checklist line: commit before running /done.",
        change_type="SKILL_EDIT",
        dry_run=False,
    )
    base.update(overrides)
    return feed.argparse.Namespace(**base)


class TestGate:
    def test_rejects_empty_confirmed_by(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--confirmed-by", "  ",
                "--finding", "x",
                "--reason", "y",
                "--proposed-change", "z",
            ],
        )
        assert feed.main() == 1
        assert "confirmed-by is required" in capsys.readouterr().err

    def test_missing_confirmed_by_flag_is_argparse_error(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--finding", "x",
                "--reason", "y",
                "--proposed-change", "z",
            ],
        )
        with pytest.raises(SystemExit):
            feed.main()


class TestDedup:
    def test_skips_when_issue_already_queued(self, monkeypatch, capsys):
        calls = []

        def fake_mcp_call(tool, arguments, timeout=90):
            calls.append((tool, arguments))
            if tool == "get_proposals":
                return {"proposals": [
                    {"id": "PENDING-EXISTING", "reason": "[paperclip:CIR-39] already here", "change": ""},
                ]}
            raise AssertionError("add_proposal should not be called when a duplicate exists")

        monkeypatch.setattr(feed, "_mcp_call", fake_mcp_call)
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--confirmed-by", "shipped-gate",
                "--finding", "x",
                "--reason", "y",
                "--proposed-change", "z",
            ],
        )
        assert feed.main() == 0
        assert "PENDING-EXISTING" in capsys.readouterr().out
        assert [c[0] for c in calls] == ["get_proposals"]


class TestQueue:
    def test_calls_add_proposal_with_expected_shape(self, monkeypatch, capsys):
        calls = []

        def fake_mcp_call(tool, arguments, timeout=90):
            calls.append((tool, arguments))
            if tool == "get_proposals":
                return {"proposals": []}
            if tool == "add_proposal":
                return {"proposal_id": "PENDING-NEW"}
            raise AssertionError(f"unexpected tool {tool}")

        monkeypatch.setattr(feed, "_mcp_call", fake_mcp_call)
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--confirmed-by", "shipped-gate",
                "--finding", "PR claimed done with no matching commit",
                "--reason", "dev-loop never states a commit is required before /done",
                "--proposed-change", "Add a checklist line: commit before running /done.",
            ],
        )
        assert feed.main() == 0
        assert "PENDING-NEW" in capsys.readouterr().out

        add_calls = [c for c in calls if c[0] == "add_proposal"]
        assert len(add_calls) == 1
        _, arguments = add_calls[0]
        assert arguments["change_type"] == "SKILL_EDIT"
        assert arguments["target"] == "dev-loop"
        assert "[paperclip:CIR-39]" in arguments["title"]
        assert "[paperclip:CIR-39]" in arguments["rationale"]
        assert "shipped-gate" in arguments["rationale"]
        assert "PAPERCLIP FINDING" in arguments["content"]

    def test_errors_when_add_proposal_returns_no_id(self, monkeypatch, capsys):
        def fake_mcp_call(tool, arguments, timeout=90):
            if tool == "get_proposals":
                return {"proposals": []}
            return {}

        monkeypatch.setattr(feed, "_mcp_call", fake_mcp_call)
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--confirmed-by", "shipped-gate",
                "--finding", "x",
                "--reason", "y",
                "--proposed-change", "z",
            ],
        )
        assert feed.main() == 1
        assert "did not return a proposal_id" in capsys.readouterr().err


class TestDryRun:
    def test_dry_run_never_calls_mcp(self, monkeypatch, capsys):
        def fail_mcp_call(*a, **k):
            raise AssertionError("dry-run must not call _mcp_call")

        monkeypatch.setattr(feed, "_mcp_call", fail_mcp_call)
        monkeypatch.setattr(
            "sys.argv",
            [
                "paperclip_evidence_feed.py",
                "--issue", "CIR-39",
                "--skill", "dev-loop",
                "--confirmed-by", "shipped-gate",
                "--finding", "x",
                "--reason", "y",
                "--proposed-change", "z",
                "--dry-run",
            ],
        )
        assert feed.main() == 0
        assert "[dry-run]" in capsys.readouterr().out


class TestBuildContent:
    def test_five_part_shape(self):
        content = feed._build_content(_args())
        for heading in (
            "What happened:",
            "Proposed change:",
            "Assumption:",
            "If assumption is wrong:",
            "If we do nothing:",
        ):
            assert heading in content
