#!/usr/bin/env python3
"""Is youk helping? One report from the event ledger, by arm and by week.

This replaces org_score as the headline. org_score counts whether gates fired, which rewards
ceremony. These are outcomes and costs:

  V1  corrections: pushback and stated-rule messages, per M+ task
  V2  review-ready inputs: did the last test run of a session pass, commits, failed test runs
      (first-pass acceptance needs the evidence packet and is reported as pending until then)
  V3  overhead: always-on tokens, hook and tool latency
  gates  how often each gate was checked and how often it blocked

Counting rule: calls and corrections come from hook events (src=hook); latency, gates and M+
task counts come from server events (src=server). Both are written by the same ledger.

Intervals are 95% bootstrap intervals of a per-session mean and are shown only with at least
10 sessions. With fewer, the raw counts are shown and the report says so. Do not read a
difference between arms off a small n.

    python3 scripts/value_report.py [--root DIR] [--project SLUG] [--since YYYY-MM-DD]
                                    [--by arm|week|arm,week] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "servers" / "shared"))
sys.path.insert(0, str(REPO / "scripts"))

import events  # noqa: E402

MIN_N = 10
M_PLUS = ("route.M", "route.L", "route.XL")


def default_root() -> Path:
    env = os.environ.get("YOUK_HOME")
    if env:
        return Path(env)
    home = Path.home() / ".claude" / "youk"
    return home if home.exists() else REPO


def load(root: Path, project: str | None = None, since: datetime | None = None) -> list[dict]:
    base = root / "state" / "events"
    slugs = [project] if project else sorted(p.name for p in base.glob("*") if p.is_dir())
    out: list[dict] = []
    for slug in slugs:
        for event in events.read_events(root, slug, since=since):
            out.append({**event, "_project": slug})
    return out


def week_of(ts: str) -> str:
    try:
        year, week, _ = datetime.fromisoformat(ts).isocalendar()
        return f"{year}-W{week:02d}"
    except (ValueError, TypeError):
        return "unknown"


def bootstrap_ci(values: list[float], draws: int = 2000, seed: int = 0) -> tuple[float, float] | None:
    """95% interval of the mean, or None when there are too few values to say anything."""
    if len(values) < MIN_N:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return means[int(draws * 0.025)], means[int(draws * 0.975) - 1]


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(pct * len(ordered)) - 1))]  # nearest rank


def group_key(event: dict, by: tuple[str, ...]) -> tuple:
    return tuple(
        (event.get("arm") or "-") if dim == "arm" else week_of(event.get("ts", ""))
        for dim in by
    )


def summarize(rows: list[dict], by: tuple[str, ...] = ("arm",), footprint: dict | None = None) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for event in rows:
        groups[group_key(event, by)].append(event)

    result_groups = []
    for key in sorted(groups):
        evs = groups[key]
        hook = [e for e in evs if e.get("src") == "hook"]
        server = [e for e in evs if e.get("src") == "server"]

        corrections = Counter(e["name"] for e in hook if e["kind"] == "correction")
        by_session: dict[str, int] = defaultdict(int)
        sessions = {e["session"] for e in hook if e.get("session")}
        for e in hook:
            if e["kind"] == "correction" and e.get("session"):
                by_session[e["session"]] += 1
        per_session = [float(by_session.get(s, 0)) for s in sessions]
        m_plus = sum(1 for e in server
                     if e["kind"] == "gate" and e["name"] in M_PLUS and e.get("status") == "ok")

        tests = [e for e in hook if e["kind"] == "test"]
        last_test: dict[str, str] = {}
        for e in sorted(tests, key=lambda x: x.get("ts", "")):
            last_test[e.get("session", "")] = e["status"]
        commits = sum(1 for e in hook if e["kind"] == "commit" and e["status"] == "ok")

        hook_ms = [e["ms"] for e in hook if e["kind"] == "hook" and "ms" in e]
        tool_ms: dict[str, list[int]] = defaultdict(list)
        for e in server:
            if e["kind"] == "tool" and "ms" in e:
                tool_ms[e["name"]].append(e["ms"])

        gates: dict[str, dict[str, int]] = defaultdict(lambda: {"checks": 0, "blocks": 0})
        for e in server:
            if e["kind"] == "gate" and not e["name"].startswith(("set.", "route.")):
                gates[e["name"]]["checks"] += 1
                gates[e["name"]]["blocks"] += e.get("status") == "block"

        result_groups.append({
            "group": "/".join(key),
            "events": len(evs),
            "sessions": len(sessions),
            "v1": {
                "pushback": corrections.get("pushback", 0),
                "rule_phrase": corrections.get("rule_phrase", 0),
                "m_plus_tasks": m_plus,
                "per_m_plus_task": (round(sum(corrections.values()) / m_plus, 2) if m_plus else None),
                "mean_per_session": round(statistics.fmean(per_session), 2) if per_session else None,
                "ci": bootstrap_ci(per_session),
            },
            "v2": {
                "sessions_with_tests": len(last_test),
                "last_test_green": sum(1 for v in last_test.values() if v == "ok"),
                "failed_test_runs": sum(1 for e in tests if e["status"] == "fail"),
                "test_runs": len(tests),
                "commits": commits,
                "first_pass_acceptance": "pending (needs the evidence packet)",
            },
            "v3": {
                "hook_ms_p50": percentile(hook_ms, 0.5),
                "hook_ms_p95": percentile(hook_ms, 0.95),
                "hook_samples": len(hook_ms),
                "slowest_tools": sorted(
                    ({"tool": t, "p50": percentile(v, 0.5), "p95": percentile(v, 0.95), "n": len(v)}
                     for t, v in tool_ms.items()), key=lambda r: -(r["p95"] or 0))[:5],
                "session_start_p95": percentile(tool_ms.get("session_start", []), 0.95),
            },
            "gates": dict(sorted(gates.items())),
            "usage": {
                "skills": Counter(e["name"] for e in hook if e["kind"] == "skill").most_common(8),
                "tools": Counter(e["name"] for e in hook if e["kind"] == "tool").most_common(8),
            },
        })
    return {
        "events": len(rows),
        "projects": sorted({e["_project"] for e in rows if "_project" in e}),
        "by": list(by),
        "groups": result_groups,
        "footprint": footprint,
    }


def _fmt_ci(ci) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else f"n<{MIN_N}, no interval"


def render(summary: dict) -> str:
    out = [f"Value report: {summary['events']} events, projects: {', '.join(summary['projects']) or 'none'}",
           f"grouped by {', '.join(summary['by'])}", ""]
    if not summary["groups"]:
        return "\n".join(out + ["No events yet. Hooks write them once the plugin hooks are live."])
    for g in summary["groups"]:
        v1, v2, v3 = g["v1"], g["v2"], g["v3"]
        out += [f"== {g['group']}  ({g['events']} events, {g['sessions']} sessions with hook data)", "",
                "V1 corrections",
                f"  pushback {v1['pushback']}, stated rules {v1['rule_phrase']}, M+ tasks {v1['m_plus_tasks']}",
                f"  per M+ task: {v1['per_m_plus_task'] if v1['per_m_plus_task'] is not None else 'n/a (no M+ tasks)'}",
                f"  per session: {v1['mean_per_session'] if v1['mean_per_session'] is not None else 'n/a'}"
                f"  95% CI {_fmt_ci(v1['ci'])}",
                "V2 review-ready inputs",
                f"  last test run green in {v2['last_test_green']} of {v2['sessions_with_tests']} sessions with tests",
                f"  failed test runs {v2['failed_test_runs']} of {v2['test_runs']}; commits {v2['commits']}",
                f"  first-pass acceptance: {v2['first_pass_acceptance']}",
                "V3 overhead",
                f"  hook script ms p50 {v3['hook_ms_p50']} p95 {v3['hook_ms_p95']} "
                f"(sampled, {v3['hook_samples']} samples; interpreter start adds ~21 ms)",
                f"  session_start p95 {v3['session_start_p95']} ms",
                "  slowest tools (server): " + (", ".join(
                    f"{t['tool']} p95 {t['p95']} ms (n={t['n']})" for t in v3["slowest_tools"]) or "none"),
                "Gates"]
        out += [f"  {name}: {s['checks']} checks, {s['blocks']} blocked" for name, s in g["gates"].items()] \
            or ["  none recorded"]
        out += ["Usage",
                "  skills: " + (", ".join(f"{n} {c}" for n, c in g["usage"]["skills"]) or "none"),
                "  tools: " + (", ".join(f"{n} {c}" for n, c in g["usage"]["tools"]) or "none"), ""]
    fp = summary.get("footprint")
    if fp:
        out += ["Always-on footprint (scripts/footprint.py)",
                f"  {fp['total_tokens']} tokens now, baseline {fp.get('baseline')}", ""]
    out += ["Diagnostic only: org_score, skill rate and close rate are process measures, not outcomes."
            " See STATS.md and `make dashboard`."]
    return "\n".join(out)


def _footprint(root: Path) -> dict | None:
    try:
        import footprint
        current = footprint.measure(REPO)
        baseline = None
        if footprint.BASELINE.exists():
            baseline = json.loads(footprint.BASELINE.read_text()).get("total_tokens")
        return {"total_tokens": current["total_tokens"], "baseline": baseline}
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--project")
    parser.add_argument("--since", help="YYYY-MM-DD")
    parser.add_argument("--by", default="arm", help="arm, week or arm,week")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root or default_root()
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC) if args.since else None
    by = tuple(d for d in args.by.split(",") if d in ("arm", "week")) or ("arm",)
    summary = summarize(load(root, args.project, since), by=by, footprint=_footprint(root))
    print(json.dumps(summary, indent=2, default=list) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
