# Value plan log

One entry per finished card, newest first. Read the entries for the cards yours depends on, not the whole file. The anchor (README.md) keeps only the facts every later card needs.

(append newest first, 5 lines max per session)

- the hooks were never running (branch vp/20-hooks-install). a probe run found 0 plugins and 0 hooks in claude code on this machine, because the installer symlinked plugin/ into ~/.claude/plugins and this version does not discover plugins that way. so the voice capture, event ledger, contract guard and session brief were all dead outside the battery.
  `scripts/install_hooks.py` now registers the hooks in settings.json with absolute paths, since the scripts import from servers/shared relative to their own location and a marketplace install would copy them away from it. idempotent, backs up first, removes only youk's own entries, and the installer, uninstaller and doctor use it. applied to the live settings on 2026-10-07 and a probe run wrote hook events.
  worth knowing: the UserPromptSubmit hook adds a generation frame to every prompt, which is context on every turn and works against the lean goal. not changed here.

- voice learning fixed (branch vp/19-voice-learning). the learned profile was written to `voice-{slug}-{register}.md` and nothing read it, because humanize reads `voice-profile.md`. humanize now loads both, and a test ties the skill text to the builder's path (`profile_path`). the measured numbers are writing targets only, never a gate.
  PR titles and bodies go through the commit voice gate in the PreToolUse hook (`gh pr create|edit`, inline, heredoc or `--body-file`), rule `voice-pr-text`. long quoted text and heredocs are masked before the git rules run, so a body that mentions `git push origin main` is not read as that command.
  `scripts/voice_report.py` prints the learned profile beside the 2026-10-06 baseline. there is no corpus on the live machine yet, since the hooks only load after the live install is on main. run it then.
  still open: only the chat register is captured, and the tell list is fixed.

- S12a built (branch vp/17-gates-as-code). `servers/shared/contract_guard.py`: 8 mechanical contracts enforced by PreToolUse on Bash, no model recall needed: commit or push to the default branch, force push (lease allowed), --no-verify, newly staged screenshot or secret file, printing .env, forced dependency installs. Ungated in bare, `YOUK_GUARD_OFF` per rule, a gate event `contract.<id>` per block; listed in `config/guardrails.yaml` and tied to the code by a test (22 tests on real git repos).
  Cost: no always-on tokens; the hook takes about 75 ms p50 as before for non-commit commands and about 200 ms for `git commit` (three git calls). Chosen to miss rather than falsely block: files are checked only when newly added, and only Bash is covered. Reading .env with the Read tool is not (a hook per Read costs a process start each); deny it in settings with `Read(**/.env*)`.
  Tool disposition: `check_voice` is enforced by the commit-msg hook, so it moved to the terminal list. `log_ab_exposure` and `mark_medium_risk_surfaced` stay full-arm-only on the test's list; the A/B pilot has 5 of 20 exposures and is dormant.
  Not done (S12b): ceremony order enforced by PreToolUse with a `next` field on tool results, and removing the legacy gate JSON files (needs a task-graph.db health check on the live install). Neither is needed to measure lean against full; both are real risk to the full arm.

- S11 built, not yet measured (branch vp/16-slim-always-on). Always-on 11,050 to 1,932 tokens (-83%), under the 3k G2 target. Skill descriptions 7,859 to 1,563 (52 rewritten to 25 words or fewer); template and AGENTS.md cut to the lean context (8 lines) and 8 lines; `compaction` and `session` moved to `docs/internal/` (they were listed every session and triggered nothing).
  Frozen: the pre-slimming template is `bench/arms/full/CLAUDE.md`, so the full arm stays what G1 measured; the runner reads it from there. Tests that pinned the old template now read the frozen file.
  Debt made visible: `check_voice`, `log_ab_exposure` and `mark_medium_risk_surfaced` were only reached by prose the lean template dropped; a test lists them as full-arm-only until S12 compiles or removes each.
  Not done: G2 (lean within 5 points of full on pass rate) needs the E1 design and the owner's budget decision; the saving is measured, the effect on results is not. Kill criterion: restore any trimmed element that costs more than 5 points.

- Eval research and design gate (branch vp/15-eval-design). G1 was a wasted design: 8% power at a 15-point effect, 12 of 14 tasks identical across arms, k=1. Research (`research-eval-design.md`, 11 findings with sources) and a native-overlap assessment (`mods-assessment.md`) written; 3 proposals queued in PENDING.
  Built: `scripts/sim/design.py` (triage, power, minimum detectable effect, cost, interim stop rule) and a gate in `run_battery.py` that refuses a run without a pilot and a design that can see the target effect. Contract saved. Cards E1 (eval v2) and E2 (compounding) added; S11 gets the lean-context rules.
  Not done: the M+ miner tier, the bare pilot, any new spend. Next paid run needs the pilot first and the owner's budget decision.

- G1 recorded (branch vp/14-g1-record). First real battery: bare vs full, 14 tasks, k=1, 28 runs, $25.95 notional (subscription), `bench/results/2026-10-05.jsonl`. pass@1 bare 0.57, full 0.64; paired +0.07 (+0.00 to +0.21); cost 1.20x; time 0.97x. Rule verdict: G1 FAIL (lower bound 0.00). Honest reading: inconclusive. One task (youk-12343343) is the whole difference; 13 of 14 identical.
  Data issues: bare youk-0313b9b1 timed out at 900 s ($0.00, understates bare cost); full youk-f9c1c0c8 quit after 8 turns; 4 youk tasks fail in both arms (likely unpassable from the prompt). Next: S11 and S12 per the gate. A rerun with k=3 would tighten the interval for about $75 notional; not done.
  Found on the way: plugin.json was invalid so hooks never loaded under --plugin-dir (#194); non-youk arms now get an empty MCP config (#195).

- S10 built, first real run NOT done (branch vp/12-replay-battery). `scripts/sim/run_battery.py` (clone at parent sha, hidden tests removed, `claude -p --output-format json` per arm in its own config dir, hidden tests restored and graded, one JSONL row per run, `--cap-usd` required, `--max-budget-usd` per run, resumable, rep-task-arm order) and `analyze.py` (task-level bootstrap, paired diff and cost ratio vs bare, G1 verdict, DECISIONS entry). `--dry-run` fake agent drives it end to end in tests. See `battery.md`.
  Spent: $0. Blocked on: dollar cap, Superpowers checkout, auth for the isolated config dirs. Unverified live: the exact `claude -p` JSON field names (`total_cost_usd`, `usage`, `num_turns`) and whether a fresh config dir can authenticate; the smoke test in `battery.md` step 3 checks both for under $5.

- S09 done (branch vp/12-replay-battery). `servers/shared/arms.py`; arm in {full, lean, bare}; every emitter (usage tap, prompt hook, session hook, server spans) reads it through `current_arm(root, slug)`; SessionStart writes `state/session-arm/{slug}` so container events carry it. Default arm is `full`; `YOUK_ARM` pins, `YOUK_ARM_MODE=randomize` hashes by session. Decision: not random by default, so ordinary work is never silently ungated.
  Hook behaviour per arm: full injects the server brief, lean injects `bench/arms/lean/context.md` (placeholder until S11), bare injects nothing and skips the Edit/Write and close gates. The server call still runs for every arm so the session counter advances.
  Cannot do: replace CLAUDE.md from a hook (it adds context only), so arms in the battery get CLAUDE.md through separate config dirs. Limit: two sessions open in one project share the arm slot.

- S08 done (branch vp/12-replay-battery). `scripts/sim/mine_tasks.py`, `bench/repos.yaml` (youk, stencil, canopy), `bench/tasks/*.yaml`: 22 mined and verified by running (pass at the commit, fail on the parent), 14 usable after fairness review: youk 6, canopy 6, stencil 2. All Python, bug-fix and small-feature heavy. 14 is above the kill-criterion floor of 12 with little margin; stencil is thin (13 commits).
  Fairness, in two parts. Automatic: prompt is the commit's subject and first paragraph with file names stripped; new names the hidden tests call are appended as an interface list (without them no arm can pass); a commit is rejected if its prompt names other new identifiers. Manual (Claude, 2026-10-05, stored in each task's `review`): 8 of 22 marked unfair because the prompt spells out the fix or the tests depend on text no prompt gives. `usable()` drops them; a remine keeps verdicts. the owner can overrule any with `review.fair`.
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
