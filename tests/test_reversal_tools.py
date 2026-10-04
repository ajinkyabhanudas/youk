"""The reversal loop used to be reachable only by importing Python modules,
which an MCP-only agent host cannot do (the self-heal skill told the agent to
call reversal_check.detect_reversals directly). These drive it through the
tool boundary the skill now names."""
from __future__ import annotations

import json

import server
from test_reversal_check import (
    _REVERSING_ENTRY,
    _log_dismissed_event,
    _write_decisions_md,
)

_PROJECT = "youk"


def _setup_reversal(root, monkeypatch):
    monkeypatch.setattr(server, "YOUK_ROOT", root)
    _write_decisions_md(root)
    server.detect_domain_reversals(_PROJECT)  # seed the ledger
    _log_dismissed_event(root)
    _write_decisions_md(root, extra=_REVERSING_ENTRY)


def test_loop_runs_end_to_end_through_the_tools(tmp_path, monkeypatch):
    _setup_reversal(tmp_path, monkeypatch)
    found = server.detect_domain_reversals(_PROJECT)
    assert found["count"] == 1
    out = server.confirm_domain_reversal(found["reversals"][0], "observability", "trace granularity", _PROJECT)
    assert out["confirmed"] is True
    rows = [json.loads(line) for line in open(out["path"]).read().splitlines()]
    assert [r["id"] for r in rows] == [out["pattern_id"]]
    assert rows[0]["domain"] == "observability"
    # the ledger advanced, so the same decision is not reported twice
    assert server.detect_domain_reversals(_PROJECT)["count"] == 0


def test_blank_domain_is_rejected_not_recorded(tmp_path, monkeypatch):
    _setup_reversal(tmp_path, monkeypatch)
    pair = server.detect_domain_reversals(_PROJECT)["reversals"][0]
    out = server.confirm_domain_reversal(pair, "", "x", _PROJECT)
    assert out["confirmed"] is False and out["error_type"] == "BUSINESS_RULE"


def test_malformed_reversal_is_a_business_error(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    out = server.confirm_domain_reversal({"nope": 1}, "d", "s", _PROJECT)
    assert out["confirmed"] is False and out["error_type"] == "BUSINESS_RULE"


def test_skill_names_the_tools_not_a_python_module():
    from pathlib import Path
    skill = (Path(__file__).parent.parent / "skills" / "self-heal" / "SKILL.md").read_text()
    assert "youk-core.detect_domain_reversals" in skill
    assert "reversal_check.detect_reversals" not in skill
