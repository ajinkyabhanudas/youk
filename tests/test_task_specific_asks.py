"""Tests for CIR-150 item 3 / CIR-151: task-specific coverage templates.

CIR-150 found coverage_tree.py's _SEED_TEMPLATES are fixed and generic (security,
correctness, data, nfr) — a plan that silently drops a functional requirement the
user explicitly asked for, but which falls outside all four buckets, showed as
100% covered, because nothing tied the checklist back to the task's own stated
asks. This proves: (1) extract_task_specific_asks parses the task's own text
deterministically; (2) build_tree wires it in as a real extra branch, so an
explicitly-requested ask a builder drops surfaces as a genuine MISSING node.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from coverage_tree import (  # noqa: E402
    Coverage,
    Node,
    build_tree,
    check_mece,
    extract_task_specific_asks,
)


class TestExtractTaskSpecificAsks:
    def test_empty_task_returns_empty(self):
        assert extract_task_specific_asks("") == []
        assert extract_task_specific_asks("   ") == []

    def test_single_clause_task_returns_empty(self):
        """One ask is the whole task restated, not a checklist."""
        assert extract_task_specific_asks("fix the login bug") == []

    def test_two_asks_joined_by_and(self):
        asks = extract_task_specific_asks("add user authentication and support password reset")
        assert asks == ["add user authentication", "support password reset"]

    def test_three_asks_with_oxford_comma(self):
        asks = extract_task_specific_asks(
            "add user authentication, support password reset, and log failed login attempts"
        )
        assert asks == [
            "add user authentication",
            "support password reset",
            "log failed login attempts",
        ]

    def test_bulleted_list(self):
        task = "build the export feature:\n- support CSV format\n- support PDF format\n- email the result"
        asks = extract_task_specific_asks(task)
        assert "support CSV format" in asks
        assert "support PDF format" in asks
        assert "email the result" in asks

    def test_numbered_list(self):
        task = "1. add rate limiting\n2. add request logging\n3. add circuit breaker"
        asks = extract_task_specific_asks(task)
        assert asks == ["add rate limiting", "add request logging", "add circuit breaker"]

    def test_short_fragments_filtered_out(self):
        """Fragments under 3 words are noise (stray connectors), not real asks."""
        asks = extract_task_specific_asks("add caching, and also, support retries with backoff")
        assert all(len(a.split()) >= 3 for a in asks)

    def test_duplicate_asks_deduplicated_case_insensitively(self):
        asks = extract_task_specific_asks(
            "add user authentication and Add User Authentication and support user logout"
        )
        assert len(asks) == 2

    def test_capped_at_max_asks(self):
        clauses = [f"support feature number {i}" for i in range(20)]
        task = ", and ".join(clauses)
        asks = extract_task_specific_asks(task)
        assert len(asks) <= 8

    def test_plus_and_also_conjunctions(self):
        asks = extract_task_specific_asks(
            "migrate the billing schema also backfill existing rows plus notify the ops channel"
        )
        assert len(asks) == 3


class TestBuildTreeWiresInTaskSpecificAsks:
    def _populator_covers_everything(self, task, domain, template):
        return [Node(concept=c, covered=Coverage.COVERED) for c in template]

    def _populator_drops_one_ask(self, task, domain, template):
        """Simulates a builder whose plan silently drops one explicitly-stated ask —
        the exact failure mode CIR-150 named."""
        return [
            Node(concept=c, covered=Coverage.COVERED)
            for c in template
            if c != "support password reset"
        ]

    def test_single_clause_task_gets_no_extra_branch(self):
        tree = build_tree("fix the login bug", ["security"], self._populator_covers_everything, adversary=None)
        domains = [b.domain for b in tree.branches]
        assert "task-specific asks" not in domains
        assert len(tree.branches) == 1

    def test_multi_ask_task_gets_the_extra_branch(self):
        task = "add user authentication, support password reset, and log failed login attempts"
        tree = build_tree(task, ["security"], self._populator_covers_everything, adversary=None)
        domains = [b.domain for b in tree.branches]
        assert "task-specific asks" in domains
        branch = next(b for b in tree.branches if b.domain == "task-specific asks")
        assert {n.concept for n in branch.nodes} == {
            "add user authentication", "support password reset", "log failed login attempts",
        }

    def test_dropped_ask_silently_omitted_fails_mece_not_100_percent(self):
        """The core proof CIR-150 asked for: a plan that SILENTLY DROPS an
        explicitly-requested ask (never even mentions it, the true failure mode
        named in the ticket) fails the task-specific branch's MECE check instead
        of rendering as complete — the same mechanism that already catches an
        omitted concept on the four generic domains, now reachable for a
        task-specific ask too."""
        task = "add user authentication, support password reset, and log failed login attempts"
        tree = build_tree(task, ["security"], self._populator_drops_one_ask, adversary=None)
        branch = next(b for b in tree.branches if b.domain == "task-specific asks")
        ok, problems = check_mece(branch, extract_task_specific_asks(task))
        assert ok is False
        assert any("support password reset" in p for p in problems)

    def test_ask_explicitly_marked_missing_surfaces_in_gaps_and_render(self):
        """When the builder is honest and marks a dropped ask MISSING (rather
        than omitting it), it must show up in gaps() and in the rendered tree —
        the same guarantee the four generic domains already have."""
        task = "add user authentication, support password reset, and log failed login attempts"

        def _populator_marks_one_missing(task, domain, template):
            return [
                Node(
                    concept=c,
                    covered=Coverage.MISSING if c == "support password reset" else Coverage.COVERED,
                )
                for c in template
            ]

        tree = build_tree(task, ["security"], _populator_marks_one_missing, adversary=None)
        gap_concepts = [n.concept for _, n in tree.all_gaps()]
        assert "support password reset" in gap_concepts
        assert "GAP" in tree.render()
        assert "support password reset" in tree.render()

    def test_opt_out_via_include_task_specific_false(self):
        task = "add user authentication, support password reset, and log failed login attempts"
        tree = build_tree(
            task, ["security"], self._populator_covers_everything, adversary=None,
            include_task_specific=False,
        )
        domains = [b.domain for b in tree.branches]
        assert "task-specific asks" not in domains

    def test_adversary_still_runs_against_the_task_specific_branch(self):
        """The adversary loop must see the new branch too, not just the four
        generic domains — otherwise it's a second-class branch that never gets
        independently checked."""
        task = "add user authentication, support password reset, and log failed login attempts"
        seen_domains: list[str] = []

        def _adversary(task, branch, template):
            seen_domains.append(branch.domain)
            return []

        build_tree(task, ["security"], self._populator_covers_everything, adversary=_adversary)
        assert "task-specific asks" in seen_domains

    def test_existing_single_domain_call_sites_unaffected(self):
        """Backward-compat: existing tests/call sites pass a trivial task like 'x'
        and must see exactly the domains they asked for, no surprise branch."""
        tree = build_tree("x", ["security"], self._populator_covers_everything, adversary=None)
        assert [b.domain for b in tree.branches] == ["security"]
