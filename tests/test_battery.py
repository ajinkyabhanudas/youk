"""Battery runner and analysis: dry run end to end, resume, cap, arm commands, known differences."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from test_mine_tasks import TEST_CMD, commit, git

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "sim"))
import analyze
import mine_tasks as mt
import run_battery as rb


@pytest.fixture
def battery(tmp_path):
    """A fixture repo with four verified tasks, mined to YAML, plus the repos map."""
    repo = tmp_path / "fixture"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, {"calc.py": "def add(a, b):\n    return a + b\n"}, "start the calculator")
    for name in ("sub", "mul", "div", "neg"):
        body = (repo / "calc.py").read_text() + f"\ndef {name}(a, b=0):\n    return '{name}'\n"
        commit(repo, {"calc.py": body,
                      f"tests/test_{name}.py": f"from calc import {name}\n\ndef test_{name}():\n"
                                               f"    assert {name}(1) == '{name}'\n"},
               f"Add the {name} helper so callers can use it directly")
    cfg = {"name": "fixture", "path": str(repo), "language": "python", "test_cmd": TEST_CMD}
    tasks = mt.mine_repo(cfg, limit=10)
    assert len(tasks) == 4
    tasks_dir = tmp_path / "tasks"
    for t in tasks:
        mt.write_task(t, tasks_dir)
    return {"repo": repo, "repos": {"fixture": cfg}, "tasks": mt.load_tasks(tasks_dir),
            "work": tmp_path / "work", "root": tmp_path / "root", "out": tmp_path / "r.jsonl"}


def _run(b, agent=rb.fake_agent, arms=("bare", "full", "superpowers"), k=1, cap=None):
    return rb.run_battery(b["tasks"], list(arms), k, agent, b["repos"], b["work"], b["out"],
                          b["root"], cap, 3.0, log=lambda m: None)


def _rows(b):
    return [json.loads(x) for x in b["out"].read_text().splitlines()]


class TestDryRun:
    def test_every_task_arm_and_rep_is_graded_end_to_end(self, battery):
        summary = _run(battery)
        rows = _rows(battery)
        assert summary["ran"] == len(rows) == 4 * 3
        assert {r["status"] for r in rows} == {"ok"}
        assert {r["arm"] for r in rows} == {"bare", "full", "superpowers"}
        assert all(isinstance(r["passed"], bool) for r in rows)
        # the fake agent restores the real fix or does nothing, so both outcomes occur
        assert {r["passed"] for r in rows} == {True, False}
        assert summary["spent_usd"] == round(0.10 * len(rows), 2)

    def test_a_pass_is_a_hidden_test_pass_not_the_agents_claim(self, battery):
        task = battery["tasks"][0]
        spec = rb.RunSpec(task, "superpowers", 0)   # no youk hooks to require
        nothing = lambda s, w, c: rb.AgentOutcome()  # noqa: E731  an agent that changes nothing
        row = rb.execute_run(spec, battery["repos"], battery["work"], nothing, battery["root"])
        assert row["passed"] is False

    def test_rerun_adds_nothing_and_a_larger_k_adds_only_the_new_reps(self, battery):
        _run(battery, k=1)
        assert _run(battery, k=1)["ran"] == 0
        assert _run(battery, k=2)["ran"] == 4 * 3

    def test_infrastructure_errors_are_retried_not_counted_as_done(self, battery):
        boom = lambda s, w, c: rb.AgentOutcome(status="infra_error", error="auth")  # noqa: E731
        _run(battery, agent=boom, arms=("bare",), k=1)
        rows = _rows(battery)
        assert all(r["passed"] is None and r["status"] == "infra_error" for r in rows)
        assert _run(battery, arms=("bare",), k=1)["ran"] == 4

    def test_work_dirs_are_cleaned_up(self, battery):
        _run(battery, k=1, arms=("bare",))
        assert not any((battery["work"] / "runs").glob("*"))


class TestCheckout:
    def test_agent_sees_the_parent_without_the_commits_new_tests(self, battery, tmp_path):
        task = battery["tasks"][0]
        dest = tmp_path / "co"
        rb.prepare_checkout(battery["repo"], task, dest)
        assert not (dest / task["added_tests"][0]).exists()
        assert git(dest, "rev-parse", "HEAD") == task["parent_sha"]
        rb.restore_hidden_tests(dest, task)
        assert (dest / task["hidden_tests"][0]).exists()


class TestCap:
    def test_stops_before_a_run_that_would_pass_the_cap_and_keeps_pairs_together(self, battery):
        summary = _run(battery, cap=1.0)       # $0.10 per fake run, worst case $3 reserve
        assert summary["ran"] == 0 and "cap" in summary["stopped"]

    def test_once_costs_are_known_it_uses_their_mean_not_the_worst_case(self):
        assert not rb.over_cap(0.30, [0.1, 0.1, 0.1], cap=1.0, max_run=3.0)
        assert rb.over_cap(0.95, [0.1, 0.1, 0.1], cap=1.0, max_run=3.0)
        assert rb.over_cap(0.0, [], cap=1.0, max_run=3.0)
        assert not rb.over_cap(99, [], cap=None, max_run=3.0)

    def test_order_is_rep_then_task_then_arm(self):
        tasks = [{"id": "t1"}, {"id": "t2"}]
        keys = [s.key for s in rb.plan(tasks, ["bare", "full"], 2, set())]
        assert keys[:4] == [("t1", "bare", 0), ("t1", "full", 0), ("t2", "bare", 0),
                            ("t2", "full", 0)]
        assert keys[4][2] == 1


class TestArmCommands:
    def _cmd(self, arm, tmp_path, sp=None):
        setup = rb.arm_setup(arm, tmp_path, sp)
        mcp = tmp_path / "mcp.json" if setup["mcp"] else None
        spec = rb.RunSpec({"id": "t"}, arm, 0)
        return setup, rb.agent_command(spec, setup, "fix it", "sess-1", "m1", 2.5, mcp)

    def test_bare_has_youk_hooks_but_no_tools_and_an_empty_claude_md(self, tmp_path):
        setup, cmd = self._cmd("bare", tmp_path)
        assert setup["env"] == {"YOUK_ARM": "bare"} and setup["mcp"] is None
        assert "--mcp-config" not in cmd and "--plugin-dir" in cmd
        assert (setup["config_dir"] / "CLAUDE.md").read_text() == ""

    def test_full_adds_the_youk_servers_and_the_template(self, tmp_path):
        setup, cmd = self._cmd("full", tmp_path)
        assert "--mcp-config" in cmd and "--strict-mcp-config" in cmd
        assert "mcp__youk-core" in cmd[cmd.index("--allowedTools") + 1]
        assert "youk" in (setup["config_dir"] / "CLAUDE.md").read_text().lower()

    def test_every_run_is_budgeted_headless_and_in_its_own_config_dir(self, tmp_path):
        setup, cmd = self._cmd("bare", tmp_path)
        assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--max-budget-usd") + 1] == "2.5"
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert cmd[cmd.index("--model") + 1] == "m1"
        assert setup["config_dir"] == tmp_path / "config" / "bare"

    def test_superpowers_needs_a_checkout_and_runs_without_youk(self, tmp_path):
        with pytest.raises(SystemExit):
            rb.arm_setup("superpowers", tmp_path, None)
        sp = tmp_path / "sp"
        sp.mkdir()
        setup, cmd = self._cmd("superpowers", tmp_path, sp)
        assert setup["plugin_dirs"] == [sp] and setup["env"] == {}
        assert str(rb.REPO_ROOT / "plugin") not in cmd

    def test_unknown_arm_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            rb.arm_setup("gold", tmp_path, None)


class TestAuth:
    ENV = {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_AUTH_TOKEN": "t", "CLAUDE_CODE_OAUTH_TOKEN": "o",
           "PATH": "/bin"}

    def test_subscription_mode_strips_every_api_credential(self):
        env = rb.auth_env(self.ENV, "subscription")
        assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "o" and env["PATH"] == "/bin"

    def test_api_key_mode_keeps_the_key_and_drops_the_oauth_token(self):
        env = rb.auth_env(self.ENV, "api-key")
        assert env["ANTHROPIC_API_KEY"] == "k" and "CLAUDE_CODE_OAUTH_TOKEN" not in env

    def test_the_input_environment_is_not_mutated(self):
        base = dict(self.ENV)
        rb.auth_env(base, "subscription")
        assert base == self.ENV

    def test_a_missing_credential_is_explained_before_any_run(self):
        assert "setup-token" in rb.check_auth({"ANTHROPIC_API_KEY": "k"}, "subscription")
        assert rb.check_auth({"CLAUDE_CODE_OAUTH_TOKEN": "o"}, "subscription") == ""
        assert "ANTHROPIC_API_KEY" in rb.check_auth({}, "api-key")
        assert rb.check_auth({"ANTHROPIC_API_KEY": "k"}, "api-key") == ""

    def test_an_error_with_no_tokens_is_infrastructure_not_a_failed_task(self):
        not_logged_in = {"is_error": True, "result": "Not logged in", "usage": {
            "input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0}}
        assert rb.is_infra_failure(not_logged_in)
        ran_out_of_budget = {"is_error": True, "subtype": "error_max_budget_usd",
                             "usage": {"input_tokens": 500, "output_tokens": 20}}
        assert not rb.is_infra_failure(ran_out_of_budget)
        assert not rb.is_infra_failure({"is_error": False, "usage": {}})

    def test_repeated_infrastructure_failures_stop_the_run(self, battery):
        calls = []

        def boom(spec, workdir, ctx):
            calls.append(spec.key)
            return rb.AgentOutcome(status="infra_error", error="Not logged in")

        summary = _run(battery, agent=boom)
        assert summary["ran"] == len(calls) == rb.MAX_CONSECUTIVE_INFRA
        assert "infrastructure errors in a row" in summary["stopped"]


class TestHooksGuard:
    def test_a_youk_arm_with_no_hook_events_is_set_aside_not_counted(self, battery):
        quiet = lambda s, w, c: rb.AgentOutcome(cost_usd=0.5, turns=3)  # noqa: E731  no hooks ran
        row = rb.execute_run(rb.RunSpec(battery["tasks"][0], "bare", 0), battery["repos"],
                             battery["work"], quiet, battery["root"])
        assert row["status"] == "infra_error" and row["passed"] is None
        assert "hooks did not fire" in row["error"]

    def test_the_superpowers_arm_has_no_youk_hooks_and_is_not_held_to_it(self, battery):
        quiet = lambda s, w, c: rb.AgentOutcome(cost_usd=0.5, turns=3)  # noqa: E731
        row = rb.execute_run(rb.RunSpec(battery["tasks"][0], "superpowers", 0), battery["repos"],
                             battery["work"], quiet, battery["root"])
        assert row["status"] == "ok"

    def test_hook_events_for_the_session_are_counted(self, tmp_path):
        import events
        events.emit(tmp_path, "bench-x", kind="session", name="start.startup", session="sid-1")
        events.emit(tmp_path, "bench-x", kind="session", name="start.startup", session="other")
        assert rb.ledger_counts(tmp_path, "bench-x", "sid-1")["hook_events"] == 1


class TestCleanup:
    def test_removes_only_bench_entries_under_knowledge_projects_and_state(self, tmp_path):
        home = tmp_path / "youk"
        keep = [home / "knowledge" / "projects" / "youk" / "contracts.md",
                home / "state" / "events" / "youk" / "2026-10.jsonl",
                home / "knowledge" / "projects" / "benchmark-notes" / "x.md"]
        drop = [home / "knowledge" / "projects" / "bench-canopy" / "contracts.md",
                home / "state" / "events" / "bench-youk" / "2026-10.jsonl",
                home / "state" / "bench-stencil.json"]
        for f in keep + drop:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x")
        removed = rb.cleanup_bench_state(home)
        assert len(removed) == 3
        assert all(f.exists() for f in keep) and not any(f.exists() for f in drop)

    def test_a_missing_home_is_fine(self, tmp_path):
        assert rb.cleanup_bench_state(tmp_path / "nope") == []


class TestClaudeOutput:
    RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 7,
              "total_cost_usd": 0.42, "usage": {"input_tokens": 100, "cache_read_input_tokens": 900,
                                                "output_tokens": 55}}

    def test_dict_and_list_forms_parse_to_the_same_outcome(self):
        a = rb.outcome_from_json(rb.parse_claude_json(json.dumps(self.RESULT)))
        b = rb.outcome_from_json(rb.parse_claude_json(
            json.dumps([{"type": "system"}, self.RESULT])))
        assert a == b
        assert (a.cost_usd, a.turns, a.tok_in, a.tok_out) == (0.42, 7, 1000, 55)

    def test_budget_exhaustion_is_an_agent_failure_not_an_infrastructure_one(self):
        out = rb.outcome_from_json({**self.RESULT, "is_error": True,
                                    "subtype": "error_max_budget_usd"})
        assert out.status == "ok" and "budget" in out.error


def _results(spec: dict[str, float], n_tasks=30, reps=2, cost: dict | None = None):
    """Synthetic rows where each arm passes a task with the given probability, deterministically."""
    import random
    rng = random.Random(7)
    rows = []
    for t in range(n_tasks):
        for arm, p in spec.items():
            for rep in range(reps):
                rows.append({"task": f"t{t}", "arm": arm, "rep": rep, "status": "ok",
                             "passed": rng.random() < p, "cost_usd": (cost or {}).get(arm, 1.0),
                             "wall_s": 100.0})
    return rows


class TestAnalysis:
    def test_a_real_difference_has_an_interval_that_excludes_zero(self):
        data = analyze.per_task(_results({"full": 0.9, "bare": 0.3}))
        diff, lo, hi, n = analyze.paired_diff({t: v["pass"] for t, v in data["full"].items()},
                                              {t: v["pass"] for t, v in data["bare"].items()})
        assert n == 30 and 0.4 < diff < 0.8 and lo > 0

    def test_identical_arms_have_an_interval_that_includes_zero(self):
        data = analyze.per_task(_results({"full": 0.5, "bare": 0.5}))
        diff, lo, hi, _ = analyze.paired_diff({t: v["pass"] for t, v in data["full"].items()},
                                              {t: v["pass"] for t, v in data["bare"].items()})
        assert lo < 0 < hi

    def test_infra_errors_are_excluded_and_counted(self):
        rows = _results({"full": 1.0, "bare": 0.0}, n_tasks=5, reps=1)
        rows.append({"task": "t0", "arm": "full", "rep": 1, "status": "infra_error",
                     "passed": None, "cost_usd": 0, "wall_s": 0})
        text = analyze.render(rows)
        assert "infrastructure errors excluded 1" in text
        assert analyze.per_task(rows)["full"]["t0"]["pass"] == 1.0

    def test_repetitions_are_averaged_per_task_before_resampling(self):
        rows = [{"task": "a", "arm": "x", "rep": r, "status": "ok", "passed": r == 0,
                 "cost_usd": 1, "wall_s": 1} for r in range(4)]
        assert analyze.per_task(rows)["x"]["a"]["pass"] == 0.25

    def test_cost_ratio_over_the_limit_fails_g1_even_when_pass_rate_wins(self):
        rows = _results({"full": 0.9, "bare": 0.3}, cost={"full": 2.0, "bare": 1.0})
        verdict = analyze.g1_verdict(analyze.comparisons(analyze.per_task(rows), "bare"), "bare")
        assert verdict.startswith("G1 FAIL") and "2.00x" in verdict

    def test_a_clear_win_at_fair_cost_passes_g1(self):
        rows = _results({"full": 0.9, "bare": 0.3}, cost={"full": 1.1, "bare": 1.0})
        verdict = analyze.g1_verdict(analyze.comparisons(analyze.per_task(rows), "bare"), "bare")
        assert verdict.startswith("G1 PASS")

    def test_no_pass_rate_gain_fails_g1(self):
        rows = _results({"full": 0.5, "bare": 0.5})
        verdict = analyze.g1_verdict(analyze.comparisons(analyze.per_task(rows), "bare"), "bare")
        assert verdict.startswith("G1 FAIL") and "not shown better" in verdict

    def test_g1_is_not_decidable_without_both_arms(self):
        rows = _results({"full": 0.5})
        assert "not decidable" in analyze.g1_verdict(
            analyze.comparisons(analyze.per_task(rows), "bare"), "bare")

    def test_analysis_is_deterministic(self):
        rows = _results({"full": 0.7, "bare": 0.4})
        assert analyze.render(rows) == analyze.render(rows)

    def test_decision_entry_follows_the_decisions_file_format(self):
        entry = analyze.decision_entry(_results({"full": 0.9, "bare": 0.3}), "bare", "2026-10-12")
        for field in ("## 2026-10-12  [G1 baseline battery]", "Chose:", "Over:", "Because:",
                      "Cost:"):
            assert field in entry

    def test_the_table_names_each_arm_with_its_interval(self):
        text = analyze.render(_results({"full": 0.9, "bare": 0.3, "superpowers": 0.6}))
        for arm in ("full", "bare", "superpowers"):
            assert f"| {arm} | 30 |" in text
        assert "Paired against bare" in text

    def test_dry_run_results_flow_through_the_analysis(self, battery):
        _run(battery)
        rows = analyze.load(battery["out"])
        assert "| bare | 4 |" in analyze.render(rows)


def test_task_yaml_files_carry_the_fields_the_runner_reads(battery):
    for t in battery["tasks"]:
        for field in ("id", "repo", "sha", "parent_sha", "prompt", "test_cmd", "hidden_tests",
                      "runnable_tests", "added_tests", "source_files"):
            assert field in t, field
    assert yaml.safe_load((Path(__file__).parent.parent / "bench" / "repos.yaml").read_text())
