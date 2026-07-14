# Changelog

All notable changes to youk are documented here.

Format: `## [version] — YYYY-MM-DD` with sections Added / Changed / Fixed / Security.

Upgrade path: `git pull --rebase && make update`. Breaking changes are marked **BREAKING** and include a migration note.

---

## [unreleased]

### Added
- Adaptive nfr_check ceremony: `nfr_autonomy_mode: validate` fires when per-skill autonomy rate ≥ 0.4 — youk scans for gaps instead of asking questions the developer already answered
- `developer_autonomy_rate` field in SessionState and session_start return — measures fraction of sessions where developer pre-empted a capability skill
- `DeveloperCaught` audit field — written by `session_end(developer_caught=[...])` when developer answered NFR questions unprompted
- `depth_multiplier` in org_score — discounts early sessions (0.7× at ≤5 sessions, 1.0× at 21+); a 9/10 on session 3 now scores lower than session 30
- `compounding_verdict: EARLY | GROWING | ELITE` in self_heal return
- Goal-satisfaction loop: `task_checkpoint` returns `goal_check` — session continues until `goal_met=True`, not on plan exhaustion
- `session-goal.json` written by `optimize_intent` when goal is concrete and unambiguous
- `done/SKILL.md` Step 0: checks session goal before closing — surfaces gap and derives next task if goal not satisfied
- youk-lite `## Growth` section: NFR pre-empts counter and direction gate pre-empts counter — manual autonomy tracking
- `framing_accuracy_rate` in org_score (0.5 weight) — measures whether goal was correctly translated before work started
- `FramingCorrect: yes/no` audit field — written by `session_end` from `direction_reversal` param
- Intent-collapse gate in `route_task`: blocks on `translation_risk: high` in `goal_translation` — quality words ("elite", "better") without observable referent block routing until user clarifies
- `goal_translation` field in `optimize_intent` output: `stated_as`, `interpreted_as`, `observable_outcome`, `translation_risk`, `translation_question`
- `/learn` Phase 4.6 — framing retrospective: writes mis-framing patterns to `knowledge/interpretation/user-intent.md`, feeds `optimize_intent` next session
- Challenge Lens 3 intent assumption question: surfaces "what experience am I assuming this quality word means?" as BLOCKING objection
- Multi-level traversal framework in `optimize_intent` and `challenge`: seven fixed angles (structural, operational, experiential, adversarial, temporal, outcome, human), bottom-up first, contradiction-first, label only after convergence
- Convergence state tracking: pressure source tracked (user vs model), convergence only credited on external pressure
- `self_heal` convergence check: multi-directional pressure against current state, unknown-unknowns flagged explicitly
- Outcome prediction logging: frame predictions logged at session start, outcomes written back at session end
- Frame revalidation mechanism: event-triggered + cross-session contradiction accumulation, human required at revalidation
- Model generation continuity: convergence state and angle set survive model transitions, drift surfaced on transition
- SECURITY.md: threat model, credential handling contract, rotation procedure
- Dockerfile base images pinned to digest — deterministic builds

- Routing breadcrumb gate: `route_task` writes `state/routing-breadcrumb.json` for M/L/XL decisions; `task_checkpoint` reads and consumes it — if absent for an M+ task, returns `routing_missed: true` + `routing_action` surfacing the missed gate
- Stale breadcrumb detection: `session_start` reads any existing breadcrumb at open; if older than 300 seconds (prior session), surfaces `⚠ Last session: route_task ran but task_checkpoint was never called` at session_plan[0] and consumes the file
- `force_learn` gate: when a session closes without `/done`, `session_start` writes `state/pending-action.json` and prepends `⚠ [BLOCKED] Last session closed without /done — Run /learn NOW` to session_plan[0]; `route_to_skill("learn")` clears the pending-action file
- Pending-action TTL: `state/pending-action.json` older than 24 hours is cleared at `session_start` — prevents stale blocks on returning sessions after a multi-day break
- `force_learn: bool` field on `SessionState` (default `False`) — returned by `session_start`, propagated via `to_dict()`
- Skill rate threshold: when skill invocation rate across recent sessions drops below 50%, `session_start` prepends the rate warning to session_plan[0] (not appended); consecutive-skips warning (≥3) preserved but only fires when rate ≥ 50%

### Fixed
- `session-goal-coverage.json` now resets when `write_session_goal` is called — stale coverage from prior goal or project no longer causes premature `goal_met=True`
- Audit format regression: old entries without `DeveloperCaught` / `FramingCorrect` parse cleanly, default to None

---

## [0.1.0] — 2026-01-01

Initial release.

### Added
- youk-core MCP server: session_start, session_end, route_task, optimize_intent, compact_context, save_contract, self_heal, task_checkpoint, track_tokens, check_nfr_gate, add_proposal, apply_proposal, get_proposals, check_doc_graph
- youk-code MCP server: route_to_skill, assess_skill, generate_skill, code-review, verify, nfr_check, write_skill_handoff, detect_skill_gaps, list_skills, check_commit_quality, generate_stack_overlay
- Capability skills: pm-review, write-spec, nfr-check, stress-test, adr, dev-loop, code-review, security-review, verify, learn, challenge, humanize, done, skill-forge
- org_score with capability_skill_rate (2.0 weight), close_cluster_rate (0.5), gap_resolution_rate (0.5), prevented_cost_score (0.5)
- youk-lite: zero-dependency CLAUDE.md memory layer — contracts, resume point, active decisions, direction gate, session goal
- Install script: `bash scripts/install.sh` — macOS, Linux, Windows (Git Bash / WSL2)
- `make doctor` with Fix: lines for every failure
- CI: lint (ruff), unit tests, config YAML validation, Docker build + MCP handshake

---

## Upgrade notes

### 0.1.0 → unreleased

**No breaking changes to audit format.** Old audit entries parse cleanly — new fields (`DeveloperCaught`, `FramingCorrect`) default to None when absent.

**Dockerfile base images now pinned.** If you have a local build cache, run `make rebuild` after pulling to pick up the pinned digest.

**`session-goal-coverage.json` reset behavior changed.** Coverage now resets each time a new goal is written. If you have an in-progress goal, it will re-evaluate from zero on the next `task_checkpoint` call.
