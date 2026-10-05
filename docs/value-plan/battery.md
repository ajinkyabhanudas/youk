# Running the replay battery

Built in S08 to S10. Nothing here runs by itself; every real run needs a dollar cap.

## Steps

1. Mine tasks (free, runs tests locally): `uv run python scripts/sim/mine_tasks.py`. Writes `bench/tasks/*.yaml`.
   Review the prompts for fairness (`--review`) and mark `review.fair` in each file; delete any task whose prompt gives the answer away.
2. Dry run, no model: `uv run python scripts/sim/run_battery.py --dry-run`. Then `uv run python scripts/sim/analyze.py bench/results/<date>-dry.jsonl` to see the table shape.
3. Smoke test, two tasks, one arm: `uv run python scripts/sim/run_battery.py --arms bare --limit 2 --cap-usd 5`. Check the cost per run before scaling.
4. First baseline: `uv run python scripts/sim/run_battery.py --cap-usd <cap> --k 1 --superpowers-dir <checkout>`.
5. Analyse: `uv run python scripts/sim/analyze.py bench/results/<date>.jsonl --decision`. Paste the table into the log and the entry into DECISIONS.md. That triggers G1.

## Arms

| Arm | Config dir | Plugins | Brief | Gates | youk tools |
|---|---|---|---|---|---|
| bare | `~/.cache/youk-bench/config/bare` | youk hooks | none | off | none |
| full | `.../config/full` | youk hooks | yes, from the live youk-core | on | youk-core, youk-code |
| superpowers | `.../config/superpowers` | Superpowers only | n/a | n/a | none |

`superpowers` needs a local checkout of the plugin (`--superpowers-dir`). The runner never installs anything.

## Things to know before a real run

- Auth: an isolated `CLAUDE_CONFIG_DIR` has no login. Export `ANTHROPIC_API_KEY`, or log in once per config dir
  (`CLAUDE_CONFIG_DIR=~/.cache/youk-bench/config/bare claude`). A run that fails on auth is recorded as `infra_error`, not as a failed task, and is retried on the next invocation.
- The `full` arm calls the live youk-core for its brief. That writes session state under the project slugs `bench-<repo>` in `~/.claude/youk/knowledge`. Delete those directories after the battery.
- Hook events go to `~/.cache/youk-bench/youk-root`, not the real ledger. `superpowers` has no youk hooks, so its tool-call count is empty; use `turns`.
- Wall time includes the hidden-test run only in the grade, not in `wall_s`; `wall_s` is the agent alone.
- A timeout is graded on whatever the agent left; it counts as an attempt.
- Cost is the CLI's own `total_cost_usd`. Subscription logins may report cost differently; check the first run against the billing page.
