#!/usr/bin/env python3
"""Pre-run design check for a battery: can this design answer its question, and at what cost?

Written after the first battery (G1) spent $26 and could not decide anything: 12 of 14 tasks gave
the same result in both arms and one run each was too noisy to see a difference. Published practice
(see docs/value-plan/research-eval-design.md) is to fix the smallest effect that matters, check the
design can see it, and only then spend. This is that check, as code, so it cannot be skipped.

Inputs are per-task pass rates of the baseline arm from a pilot (bare arm, k >= 2). Tasks the
baseline always passes (ceiling) or never passes (floor) cannot show an effect and are not counted
as informative. Selection uses the baseline arm only, never the arm under test.

    python3 scripts/sim/design.py PILOT.jsonl --k 3 --target-effect 0.15 --cost-per-run 0.9
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_TARGET_EFFECT = 0.15     # pass-rate points that would change a decision
DEFAULT_MIN_POWER = 0.80
DEFAULT_MIN_INFORMATIVE = 0.50   # share of tasks that can show an effect at all
SIMS = 1500
SEED = 20261006


def base_rates(rows: list[dict], arm: str = "bare") -> dict[str, tuple[int, int]]:
    """{task: (passes, runs)} for one arm. Infrastructure errors and ungraded runs are skipped."""
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("arm") != arm or r.get("status") == "infra_error" or r.get("passed") is None:
            continue
        out[r["task"]][0] += 1 if r["passed"] else 0
        out[r["task"]][1] += 1
    return {t: (p, n) for t, (p, n) in out.items()}


def triage(rates: dict[str, tuple[int, int]]) -> dict[str, str]:
    """ceiling (always passes), floor (never passes) or mixed. Only mixed tasks can show an
    effect. Fewer than 2 runs cannot tell a floor from a coin that landed tails: `unknown`."""
    out = {}
    for task, (passes, runs) in rates.items():
        if runs < 2:
            out[task] = "unknown"
        elif passes == runs:
            out[task] = "ceiling"
        elif passes == 0:
            out[task] = "floor"
        else:
            out[task] = "mixed"
    return out


def informative_share(labels: dict[str, str]) -> float:
    return sum(1 for v in labels.values() if v == "mixed") / len(labels) if labels else 0.0


def shrunk(passes: int, runs: int) -> float:
    """Pass rate pulled toward one half, so a 1-run 'always passes' is not read as certainty."""
    return (passes + 0.5) / (runs + 1)


def _crit(df: int) -> float:
    z = 1.959964
    return z * (1 + (z * z + 1) / (4 * max(df, 1)))   # small-sample widening of the normal


def _binom(rng: random.Random, n: int, p: float) -> int:
    return sum(rng.random() < p for _ in range(n))


def power(rates: dict[str, tuple[int, int]], effect: float, n_tasks: int, k: int,
          sims: int = SIMS, seed: int = SEED) -> float:
    """Chance a paired comparison detects `effect` (added to each task's pass rate, capped at 0
    and 1) with n_tasks drawn from the pilot tasks and k runs per arm. Tasks at a rate of 0 or 1
    after shrinking still move a little, so an all-0/1 pilot does not read as certainty."""
    if not rates or n_tasks < 2:
        return 0.0
    pool = [shrunk(p, n) for p, n in rates.values()]
    rng = random.Random(seed)
    hits = 0
    for _ in range(sims):
        diffs = []
        for p in (rng.choice(pool) for _ in range(n_tasks)):
            bare = _binom(rng, k, p)
            full = _binom(rng, k, min(1.0, max(0.0, p + effect)))
            diffs.append((full - bare) / k)
        sd = statistics.pstdev(diffs) * math.sqrt(n_tasks / (n_tasks - 1))
        if sd == 0:
            hits += 1 if statistics.fmean(diffs) != 0 else 0
            continue
        t = statistics.fmean(diffs) / (sd / math.sqrt(n_tasks))
        hits += t > _crit(n_tasks - 1)
    return hits / sims


def mde(rates: dict[str, tuple[int, int]], n_tasks: int, k: int, target_power: float = 0.8,
        sims: int = 600) -> float | None:
    """Smallest effect (in pass-rate points, searched in steps of 0.025) seen with target_power.
    None if even a 50-point effect is not."""
    for step in range(1, 21):
        effect = step * 0.025
        if power(rates, effect, n_tasks, k, sims=sims) >= target_power:
            return round(effect, 3)
    return None


def tasks_needed(rates: dict[str, tuple[int, int]], effect: float, k: int,
                 target_power: float = 0.8, cap: int = 200) -> int | None:
    for n in range(6, cap + 1, 2):
        if power(rates, effect, n, k, sims=400) >= target_power:
            return n
    return None


def cost_estimate(n_tasks: int, k: int, arms: int, cost_per_run: float) -> float:
    return round(n_tasks * k * arms * cost_per_run, 2)


def design_report(rates: dict[str, tuple[int, int]], k: int, arms: int = 2,
                  target_effect: float = DEFAULT_TARGET_EFFECT, cost_per_run: float = 1.0,
                  min_power: float = DEFAULT_MIN_POWER,
                  min_informative: float = DEFAULT_MIN_INFORMATIVE,
                  cap_usd: float | None = None) -> dict:
    labels = triage(rates)
    informative = [t for t, v in labels.items() if v == "mixed"]
    n = len(informative)
    pilot_k = [r for _, r in rates.values()]
    use = {t: rates[t] for t in informative} or rates
    p = power(use, target_effect, max(n, 2), k)
    report = {
        "tasks_in_pilot": len(rates),
        "labels": dict(sorted(labels.items())),
        "informative_tasks": n,
        "informative_share": round(informative_share(labels), 2),
        "pilot_runs_per_task": min(pilot_k) if pilot_k else 0,
        "k": k, "arms": arms, "target_effect": target_effect,
        "power_at_target": round(p, 2),
        "mde_at_power": mde(use, max(n, 2), k, min_power) if n >= 2 else None,
        "estimated_cost_usd": cost_estimate(n, k, arms, cost_per_run),
        "problems": [],
    }
    if report["pilot_runs_per_task"] < 2:
        report["problems"].append("pilot has fewer than 2 runs per task, so floor and ceiling "
                                  "tasks cannot be told from noise; pilot the baseline with k>=2")
    if report["informative_share"] < min_informative:
        report["problems"].append(
            f"only {report['informative_share']:.0%} of tasks can show an effect "
            f"(need {min_informative:.0%}); add tasks the baseline sometimes solves")
    if p < min_power:
        need = tasks_needed(use, target_effect, k, min_power)
        report["problems"].append(
            f"power {p:.0%} at a {target_effect:.0%}-point effect is under {min_power:.0%}; "
            f"smallest detectable effect with {n} tasks and k={k} is "
            f"{report['mde_at_power'] if report['mde_at_power'] is not None else 'over 50 points'}"
            + (f"; about {need} informative tasks would be needed" if need else ""))
    if cap_usd is not None and report["estimated_cost_usd"] > cap_usd:
        report["problems"].append(
            f"estimated cost ${report['estimated_cost_usd']} exceeds the cap ${cap_usd:g}")
    report["ok"] = not report["problems"]
    return report


def interim_decision(diffs: list[float], look: int, looks: int, mde_target: float) -> str:
    """Group-sequential rule for running in rounds. Bonferroni split of 5% across the planned
    looks, so stopping early on a win cannot inflate false positives. Stops for futility when
    the interval's upper end cannot reach the effect that mattered.
    Returns stop_efficacy, stop_futility or continue."""
    n = len(diffs)
    if n < 6 or looks < 1:
        return "continue"
    alpha = 0.05 / looks
    z = statistics.NormalDist().inv_cdf(1 - alpha / 2)
    mean = statistics.fmean(diffs)
    se = statistics.stdev(diffs) / math.sqrt(n) if statistics.pstdev(diffs) else 1e-9
    crit = z * (1 + (z * z + 1) / (4 * (n - 1)))
    if mean - crit * se > 0:
        return "stop_efficacy"
    if look < looks and mean + crit * se < mde_target:
        return "stop_futility"
    return "continue"


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def render(report: dict) -> str:
    lines = [f"pilot: {report['tasks_in_pilot']} tasks, {report['pilot_runs_per_task']} run(s) each; "
             f"informative {report['informative_tasks']} ({report['informative_share']:.0%})",
             f"plan: k={report['k']}, {report['arms']} arms, target effect "
             f"{report['target_effect']:.0%} points",
             f"power at target: {report['power_at_target']:.0%}; smallest detectable effect: "
             f"{report['mde_at_power']}",
             f"estimated cost: ${report['estimated_cost_usd']}"]
    counts = defaultdict(int)
    for v in report["labels"].values():
        counts[v] += 1
    lines.append("tasks: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    lines += [f"PROBLEM: {p}" for p in report["problems"]]
    lines.append("DESIGN OK: the run can answer its question." if report["ok"]
                 else "DESIGN NOT OK: do not spend on this run.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pilot", type=Path, help="results jsonl containing the baseline arm")
    ap.add_argument("--baseline", default="bare")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--arms", type=int, default=2)
    ap.add_argument("--target-effect", type=float, default=DEFAULT_TARGET_EFFECT)
    ap.add_argument("--cost-per-run", type=float, default=1.0)
    ap.add_argument("--cap-usd", type=float)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = design_report(base_rates(load_rows(args.pilot), args.baseline), args.k, args.arms,
                           args.target_effect, args.cost_per_run, cap_usd=args.cap_usd)
    print(json.dumps(report, indent=1) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
