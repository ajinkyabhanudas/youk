# Running the replay battery

Built in S08 to S10. Nothing here runs by itself; every real run needs a dollar cap.

## Steps

1. Mine tasks (free, runs tests locally): `uv run python scripts/sim/mine_tasks.py`. Writes `bench/tasks/*.yaml`.
   Prompts were reviewed on 2026-10-05: 14 of 22 tasks are usable, the rest are marked `review.fair: false` and skipped by the runner. Audit with `mine_tasks.py --review`; set `review.fair` in a task file to overrule.
2. Dry run, no model: `uv run python scripts/sim/run_battery.py --dry-run --arms bare,full,superpowers`. Then `uv run python scripts/sim/analyze.py bench/results/<date>-dry.jsonl` to see the table shape.
3. Smoke test, two tasks, one arm: `uv run python scripts/sim/run_battery.py --arms bare --limit 2 --cap-usd 5`. Check the cost per run before scaling.
3b. Triage pilot (required): run `run_battery.py --arms bare --k 3 --pilot-run --cap-usd <cap>` on all candidate tasks, then `uv run python scripts/sim/design.py <pilot.jsonl> --k 3 --target-effect 0.15 --cost-per-run <measured>`. The runner refuses a real run without `--pilot` and a passing design.
4. Comparison run (after the pilot passes), for example: `uv run python scripts/sim/run_battery.py --cap-usd 50 --k 3 --pilot <pilot.jsonl>`. Add `--arms bare,full,superpowers --superpowers-dir <checkout>` later.
5. Analyse: `uv run python scripts/sim/analyze.py bench/results/<date>.jsonl --decision`. Paste the table into the log and the entry into DECISIONS.md. That triggers G1.

## Arms

| Arm | Config dir | Plugins | Brief | Gates | youk tools |
|---|---|---|---|---|---|
| bare | `~/.cache/youk-bench/config/bare` | youk hooks | none | off | none |
| full | `.../config/full` | youk hooks | yes, from the live youk-core | on | youk-core, youk-code |
| superpowers | `.../config/superpowers` | Superpowers only | n/a | n/a | none |

`superpowers` needs a local checkout of the plugin (`--superpowers-dir`). The runner never installs anything.

## Things to know before a real run

- Auth is subscription only by default. Run `claude setup-token` once in your terminal and `export CLAUDE_CODE_OAUTH_TOKEN=<token>`; each isolated config dir has no login of its own, and the token works in all of them. In this mode the runner removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the agent's environment, so a key in your shell is never billed. `--auth api-key` uses a key instead and is never chosen on its own.
- Under a subscription nothing is billed per token. `total_cost_usd` is what the same tokens would cost at API rates, so the $50 cap limits how many tokens the battery uses. The real constraint is your subscription's usage limit: a run that hits it comes back as an error with zero tokens, is recorded as `infra_error`, and three in a row stop the battery. Rerunning continues where it stopped.
- Measured 2026-10-05: a one-word prompt cost $0.15 notional with the default config (23k tokens of context), and `claude -p --output-format json` returns `total_cost_usd`, `usage` and `num_turns` as the runner expects. An isolated config dir with no credentials returns `is_error: true`, `result: "Not logged in"` and zero tokens.
- The `full` arm calls the live youk-core for its brief. That writes session state under the project slugs `bench-<repo>` in `~/.claude/youk`. The runner removes every `bench-*` entry under `knowledge/projects` and `state` when it finishes (`--youk-home`).
- Hook events go to `~/.cache/youk-bench/youk-root`, not the real ledger. `superpowers` has no youk hooks, so its tool-call count is empty; use `turns`.
- Wall time includes the hidden-test run only in the grade, not in `wall_s`; `wall_s` is the agent alone.
- A timeout is graded on whatever the agent left; it counts as an attempt.
- Cost is the CLI's own `total_cost_usd`. Subscription logins may report cost differently; check the first run against the billing page.
