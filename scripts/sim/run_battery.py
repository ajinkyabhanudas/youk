#!/usr/bin/env python3
"""Run the replay battery: task x arm x repetition, headless, graded by the hidden tests (S10).

For each run: a fresh clone of the repo at the task's parent commit with the commit's new tests
removed, the agent run through `claude -p` under the arm's own config directory, then the hidden
tests restored and run. One JSON line per run goes to bench/results/{date}.jsonl.

Arms:
  bare          youk's hooks (events only), no brief, gates off, no youk tools
  full          youk as installed: hooks, brief, CLAUDE.md template, youk-core and youk-code tools
  superpowers   the Superpowers plugin from a checkout you give with --superpowers-dir, no youk

Money: --cap-usd is required for a real run. Each run also gets --max-budget-usd, so one runaway
cannot spend the cap. The loop stops before a run it expects to push spending over the cap.
Order is repetition, then task, then arm, so stopping early leaves paired data, not one full arm.

    python3 scripts/sim/run_battery.py --dry-run                      fake agent, no money
    python3 scripts/sim/run_battery.py --cap-usd 50 --k 1             first real run
    python3 scripts/sim/run_battery.py --cap-usd 50 --k 1 --limit 2   smoke test on two tasks
Re-running appends only the (task, arm, rep) combinations the results file lacks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servers" / "shared"))
import mine_tasks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "bench" / "results"
ARMS = ("bare", "full", "superpowers")
DEFAULT_WORK = Path.home() / ".cache" / "youk-bench"
DEFAULT_TIMEOUT_S = 900
DEFAULT_MAX_RUN_USD = 3.0
YOUK_MCP = {"mcpServers": {
    "youk-core": {"type": "http", "url": "http://127.0.0.1:8001/mcp"},
    "youk-code": {"type": "http", "url": "http://127.0.0.1:8002/mcp"},
}}
ALLOWED_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "Skill"]
PROMPT_FRAME = ("Work in the current directory, a git checkout. Make the change described below "
                "so the project's tests for it pass. Do not ask questions.\n\n")


@dataclass
class RunSpec:
    task: dict
    arm: str
    rep: int

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.task["id"], self.arm, self.rep)


@dataclass
class AgentOutcome:
    status: str = "ok"          # ok | timeout | infra_error
    cost_usd: float = 0.0
    turns: int | None = None
    tok_in: int | None = None
    tok_out: int | None = None
    error: str = ""


Agent = Callable[[RunSpec, Path, dict], AgentOutcome]


# ---- arm configuration ------------------------------------------------------------------------

def arm_setup(arm: str, work: Path, superpowers_dir: Path | None) -> dict:
    """What distinguishes an arm: config dir, plugins, MCP, CLAUDE.md, env. Pure data plus file
    writes in the arm's own config dir; nothing touches the real ~/.claude."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    config = work / "config" / arm
    config.mkdir(parents=True, exist_ok=True)
    claude_md = config / "CLAUDE.md"
    spec: dict = {"config_dir": config, "plugin_dirs": [], "mcp": None, "env": {}}
    if arm == "superpowers":
        if not superpowers_dir or not Path(superpowers_dir).is_dir():
            raise SystemExit("arm superpowers needs --superpowers-dir <path to a Superpowers "
                             "plugin checkout>; see docs/value-plan/battery.md")
        spec["plugin_dirs"] = [Path(superpowers_dir)]
        claude_md.write_text("")
        return spec
    spec["plugin_dirs"] = [REPO_ROOT / "plugin"]
    spec["env"] = {"YOUK_ARM": arm}
    if arm == "full":
        spec["mcp"] = YOUK_MCP
        claude_md.write_text((REPO_ROOT / "docs" / "claude-md-template.md").read_text())
    else:
        claude_md.write_text("")
    return spec


def agent_command(spec: RunSpec, setup: dict, prompt: str, session_id: str, model: str | None,
                  max_run_usd: float, mcp_file: Path | None) -> list[str]:
    cmd = ["claude", "-p", PROMPT_FRAME + prompt, "--output-format", "json",
           "--max-budget-usd", f"{max_run_usd:g}", "--session-id", session_id,
           "--permission-mode", "acceptEdits", "--setting-sources", "project,local"]
    allowed = list(ALLOWED_TOOLS)
    if setup["mcp"]:
        allowed += ["mcp__youk-core", "mcp__youk-code"]
        cmd += ["--mcp-config", str(mcp_file), "--strict-mcp-config"]
    cmd += ["--allowedTools", ",".join(allowed)]
    for plugin in setup["plugin_dirs"]:
        cmd += ["--plugin-dir", str(plugin)]
    if model:
        cmd += ["--model", model]
    return cmd


def parse_claude_json(stdout: str) -> dict:
    """The `result` message from `claude -p --output-format json` (a dict, or a list of messages)."""
    data = json.loads(stdout)
    if isinstance(data, list):
        data = next((m for m in reversed(data) if isinstance(m, dict) and m.get("type") == "result"),
                    {})
    return data if isinstance(data, dict) else {}


def outcome_from_json(data: dict) -> AgentOutcome:
    usage = data.get("usage") or {}
    tok_in = sum(int(usage.get(k) or 0) for k in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return AgentOutcome(
        cost_usd=float(data.get("total_cost_usd") or 0.0),
        turns=data.get("num_turns"),
        tok_in=tok_in or None,
        tok_out=usage.get("output_tokens"),
        # an agent that ran out of budget or turns still produced a gradable checkout
        error="" if not data.get("is_error") else str(data.get("subtype", "error"))[:60],
    )


def make_claude_agent(work: Path, superpowers_dir: Path | None, model: str | None,
                      max_run_usd: float, timeout_s: int) -> Agent:
    def agent(spec: RunSpec, workdir: Path, ctx: dict) -> AgentOutcome:
        setup = arm_setup(spec.arm, work, superpowers_dir)
        mcp_file = None
        if setup["mcp"]:
            mcp_file = setup["config_dir"] / "mcp.json"
            mcp_file.write_text(json.dumps(setup["mcp"]))
        cmd = agent_command(spec, setup, spec.task["prompt"], ctx["session_id"], model,
                            max_run_usd, mcp_file)
        env = {**os.environ, **{k: str(v) for k, v in setup["env"].items()},
               "CLAUDE_CONFIG_DIR": str(setup["config_dir"]), "YOUK_ROOT": str(ctx["youk_root"]),
               "YOUK_CORE_URL": os.environ.get("YOUK_CORE_URL", "http://127.0.0.1:8001")}
        try:
            done = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, env=env,
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return AgentOutcome(status="timeout", error="timeout")
        except OSError as exc:
            return AgentOutcome(status="infra_error", error=str(exc)[:80])
        try:
            data = parse_claude_json(done.stdout)
        except json.JSONDecodeError:
            data = {}
        if not data:
            return AgentOutcome(status="infra_error",
                                error=(done.stderr.strip().splitlines() or ["no output"])[-1][:80])
        out = outcome_from_json(data)
        if data.get("is_error") and "auth" in json.dumps(data).lower():
            out.status = "infra_error"
        return out
    return agent


# ---- dry run ----------------------------------------------------------------------------------

DRY_PASS_RATE = {"bare": 0.5, "full": 0.6, "superpowers": 0.55}


def fake_agent(spec: RunSpec, workdir: Path, ctx: dict) -> AgentOutcome:
    """No model. Applies the real commit's source change with an arm-dependent, deterministic
    probability, so grading, cost accounting and analysis run end to end for free."""
    roll = int(hashlib.sha256("|".join(map(str, spec.key)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if roll < DRY_PASS_RATE[spec.arm]:
        sources = spec.task["source_files"]
        subprocess.run(["git", "-C", str(workdir), "checkout", spec.task["sha"], "--", *sources],
                       capture_output=True, check=False)
    return AgentOutcome(cost_usd=0.10, turns=5, tok_in=1000, tok_out=200)


# ---- one run ----------------------------------------------------------------------------------

def prepare_checkout(repo: Path, task: dict, dest: Path) -> None:
    """Parent commit, the commit's new tests removed. Modified tests stay at their parent version."""
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(repo), str(dest)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", "--detach", task["parent_sha"]],
                   check=True, capture_output=True)
    for rel in task["added_tests"]:
        (dest / rel).unlink(missing_ok=True)


def restore_hidden_tests(dest: Path, task: dict) -> None:
    for rel in task["hidden_tests"]:
        blob = subprocess.run(["git", "-C", str(dest), "show", f"{task['sha']}:{rel}"],
                              capture_output=True, text=True, check=True).stdout
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(blob)


def ledger_counts(youk_root: Path, slug: str, session_id: str) -> dict:
    """Tool calls and corrections the hooks recorded for this session, if the arm has hooks."""
    try:
        import events
        sid = events.hash_identifier(session_id)
        mine = [e for e in events.read_events(youk_root, slug) if e.get("session") == sid]
        return {"tool_calls": sum(1 for e in mine if e["kind"] == "tool" and e.get("src") == "hook"),
                "corrections": sum(1 for e in mine if e["kind"] == "correction")}
    except Exception:
        return {"tool_calls": None, "corrections": None}


def execute_run(spec: RunSpec, repos: dict[str, dict], work: Path, agent: Agent,
                youk_root: Path) -> dict:
    task = spec.task
    cfg = repos[task["repo"]]
    repo = Path(cfg["path"]).expanduser()
    slug = f"bench-{task['repo']}"            # one stable slug per repo, so runs do not litter
    workdir = work / "runs" / slug
    session_id = str(uuid.uuid4())
    prepare_checkout(repo, task, workdir)
    start = time.monotonic()
    outcome = agent(spec, workdir, {"session_id": session_id, "youk_root": youk_root})
    wall = round(time.monotonic() - start, 1)
    passed = None
    if outcome.status != "infra_error":
        restore_hidden_tests(workdir, task)
        passed = mine_tasks.run_tests(workdir, task["test_cmd"], task["runnable_tests"])
    shutil.rmtree(workdir, ignore_errors=True)
    return {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "task": task["id"],
            "repo": task["repo"], "arm": spec.arm, "rep": spec.rep, "status": outcome.status,
            "passed": passed, "cost_usd": round(outcome.cost_usd, 4), "wall_s": wall,
            "turns": outcome.turns, "tok_in": outcome.tok_in, "tok_out": outcome.tok_out,
            "error": outcome.error, **ledger_counts(youk_root, slug, session_id)}


# ---- the battery ------------------------------------------------------------------------------

def plan(tasks: list[dict], arms: list[str], k: int, done: set) -> list[RunSpec]:
    specs = [RunSpec(t, a, r) for r in range(k) for t in tasks for a in arms]
    return [s for s in specs if s.key not in done]


def load_done(path: Path) -> set[tuple[str, str, int]]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") != "infra_error":      # an infrastructure failure is worth a retry
            out.add((row["task"], row["arm"], row["rep"]))
    return out


def over_cap(spent: float, costs: list[float], cap: float | None, max_run: float) -> bool:
    if cap is None:
        return False
    estimate = sum(costs) / len(costs) if len(costs) >= 3 else max_run
    return spent + estimate > cap


def run_battery(tasks: list[dict], arms: list[str], k: int, agent: Agent, repos: dict[str, dict],
                work: Path, out_path: Path, youk_root: Path, cap: float | None,
                max_run_usd: float, log=print) -> dict:
    done = load_done(out_path)
    specs = plan(tasks, arms, k, done)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spent, costs, ran, stopped = 0.0, [], 0, ""
    for spec in specs:
        if over_cap(spent, costs, cap, max_run_usd):
            stopped = f"cap ${cap:g} reached after ${spent:.2f}"
            break
        row = execute_run(spec, repos, work, agent, youk_root)
        with out_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        spent += row["cost_usd"]
        costs.append(row["cost_usd"])
        ran += 1
        log(f"{ran}/{len(specs)} {spec.task['id']} {spec.arm} rep{spec.rep}: "
            f"{row['status']} passed={row['passed']} ${row['cost_usd']:.2f}")
    return {"planned": len(specs), "ran": ran, "skipped_done": len(done), "spent_usd": round(spent, 2),
            "stopped": stopped}


def estimate_line(n_runs: int, max_run: float, cap: float | None) -> str:
    worst = n_runs * max_run
    return (f"{n_runs} runs; worst case ${worst:.0f} at ${max_run:g} per run"
            + (f"; cap ${cap:g}" if cap is not None else "; no cap (dry run)"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--k", type=int, default=1, help="repetitions per task and arm")
    ap.add_argument("--cap-usd", type=float, help="total spend limit; required unless --dry-run")
    ap.add_argument("--max-run-usd", type=float, default=DEFAULT_MAX_RUN_USD)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--model")
    ap.add_argument("--limit", type=int, help="use only the first N tasks (smoke test)")
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--superpowers-dir", type=Path)
    ap.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    ap.add_argument("--tasks-dir", type=Path, default=mine_tasks.TASKS_DIR)
    ap.add_argument("--repos", type=Path, default=mine_tasks.REPOS_FILE)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    arms = [a for a in args.arms.split(",") if a]
    bad = [a for a in arms if a not in ARMS]
    if bad:
        ap.error(f"unknown arms {bad}")
    if not args.dry_run and args.cap_usd is None:
        ap.error("--cap-usd is required for a real run (set the dollar limit deliberately)")

    tasks = mine_tasks.load_tasks(args.tasks_dir)
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.limit:
        tasks = tasks[:args.limit]
    if not tasks:
        ap.error(f"no tasks in {args.tasks_dir}; run scripts/sim/mine_tasks.py first")
    repos = {r["name"]: r for r in yaml.safe_load(args.repos.read_text())["repos"]}

    work = args.work_dir
    out = args.out or RESULTS_DIR / f"{datetime.now(UTC):%Y-%m-%d}{'-dry' if args.dry_run else ''}.jsonl"
    youk_root = work / "youk-root"
    youk_root.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        agent: Agent = fake_agent
    else:
        for arm in arms:
            arm_setup(arm, work, args.superpowers_dir)       # fail fast on a missing checkout
        if shutil.which("claude") is None:
            ap.error("the claude CLI is not on PATH")
        agent = make_claude_agent(work, args.superpowers_dir, args.model, args.max_run_usd,
                                  args.timeout)
    print(estimate_line(len(plan(tasks, arms, args.k, load_done(out))), args.max_run_usd,
                        args.cap_usd))
    summary = run_battery(tasks, arms, args.k, agent, repos, work, out, youk_root,
                          args.cap_usd, args.max_run_usd)
    print(json.dumps(summary))
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
