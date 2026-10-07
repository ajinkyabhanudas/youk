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

## Phases

Each phase is safe to stop after. Each one says what it leaves behind and how to resume, so a disrupted session or a low usage week costs a rerun of one command and nothing more. Model usage only happens in E1C.

| phase | what | model usage | leaves behind | resume |
|---|---|---|---|---|
| E1a | miner `--tier m` and `--skip-existing`, runner `--chunk N` | none | a merged PR | read git log for the PR, rerun the tests |
| E1b | mine M+ tasks, `mine_tasks.py --tier m --per-repo 12 --skip-existing` | none, tests run locally | `bench/tasks/*.yaml` with `tier: m` | rerun the same command, finished tasks are skipped |
| E1e | look up public multi-language task sets, written up in `docs/value-plan/public-tasks.md` | a little for the lookup | the research note | read the note, nothing to rerun |
| E1f | `scripts/sim/public_tasks.py` loader, and grading in the instance image through the swebench harness | none | a merged PR | read git log for the PR, rerun the tests |
| E1g | `public_tasks.py fetch`, then `sample --per-language 3` and a read of each statement | none, one download | `bench/tasks-public/*.yaml` | rerun with `--skip-existing`, finished tasks are kept |
| E1c | bare pilot in chunks, `run_battery.py --arms bare --k 3 --pilot-run --chunk 3 --cap-usd 10 --out bench/results/pilot.jsonl` | yes, about 9 runs per call | rows in `bench/results/pilot.jsonl` | rerun the same command, finished rows are skipped |
| E1d | `design.py bench/results/pilot.jsonl --k 3`, then decide the comparison | none | the design report | rerun, it only reads the pilot file |

Run E1c on `bench/tasks` first, and on `--tasks-dir bench/tasks-public` as a second pass. Run it only when the week's usage allows it. One call is a chunk of 3 tasks, and stopping between calls loses nothing. Check progress at any time with the design command from E1d.
