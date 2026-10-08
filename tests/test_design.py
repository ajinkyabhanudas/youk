"""The pre-run design check: it must have refused the first battery, and must pass a sound design."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "sim"))
import design
import run_battery as rb


def rows(per_task: dict[str, list[bool]], arm="bare", cost=1.0):
    return [{"task": t, "arm": arm, "rep": i, "status": "ok", "passed": ok, "cost_usd": cost}
            for t, results in per_task.items() for i, ok in enumerate(results)]


G1_LIKE = {f"t{i}": [True] for i in range(7)} | {f"t{i}": [False] for i in range(7, 14)}
MIXED = {f"t{i}": [True, False, True] if i % 2 else [False, True, False] for i in range(30)}


class TestTriage:
    def test_ceiling_floor_mixed_and_unknown(self):
        rates = design.base_rates(rows({"a": [True, True], "b": [False, False], "c": [True, False],
                                        "d": [True]}))
        assert design.triage(rates) == {"a": "ceiling", "b": "floor", "c": "mixed", "d": "unknown"}

    def test_infra_errors_and_other_arms_do_not_count(self):
        rs = rows({"a": [True, False]}) + rows({"a": [False]}, arm="full")
        rs.append({"task": "a", "arm": "bare", "status": "infra_error", "passed": None})
        assert design.base_rates(rs) == {"a": (1, 2)}

    def test_informative_share_counts_only_mixed(self):
        assert design.informative_share({"a": "mixed", "b": "ceiling", "c": "floor", "d": "mixed"}) == 0.5
        assert design.informative_share({}) == 0.0


class TestPower:
    def test_more_runs_and_tasks_raise_power(self):
        rates = design.base_rates(rows(MIXED))
        small = design.power(rates, 0.15, 14, 1, sims=400)
        big = design.power(rates, 0.15, 40, 3, sims=400)
        assert big > small and big > 0.5

    def test_no_effect_is_rarely_detected(self):
        rates = design.base_rates(rows(MIXED))
        assert design.power(rates, 0.0, 30, 3, sims=600) < 0.15

    def test_a_larger_effect_is_easier_to_see(self):
        rates = design.base_rates(rows(MIXED))
        assert design.power(rates, 0.4, 20, 3, sims=400) > design.power(rates, 0.1, 20, 3, sims=400)

    def test_mde_shrinks_as_the_design_grows(self):
        rates = design.base_rates(rows(MIXED))
        big, small = design.mde(rates, 40, 3), design.mde(rates, 14, 1)
        assert big is not None and (small is None or big <= small)

    def test_deterministic(self):
        rates = design.base_rates(rows(MIXED))
        assert design.power(rates, 0.2, 20, 2, sims=300) == design.power(rates, 0.2, 20, 2, sims=300)


class TestReport:
    def test_the_first_battery_design_is_refused(self):
        report = design.design_report(design.base_rates(rows(G1_LIKE)), k=1, arms=2, cost_per_run=0.9)
        assert not report["ok"]
        joined = " ".join(report["problems"])
        assert "fewer than 2 runs" in joined and "power" in joined

    def test_a_sound_design_passes(self):
        pilot = {f"t{i}": [True, False, True] if i % 2 else [False, True, False] for i in range(60)}
        report = design.design_report(design.base_rates(rows(pilot)), k=3, arms=2,
                                      target_effect=0.15, cost_per_run=0.5, cap_usd=500)
        assert report["ok"], report["problems"]
        assert report["informative_share"] == 1.0

    def test_cost_over_the_cap_is_a_problem(self):
        pilot = {f"t{i}": [True, False] for i in range(60)}
        report = design.design_report(design.base_rates(rows(pilot)), k=3, arms=2,
                                      cost_per_run=1.0, cap_usd=50)
        assert any("exceeds the cap" in p for p in report["problems"])

    def test_floor_and_ceiling_pilots_fail_on_informative_share(self):
        pilot = {f"t{i}": [True, True] for i in range(10)} | {f"u{i}": [False, False] for i in range(10)}
        report = design.design_report(design.base_rates(rows(pilot)), k=3)
        assert report["informative_share"] == 0 and not report["ok"]


class TestInterim:
    def test_a_clear_win_stops_early(self):
        assert design.interim_decision([0.4, 0.3, 0.5, 0.4, 0.35, 0.45, 0.4, 0.3], 1, 3, 0.15) == "stop_efficacy"

    def test_nothing_going_on_stops_for_futility_before_the_last_look(self):
        diffs = [0.0, 0.0, 0.05, -0.05, 0.0, 0.0, 0.0, 0.0, 0.05, -0.05, 0.0, 0.0]
        assert design.interim_decision(diffs, 1, 3, 0.15) == "stop_futility"

    def test_too_few_tasks_always_continues(self):
        assert design.interim_decision([0.5, 0.5, 0.5], 1, 3, 0.15) == "continue"

    def test_the_last_look_never_stops_for_futility(self):
        assert design.interim_decision([0.0] * 6 + [0.05, -0.05] * 3, 3, 3, 0.15) in (
            "continue", "stop_efficacy")


class TestRunnerGate:
    def test_no_pilot_refuses_and_writes_the_verdict(self, tmp_path):
        out = tmp_path / "r.jsonl"
        ok, text = rb.design_gate(None, ["bare", "full"], 3, 50, 0.15, False, out)
        assert not ok and "no pilot" in text
        assert json.loads(out.with_suffix(".design.json").read_text())["ok"] is False

    def test_an_underpowered_pilot_refuses_unless_overridden_and_the_override_is_recorded(self, tmp_path):
        pilot = tmp_path / "p.jsonl"
        pilot.write_text("\n".join(json.dumps(r) for r in rows(G1_LIKE)))
        out = tmp_path / "r.jsonl"
        ok, _ = rb.design_gate(pilot, ["bare", "full"], 1, 50, 0.15, False, out)
        assert not ok
        ok, _ = rb.design_gate(pilot, ["bare", "full"], 1, 50, 0.15, True, out)
        assert ok and json.loads(out.with_suffix(".design.json").read_text())["override"] is True

    def test_a_sound_pilot_passes(self, tmp_path):
        pilot = tmp_path / "p.jsonl"
        sound = {f"t{i}": [True, False, True] if i % 2 else [False, True, False] for i in range(60)}
        pilot.write_text("\n".join(json.dumps(r) for r in rows(sound, cost=0.4)))
        ok, text = rb.design_gate(pilot, ["bare", "full"], 3, 500, 0.15, False, tmp_path / "r.jsonl")
        assert ok and "DESIGN OK" in text


class TestPilotGate:
    def test_a_baseline_only_pilot_with_k2_inside_the_cap_passes(self):
        ok, text = rb.pilot_gate(["bare"], 3, 20, 100)
        assert ok and "estimated $90" in text

    def test_a_resumed_pilot_is_priced_on_the_runs_left_not_the_whole_plan(self):
        ok, text = rb.pilot_gate(["bare"], 3, 3, 6, runs_left=3)
        assert ok and "3 runs left" in text and "estimated $4.5" in text
        ok, _ = rb.pilot_gate(["bare"], 3, 3, 6)
        assert not ok                       # the whole plan, 9 runs at 1.50, would not fit

    def test_default_cost_per_run_matches_the_measured_pilot(self):
        import inspect
        assert rb.DEFAULT_RUN_USD == 1.5
        assert inspect.signature(design.design_report).parameters["cost_per_run"].default == 1.5
        assert inspect.signature(rb.pilot_gate).parameters["cost_per_run"].default == 1.5

    def test_a_pilot_must_be_baseline_only_k2_and_affordable(self):
        ok, text = rb.pilot_gate(["bare", "full"], 1, 100, 50)
        assert not ok
        for part in ("baseline arm only", "k>=2", "exceeds the cap"):
            assert part in text
