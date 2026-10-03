"""Tests for DomainScopeEvent (Phase 1 of docs/system-observability-design.md, CIR-177).

Governed by ADR-009: no Pydantic, raise-on-malformed, no coercion -- same
discipline as test_disposition_event.py and test_pattern_entry.py. These
tests prove:
  - the real billing/PCI-DSS worked example from
    docs/problem-space-modeling-design.md's "Domain scope" section, logged
    with append_domain_scope_event, produces exactly that line, on disk,
    in a real (tmp_path-scoped) domain-scope log -- read back after
    writing, not mocked.
  - a malformed call (missing reason, empty domains list) raises before
    anything is written.
"""
from __future__ import annotations

import json

import pytest

from domain_scope_event import (
    DomainScopeEvent,
    DomainScopeValidationError,
    append_domain_scope_event,
)

# The real worked example from docs/problem-space-modeling-design.md's
# "Domain scope" section -- not a synthetic example.
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


def _valid_kwargs(**overrides) -> dict:
    kwargs = dict(
        task=_TASK,
        domains=_DOMAINS,
        timestamp="2026-10-03T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return kwargs


# --- valid construction --------------------------------------------------


def test_valid_event_constructs():
    event = DomainScopeEvent(**_valid_kwargs())
    assert event.task == _TASK
    assert event.domains == _DOMAINS


# --- guardrail: missing reason raises -------------------------------------


def test_missing_reason_raises():
    malformed = [{"domain": "financial regulation"}, _DOMAINS[1]]
    with pytest.raises(DomainScopeValidationError, match="reason"):
        DomainScopeEvent(**_valid_kwargs(domains=malformed))


def test_empty_reason_raises():
    malformed = [{"domain": "financial regulation", "reason": ""}, _DOMAINS[1]]
    with pytest.raises(DomainScopeValidationError, match="reason"):
        DomainScopeEvent(**_valid_kwargs(domains=malformed))


# --- guardrail: empty domains list raises ---------------------------------


def test_empty_domains_list_raises():
    with pytest.raises(DomainScopeValidationError, match="domains"):
        DomainScopeEvent(**_valid_kwargs(domains=[]))


def test_wrong_type_domains_raises():
    with pytest.raises(DomainScopeValidationError, match="domains"):
        DomainScopeEvent(**_valid_kwargs(domains="financial regulation"))


def test_missing_task_raises():
    with pytest.raises(DomainScopeValidationError, match="task"):
        DomainScopeEvent(**_valid_kwargs(task=""))


# --- no Pydantic -----------------------------------------------------------


def test_module_does_not_import_pydantic():
    import ast

    import domain_scope_event

    with open(domain_scope_event.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported_names = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "pydantic" not in imported_names


# --- real append + read-back, tmp_path-scoped ------------------------------


def test_append_domain_scope_event_writes_real_line_and_reads_back(tmp_path):
    log_path = tmp_path / "domain-scope-log.jsonl"

    event = append_domain_scope_event(
        task=_TASK,
        domains=_DOMAINS,
        log_path=log_path,
    )

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    written = json.loads(lines[0])
    assert written["task"] == _TASK
    assert written["domains"] == _DOMAINS
    assert "timestamp" in written
    assert event.task == _TASK
    assert event.domains == _DOMAINS


def test_logging_multiple_tasks_produces_multiple_real_lines(tmp_path):
    log_path = tmp_path / "domain-scope-log.jsonl"

    append_domain_scope_event(task=_TASK, domains=_DOMAINS, log_path=log_path)
    append_domain_scope_event(
        task="Add a chat UI for support agents.",
        domains=[
            {"domain": "UX", "reason": "real-time chat has distinct interaction patterns from request/response UIs"},
            {"domain": "cognitive science", "reason": "support-agent attention/workload affects message pacing design"},
        ],
        log_path=log_path,
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["task"] == _TASK
    assert rows[1]["task"] == "Add a chat UI for support agents."


def test_append_domain_scope_event_raises_before_writing_on_malformed_input(tmp_path):
    log_path = tmp_path / "domain-scope-log.jsonl"

    with pytest.raises(DomainScopeValidationError):
        append_domain_scope_event(
            task=_TASK,
            domains=[{"domain": "financial regulation"}],
            log_path=log_path,
        )

    assert not log_path.exists()


def test_append_domain_scope_event_raises_on_empty_domains_before_writing(tmp_path):
    log_path = tmp_path / "domain-scope-log.jsonl"

    with pytest.raises(DomainScopeValidationError):
        append_domain_scope_event(
            task=_TASK,
            domains=[],
            log_path=log_path,
        )

    assert not log_path.exists()
