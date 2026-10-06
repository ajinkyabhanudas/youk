# Value plan (anchor)

Every session on this plan reads this file and its own card in `cards/`, and nothing else by default.
Keep this file under ~3,000 tokens. At session end finish the task with `task_checkpoint` and add an entry to `log.md`; promote to "Facts later cards rely on" only what every later card needs.

## Thesis

youk wins by being the measured, minimal, enforced layer around the model. Deterministic rules
move out of prompts into code and hooks, so they cost no tokens and cannot be skipped. The model
keeps only judgment. Every component has to show an outcome number or it gets cut.

Against Superpowers: it publishes no outcome numbers, has no memory, and enforces by prompt.
youk's wedge is (1) measured results, (2) contracts that stop repeat mistakes, (3) mechanical
enforcement, (4) a small always-on footprint, (5) review-ready evidence on every change.

## Why this plan (evidence, 2026-10-05)

- 11 of 32 registered stages have ever fired; 18 have no real log (`scripts/system_status.py`).
- Skill-invocation log holds 1 record across all sessions. Model-reported logging does not work.
- STATS.md: org_score measures gates fired, not code quality. Developer autonomy 0/87.
- No per-call usage trace exists. The wiring pulse checks that a tool name appears somewhere, not that it ran.
- Always-on, measured by `scripts/footprint.py` (chars/4): CLAUDE.md template 2.3k, AGENTS.md 0.8k, 54 skill descriptions 7.9k, total 11.1k tokens, plus the brief. Not always loaded: skill bodies 147k, MCP docstrings 16k (86 tools).
- Research: context files cost +20% and gain ~0-4% ([arXiv 2602.11988](https://arxiv.org/abs/2602.11988)); instruction compliance decays with count; METR found devs 19% slower while feeling 20% faster; developers name verification as the top bottleneck.
- youk's own learned patterns already say this: put deterministic rules in code, replace proxy metrics with outcome metrics.

## Start here (next session: S11 and S12, G1 recorded)

Run `python3 scripts/plan_status.py` to see where the plan stands, read this file, then `battery.md`. Nothing else by default.
Work in a git worktree off `origin/main`; do not switch branches in `~/.claude/youk` (live bind mount, see Operating notes).

**Status.** S00 to S10 are merged. G1 is recorded (see DECISIONS.md 2026-10-06 and log.md): full did not beat bare in a measurable way (+0.07, interval +0.00 to +0.21, 14 tasks), at 1.20x cost. By the gate's rule S11 and S12 are the priority. The reading is inconclusive rather than negative; a k=3 rerun (about $75 notional) would tighten it.
The live install is on main and the ledger collects real events from the battery root only.

**Next.** S11, then S12, each judged against G2 (lean within 5 points of full, always-on at or under 3k tokens, tokens per task down 30%).

## First goal (M1: youk can see itself)

Done when, after 5 real sessions with hooks live, one command prints per-skill and per-tool fire counts,
correction, test and commit counts, hook p95 ms, and the always-on token table, all from the ledger.
Cards: S02, S03, S01. No behaviour of youk changes in M1. Outputs: ledger, taps, footprint baseline.
It unlocks every removal decision, because deleting anything before M1 is a guess.

## Value contract

| Id | Outcome | Measured as |
|---|---|---|
| V1 | Fewer repeated corrections | correction events per M+ task; repeat-gap rate (EVAL.md definition) |
| V2 | Review-ready changes | first-pass acceptance (no fix request in next 3 turns and tests green at stop); evidence-packet present rate |
| V3 | Low overhead | always-on tokens (budget 3k, brief 1k); tokens and wall time per task; hook p95 ms; session_start ms |
| B | Correctness on replayable tasks | pass@1 on hidden tests, cost, time, per arm |

Arms: `bare` (events only), `full` (current youk), `lean` (new), `superpowers` (external, sandboxed).
Any component with no movement on V1, V2, V3 or B after its review date is removed.

## Standard DoD (every card)

1. Tests green, ruff clean, full suite green.
2. New stage, tool, hook or skill has a `docs/system-map.yaml` entry with `grounding` and `emits`.
3. It emits a typed event asserted in a test, or is tagged `diagnostic: true` with a reason.
4. Token cost declared; footprint budget not exceeded.
5. Metric and kill criterion plus review date written in the card.
6. Task finished via `task_checkpoint`, 5-line entry added to `log.md`; `/learn` run.

Items 2 to 4 apply once S02, S06 and S01 land.

## NFR defaults (pre-answered for nfr_check)

- Failure isolation: emit and hooks never raise or block; exit 0 on any error.
- Privacy: ADR-011. Events carry scalars, enums and hashed ids only. No free text.
- Concurrency: append-only through `locked_jsonl_append`. No read-modify-write.
- Volume: shard per project per month; readers stream; no unbounded in-memory loads.
- Schema: `v` field, additive changes only. Events carry `eid`; readers dedupe.
- Cost: hook p95 budget 50 ms (verify in S03). Experiment runs have a hard dollar cap set by Ajinkya.

## Session protocol (context cost control)

- Load: this file, your card, the files the card lists under "Load". Nothing else.
- If a card needs more than ~8 files or ~3k lines of reading, split it before starting.
- Cards name "Verify first" assumptions. Check them in the first 10 minutes; if one is false, stop and amend the card.
- End: finish the task with `task_checkpoint` (it marks the task done), add a 5-line entry to `log.md`, run `/learn`.
- Task graph: `tasks.json` holds ids and edges; `plan_status.py --load` puts them in the graph.

## Status

Not kept in any document. It lives in the task graph: `python3 scripts/plan_status.py` prints what is done,
what stopped mid-task and what is next. `tasks.json` defines the plan (ids, labels, dependencies) and
`plan_status.py --load` adds any task the graph lacks. Work that names a task ("build S08") is routed to that
task's node, started by `route_task` and finished by `task_checkpoint`, so status updates as a side effect of
doing the work. See `docs/resume-state.md`.

## Phase 1 status (S00 to S07): merged

#177 make-version-skip, #178 digest, #179 plan docs, #180 uv (S00), #181 event ledger (S02), #182 hook taps (S03),
#183 footprint (S01), #184 contracts (S07), #185 server spans (S04), #186 value report (S05), #187 registry gate (S06),
all merged to main. Follow-ups (phrase lists, `tool_response`) in #189. Nothing runs live until `~/.claude/youk` is
updated to main and youk-core restarts; the ledger stays empty until the plugin hooks reload in a new session.

## Phase 2 status (S08 to S10): built, first run pending

Branch vp/12-replay-battery. `scripts/sim/mine_tasks.py`, `run_battery.py`, `analyze.py`, `servers/shared/arms.py`, `bench/repos.yaml`, `bench/tasks/`, `bench/arms/`. See `battery.md` to run it.

## Operating notes

- Work in a git worktree. `~/.claude/youk` is bind-mounted into the youk containers as `/youk` and `/shared`,
  so switching branches there changes the code the running server reads.
- The deploy-freshness gate (`plugin/scripts/server_freshness.py`) auto-restarts youk-core on the next youk tool
  call when a commit under `servers/` or `skills/` is newer than the container's boot. On 2026-10-05 it already
  counted three such commits before this work, so the first youk call from any session restarts the server.
- Local environment: `uv sync`, then `uv run pytest`. GNU make 4 is needed for two Makefile tests (macOS ships 3.81;
  `brew install make`). The pre-commit contract runs the full suite through `uv run --frozen`.
- Hook payload field names in S03 are partly unverified live; check the first real ledger with `make value-report`.

## Order

S00 (reproducible env first), S02, S03, S01, S07 (quick fix, visible bug), S04, S05, S06, S08, S09, S10 (built; first run pending), G1, then S11, S12, S13, S14 in
that order. S15 runs whenever youk-core can be restarted safely. S16 waits for data.

## Gates

- G1 (after first S10 run): compare bare, full, superpowers on B. If full is not better than bare on
  pass rate, or costs over 1.3x, S11 and S12 are the priority and S13 may be cut to test-run-only.
- G2 (after S11, S12): lean pass rate within 5 points of full (CI), always-on at or under 3k tokens,
  tokens per task down at least 30%. Fail means bisect by component and revert the offender.
- Market claims only from battery results with intervals, with live data labelled as anecdote.

## Not doing until G2

Langfuse export of events, semantic similarity graph, new skills, team or multi-user features, new personas.
Each lacks a measured need today.

## Limits (state these wherever results are shown)

- Replay tasks measure correctness and cost on bug-fix and small-feature work. They do not measure
  compounding across sessions or review time. Live A/B covers those, with a small sample.
- Mined tasks come from private repos to limit contamination, but the model may still have seen similar code.
- Superpowers arm uses its default config on my sandbox. Results are not a statement about its best case.
- Hook and CLI behaviour in cards is "verify first", not assumed.

## Facts later cards rely on

- Ledger: `events.emit(root, slug, kind=, name=, ...)`; kinds tool, skill, gate, hook, correction, test, commit, outcome, session; ids hashed; never raises.
- Counting rule: calls and corrections from `src=hook`, latency, gates and M+ task counts from `src=server`.
- Server events have no arm yet (the container has no `YOUK_ARM`); S09 must give them one or per-arm M+ rates break.
- Hook cost: about 41 ms p50 per call including interpreter start, with `python3 -S`. Hook `hook` events are sampled 1 in 10 (`n=10` is the weight).
- `make value-report`, `make footprint` (budget 11,050 tokens), `scripts/classify_contracts.py` (16 mechanical contracts of 208, for S12).
- Arms: `servers/shared/arms.py`. Default arm is `full`; `YOUK_ARM` pins, `YOUK_ARM_MODE=randomize` hashes. Every emitter reads the arm through `current_arm(root, slug)` (state file `state/session-arm/{slug}`), so server events carry it.
- Battery: `run_battery.py` needs `--cap-usd`; results in `bench/results/`; `analyze.py` resamples tasks, not runs.
- Per-card detail: `log.md`.
