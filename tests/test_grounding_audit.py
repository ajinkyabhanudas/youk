"""Grounding, vendor-neutrality and gate behaviour found wanting in the
2026-10-04 audit. Each test fails on the code as it was before the fix."""
from __future__ import annotations

import json
import re
import subprocess
import zlib

import pytest

import intent
import semantic_similarity
from inference import AnthropicIntentProvider, GenerationResult, InferenceCapability, InferenceStatus
from sizing_decision import find_similar_sizing_precedents, log_sizing_decision


class _BagModel:
    """Deterministic stand-in for the sentence-embedding model: word-count
    vectors. Lets retrieval logic be tested without the real weights."""

    def encode(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 256
            for w in re.findall(r"[a-z]+", t.lower()):
                v[zlib.crc32(w.encode()) % 256] += 1
            out.append(v)
        return out


@pytest.fixture
def bag_model(monkeypatch):
    monkeypatch.setattr(semantic_similarity, "_model", lambda: _BagModel())


def _log(path, task, resolved="L", llm="", mismatch=False):
    log_sizing_decision(task=task, deterministic_size=resolved, llm_estimated_size=llm,
                        resolved_size=resolved, mismatch_flag=mismatch, log_path=path)


# --- goal 1: retrieval grounding ------------------------------------------------

def test_unrelated_history_is_not_presented_as_precedent(bag_model, tmp_path):
    log = tmp_path / "s.jsonl"
    _log(log, "rotate the log files weekly", "XS")
    assert find_similar_sizing_precedents("design a new architecture for the payment system", log_path=log) == []
    block, info = intent._sizing_grounding("design a new architecture for the payment system",
                                           log_path=log, brief_path=tmp_path / "none.json")
    assert block == "" and info["status"] == "no_evidence"


def test_relevant_precedent_is_kept_and_duplicates_collapse(bag_model, tmp_path):
    log = tmp_path / "s.jsonl"
    for _ in range(3):
        _log(log, "design a new architecture for the payment system", "L")
    _log(log, "rotate the log files weekly", "XS")
    found = find_similar_sizing_precedents("redesign the architecture for the billing system", log_path=log)
    assert [f["task"] for f in found] == ["design a new architecture for the payment system"]


def test_past_model_undersizing_is_fed_back_into_the_prompt(bag_model, tmp_path):
    log = tmp_path / "s.jsonl"
    _log(log, "design a new architecture for the payment system", "L", llm="S", mismatch=True)
    block, info = intent._sizing_grounding("redesign the architecture for the billing system",
                                           log_path=log, brief_path=tmp_path / "none.json")
    assert "the model first estimated S; keyword scoring raised it" in block
    assert info == {"status": "grounded", "precedent_count": 1, "domain_invariant_count": 0, "lesson_count": 0}


def test_retrieval_failure_is_reported_not_silent(monkeypatch, tmp_path):
    def boom():
        raise ModuleNotFoundError("sentence_transformers")
    monkeypatch.setattr(semantic_similarity, "_model", boom)
    log = tmp_path / "s.jsonl"
    _log(log, "design a new architecture for the payment system")
    block, info = intent._sizing_grounding("redesign the architecture", log_path=log,
                                           brief_path=tmp_path / "none.json")
    assert block == "" and info["status"] == "unavailable"


# --- goal 6: domain brief reaches the sizing/scope call -------------------------

def _brief(tmp_path):
    p = tmp_path / "domain-brief.json"
    p.write_text(json.dumps({"project": "proj", "bounded_contexts": [{
        "name": "contract promotion",
        "ubiquitous_language": ["contract", "promotion", "global"],
        "invariants": [{"statement": "Global contracts never overwrite project contracts.",
                        "source_file": "DECISIONS.md", "source_id": "D-12"}],
    }]}))
    return p


def test_domain_invariants_reach_the_prompt_only_when_vocabulary_overlaps(tmp_path):
    brief = _brief(tmp_path)
    block, info = intent._sizing_grounding("change how contract promotion works",
                                           log_path=tmp_path / "none.jsonl", brief_path=brief, project_slug="proj")
    assert "Global contracts never overwrite project contracts. (D-12)" in block
    assert info["domain_invariant_count"] == 1 and info["status"] == "grounded"
    block, info = intent._sizing_grounding("tweak button colours", log_path=tmp_path / "none.jsonl",
                                           brief_path=brief, project_slug="proj")
    assert block == "" and info["domain_invariant_count"] == 0


def test_domain_context_still_works_when_the_embedding_model_is_down(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_similarity, "_model", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    log = tmp_path / "s.jsonl"
    _log(log, "anything")
    block, info = intent._sizing_grounding("change contract promotion", log_path=log, brief_path=_brief(tmp_path), project_slug="proj")
    assert info["status"] == "grounded" and "D-12" in block


def test_grounding_lands_in_the_logged_sizing_decision(tmp_path):
    log = tmp_path / "s.jsonl"
    d = log_sizing_decision(task="t", deterministic_size="M", llm_estimated_size="M", resolved_size="M",
                            mismatch_flag=False, log_path=log,
                            grounding={"status": "unavailable", "precedent_count": 0, "domain_invariant_count": 0})
    assert json.loads(log.read_text())["grounding_status"] == "unavailable" == d.grounding_status


# --- goal 4: nothing downstream of the adapter sees a vendor response ----------

class _FakeProvider:
    capability = InferenceCapability("other-vendor", "m1", InferenceStatus.AVAILABLE, "ok")

    def generate(self, system, user, max_tokens):
        self.user = user
        return GenerationResult(text='{"problem": "p", "estimated_size": "M"}', input_tokens=5, output_tokens=7)


def test_optimize_intent_runs_on_a_non_anthropic_result(monkeypatch, tmp_path):
    provider = _FakeProvider()
    monkeypatch.setattr(intent, "_PROVIDER", provider)
    monkeypatch.setattr(intent, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(intent, "YOUK_ROOT", tmp_path)
    result = intent.optimize_intent("rework the retry behaviour of the uploader")
    assert result["mode"] == "api_optimized" and result["estimated_size"] == "M"
    assert result["grounding"]["status"] == "no_evidence"


def test_anthropic_adapter_normalises_its_response(monkeypatch):
    class _Block:
        text = "hello"

    class _Usage:
        input_tokens, output_tokens = 11, 3

    class _Msg:
        content, usage = [_Block()], _Usage()

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                return _Msg()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    p = AnthropicIntentProvider("m")
    p._client = _Client()
    assert p.generate("s", "u", 10) == GenerationResult("hello", 11, 3)


# --- goal 2: doc-registration gate against a real git repo ---------------------

def _repo(path, with_map=True, tracked=()):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if with_map:
        (path / "docs").mkdir()
        (path / "docs" / "doc-map.yaml").write_text("src_files: []\n")
    for rel in tracked:
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text("x")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=a@b", "-c", "user.name=n",
                    "commit", "-qm", "i", "--allow-empty"], check=True)


def test_new_file_in_new_untracked_directory_is_seen(youk_root, tmp_path):
    import session
    _repo(tmp_path)
    (tmp_path / "servers" / "fresh").mkdir(parents=True)
    (tmp_path / "servers" / "fresh" / "mod.py").write_text("x")
    result = session.task_checkpoint(str(tmp_path), "add mod", size="M")
    assert result["doc_registration_gap"] == ["servers/fresh/mod.py"]


def test_project_without_a_doc_map_is_not_judged_by_one(youk_root, tmp_path):
    import session
    _repo(tmp_path, with_map=False, tracked=["servers/api/handler.py"])
    (tmp_path / "servers" / "api" / "handler.py").write_text("changed")
    result = session.task_checkpoint(str(tmp_path), "edit handler", size="M")
    assert "doc_registration_gap" not in result and "doc_registration_error" not in result


def test_gate_failure_is_surfaced_not_swallowed(youk_root, tmp_path, monkeypatch):
    import session
    _repo(tmp_path)
    monkeypatch.setattr(session, "_touched_files", lambda p: (_ for _ in ()).throw(RuntimeError("git gone")))
    result = session.task_checkpoint(str(tmp_path), "t", size="M")
    assert result["doc_registration_error"] == "RuntimeError: git gone"


# --- goal 3: sizing must not inflate a small task via substring hits -----------

def _real_routes():
    import yaml
    from pathlib import Path
    return yaml.safe_load((Path(__file__).parent.parent / "config" / "routes.yaml").read_text())


@pytest.mark.parametrize("task", [
    "update the padding on the settings page",
    "change the address field label",
])
def test_signal_inside_a_longer_word_does_not_inflate_size(task):
    import routing
    assert routing._score_size(task, _real_routes()).value in ("XS", "S")


@pytest.mark.parametrize("task", ["add a button", "adding a button to the form", "added a retry"])
def test_inflected_signal_still_matches(task):
    import routing
    assert routing._score_size(task, _real_routes()).value == "M"


# --- goal 5: the sizing log is read back by /health ----------------------------

def _rows(tmp_path, specs):
    log = tmp_path / "state" / "sizing-decisions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    for i, (status, llm, mismatch) in enumerate(specs):
        log_sizing_decision(task=f"t{i}", deterministic_size="M", llm_estimated_size=llm,
                            resolved_size="M", mismatch_flag=mismatch, log_path=log,
                            grounding={"status": status} if status else None)


def test_health_reports_cold_estimates(tmp_path):
    import health
    _rows(tmp_path, [("unavailable", "S", False)] * 4 + [("grounded", "M", False)] * 2)
    out = health._sizing_grounding_findings(tmp_path)
    assert len(out) == 1 and "4 of the last 6" in out[0] and "cold guesses" in out[0]


def test_health_reports_frequent_model_undersizing(tmp_path):
    import health
    _rows(tmp_path, [("grounded", "S", True)] * 3 + [("grounded", "M", False)] * 3)
    assert any("3 of the last 6" in f and "below" in f for f in health._sizing_grounding_findings(tmp_path))


def test_health_is_quiet_with_little_or_healthy_data(tmp_path):
    import health
    assert health._sizing_grounding_findings(tmp_path) == []
    _rows(tmp_path, [("unavailable", "S", True)] * 2)  # under min_rows
    assert health._sizing_grounding_findings(tmp_path) == []
    _rows(tmp_path, [("grounded", "M", False)] * 8)
    assert health._sizing_grounding_findings(tmp_path) == []


# --- failures that used to vanish -----------------------------------------------

def test_touched_files_propagates_a_git_failure(tmp_path, monkeypatch):
    import git_context

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("git", 5)
    monkeypatch.setattr(git_context.subprocess, "run", boom)
    with pytest.raises(subprocess.TimeoutExpired):
        git_context._touched_files(str(tmp_path))


def test_touched_files_for_a_non_repo_is_empty_not_an_error(tmp_path):
    import git_context
    assert git_context._touched_files(str(tmp_path)) == []


def test_unlogged_sizing_decision_is_reported_and_routing_still_works(youk_root, monkeypatch, capsys):
    import routing
    import sizing_decision

    def boom(**kw):
        raise OSError("disk full")
    monkeypatch.setattr(sizing_decision, "log_sizing_decision", boom)
    decision = routing.route_task("fix a typo in the readme")
    assert decision is not None
    assert "sizing decision not logged (OSError: disk full)" in capsys.readouterr().err


def test_a_brief_for_another_or_unknown_project_is_not_used(tmp_path):
    brief = _brief(tmp_path)
    for slug in ("someone-elses-project", ""):
        block, info = intent._sizing_grounding("change contract promotion", log_path=tmp_path / "none.jsonl",
                                               brief_path=brief, project_slug=slug)
        assert block == "" and info["domain_invariant_count"] == 0


# --- reusable learnings: promoted lessons are retrieved per task ----------------

def _patterns(tmp_path, statements, scope="global"):
    p = tmp_path / "global-patterns.jsonl"
    p.write_text("".join(json.dumps({"scope": scope, "statement": s}) + "\n" for s in statements))
    return p


def test_relevant_lessons_reach_the_prompt_and_unrelated_ones_do_not(bag_model, tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_similarity, "LESSON_RELEVANCE_FLOOR", 0.3)
    patterns = _patterns(tmp_path, [
        "retry logic for the file uploader needs a backoff cap",
        "rotate secrets quarterly",
    ])
    block, info = intent._sizing_grounding(
        "add retry logic to the file uploader", log_path=tmp_path / "none.jsonl",
        brief_path=tmp_path / "none.json", patterns_path=patterns,
    )
    assert "retry logic for the file uploader needs a backoff cap" in block
    assert "rotate secrets" not in block
    assert info["lesson_count"] == 1 and info["status"] == "grounded"


def test_only_global_promoted_lessons_are_used_and_duplicates_collapse(bag_model, tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_similarity, "LESSON_RELEVANCE_FLOOR", 0.3)
    p = tmp_path / "global-patterns.jsonl"
    rows = [{"scope": "local", "statement": "retry logic for the uploader"},
            {"scope": "global", "statement": "Retry logic for the uploader"},
            {"scope": "global", "statement": "retry logic for the uploader"}]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    found = intent._relevant_global_patterns("add retry logic to the uploader", p)
    assert [r["statement"] for r in found] == ["Retry logic for the uploader"]


def test_no_patterns_file_is_a_normal_state_not_an_unavailable_one(tmp_path):
    block, info = intent._sizing_grounding(
        "anything", log_path=tmp_path / "none.jsonl", brief_path=tmp_path / "none.json",
        project_slug="", patterns_path=tmp_path / "missing.jsonl",
    )
    assert block == "" and info["status"] == "no_evidence"


def test_lesson_count_is_logged(tmp_path):
    log = tmp_path / "s.jsonl"
    log_sizing_decision(task="t", deterministic_size="M", llm_estimated_size="M", resolved_size="M",
                        mismatch_flag=False, log_path=log,
                        grounding={"status": "grounded", "lesson_count": 2})
    assert json.loads(log.read_text())["lesson_count"] == 2


# --- promoted lessons record the projects they actually came from ---------------

def _project_contracts(root, files):
    for name, lines in files.items():
        d = root / "knowledge" / "projects" / name
        d.mkdir(parents=True)
        (d / "contracts.md").write_text("# contracts\n" + "".join(f"- {ln}\n" for ln in lines))


def test_promoted_lesson_records_its_real_source_projects(bag_model, tmp_path):
    from global_contracts import promote_to_global_contracts
    _project_contracts(tmp_path, {
        "alpha": ["always run the tests before committing"],
        "beta": ["always run the tests before committing code"],
        "gamma": ["plan the quarterly roadmap in january"],
    })
    out = promote_to_global_contracts(["always run the tests before committing"], tmp_path, "testing", "ci")
    assert out["promoted"] == 1
    row = json.loads((tmp_path / "state" / "global-patterns.jsonl").read_text().splitlines()[0])
    assert sorted(p["project"] for p in row["provenance"]) == ["alpha", "beta"]
    assert row["confirmed_count"] == 2


def test_unknown_source_is_recorded_as_unknown_with_a_zero_count(bag_model, tmp_path):
    from global_contracts import promote_to_global_contracts
    promote_to_global_contracts(["always run the tests before committing"], tmp_path, "testing", "ci")
    row = json.loads((tmp_path / "state" / "global-patterns.jsonl").read_text().splitlines()[0])
    assert row["provenance"] == [{"project": "unknown", "abstracted": True}]
    assert row["confirmed_count"] == 0


# --- session start: choose learnings by evidence, keep defaults, drop retired --

def _write_store(root, rows):
    p = root / "state" / "global-patterns.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _row(i, count, created, status="promoted"):
    return {"id": f"p{i}", "scope": "global", "status": status, "sub_domain": "s",
            "statement": f"lesson {i}", "confirmed_count": count, "created_at": created}


def test_session_start_prefers_well_supported_learnings_over_newer_ones(youk_root):
    import session
    _write_store(youk_root, [
        _row(1, 3, "2026-01-01"), _row(2, 0, "2026-09-01"), _row(3, 2, "2026-02-01"),
        _row(4, 0, "2026-10-01"),
    ])
    assert session._load_global_contracts(cap=2) == ["- [s] lesson 1", "- [s] lesson 3"]


def test_session_start_never_loads_a_retired_learning(youk_root):
    import session
    _write_store(youk_root, [_row(1, 5, "2026-01-01"), dict(_row(1, 5, "2026-01-01"), status="retired"),
                             _row(2, 1, "2026-02-01")])
    assert session._load_global_contracts(cap=5) == ["- [s] lesson 2"]


def test_default_contracts_survive_a_full_personal_store(youk_root):
    import session
    (youk_root / "knowledge").mkdir(parents=True, exist_ok=True)
    (youk_root / "knowledge" / "default-contracts.md").write_text("# d\n- default one\n- default two\n")
    _write_store(youk_root, [_row(i, 1, f"2026-0{i}-01") for i in range(1, 9)])
    out = session._load_global_contracts(cap=4)
    assert out[:2] == ["- default one", "- default two"] and len(out) == 4


def test_session_start_falls_back_to_contracts_md_without_a_store(youk_root):
    import session
    g = youk_root / "knowledge" / "global"
    g.mkdir(parents=True, exist_ok=True)
    (g / "contracts.md").write_text("# g\n- [x] one\n- [x] two\n- [x] three\n")
    assert session._load_global_contracts(cap=2) == ["- [x] two", "- [x] three"]


# --- Domain Brief for projects other than youk ----------------------------------

_DECISIONS = """# Decisions

## 2026-08-27 [Webhook retry policy]
Chose:      Retry failed webhooks three times with backoff.
Over:       Retry forever.
Because:    Endless retries hid a customer outage for a day.
Cost:       A burst outage can drop events.
"""


def test_a_brief_is_built_from_the_projects_own_decisions_and_kept_fresh(tmp_path):
    import os
    from domain_brief import project_brief_path, refresh_project_domain_brief
    youk, proj = tmp_path / "youk", tmp_path / "shop"
    proj.mkdir()
    youk.mkdir()
    assert refresh_project_domain_brief(youk, proj, "shop") == "absent"
    (proj / "DECISIONS.md").write_text(_DECISIONS)
    assert refresh_project_domain_brief(youk, proj, "shop") == "built"
    brief = json.loads(project_brief_path(youk, "shop").read_text())
    assert brief["project"] == "shop" and brief["bounded_contexts"]
    assert refresh_project_domain_brief(youk, proj, "shop") == "fresh"
    newer = project_brief_path(youk, "shop").stat().st_mtime + 10
    os.utime(proj / "DECISIONS.md", (newer, newer))
    assert refresh_project_domain_brief(youk, proj, "shop") == "built"


def test_each_project_gets_its_own_brief_file(tmp_path):
    from domain_brief import project_brief_path
    assert project_brief_path(tmp_path, "a") != project_brief_path(tmp_path, "b")
    assert project_brief_path(tmp_path, "../x/y").parent == tmp_path / "state" / "domain-briefs"


def test_sizing_uses_the_current_projects_own_brief(tmp_path, monkeypatch):
    from domain_brief import refresh_project_domain_brief
    youk, proj = tmp_path / "youk", tmp_path / "shop"
    proj.mkdir()
    youk.mkdir()
    (proj / "DECISIONS.md").write_text(_DECISIONS)
    refresh_project_domain_brief(youk, proj, "shop")
    monkeypatch.setattr(intent, "YOUK_ROOT", youk)
    task = "change the webhook retry backoff"
    block, info = intent._sizing_grounding(task, log_path=tmp_path / "none.jsonl", project_slug="shop",
                                           patterns_path=tmp_path / "none.jsonl")
    assert "Retry failed webhooks three times" in block and info["domain_invariant_count"] >= 1
    block, info = intent._sizing_grounding(task, log_path=tmp_path / "none.jsonl", project_slug="other",
                                           patterns_path=tmp_path / "none.jsonl")
    assert info["domain_invariant_count"] == 0
