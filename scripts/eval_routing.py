#!/usr/bin/env python3
"""youk routing accuracy eval — runs labelled examples through _score_size and reports.

Usage:
  python3 scripts/eval_routing.py          # print results to stdout
  python3 scripts/eval_routing.py --json   # output JSON for CI integration

Exit code:
  0 — accuracy >= 75%
  1 — accuracy < 75% (routing needs attention)

Why 75%: the heuristic is a net-score keyword classifier, not an ML model.
75% is the threshold below which routing errors are systematically degrading
gate compliance downstream (nfr-check skips, dev-loop skips).
"""
from __future__ import annotations

import json
import sys
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ROUTES_FILE = REPO_ROOT / "config" / "routes.yaml"
ACCURACY_THRESHOLD = 0.75

# ── Inline _score_size (avoids Docker path dependency in routing.py) ───────────

_SPARK = " ▁▂▃▄▅▆▇█"


def _score_size(task: str, routes: dict) -> str:
    task_lower = task.lower()
    sizes = routes.get("task_sizes", {})
    size_order = {"XL": 5, "L": 4, "M": 3, "S": 2, "XS": 1}

    scored: list[tuple[int, str]] = []
    for size_name, config in sizes.items():
        positive = sum(1 for s in config.get("signals", []) if s.lower() in task_lower)
        negative = sum(1 for s in config.get("negative_signals", []) if s.lower() in task_lower)
        net = positive - (negative * 2)
        if net > 0:
            scored.append((net, size_name))

    if not scored:
        xs_signals = sizes.get("XS", {}).get("signals", [])
        if any(s.lower() in task_lower for s in xs_signals):
            return "XS"
        word_count = len(task.split())
        if word_count <= 5:
            return "XS"
        elif word_count <= 15:
            return "S"
        elif word_count <= 40:
            return "M"
        return "L"

    scored.sort(key=lambda x: (x[0], size_order.get(x[1], 0)), reverse=True)
    return scored[0][1]


# ── Labelled eval set ─────────────────────────────────────────────────────────
# Format: (task_description, expected_size, rationale)
# Rationale is for human review — documents why the expected size was chosen.

EVAL_CASES: list[tuple[str, str, str]] = [
    # XS — typo, rename, one-liner
    ("fix typo in README", "XS", "single word correction, no logic"),
    ("rename variable userId to user_id in auth.py", "XS", "rename with no logic change"),
    ("update comment on line 42 to match new behavior", "XS", "comment-only change"),

    # S — small bug fix, single function, config change
    ("fix the null pointer in session.py when user is not logged in", "S", "single bug fix"),
    ("add a test for the edge case where input is empty", "S", "single test addition"),
    ("update the timeout config from 30s to 60s", "S", "single config change"),
    ("correct the error message in the login handler", "S", "small targeted fix"),

    # M — feature, new module, multi-file change
    ("add rate limiting to the API endpoint", "M", "new cross-cutting feature"),
    ("implement caching for the query results", "M", "new capability, multiple files"),
    ("build a retry mechanism for the external API calls", "M", "new module with failure handling"),
    ("add dark mode support to the dashboard component", "M", "UI feature across components"),
    ("refactor the session management to use the new token format", "M", "multi-file refactor"),

    # L — architecture, new service, multi-week scope
    ("design and implement the authentication system with JWT, refresh tokens, and audit logging", "L", "multi-component auth system"),
    ("migrate the database from SQLite to PostgreSQL including schema changes and data migration", "L", "multi-phase migration"),
    ("build the skill-generation pipeline: detect gaps, generate SKILL.md, propose, apply", "L", "multi-tool pipeline"),

    # XL — cross-system, multi-sprint
    ("build youk-pm: a product management variant with PRD generation, roadmap tracking, and stakeholder reporting", "XL", "new youk variant, multiple servers"),

    # Tricky: positive signals for large sizes but negative signals should pull down
    ("fix the implementation of the retry logic with a one-liner backoff", "XS",
     "one-liner negative signal should dominate despite 'implement' positive"),
    ("add a typo fix to the authentication system spec", "XS",
     "typo/clarification negative should dominate despite 'authentication' positive"),
    ("update the single variable name in the route config", "XS",
     "single variable = XS despite config mention"),

    # Ambiguous: should fall back to word count heuristic
    ("review this", "S", "short unstructured task — word count heuristic, review = S signal"),
]


# ── Evaluator ─────────────────────────────────────────────────────────────────

def run_eval() -> dict:
    if not ROUTES_FILE.exists():
        return {"error": f"routes.yaml not found at {ROUTES_FILE}"}

    with open(ROUTES_FILE) as f:
        routes = yaml.safe_load(f)

    results = []
    for task, expected, rationale in EVAL_CASES:
        actual = _score_size(task, routes)
        passed = actual == expected
        results.append({
            "task": task,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "rationale": rationale,
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = passed / total if total else 0.0

    failures = [r for r in results if not r["passed"]]
    size_confusion: dict[str, dict[str, int]] = {}
    for r in failures:
        exp = r["expected"]
        act = r["actual"]
        size_confusion.setdefault(exp, {})
        size_confusion[exp][act] = size_confusion[exp].get(act, 0) + 1

    return {
        "total": total,
        "passed": passed,
        "accuracy": round(accuracy, 3),
        "accuracy_pct": round(accuracy * 100, 1),
        "threshold_pct": round(ACCURACY_THRESHOLD * 100, 1),
        "meets_threshold": accuracy >= ACCURACY_THRESHOLD,
        "failures": failures,
        "size_confusion": size_confusion,
        "results": results,
    }


# ── Renderer ──────────────────────────────────────────────────────────────────

def render_terminal(ev: dict) -> None:
    if "error" in ev:
        print(f"ERROR: {ev['error']}", file=sys.stderr)
        return

    status = "PASS" if ev["meets_threshold"] else "FAIL"
    print(f"\nyouk routing eval — {status}")
    print(f"Accuracy: {ev['accuracy_pct']}% ({ev['passed']}/{ev['total']}) "
          f"[threshold: {ev['threshold_pct']}%]")
    print()

    if ev["failures"]:
        print(f"Failures ({len(ev['failures'])}):")
        for f in ev["failures"]:
            print(f"  [{f['expected']}→{f['actual']}] {f['task'][:70]}")
            print(f"           rationale: {f['rationale']}")
        print()

    if ev["size_confusion"]:
        print("Confusion (expected → actual counts):")
        for exp, actuals in sorted(ev["size_confusion"].items()):
            for act, count in sorted(actuals.items()):
                print(f"  {exp} → {act}: {count}x")
        print()

    if ev["meets_threshold"]:
        print(f"Routing heuristic meets the {ev['threshold_pct']}% accuracy bar.")
    else:
        print(
            f"⚠ Routing accuracy {ev['accuracy_pct']}% is below {ev['threshold_pct']}% threshold.\n"
            "Review config/routes.yaml signals — failures above show which size tiers misfire."
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    json_mode = "--json" in sys.argv
    ev = run_eval()

    if json_mode:
        print(json.dumps(ev, indent=2))
    else:
        render_terminal(ev)

    if "error" in ev or not ev.get("meets_threshold"):
        sys.exit(1)


if __name__ == "__main__":
    main()
