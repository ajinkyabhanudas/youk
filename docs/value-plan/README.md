# Value plan (anchor)

Every session on this plan reads this file and its own card in `cards/`, and nothing else by default.
Keep this file under ~1,500 tokens. Update the status table and "State of the world" at session end.

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
- Always-on estimate (chars/4, S01 replaces it): CLAUDE.md ~2.3k, AGENTS.md ~0.7k, 54 skill descriptions ~8.4k, brief ~1k.
- Research: context files cost +20% and gain ~0-4% ([arXiv 2602.11988](https://arxiv.org/abs/2602.11988)); instruction compliance decays with count; METR found devs 19% slower while feeling 20% faster; developers name verification as the top bottleneck.
- youk's own learned patterns already say this: put deterministic rules in code, replace proxy metrics with outcome metrics.

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
6. Card status and 5-line state of the world updated here; `/learn` run.

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
- End: set card status, append a 5-line state of the world below, run `/learn`.
- Task graph: `tasks.json` holds ids and edges for `create_task_graph`. Not loaded yet (youk-core busy).

## Status

| Id | Title | Size | Depends | Status |
|---|---|---|---|---|
| S00 | Move dependency management to uv | M | none | todo |
| S01 | Footprint baseline and budget | S | none | todo |
| S02 | Event ledger core | M | none | done |
| S03 | Hook taps | M | S02 | done |
| S04 | Server spans and gate events | M | S02 | todo |
| S05 | Value report | M | S03, S04 | todo |
| S06 | Registry completeness gate | M | S02 | todo |
| S07 | Contracts unification | M | none | todo |
| S08 | Replay battery | M | none | todo |
| S09 | Arm router | M | S02, S03 | todo |
| S10 | Headless runner and analysis | L | S05, S08, S09 | todo |
| G1 | Gate: baseline numbers decide S11, S12 scope | decision | S10 | todo |
| S11 | Slim always-on | M | S01, G1 | todo |
| S12 | Gates as code | L | G1, S10, S07 | todo |
| S13 | Evidence packet | M | S03 | todo |
| S14 | Startup and pulse consolidation | M | S05 | todo |
| S15 | Reload-safe ops | L | none | todo |
| S16 | Skill pruning (time-gated) | S | S03 + 20 sessions | todo |
| G2 | Gate: lean noninferior to full | decision | S11, S12 | todo |
| S17 | Portable install and lean pack | M | G2, S15 | todo |
| S18 | Evidence page | S | G2, S10 | todo |

## Order

S00 (reproducible env first), S02, S03, S01, S07 (quick fix, visible bug), S04, S05, S06, S08, S09, S10, G1, then S11, S12, S13, S14 in
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

## State of the world

(append newest first, 5 lines max per session)

- S03 done (branch vp/05-hook-taps). `plugin/scripts/usage_tap.py` handles PostToolUse, PostToolUseFailure, SessionEnd; the prompt and session-start hooks emit correction and session events. Registered in plugin/hooks/hooks.json.
  Verified: PostToolUse carries `duration` and Bash `exit_code`; matcher `Skill` works; payload key names vary (`skill`/`skill_name`, `prompt`), so the tap accepts both. Not verified live: whether a failing Bash arrives as PostToolUseFailure; both paths are handled.
  Latency incl. interpreter: p50 41 ms, p95 45-54 ms with `python3 -S` (stdlib only), 57/67 ms without it. Budget 50 ms p95 is met on a good run and borderline on a noisy one.
  `hook` events are sampled 1 in 10 (field n=10 is the weight). events.py dropped dataclass/enum to stay import-light.
  Found, not fixed: post_tool_use.py reads `tool_result` but the payload field is `tool_response`; phrase lists are duplicated in youk_hook_utils, server.py:458 and tests (S07 should unify).

- S02 done (branch vp/04-event-ledger). `servers/shared/events.py`: `emit(root, slug, kind=, name=, ...)` never raises; `read_events(root, slug, since, kinds)` streams.
  Schema v1 kinds: tool, skill, gate, hook, correction, test, commit, outcome, session. Statuses: ok, fail, block. Session and task ids are hashed on emit.
  Shards: state/events/{slug}/{YYYY-MM}.jsonl. Append p95 0.12 ms (budget 5 ms). Registry entry `event_ledger_emit` has `real_log: null` because the log is sharded.
  Subsystem `value-instrumentation` added to the registry test. Environment: uv (S00 done) plus GNU make 4 for two Makefile tests.
