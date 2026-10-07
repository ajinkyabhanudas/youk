#!/usr/bin/env python3
"""Run the replay battery: task x arm x repetition, headless, graded by the hidden tests (S10).

For each run: a fresh clone of the repo at the task's parent commit with the commit's new tests
removed, the agent run through `claude -p` under the arm's own config directory, then the hidden
tests restored and run. One JSON line per run goes to bench/results/{date}.jsonl.

Arms:
  bare          youk's hooks (events only), no brief, gates off, no youk tools
  full          youk as installed: hooks, brief, CLAUDE.md template, youk-core and youk-code tools
  superpowers   the Superpowers plugin from a checkout you give with --superpowers-dir, no youk

Auth: subscription by default. API keys are supported (`--auth api-key`) and never used unless asked:
in the default mode ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are removed from the agent's
environment, and CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) is required, because each
isolated config dir has no login of its own. Under a subscription `total_cost_usd` is notional,
what the same tokens would cost at API rates, so the cap limits tokens used, not dollars billed.

Money: --cap-usd is required for a real run. Each run also gets --max-budget-usd, so one runaway
cannot spend the cap. The loop stops before a run it expects to push spending over the cap.
Order is repetition, then task, then arm, so stopping early leaves paired data, not one full arm.

    python3 scripts/sim/run_battery.py --dry-run --arms bare,full,superpowers   fake agent, no money
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
import design  # noqa: E402
import mine_tasks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "bench" / "results"
ARMS = ("bare", "full", "superpowers")
DEFAULT_WORK = Path.home() / ".cache" / "youk-bench"
DEFAULT_TIMEOUT_S = 900
MAX_CONSECUTIVE_INFRA = 3     # stop instead of burning through the task list on a broken setup
AUTH_MODES = ("subscription", "api-key")
KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
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
        claude_md.write_text((REPO_ROOT / "bench" / "arms" / "full" / "CLAUDE.md").read_text())
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
    else:
        # No MCP servers at all, so a repo's own .mcp.json or a stray user config cannot give
        # an arm tools it was not meant to have.
        cmd += ["--mcp-config", json.dumps({"mcpServers": {}}), "--strict-mcp-config"]
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


def auth_env(base: dict, mode: str) -> dict:
    """The environment the agent runs in. Subscription mode removes every API credential so a key
    in the shell can never be billed by accident; api-key mode removes the OAuth token instead."""
    if mode not in AUTH_MODES:
        raise ValueError(f"unknown auth mode {mode!r}")
    env = dict(base)
    drop = KEY_VARS if mode == "subscription" else (TOKEN_VAR,)
    for name in drop:
        env.pop(name, None)
    return env


def check_auth(base: dict, mode: str) -> str:
    """"" if the chosen mode has its credential, else what to do about it."""
    if mode == "subscription" and not base.get(TOKEN_VAR):
        return (f"subscription mode needs {TOKEN_VAR}. Run `claude setup-token` in your terminal "
                f"and export the token it prints, or pass --auth api-key to use a key.")
    if mode == "api-key" and not base.get("ANTHROPIC_API_KEY"):
        return "api-key mode needs ANTHROPIC_API_KEY in the environment."
    return ""


def is_infra_failure(data: dict) -> bool:
    """An error result that never reached the model (not logged in, rate limit, network). Zero
    tokens and an error means the agent did not get to try the task."""
    usage = data.get("usage") or {}
    spent = sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                "cache_creation_input_tokens"))
    return bool(data.get("is_error")) and spent == 0


def make_claude_agent(work: Path, superpowers_dir: Path | None, model: str | None,
                      max_run_usd: float, timeout_s: int, auth: str = "subscription") -> Agent:
    def agent(spec: RunSpec, workdir: Path, ctx: dict) -> AgentOutcome:
        setup = arm_setup(spec.arm, work, superpowers_dir)
        mcp_file = None
        if setup["mcp"]:
            mcp_file = setup["config_dir"] / "mcp.json"
            mcp_file.write_text(json.dumps(setup["mcp"]))
        cmd = agent_command(spec, setup, spec.task["prompt"], ctx["session_id"], model,
                            max_run_usd, mcp_file)
        env = {**auth_env(dict(os.environ), auth), **{k: str(v) for k, v in setup["env"].items()},
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
        if is_infra_failure(data):
            out.status = "infra_error"
            out.error = str(data.get("result", "error"))[:80]
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
                "corrections": sum(1 for e in mine if e["kind"] == "correction"),
                "hook_events": len(mine)}
    except Exception:
        return {"tool_calls": None, "corrections": None, "hook_events": None}


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
    counts = ledger_counts(youk_root, slug, session_id)
    # A youk arm whose hooks never fired (a plugin that failed to load) is not that arm: the run
    # is set aside as an infrastructure error and retried, not counted.
    if (spec.arm in ("bare", "full") and agent is not fake_agent and outcome.status == "ok"
            and not counts["hook_events"]):
        outcome.status, outcome.error, passed = "infra_error", "youk hooks did not fire", None
    return {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "task": task["id"],
            "repo": task["repo"], "arm": spec.arm, "rep": spec.rep, "status": outcome.status,
            "passed": passed, "cost_usd": round(outcome.cost_usd, 4), "wall_s": wall,
            "turns": outcome.turns, "tok_in": outcome.tok_in, "tok_out": outcome.tok_out,
            "error": outcome.error, **counts}


# ---- the battery ------------------------------------------------------------------------------

def plan(tasks: list[dict], arms: list[str], k: int, done: set) -> list[RunSpec]:
    specs = [RunSpec(t, a, r) for r in range(k) for t in tasks for a in arms]
    return [s for s in specs if s.key not in done]


def next_chunk(tasks: list[dict], arms: list[str], k: int, done: set, n: int) -> list[dict]:
    """The first n tasks that still have a run to do, in file order."""
    pending = {s.task["id"] for s in plan(tasks, arms, k, done)}
    return [t for t in tasks if t["id"] in pending][:n]


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
    spent, costs, ran, stopped, streak = 0.0, [], 0, "", 0
    for spec in specs:
        if over_cap(spent, costs, cap, max_run_usd):
            stopped = f"cap ${cap:g} reached after ${spent:.2f}"
            break
        if streak >= MAX_CONSECUTIVE_INFRA:
            stopped = f"{streak} infrastructure errors in a row; fix the setup and rerun"
            break
        row = execute_run(spec, repos, work, agent, youk_root)
        streak = streak + 1 if row["status"] == "infra_error" else 0
        with out_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        spent += row["cost_usd"]
        costs.append(row["cost_usd"])
        ran += 1
        log(f"{ran}/{len(specs)} {spec.task['id']} {spec.arm} rep{spec.rep}: "
            f"{row['status']} passed={row['passed']} ${row['cost_usd']:.2f}")
    return {"planned": len(specs), "ran": ran, "skipped_done": len(done), "spent_usd": round(spent, 2),
            "stopped": stopped}


def cleanup_bench_state(youk_home: Path) -> list[str]:
    """Remove what the full arm's live youk-core left for the battery's project slugs. Only
    entries whose name starts with `bench-` under knowledge/projects and state are touched."""
    removed = []
    for base in (youk_home / "knowledge" / "projects", youk_home / "state"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("bench-*")):
            if not path.name.startswith("bench-") or path.is_symlink():
                continue
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed.append(str(path.relative_to(youk_home)))
            except OSError:
                pass
    return removed


def design_gate(pilot_path: Path | None, arms: list[str], k: int, cap: float | None,
                target_effect: float, allow_underpowered: bool,
                out_path: Path) -> tuple[bool, str]:
    """The pre-run design check (scripts/sim/design.py). A real run needs a baseline pilot and a
    design that can see the target effect. An override is allowed but is written next to the
    results, so an underpowered run is never mistaken for a sound one."""
    if pilot_path is None or not Path(pilot_path).exists():
        text = ("no pilot results given (--pilot). Run the baseline arm on the candidate tasks "
                "with k>=2 first; without it floor and ceiling tasks cannot be told from noise.")
        report = {"ok": False, "problems": [text]}
    else:
        rows = design.load_rows(Path(pilot_path))
        baseline = "bare" if "bare" in arms else arms[0]
        rates = design.base_rates(rows, baseline)
        costs = [r.get("cost_usd") or 0.0 for r in rows
                 if r.get("arm") == baseline and r.get("status") == "ok"]
        report = design.design_report(
            rates, k, len(arms), target_effect,
            cost_per_run=(sum(costs) / len(costs)) if costs else DEFAULT_MAX_RUN_USD / 3,
            cap_usd=cap)
        text = design.render(report)
    report["override"] = bool(allow_underpowered and not report["ok"])
    out_path.with_suffix(".design.json").write_text(json.dumps(report, indent=1, default=str))
    return (report["ok"] or allow_underpowered), text


def pilot_gate(arms: list[str], k: int, n_tasks: int, cap: float | None,
               cost_per_run: float = DEFAULT_MAX_RUN_USD / 3) -> tuple[bool, str]:
    """A pilot is the baseline arm alone with k>=2, to find which tasks can discriminate. It is
    exempt from the power check (it produces the data for it) but not from the cost check."""
    problems = []
    if arms != ["bare"]:
        problems.append("a pilot runs the baseline arm only (--arms bare)")
    if k < 2:
        problems.append("a pilot needs k>=2 so floor and ceiling tasks can be told from noise")
    est = design.cost_estimate(n_tasks, k, 1, cost_per_run)
    if cap is not None and est > cap:
        problems.append(f"estimated pilot cost ${est} exceeds the cap ${cap:g}")
    text = f"pilot: {n_tasks} tasks x k={k} x bare, estimated ${est} at ${cost_per_run:.2f} per run"
    return (not problems), "\n".join([text, *[f"PROBLEM: {p}" for p in problems]])


def estimate_line(n_runs: int, max_run: float, cap: float | None) -> str:
    worst = n_runs * max_run
    return (f"{n_runs} runs; worst case ${worst:.0f} at ${max_run:g} per run"
            + (f"; cap ${cap:g}" if cap is not None else "; no cap (dry run)"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arms", default="bare,full",
                    help="comma-separated; add superpowers once you have --superpowers-dir")
    ap.add_argument("--k", type=int, default=1, help="repetitions per task and arm")
    ap.add_argument("--cap-usd", type=float, help="total spend limit; required unless --dry-run")
    ap.add_argument("--max-run-usd", type=float, default=DEFAULT_MAX_RUN_USD)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--model")
    ap.add_argument("--limit", type=int, help="use only the first N tasks (smoke test)")
    ap.add_argument("--chunk", type=int,
                    help="run only the next N tasks that still have unfinished runs, then stop")
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--auth", choices=AUTH_MODES, default="subscription",
                    help="subscription (default, needs CLAUDE_CODE_OAUTH_TOKEN) or api-key")
    ap.add_argument("--youk-home", type=Path, default=Path.home() / ".claude" / "youk",
                    help="live youk install whose bench-* state is removed after the run")
    ap.add_argument("--pilot", type=Path,
                    help="baseline results (k>=2) used by the pre-run design check")
    ap.add_argument("--target-effect", type=float, default=design.DEFAULT_TARGET_EFFECT,
                    help="smallest pass-rate difference that would change a decision")
    ap.add_argument("--pilot-run", action="store_true",
                    help="this run is the baseline pilot (bare only, k>=2); skips the power check")
    ap.add_argument("--allow-underpowered", action="store_true",
                    help="run even if the design check fails; recorded in the .design.json")
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

    tasks = mine_tasks.usable(mine_tasks.load_tasks(args.tasks_dir))
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.limit:
        tasks = tasks[:args.limit]
    if not tasks:
        ap.error(f"no tasks in {args.tasks_dir}; run scripts/sim/mine_tasks.py first")
    out = args.out or RESULTS_DIR / f"{datetime.now(UTC):%Y-%m-%d}{'-dry' if args.dry_run else ''}.jsonl"
    if args.chunk:
        tasks = next_chunk(tasks, arms, args.k, load_done(out), args.chunk)
        if not tasks:
            print("nothing left: every task has finished runs")
            return 0
    repos = {r["name"]: r for r in yaml.safe_load(args.repos.read_text())["repos"]}

    work = args.work_dir
    youk_root = work / "youk-root"
    youk_root.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        if args.pilot_run:
            ok, text = pilot_gate(arms, args.k, len(tasks), args.cap_usd)
        else:
            ok, text = design_gate(args.pilot, arms, args.k, args.cap_usd, args.target_effect,
                                   args.allow_underpowered, out)
        print(text)
        if not ok:
            print("refusing to spend: the design check failed (see "
                  "docs/value-plan/research-eval-design.md). --allow-underpowered overrides.",
                  file=sys.stderr)
            return 2
    if args.dry_run:
        agent: Agent = fake_agent
    else:
        for arm in arms:
            arm_setup(arm, work, args.superpowers_dir)       # fail fast on a missing checkout
        if shutil.which("claude") is None:
            ap.error("the claude CLI is not on PATH")
        problem = check_auth(dict(os.environ), args.auth)
        if problem:
            ap.error(problem)
        agent = make_claude_agent(work, args.superpowers_dir, args.model, args.max_run_usd,
                                  args.timeout, args.auth)
    print(estimate_line(len(plan(tasks, arms, args.k, load_done(out))), args.max_run_usd,
                        args.cap_usd))
    summary = run_battery(tasks, arms, args.k, agent, repos, work, out, youk_root,
                          args.cap_usd, args.max_run_usd)
    print(json.dumps(summary))
    if not args.dry_run:
        gone = cleanup_bench_state(args.youk_home)
        print(f"removed {len(gone)} bench-* state entries from {args.youk_home}")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
