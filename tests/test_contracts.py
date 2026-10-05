"""One definition of which contracts apply (servers/shared/contracts.py).

The bug this closes: the session brief printed "Pinned Contracts: none saved" next to
"Active contract: ..." because the brief and the plan read different sources.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import contracts

REPO = Path(__file__).parent.parent


def _seed(root, project="proj", defaults=(), store=(), rendered=(), project_lines=()):
    (root / "knowledge" / "global").mkdir(parents=True, exist_ok=True)
    if defaults:
        (root / "knowledge" / "default-contracts.md").write_text(
            "# defaults\n\n" + "".join(f"- {d}\n" for d in defaults))
    if store:
        (root / "state").mkdir(parents=True, exist_ok=True)
        (root / "state" / "global-patterns.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in store))
    if rendered:
        (root / "knowledge" / "global" / "contracts.md").write_text(
            "# rendered\n" + "".join(f"- {r}\n" for r in rendered))
    if project_lines:
        d = root / "knowledge" / "projects" / project
        d.mkdir(parents=True, exist_ok=True)
        (d / "contracts.md").write_text("# p\n---\n" + "".join(f"- {p}\n" for p in project_lines))


def _row(i, count=1, status="promoted"):
    return {"id": f"p{i}", "status": status, "sub_domain": "s", "statement": f"lesson {i}",
            "confirmed_count": count, "created_at": f"2026-01-0{i}"}


class TestReading:
    def test_headings_rules_and_blanks_are_skipped(self, tmp_path):
        _seed(tmp_path, project_lines=["always run tests"])
        assert contracts.project_contracts(tmp_path, "proj") == ["- always run tests"]

    def test_missing_files_are_empty_not_errors(self, tmp_path):
        assert contracts.project_contracts(tmp_path, "none") == []
        assert contracts.global_contracts(tmp_path) == []

    def test_defaults_then_best_supported_learnings(self, tmp_path):
        _seed(tmp_path, defaults=["d1"], store=[_row(1, 0), _row(2, 5), _row(3, 2)])
        assert contracts.global_contracts(tmp_path, cap=3) == [
            "- d1", "- [s] lesson 2", "- [s] lesson 3"]

    def test_retired_learning_never_loads(self, tmp_path):
        _seed(tmp_path, store=[_row(1, 5), dict(_row(1, 5), status="retired"), _row(2, 1)])
        assert contracts.global_contracts(tmp_path) == ["- [s] lesson 2"]

    def test_rendered_file_is_the_fallback_without_a_store(self, tmp_path):
        _seed(tmp_path, rendered=["one", "two", "three"])
        assert contracts.global_contracts(tmp_path, cap=2) == ["- two", "- three"]

    def test_effective_puts_global_first_then_project(self, tmp_path):
        _seed(tmp_path, defaults=["d1"], project_lines=["p1"])
        got = contracts.effective_contracts(tmp_path, "proj")
        assert got["all"] == ["- d1", "- p1"] and got["global"] == ["- d1"]


class TestEveryConsumerAgrees:
    """Same fixture, every reader, same answer."""

    def _setup(self, youk_root):
        _seed(youk_root, project="proj", defaults=["d1", "d2"], store=[_row(1, 3), _row(2, 1)],
              project_lines=["always run tests"])
        return youk_root

    def test_session_hooks_and_brief_see_the_same_contracts(self, youk_root, tmp_path):
        root = self._setup(youk_root)
        sys.path.insert(0, str(REPO / "plugin" / "scripts"))
        import compaction
        import session
        from youk_hook_utils import load_contracts, load_global_contracts

        expected_global = contracts.global_contracts(root, 10)
        expected_project = contracts.project_contracts(root, "proj")
        assert session._load_contracts("proj") == expected_project
        assert session._load_global_contracts(10) == expected_global
        assert load_contracts(root, "proj") == expected_project
        assert load_global_contracts(root, 10) == expected_global
        brief = compaction.build_brief(str(tmp_path / "proj"))
        assert brief["verbatim_lines"] == expected_global + expected_project


class TestBriefIsNotSelfContradictory:
    def test_global_contracts_without_project_ones_does_not_say_none(self, youk_root, tmp_path):
        _seed(youk_root, defaults=["d1", "d2"])
        import compaction
        text = compaction.build_brief(str(tmp_path / "proj"))["brief"]
        assert "none saved" not in text
        assert "2 global contract(s) also apply" in text

    def test_says_none_only_when_there_are_no_contracts_at_all(self, youk_root, tmp_path):
        import compaction
        text = compaction.build_brief(str(tmp_path / "proj"))["brief"]
        assert "none saved" in text

    def test_digest_counts_every_applicable_contract(self, youk_root, tmp_path):
        _seed(youk_root, defaults=["d1"], project_lines=["p1", "p2"])
        import compaction
        assert "3 contract(s) pinned" in compaction.build_brief(str(tmp_path / "proj"))["digest"]

    def test_session_plan_no_longer_prints_a_lone_active_contract(self):
        from session import _generate_session_plan
        plan = _generate_session_plan(
            slug="t", resume_point="x", contracts=["- c1"], pending_proposals=0,
            close_cluster_missed=False, project_type="python", session_counter=10)
        assert not any(item.startswith("Active contract") for item in plan)


class TestClassification:
    def test_real_contracts_that_a_machine_can_check(self):
        for text in (
            "always run `ruff check src/ tests/ scripts/` before committing — fix any errors",
            "screenshot files from Playwright testing must never be committed.",
            "never read .env or any secrets file directly",
            "when opening a PR, always create a new feature branch — never push commits directly to main.",
            "do not use --no-verify to skip hooks",
            "Never use --legacy-peer-deps or --force to resolve a dependency conflict.",
        ):
            assert contracts.classify_contract(text) == "mechanical", text

    def test_real_contracts_that_need_judgment(self):
        for text in (
            "A branch is mergeable when every defined gate clears, not just when unit tests pass.",
            "Before stating a conclusion, ask: what is the strongest argument that this is wrong?",
            "decide everything the evidence can settle and state the call with its reasoning",
            "before every commit, run the project's own lint and format checks and its test suite",
            # false positives of the first, looser rule, from real contracts
            "Circaid never edits youk core in place. Every core change is an upstream extension point",
            "When writing a SKILL_EDIT proposal, the `content` field must be the FULL section text",
            "Client scope is a path level above session slug (`state/scopes/{scope}/sessions/{slug}/`)",
        ):
            assert contracts.classify_contract(text) == "judgment", text
