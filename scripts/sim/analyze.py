#!/usr/bin/env python3
"""Compare arms on the battery results with bootstrap intervals (S10).

Unit of analysis is the task: each task's repetitions are averaged first, then tasks are
resampled with replacement. Runs on the same task are not independent, so resampling runs
would give intervals that are too narrow. Runs that failed for infrastructure reasons
(`status: infra_error`) are excluded and counted; a timeout counts as a failed attempt.

    python3 scripts/sim/analyze.py bench/results/2026-10-12.jsonl [--baseline bare] [--decision]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

BOOTSTRAP_N = 5000
SEED = 20261005
COST_RATIO_LIMIT = 1.3     # G1: full costing more than this multiple of bare is a finding


def load(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def per_task(rows: list[dict]) -> dict[str, dict[str, dict[str, float]]]:
    """{arm: {task: {pass, cost, wall}}}, repetitions averaged, infra errors dropped."""
    grouped: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.get("status") == "infra_error" or r.get("passed") is None:
            continue
        grouped[r["arm"]][r["task"]].append(r)
    out: dict = {}
    for arm, tasks in grouped.items():
        out[arm] = {t: {"pass": statistics.fmean(1.0 if x["passed"] else 0.0 for x in rs),
                        "cost": statistics.fmean(x.get("cost_usd") or 0.0 for x in rs),
                        "wall": statistics.fmean(x.get("wall_s") or 0.0 for x in rs)}
                    for t, rs in tasks.items()}
    return out


def _interval(samples: list[float]) -> tuple[float, float]:
    samples = sorted(samples)
    lo = samples[int(0.025 * (len(samples) - 1))]
    hi = samples[int(0.975 * (len(samples) - 1))]
    return lo, hi


def bootstrap_mean(values: list[float], n: int = BOOTSTRAP_N, seed: int = SEED):
    """(mean, lo, hi) for the mean of per-task values."""
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(n)]
    return statistics.fmean(values), *_interval(means)


def paired_diff(a: dict[str, float], b: dict[str, float], n: int = BOOTSTRAP_N, seed: int = SEED):
    """Mean of (a - b) over the tasks both arms ran, with a bootstrap interval over tasks."""
    shared = sorted(set(a) & set(b))
    if not shared:
        return None
    diffs = [a[t] - b[t] for t in shared]
    return (*bootstrap_mean(diffs, n, seed), len(shared))


def paired_ratio(a: dict[str, float], b: dict[str, float], n: int = BOOTSTRAP_N, seed: int = SEED):
    """Ratio of mean(a) to mean(b) over shared tasks, interval by resampling tasks."""
    shared = sorted(set(a) & set(b))
    if not shared or sum(b[t] for t in shared) == 0:
        return None
    rng = random.Random(seed)
    ratios = []
    for _ in range(n):
        pick = rng.choices(shared, k=len(shared))
        denom = sum(b[t] for t in pick)
        if denom:
            ratios.append(sum(a[t] for t in pick) / denom)
    point = sum(a[t] for t in shared) / sum(b[t] for t in shared)
    return (point, *_interval(ratios), len(shared)) if ratios else None


def arm_table(data: dict) -> list[dict]:
    rows = []
    for arm in sorted(data):
        tasks = data[arm]
        p = bootstrap_mean([v["pass"] for v in tasks.values()])
        rows.append({"arm": arm, "tasks": len(tasks), "pass": p,
                     "cost": statistics.fmean(v["cost"] for v in tasks.values()),
                     "wall": statistics.fmean(v["wall"] for v in tasks.values())})
    return rows


def comparisons(data: dict, baseline: str) -> list[dict]:
    out = []
    base = data.get(baseline)
    if base is None:
        return out
    for arm in sorted(data):
        if arm == baseline:
            continue
        out.append({
            "arm": arm,
            "pass_diff": paired_diff({t: v["pass"] for t, v in data[arm].items()},
                                     {t: v["pass"] for t, v in base.items()}),
            "cost_ratio": paired_ratio({t: v["cost"] for t, v in data[arm].items()},
                                       {t: v["cost"] for t, v in base.items()}),
            "wall_ratio": paired_ratio({t: v["wall"] for t, v in data[arm].items()},
                                       {t: v["wall"] for t, v in base.items()}),
        })
    return out


def g1_verdict(comps: list[dict], baseline: str) -> str:
    """G1 from the README: if full is not better than bare on pass rate, or costs over 1.3x,
    S11 and S12 are the priority."""
    full = next((c for c in comps if c["arm"] == "full"), None)
    if full is None or full["pass_diff"] is None:
        return "G1 not decidable: need arms full and " + baseline + " on shared tasks."
    diff, lo, hi, n = full["pass_diff"]
    cost = full["cost_ratio"]
    notes = []
    if diff <= 0 or lo <= 0:
        notes.append(f"full is not shown better than {baseline} on pass rate "
                     f"({diff:+.2f}, 95% interval {lo:+.2f} to {hi:+.2f}, {n} tasks)")
    else:
        notes.append(f"full beats {baseline} on pass rate ({diff:+.2f}, {lo:+.2f} to {hi:+.2f})")
    if cost and cost[0] > COST_RATIO_LIMIT:
        notes.append(f"full costs {cost[0]:.2f}x {baseline}, over the {COST_RATIO_LIMIT}x limit")
    bad = (diff <= 0 or lo <= 0) or (cost and cost[0] > COST_RATIO_LIMIT)
    head = ("G1 FAIL: S11 and S12 are the priority; S13 may be cut to test-run-only."
            if bad else "G1 PASS: full justifies its cost; S11 and S12 proceed as planned.")
    return head + " " + "; ".join(notes) + "."


def _fmt(x, spec=".2f"):
    return format(x, spec)


def render(rows: list[dict], baseline: str = "bare") -> str:
    data = per_task(rows)
    excluded = sum(1 for r in rows if r.get("status") == "infra_error")
    lines = [f"runs {len(rows)}, infrastructure errors excluded {excluded}", ""]
    lines += ["| arm | tasks | pass@1 (95% interval) | cost per task | wall s per task |",
              "|---|---|---|---|---|"]
    for r in arm_table(data):
        m, lo, hi = r["pass"]
        lines.append(f"| {r['arm']} | {r['tasks']} | {m:.2f} ({lo:.2f} to {hi:.2f}) "
                     f"| ${r['cost']:.2f} | {r['wall']:.0f} |")
    comps = comparisons(data, baseline)
    if comps:
        lines += ["", f"Paired against {baseline}, tasks resampled:", "",
                  "| arm | pass difference | cost ratio | time ratio |", "|---|---|---|---|"]
        for c in comps:
            d, cr, wr = c["pass_diff"], c["cost_ratio"], c["wall_ratio"]
            lines.append(
                f"| {c['arm']} | " + (f"{d[0]:+.2f} ({d[1]:+.2f} to {d[2]:+.2f}, n={d[3]})" if d else "n/a")
                + " | " + (f"{cr[0]:.2f}x ({cr[1]:.2f} to {cr[2]:.2f})" if cr else "n/a")
                + " | " + (f"{wr[0]:.2f}x ({wr[1]:.2f} to {wr[2]:.2f})" if wr else "n/a") + " |")
        lines += ["", g1_verdict(comps, baseline)]
    return "\n".join(lines)


def decision_entry(rows: list[dict], baseline: str, date: str) -> str:
    """A DECISIONS.md entry in the file's own format, filled from the numbers."""
    data = per_task(rows)
    comps = comparisons(data, baseline)
    verdict = g1_verdict(comps, baseline)
    n_tasks = len({r["task"] for r in rows})
    return (f"## {date}  [G1 baseline battery]\n"
            f"Chose:      {verdict}\n"
            f"Over:       Deciding S11 and S12 scope without replay evidence.\n"
            f"Because:    {len(rows)} runs over {n_tasks} tasks, arms {', '.join(sorted(data))}; "
            "task-level paired bootstrap. See bench/results for the rows.\n"
            "Cost:       Replay tasks measure correctness and cost on small bug-fix and feature "
            "work in the developer's own repos. They do not measure compounding across sessions, and "
            "the model may have seen similar code.\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--baseline", default="bare")
    ap.add_argument("--decision", action="store_true", help="print a DECISIONS.md entry")
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    rows = load(args.results)
    if not rows:
        print("no results", file=sys.stderr)
        return 1
    print(decision_entry(rows, args.baseline, args.date or "YYYY-MM-DD")
          if args.decision else render(rows, args.baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
