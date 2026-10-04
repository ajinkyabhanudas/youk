"""The reversal loop used to be reachable only by importing Python modules,
which an MCP-only agent host cannot do (the self-heal skill told the agent to
call reversal_check.detect_reversals directly). These drive it through the
tool boundary the skill now names."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from test_reversal_check import (
    _REVERSING_ENTRY,
    _log_dismissed_event,
    _write_decisions_md,
)

_PROJECT = "youk"

# conftest puts both containers' src dirs on sys.path, so a bare `import server`
# can resolve to youk-code's. Load youk-core's by path.
_spec = importlib.util.spec_from_file_location(
    "youk_core_server", Path(__file__).parent.parent / "servers" / "core" / "src" / "server.py"
)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


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
    skill = (Path(__file__).parent.parent / "skills" / "self-heal" / "SKILL.md").read_text()
    assert "youk-core.detect_domain_reversals" in skill
    assert "reversal_check.detect_reversals" not in skill


# --- promotion: confirmed patterns -> cross-project store ---------------------

def _seed_two_project_group(root):
    from test_pattern_promotion import _confirmed_entry, _write_confirmed
    _write_confirmed(root, [
        _confirmed_entry("pat-youk-1", "youk", "testing", "flaky-tests",
                         "Retrying a flaky test in claude code without root-causing it hides a real bug."),
        _confirmed_entry("pat-circaid-1", "circaid", "testing", "flaky-tests",
                         "Retrying a flaky test in mcp without root-causing it hides a real bug."),
    ])


def test_promotion_runs_through_the_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    _seed_two_project_group(tmp_path)
    found = server.find_pattern_promotion_candidates()
    assert found["count"] == 1
    g = found["groups"][0]
    assert g["projects"] == ["circaid", "youk"] and sorted(g["pattern_ids"]) == ["pat-circaid-1", "pat-youk-1"]
    out = server.promote_pattern_group("testing", "flaky-tests", g["abstracted_statements"][0])
    assert out["promoted"] is True
    row = json.loads(open(out["path"]).read().splitlines()[0])
    assert row["scope"] == "global" and row["id"] == out["pattern_id"]
    assert all(p["abstracted"] for p in row["provenance"])


def test_promotion_is_refused_for_a_group_that_does_not_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    out = server.promote_pattern_group("testing", "flaky-tests", "anything")
    assert out["promoted"] is False and out["error_type"] == "BUSINESS_RULE"


def test_single_project_patterns_are_never_candidates(tmp_path, monkeypatch):
    from test_pattern_promotion import _confirmed_entry, _write_confirmed
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    _write_confirmed(tmp_path, [_confirmed_entry("only-youk", "youk", "testing", "flaky-tests",
                                                 "Retrying a flaky test in claude code hides a real bug.")])
    assert server.find_pattern_promotion_candidates()["count"] == 0
    assert server.promote_pattern_group("testing", "flaky-tests", "x")["promoted"] is False


def test_skill_has_a_promotion_step_naming_the_tools():
    skill = (Path(__file__).parent.parent / "skills" / "self-heal" / "SKILL.md").read_text()
    assert "youk-core.find_pattern_promotion_candidates" in skill
    assert "youk-core.promote_pattern_group" in skill


# --- retirement and duplicate protection --------------------------------------

def _promote_one(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    _seed_two_project_group(tmp_path)
    g = server.find_pattern_promotion_candidates()["groups"][0]
    return server.promote_pattern_group("testing", "flaky-tests", g["abstracted_statements"][0])


def test_retired_learning_leaves_contracts_md_and_retrieval(tmp_path, monkeypatch):
    import intent
    out = _promote_one(tmp_path, monkeypatch)
    contracts = tmp_path / "knowledge" / "global" / "contracts.md"
    from global_contracts import render_contracts_md
    render_contracts_md(tmp_path)
    assert "flaky test" in contracts.read_text()

    res = server.retire_global_pattern(out["pattern_id"], "contradicted by a later decision")
    assert res["retired"] is True
    assert "flaky test" not in contracts.read_text()
    assert intent._relevant_global_patterns("retry a flaky test", tmp_path / "state" / "global-patterns.jsonl") == []
    import pattern_promotion
    assert pattern_promotion.query_global_patterns(tmp_path) == []
    # append-only: the original row and the tombstone are both on disk
    rows = [json.loads(line) for line in open(res["path"]).read().splitlines()]
    assert [r["status"] for r in rows] == ["promoted", "retired"]
    assert rows[1]["retired_reason"] == "contradicted by a later decision"


def test_retire_needs_a_reason_and_a_real_id(tmp_path, monkeypatch):
    out = _promote_one(tmp_path, monkeypatch)
    assert server.retire_global_pattern(out["pattern_id"], "  ")["retired"] is False
    assert server.retire_global_pattern("nope", "why")["error_type"] == "BUSINESS_RULE"


def test_a_retired_wording_cannot_be_promoted_again(tmp_path, monkeypatch):
    # promote_group's own id is deterministic, so re-promotion hits locked_append_if_id_absent;
    # a *reworded* duplicate is what the semantic guard stops.
    import pattern_promotion
    monkeypatch.setattr(server, "YOUK_ROOT", tmp_path)
    p = tmp_path / "state" / "global-patterns.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"id": "old", "statement": "always retry a flaky test until it passes", "status": "retired",
                             "scope": "global"}) + "\n")
    import re
    import zlib

    import semantic_similarity
    class _Bag:
        def encode(self, texts):
            out = []
            for t in texts:
                v = [0.0] * 256
                for w in re.findall(r"[a-z]+", t.lower()):
                    v[zlib.crc32(w.encode()) % 256] += 1
                out.append(v)
            return out
    monkeypatch.setattr(semantic_similarity, "_model", lambda: _Bag())
    assert pattern_promotion._find_duplicate(tmp_path, "Always retry a flaky test until it passes") == "old"
    assert pattern_promotion._find_duplicate(tmp_path, "never retry a flaky test until it passes") is None
    assert pattern_promotion._find_duplicate(tmp_path, "Always retry a flaky test until it passes", own_id="old") is None
    assert pattern_promotion._find_duplicate(tmp_path, "rotate the log files weekly") is None
