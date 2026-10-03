"""Tests for servers/core/src/pattern_promotion.py (Phase D of
pattern-learning-architecture-design.md -- see its "Phase D, precisely"
section).

Real scenarios, not synthetic shortcuts:
  - two real-shaped confirmed PatternEntry rows for the SAME
    (domain, sub_domain) but from two DIFFERENT real projects ('youk' and
    'circaid'), with statements abstract_claim() can confidently abstract
    (real glossary terms: "claude code", "mcp") -- confirm
    find_promotion_candidates finds that real group.
  - a second, separate (domain, sub_domain) group, also spanning two real
    projects, where one statement contains an unrecognized identifier-shaped
    term ("custom_retry_queue", not in GLOSSARY) -- confirm that group is
    dropped (confident=False refusal), never promoted, while the real match
    above is unaffected.
  - promote_group on the real match produces a real PatternEntry that
    passes PatternEntry's own validation (every provenance row
    abstracted=True, scope=global, status=promoted).
  - query_global_patterns reads back exactly what was written, with and
    without a domain/sub_domain filter.
"""
from __future__ import annotations

import json

import pytest

from pattern_entry import PatternEntry
from pattern_promotion import (
    confirmed_patterns_path,
    find_promotion_candidates,
    global_patterns_path,
    promote_group,
    query_global_patterns,
)

_DOMAIN = "testing"
_SUB_DOMAIN = "flaky-tests"
_CREATED_AT = "2026-10-03T00:00:00+00:00"

_DOMAIN_DROPPED = "payments"
_SUB_DOMAIN_DROPPED = "webhook-retry"


def _confirmed_entry(entry_id: str, project: str, domain: str, sub_domain: str, statement: str) -> dict:
    return PatternEntry(
        id=entry_id,
        scope="local",
        domain=domain,
        sub_domain=sub_domain,
        statement=statement,
        evidence_level="internally_checked",
        provenance=[
            {
                "project": project,
                "source_file": "DECISIONS.md",
                "source_id": f"2026-10-03 [{entry_id}]",
                "abstracted": False,
            }
        ],
        status="confirmed",
        created_at=_CREATED_AT,
        confirmed_count=1,
    ).to_dict()


def _write_confirmed(root, rows: list[dict]) -> None:
    path = confirmed_patterns_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


@pytest.fixture
def seeded_root(tmp_path):
    """Two real groups: one real cross-project match (abstract_claim
    confident on both members), one that must be dropped (one member's
    statement has an unrecognized identifier-shaped term)."""
    rows = [
        _confirmed_entry(
            "pat-youk-1",
            "youk",
            _DOMAIN,
            _SUB_DOMAIN,
            "Retrying a flaky test in claude code without root-causing it hides a real bug.",
        ),
        _confirmed_entry(
            "pat-circaid-1",
            "circaid",
            _DOMAIN,
            _SUB_DOMAIN,
            "Retrying a flaky test in mcp without root-causing it hides a real bug.",
        ),
        _confirmed_entry(
            "pat-youk-2",
            "youk",
            _DOMAIN_DROPPED,
            _SUB_DOMAIN_DROPPED,
            "A custom_retry_queue silently drops webhook retries after a redeploy.",
        ),
        _confirmed_entry(
            "pat-circaid-2",
            "circaid",
            _DOMAIN_DROPPED,
            _SUB_DOMAIN_DROPPED,
            "Webhook retries were silently dropped after a redeploy in mcp.",
        ),
    ]
    _write_confirmed(tmp_path, rows)
    return tmp_path


# --- find_promotion_candidates -------------------------------------------


def test_finds_real_cross_project_match(seeded_root):
    candidates = find_promotion_candidates(seeded_root)

    matches = [c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN)]
    assert len(matches) == 1
    group = matches[0]
    assert group["projects"] == {"youk", "circaid"}
    assert len(group["entries"]) == 2
    assert len(group["abstracted_statements"]) == 2
    assert "claude code" not in group["abstracted_statements"][0]
    assert "mcp" not in group["abstracted_statements"][1]


def test_drops_group_with_unconfident_abstraction(seeded_root):
    candidates = find_promotion_candidates(seeded_root)

    dropped = [
        c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN_DROPPED, _SUB_DOMAIN_DROPPED)
    ]
    assert dropped == []


def test_no_confirmed_patterns_file_returns_empty(tmp_path):
    assert find_promotion_candidates(tmp_path) == []


def test_single_project_group_never_a_candidate(tmp_path):
    _write_confirmed(
        tmp_path,
        [
            _confirmed_entry(
                "pat-solo-1",
                "youk",
                _DOMAIN,
                _SUB_DOMAIN,
                "Retrying a flaky test in claude code without root-causing it hides a real bug.",
            )
        ],
    )
    assert find_promotion_candidates(tmp_path) == []


# --- promote_group ---------------------------------------------------------


def test_promote_group_produces_valid_global_entry(seeded_root):
    candidates = find_promotion_candidates(seeded_root)
    group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN))
    chosen_statement = group["abstracted_statements"][0]

    promoted = promote_group(group, chosen_statement, root=seeded_root)

    assert promoted.scope == "global"
    assert promoted.status == "promoted"
    assert promoted.statement == chosen_statement
    assert promoted.confirmed_count == 2
    assert len(promoted.provenance) == 2
    assert {row["project"] for row in promoted.provenance} == {"youk", "circaid"}
    assert all(row["abstracted"] is True for row in promoted.provenance)

    written = global_patterns_path(seeded_root).read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 1
    assert json.loads(written[0])["id"] == promoted.id


def test_promote_group_is_deterministic(seeded_root):
    candidates = find_promotion_candidates(seeded_root)
    group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN))
    chosen_statement = group["abstracted_statements"][0]

    first = promote_group(group, chosen_statement, root=seeded_root)
    second_root_candidates = find_promotion_candidates(seeded_root)
    second_group = next(
        c for c in second_root_candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN)
    )
    second = promote_group(second_group, chosen_statement, root=seeded_root)

    assert first.id == second.id


# --- query_global_patterns ---------------------------------------------------


def test_query_global_patterns_round_trips(seeded_root):
    candidates = find_promotion_candidates(seeded_root)
    group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN))
    promoted = promote_group(group, group["abstracted_statements"][0], root=seeded_root)

    all_entries = query_global_patterns(seeded_root)
    assert len(all_entries) == 1
    assert all_entries[0].id == promoted.id
    assert all_entries[0].to_dict() == promoted.to_dict()


def test_query_global_patterns_filters_by_domain_and_sub_domain(seeded_root):
    candidates = find_promotion_candidates(seeded_root)
    group = next(c for c in candidates if (c["domain"], c["sub_domain"]) == (_DOMAIN, _SUB_DOMAIN))
    promote_group(group, group["abstracted_statements"][0], root=seeded_root)

    assert len(query_global_patterns(seeded_root, domain=_DOMAIN)) == 1
    assert len(query_global_patterns(seeded_root, domain=_DOMAIN, sub_domain=_SUB_DOMAIN)) == 1
    assert query_global_patterns(seeded_root, domain="nonexistent-domain") == []
    assert query_global_patterns(seeded_root, domain=_DOMAIN, sub_domain="nonexistent-sub") == []


def test_query_global_patterns_missing_file_returns_empty(tmp_path):
    assert query_global_patterns(tmp_path) == []
