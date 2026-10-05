# Value plan log

One entry per finished card, newest first. Read the entries for the cards yours depends on, not the whole file. The anchor (README.md) keeps only the facts every later card needs.

(append newest first, 5 lines max per session)

- S10 built, first real run NOT done (branch vp/12-replay-battery). `scripts/sim/run_battery.py` (clone at parent sha, hidden tests removed, `claude -p --output-format json` per arm in its own config dir, hidden tests restored and graded, one JSONL row per run, `--cap-usd` required, `--max-budget-usd` per run, resumable, rep-task-arm order) and `analyze.py` (task-level bootstrap, paired diff and cost ratio vs bare, G1 verdict, DECISIONS entry). `--dry-run` fake agent drives it end to end in tests. See `battery.md`.
  Spent: $0. Blocked on: dollar cap, Superpowers checkout, auth for the isolated config dirs. Unverified live: the exact `claude -p` JSON field names (`total_cost_usd`, `usage`, `num_turns`) and whether a fresh config dir can authenticate; the smoke test in `battery.md` step 3 checks both for under $5.

- S09 done (branch vp/12-replay-battery). `servers/shared/arms.py`; arm in {full, lean, bare}; every emitter (usage tap, prompt hook, session hook, server spans) reads it through `current_arm(root, slug)`; SessionStart writes `state/session-arm/{slug}` so container events carry it. Default arm is `full`; `YOUK_ARM` pins, `YOUK_ARM_MODE=randomize` hashes by session. Decision: not random by default, so ordinary work is never silently ungated.
  Hook behaviour per arm: full injects the server brief, lean injects `bench/arms/lean/context.md` (placeholder until S11), bare injects nothing and skips the Edit/Write and close gates. The server call still runs for every arm so the session counter advances.
  Cannot do: replace CLAUDE.md from a hook (it adds context only), so arms in the battery get CLAUDE.md through separate config dirs. Limit: two sessions open in one project share the arm slot.

- S08 done (branch vp/12-replay-battery). `scripts/sim/mine_tasks.py`, `bench/repos.yaml` (youk, stencil, canopy), `bench/tasks/*.yaml`: 21 tasks verified by running (pass at the commit, fail on the parent): youk 10, canopy 9, stencil 2; all Python, bug-fix and small-feature heavy. Kill criterion (under 12) not triggered, but stencil is thin (13 commits).
  Fairness: prompt is the commit's subject and first paragraph with file names stripped, and a commit is rejected if the prompt names an identifier the commit introduces (11 rejected). That is a heuristic, not a guarantee: bullet-list subjects like canopy-15c56d0a still describe the fix. Ajinkya's review of `--review` output is still required.
  Old youk history predates the lockfile, so youk tasks run with the host venv (`{python}` in repos.yaml); canopy needs `PYTHONPATH=src` and its own interpreter.

- Phase 1 follow-ups done (branch vp/11-phrases-and-tool-response). Phrase lists: there were two distinct lists plus a pasted test copy, not three copies; each now lives once in `servers/shared/phrases.py` (`PUSHBACK_PHRASES`, `LOOP_CORRECTION_PHRASES`, `CONTRACT_PHRASES`) and a test fails on any other definition.
  `post_tool_use.py` now reads `tool_response` (a dict for Bash), falling back to `tool_result`. Before this, `last_signal` in active_task.json was never filled from command output, so briefs showed an empty "last signal" for Bash.

- S06 done (branch vp/10-registry-gate). Phase 1 (S00-S07) complete. `tests/test_registry_gate.py`: stages must declare real_log, emits or untraced_reason; every hook script has an entry; every check_*_gate is in GATE_CHECKS; the tap matches `Skill`; no tool is orphaned (check moved from startup to CI).
  Registry is now 44 stages (5 hook entries added, subsystem `host-hooks`): 10 traced via ledger, 17 declared untraced with a reason, the rest have a real_log. `session_start_hook` added to the wiring allow-list (called by the host hook, never by name).
  Fixed on the way: `coverage-tree` frontmatter was invalid YAML; `verify` had `skill:` and no `name:`.
  Correction: `domain_edge_case_review.py` is not dead on main (nfr.py uses it); it stays.

- S05 done (branch vp/09-value-report). `make value-report` / `scripts/value_report.py [--by arm,week] [--json]`; export_stats points to it as the headline. 15 tests on ledgers with known answers.
  Counting rule: calls and corrections from `src=hook`; latency, gates, M+ task counts from `src=server`. Intervals only with 10+ sessions.
  Reported now: V1 corrections per M+ task and per session; V2 inputs (last test run green per session, failed runs, commits); V3 hook and tool latency and footprint; gate checks and blocks.
  Not measurable yet: first-pass acceptance (needs S13), tokens per task (no token events), repeat-gap rate (needs audit logs; enum events cannot identify a repeat). S09 must give server events an arm or per-arm M+ rates break.

- S04 done (branch vp/08-server-spans). `servers/shared/tool_spans.py`: `install_tool_spans(mcp, get_root, get_slug)` wraps every `@mcp.tool` at registration on both servers; a test asserts every registered tool is wrapped (core and code).
  Events carry `src=server`. Counting rule for the report (S05): call counts from `src=hook`, latency and errors from `src=server`. Server also emits gate (`nfr`, `challenge`, `intake`, `task_contract`, `proposal_backlog`, `set.<gate>`, `route.<size>`) and outcome (`task_done`, `checkpoint.<size>`, `session_end`) events.
  Task id: only where a call carries one (set_gate, mark_task_done), hashed. Other events join by session (`<slug>-<counter>` hashed) and time; a persisted current-task was left out until a report needs it. Wrapper overhead under 2 ms per call (asserted).
  Not live: the running youk-core must restart to pick this up (it is a live bind mount, so merge-then-restart).

- S07 done (branch vp/07-contracts). `servers/shared/contracts.py`: `project_contracts`, `global_contracts(root, cap)`, `effective_contracts`, `classify_contract`; session.py, compaction.py and the hook utils all call it. `effective_patterns` moved there (global_contracts.py re-exports it).
  Fixed: brief said "none saved" beside "Active contract". The plan line is gone; the brief counts global contracts; `verbatim_lines` and the digest count global (top 10) plus project. PreCompact hook now injects defaults plus best-supported learnings, not the first lines of the rendered file.
  Real data (`scripts/classify_contracts.py --root ~/.claude/youk`): 208 unique contracts, 16 mechanical (ruff before commit, never commit screenshots, never read .env, branch before PR, never --force), 192 judgment. The 16 are the S12 compile candidates; review by hand first.
  Not done: the correction phrase lists at youk_hook_utils, server.py:458 and the test copy are still three copies; post_tool_use.py still reads `tool_result` (host sends `tool_response`).

- S01 done (branch vp/06-footprint). `make footprint` / `scripts/footprint.py`; budget in `bench/footprint-baseline.json`, enforced by `tests/test_footprint_budget.py` (ratchet: template, AGENTS.md, skill descriptions).
  Baseline 11,050 tokens. Skill descriptions are 71% of it; largest: surface-options 359, adversarial-planning 276, forward-deployed-pod 230. S11 target: total at or under 3,000.
  Lower the baseline with `--write-baseline` whenever a card reduces it.

- S03 done (branch vp/05-hook-taps). `plugin/scripts/usage_tap.py` handles PostToolUse, PostToolUseFailure, SessionEnd; the prompt and session-start hooks emit correction and session events. Registered in plugin/hooks/hooks.json.
  Verified: PostToolUse carries `duration` and Bash `exit_code`; matcher `Skill` works; payload key names vary (`skill`/`skill_name`, `prompt`), so the tap accepts both. Not verified live: whether a failing Bash arrives as PostToolUseFailure; both paths are handled.
  Latency incl. interpreter: p50 41 ms, p95 45-54 ms with `python3 -S` (stdlib only), 57/67 ms without it. Budget 50 ms p95 is met on a good run and borderline on a noisy one.
  `hook` events are sampled 1 in 10 (field n=10 is the weight). events.py dropped dataclass/enum to stay import-light.
  Found, not fixed: post_tool_use.py reads `tool_result` but the payload field is `tool_response`; phrase lists are duplicated in youk_hook_utils, server.py:458 and tests (S07 should unify).

- S02 done (branch vp/04-event-ledger). `servers/shared/events.py`: `emit(root, slug, kind=, name=, ...)` never raises; `read_events(root, slug, since, kinds)` streams.
  Schema v1 kinds: tool, skill, gate, hook, correction, test, commit, outcome, session. Statuses: ok, fail, block. Session and task ids are hashed on emit.
  Shards: state/events/{slug}/{YYYY-MM}.jsonl. Append p95 0.12 ms (budget 5 ms). Registry entry `event_ledger_emit` has `real_log: null` because the log is sharded.
  Subsystem `value-instrumentation` added to the registry test. Environment: uv (S00 done) plus GNU make 4 for two Makefile tests.
