# E1 Eval v2: triage pilot, M+ tier, design gate

Size M. Depends: S10. Metric: B, V3. Replaces the G1 design, which could not decide anything.

**Goal.** A battery that can answer "does full, lean or bare solve more, and at what cost" on small and on M+ tasks, and says in advance what it can detect.

**Why.** G1: 14 tasks, k=1, 12 of 14 tasks identical across arms, power about 8% at a 15-point effect. See `research-eval-design.md`.

**Build (done in this branch).** `scripts/sim/design.py` (triage, power, minimum detectable effect, cost, interim stop rule) and a design gate in `run_battery.py`: no `--pilot`, or a design that cannot see the target effect, refuses to run; `--allow-underpowered` overrides and is recorded in `<results>.design.json`.

**Build (next).**
1. Miner tier flag: `--tier m` with limits up to 12 files and 500 lines; tasks carry `tier` (s or m); analysis reports tiers separately.
2. Triage pilot on the bare arm only, k=3, on all candidate tasks. Keep mixed tasks (bare passes sometimes). Report ceiling and floor counts. No selection on any other arm.
3. Add "should not fire" tasks (trivial changes) so youk's overhead on small work is measured, not assumed.
4. Failure-reason tag per run (timeout, quit early, wrong fix, infra) written to the results row.
5. Rounds with interim looks using `design.interim_decision`; stop for efficacy or futility.
6. Arms: bare, lean, full. Cost-matched retry baseline (bare with a second attempt) as a fourth arm only if the budget allows.

**Verify first.** The pilot's informative share is at least 50%. If not, mine more or harder tasks before spending on the arm comparison.

**DoD.** Standard DoD plus: design report attached to the results, the decision entry names the minimum detectable effect, and a result inside that effect is written as "no effect larger than X detected", never "no effect".

**Kill criterion.** If after two pilots the informative share stays under 30%, stop replay evaluation and rely on the live ledger and a randomized live trial.

**Handoff.** Pilot table (task, bare k=3 result, label), design report, estimated and actual cost.
