# S10 Headless runner and analysis

Size L (split S10a runner, S10b analysis if the first overruns). Depends: S05, S08, S09. Metric: B.

**Goal.** Run task x arm x repetitions headlessly, then compare arms with intervals. First run is the G1 baseline.

**Why.** This is the evidence youk lacks and Superpowers also lacks.

**Load.** `bench/tasks/`, `bench/arms/`, `servers/shared/events.py`, `scripts/value_report.py`. External: the `claude` CLI docs.

**Verify first.**
- Headless flag set (`-p`, JSON output with token usage) and config isolation per arm (separate config dir).
- How to install the Superpowers plugin into an isolated config dir.
- Per-run timeout and a way to enforce the dollar cap.

**Build.**
- `scripts/sim/run_battery.py`: worktree per run, arm config dir, run agent, restore hidden tests, run them, collect
  pass/fail, tokens, wall time, tool calls, events. Results to `bench/results/{date}.jsonl`.
- `scripts/sim/analyze.py`: paired comparison per task, bootstrap intervals, table of pass@1, cost, time per arm.
- Arms: bare, full, superpowers. Repetitions k=3 at first.
- `--dry-run` with a fake agent for tests.
- DECISIONS.md entry template filled by the analysis.

**Tests.** Dry run end to end; analysis against synthetic results with known differences.

**Out of scope.** Changing youk to improve results (S11, S12).

**DoD.** Standard DoD plus a stated dollar cap and total spent in the handoff.

**Kill criterion.** If k=3 runs on 20 tasks cost more than the cap, reduce tasks, not rigor.

**Handoff.** Paste the arm comparison table. This triggers G1.
