"""Tests for scripts/system_status.py (Phase 3 of
docs/system-observability-design.md, CIR-179).

Builds a real, tmp_path-scoped stage registry plus real log files written
with the same real fixtures/functions other phases' tests use
(append_domain_scope_event, append_disposition_event), rather than a
synthetic status object -- a hand-built report dict would test the
rendering logic and let real read-path bugs (wrong timestamp key, wrong
file shape) through. Never run against the real repo's own state/
directory -- same isolation discipline as every other test here.
"""
from __future__ import annotations

import json

from disposition_event import append_disposition_event
from domain_scope_event import append_domain_scope_event
from system_status import NEVER_FIRED, NO_REAL_LOG, build_report, load_stages, render_report

_TASK = "Add a billing feature that stores card tokens for repeat customers."
_DOMAINS = [
    {
        "domain": "financial regulation",
        "reason": "storing payment card data triggers PCI-DSS scope regardless of how the feature is implemented",
    },
    {
        "domain": "security",
        "reason": "token storage is a credential-storage problem, not a generic data-storage one",
    },
]


def _write_system_map(tmp_path, stages: list[dict]):
    import yaml

    path = tmp_path / "system-map.yaml"
    path.write_text(yaml.safe_dump(stages), encoding="utf-8")
    return path


def _stage(
    name,
    grounding="deterministic",
    subsystem="verification-pipeline",
    triggers_on="test trigger",
    real_log=None,
):
    return {
        "name": name,
        "grounding": grounding,
        "subsystem": subsystem,
        "triggers_on": triggers_on,
        "reads": [],
        "writes": [],
        "real_log": real_log,
    }


def test_load_stages_reads_real_yaml(tmp_path):
    stages = [_stage("a", real_log="state/a.jsonl"), _stage("b", real_log=None)]
    path = _write_system_map(tmp_path, stages)
    loaded = load_stages(path)
    assert [s["name"] for s in loaded] == ["a", "b"]


def test_stage_with_null_real_log_and_no_pairing_reports_no_real_log(tmp_path):
    """A purely-mechanical stage (grounding=deterministic) with real_log:
    null must be reported as NO_REAL_LOG, never as NEVER_FIRED -- the design
    doc's explicit distinction (unobservable by design vs. untested)."""
    stages = [_stage("mechanical_stage", grounding="deterministic", real_log=None)]
    root = tmp_path / "repo"
    root.mkdir()

    reports = build_report(root, stages)

    assert len(reports) == 1
    assert reports[0].state == NO_REAL_LOG
    assert reports[0].real_log is None


def test_stage_with_real_log_but_absent_file_is_never_fired_not_an_error(tmp_path):
    """A stage whose real_log file does not exist yet on disk is a distinct
    state from NO_REAL_LOG -- the log is designed to exist, it just hasn't
    fired yet."""
    stages = [_stage("unfired_stage", real_log="state/never-written.jsonl")]
    root = tmp_path / "repo"
    root.mkdir()
    assert not (root / "state" / "never-written.jsonl").exists()

    reports = build_report(root, stages)

    assert reports[0].state == NEVER_FIRED
    assert reports[0].entry_count == 0
    assert reports[0].last_timestamp is None


def test_never_fired_and_no_real_log_are_distinct_states_in_one_report(tmp_path):
    stages = [
        _stage("unfired_stage", grounding="deterministic", real_log="state/unfired.jsonl"),
        _stage("unobservable_stage", grounding="deterministic", real_log=None),
    ]
    root = tmp_path / "repo"
    root.mkdir()

    reports = build_report(root, stages)
    by_name = {r.name: r for r in reports}

    assert by_name["unfired_stage"].state == NEVER_FIRED
    assert by_name["unobservable_stage"].state == NO_REAL_LOG
    rendered = render_report(reports)
    assert "never fired" in rendered
    assert "no real log exists for this stage" in rendered


def test_jsonl_log_with_real_entries_reports_fired_count_and_latest_timestamp(tmp_path):
    root = tmp_path / "repo"
    log_path = root / "state" / "domain-scope-log.jsonl"
    append_domain_scope_event(task=_TASK, domains=_DOMAINS, log_path=log_path)
    append_domain_scope_event(
        task="Add a chat UI for support agents.",
        domains=[{"domain": "UX", "reason": "real-time chat has distinct interaction patterns"}],
        log_path=log_path,
    )

    stages = [
        _stage(
            "domain_scope_naming",
            grounding="llm_judgment",
            subsystem="problem-space-modeling",
            real_log="state/domain-scope-log.jsonl",
        )
    ]

    reports = build_report(root, stages)

    assert reports[0].state == "fired"
    assert reports[0].entry_count == 2
    assert reports[0].last_timestamp is not None


def test_llm_judgment_stage_surfaces_real_decision_content(tmp_path):
    """Requirement 5: for an llm_judgment stage with real entries, the
    report must surface the actual logged decisions (task + domains +
    reasons), not just a fire count -- the real drift/bias scan."""
    root = tmp_path / "repo"
    log_path = root / "state" / "domain-scope-log.jsonl"
    append_domain_scope_event(task=_TASK, domains=_DOMAINS, log_path=log_path)

    stages = [
        _stage(
            "domain_scope_naming",
            grounding="llm_judgment",
            subsystem="problem-space-modeling",
            real_log="state/domain-scope-log.jsonl",
        )
    ]

    reports = build_report(root, stages)

    assert len(reports[0].judgment_rows) == 1
    row = reports[0].judgment_rows[0]
    assert row["task"] == _TASK
    assert row["domains"] == _DOMAINS

    rendered = render_report(reports)
    assert "financial regulation" in rendered
    assert "PCI-DSS" in rendered


def test_judgment_stage_with_null_real_log_pairs_to_its_real_logging_stage(tmp_path):
    """domain_edge_case_disposition_judgment's own real_log is null by
    design (the judgment itself is session output); the durable record is
    written by append_disposition_event, named in that stage's own
    triggers_on. The report must find that pairing generically and surface
    append_disposition_event's real content under the judgment stage, not
    report a false NO_REAL_LOG."""
    root = tmp_path / "repo"
    log_path = root / "state" / "disposition-log.jsonl"
    append_disposition_event(
        project="youk",
        task="Add a new trace field.",
        bounded_context="Langfuse trace granularity",
        source_file="DECISIONS.md",
        source_id="2026-08-27 [Langfuse trace granularity]",
        disposition="dismissed",
        log_path=log_path,
    )

    stages = [
        _stage(
            "domain_edge_case_disposition_judgment",
            grounding="llm_judgment",
            subsystem="problem-space-modeling",
            triggers_on="judged against the task text and assigned accepted/dismissed/ignored",
            real_log=None,
        ),
        _stage(
            "append_disposition_event",
            grounding="deterministic",
            subsystem="pattern-learning-architecture",
            triggers_on="called right after domain_edge_case_disposition_judgment decides a candidate's disposition",
            real_log="state/disposition-log.jsonl",
        ),
    ]

    reports = build_report(root, stages)
    by_name = {r.name: r for r in reports}

    judgment_report = by_name["domain_edge_case_disposition_judgment"]
    assert judgment_report.state == "fired"
    assert judgment_report.judgment_via == "append_disposition_event"
    assert len(judgment_report.judgment_rows) == 1
    assert judgment_report.judgment_rows[0]["disposition"] == "dismissed"


def test_judgment_stage_with_no_pairing_and_null_real_log_reports_no_real_log(tmp_path):
    """A real registry gap (e.g. challenge_lens3_external_evidence): no
    sibling stage's triggers_on names it, so no pairing exists -- this must
    report NO_REAL_LOG, never a fabricated fired/never-fired status."""
    stages = [
        _stage(
            "challenge_lens3_external_evidence",
            grounding="llm_judgment",
            subsystem="problem-space-modeling",
            triggers_on="reads what research found before asserting a hidden-assumption objection",
            real_log=None,
        )
    ]
    root = tmp_path / "repo"
    root.mkdir()

    reports = build_report(root, stages)

    assert reports[0].state == NO_REAL_LOG
    assert reports[0].judgment_rows == []


def test_domain_brief_single_json_object_shape(tmp_path):
    """state/domain-brief.json is a single JSON object, not a JSONL log --
    'fired' means the file exists with a real generated_at, not a row count."""
    root = tmp_path / "repo"
    brief_path = root / "state" / "domain-brief.json"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(
        json.dumps({"project": "youk", "generated_at": "2026-10-03T00:00:00+00:00", "sources": []}),
        encoding="utf-8",
    )

    stages = [_stage("build_domain_brief", real_log="state/domain-brief.json")]

    reports = build_report(root, stages)

    assert reports[0].state == "fired"
    assert reports[0].entry_count == 1
    assert reports[0].last_timestamp == "2026-10-03T00:00:00+00:00"


def test_domain_brief_missing_file_is_never_fired(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    stages = [_stage("build_domain_brief", real_log="state/domain-brief.json")]

    reports = build_report(root, stages)

    assert reports[0].state == NEVER_FIRED


def test_claims_directory_shape_counts_files_and_uses_mtime(tmp_path):
    """state/verification-contracts/claims/ is a DIRECTORY of per-claim JSON
    files with no top-level timestamp field in their own content -- the
    report must count real files and fall back to file mtime for
    'most recent', not error or treat the directory as a JSONL log."""
    root = tmp_path / "repo"
    claims_dir = root / "state" / "verification-contracts" / "claims"
    claims_dir.mkdir(parents=True)
    (claims_dir / "claim-one.json").write_text(
        json.dumps({"statement": "x", "dimension": "host", "sub_claims": []}), encoding="utf-8"
    )
    (claims_dir / "claim-two.json").write_text(
        json.dumps({"statement": "y", "dimension": "host", "sub_claims": []}), encoding="utf-8"
    )

    stages = [_stage("generate_sub_claims", real_log="state/verification-contracts/claims/")]

    reports = build_report(root, stages)

    assert reports[0].state == "fired"
    assert reports[0].entry_count == 2
    assert reports[0].last_timestamp is not None


def test_claims_directory_absent_is_never_fired_not_an_error(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    stages = [_stage("generate_sub_claims", real_log="state/verification-contracts/claims/")]

    reports = build_report(root, stages)

    assert reports[0].state == NEVER_FIRED
    assert reports[0].entry_count == 0


def test_malformed_jsonl_line_is_skipped_not_fatal(tmp_path):
    root = tmp_path / "repo"
    log_path = root / "state" / "events.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        '{"claim_id": "c1", "stage": "bound", "outcome": "advance", "timestamp": "2026-10-01T00:00:00+00:00"}\n'
        "not valid json\n"
        '{"claim_id": "c2", "stage": "bound", "outcome": "advance", "timestamp": "2026-10-02T00:00:00+00:00"}\n',
        encoding="utf-8",
    )

    stages = [_stage("bound", real_log="state/events.jsonl")]

    reports = build_report(root, stages)

    assert reports[0].entry_count == 2
    assert reports[0].last_timestamp == "2026-10-02T00:00:00+00:00"


def test_render_report_groups_by_subsystem_and_includes_summary_counts(tmp_path):
    stages = [
        _stage("a", subsystem="verification-pipeline", real_log="state/a.jsonl"),
        _stage("b", subsystem="problem-space-modeling", real_log=None),
    ]
    root = tmp_path / "repo"
    root.mkdir()

    reports = build_report(root, stages)
    rendered = render_report(reports)

    assert "verification-pipeline" in rendered
    assert "problem-space-modeling" in rendered
    assert "1 never fired" in rendered
    assert "1 no real log" in rendered


def test_real_system_map_produces_a_report_for_every_stage():
    """Runs against this repo's real docs/system-map.yaml (not a fixture),
    against an isolated empty tmp root so no real production state/ is
    touched -- proves the real registry's shapes (including the two
    special-cased real_log paths) all parse without error."""
    import tempfile
    from pathlib import Path

    stages = load_stages()
    assert len(stages) >= 29

    with tempfile.TemporaryDirectory() as tmp:
        reports = build_report(Path(tmp), stages)

    assert len(reports) == len(stages)
    states = {r.state for r in reports}
    assert states <= {"fired", NEVER_FIRED, NO_REAL_LOG}
