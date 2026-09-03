# Changelog

All notable changes to youk are documented here.

Format: `## [version] — YYYY-MM-DD` with sections Added / Changed / Fixed / Security.

Upgrade path: `git pull --rebase && make update`. Breaking changes are marked **BREAKING** and include a migration note.

---

## [1.2.1] — 2026-09-03

### Fixed

**The documented install did not work (#114)**

`curl -sL .../scripts/install.sh | bash` — the first command in the README — cloned the
repo and then aborted:

```
▶ Pre-install snapshot
bash: line 143: /wherever/you/were/lib/snapshot.sh: No such file or directory
```

A piped script has no `BASH_SOURCE[0]`, so `SCRIPT_DIR` resolved to whatever directory
the operator happened to be standing in, and sourcing `lib/snapshot.sh` from there
failed. `set -e` then stopped the install before symlinks, MCP registration, the Docker
build, or the CLAUDE.md patch. Reading `BASH_SOURCE[0]` under `set -u` also emitted an
`unbound variable` error on line 14 of every piped run.

Present since #5 and shipped in v1.0.0, v1.1.0 and v1.2.0. Anything sourced now comes
from the clone at `$YOUK_DIR`, which step 1 guarantees exists, and a missing file says
so instead of dying on a bare `No such file`.

### Added

**Installing a specific version (#114)**

Both installers take `YOUK_REF`, any tag or branch, defaulting to the latest on `main`:

```bash
YOUK_REF=v1.2.1 bash -c "$(curl -sL https://raw.githubusercontent.com/ajinkyabhanudas/youk/main/scripts/install.sh)"
```

```powershell
$env:YOUK_REF = "v1.2.1"; .\scripts\install.ps1
```

A ref that does not resolve stops the install and names it. There is no fallback to the
default branch, because handing someone a version other than the one they asked for is
worse than not installing. `install.ps1` maps `$env:YOUK_REF` explicitly — PowerShell
does not surface environment variables as plain variables, and without that the pin
would have been silently ignored on Windows.

**Pinned installs stay pinned (#114)**

Re-running the installer on a detached HEAD reported the failed pull as "Already up to
date", which said the opposite of what happened. Both installers now branch on
`git symbolic-ref` and report the pin by name. `make update` rebuilds at the pinned
version rather than aborting with "You are not currently on a branch".

### Upgrade notes

`git pull --rebase && make update`. No API changes.

---

## [1.2.0] — 2026-09-03

Thirty-two changes since 1.1.0. The theme, visible only in hindsight: most of these are
surfaces that reported healthy while the thing underneath was unreachable. A gate that
wrote to a row nothing read, a skill directory git had been told to ignore, a check that
passed on broken and fixed input alike. Where a fix landed, a sentinel landed with it.

### Added

**Self-measurement and the A/B pilot (#97, #98, #99, #100, #101, #102)**

- `ab_experiments.py`: session-hash variant assignment, exposure logging, and
  `pilot_status()` with an explicit `not_enough_data` state rather than a number with no
  basis behind it.
- Pre-registration boundary — the readout is fixed before the data is looked at.
- Deterministic reaction classifier for exposures, no model call in the loop.
- `nfr_autonomy_mode` wired to a real branch, giving the pilot a second signal.
- `compare_youk_vs_no_youk`: replay-based self-measurement (Phase 4v1).
- `scan_experiment_gaps`: proposes instrumentation for decision points that record nothing.

**Observability, scoped to the maintainer (#85, #88, #95)**

Langfuse session traces and a `patch_cycle_rate` score, then deliberately narrowed:
moved under `dev/`, project paths hashed, identifying data no longer sent. Opt-in via
`.env.langfuse`, off by default.

**Comprehension channel (#110)**

`output_channels` shipped in 1.1.0 with a data model, tests, and no caller. It now has a
store. `admit_comprehension_item` records a load-bearing item — a trade-off, a
foreclosure, or a reusable pattern, and nothing else qualifies. `render_task_view` emits
the paced digest at a boundary. The file is project-scoped and rendering marks rather
than deletes, so a session that ends without rendering leaves its items for the next one.
Oversize input is rejected rather than truncated, because a truncating cap would let an
append-only free-text store quietly become a transcript log.

**Destructive-command checkpoint (#106)**

An automatic checkpoint before a destructive bash command runs.

### Fixed

**Routing breadcrumb path mismatch (#109)**

`route_task` wrote the breadcrumb to `state/sessions/{slug}/`; the nfr and challenge gate
mirrors read `state/`. The paths never agreed once a session had a slug, so both mirrors
fell through to a `task[:40]` fallback and `set_gate` created a stub row keyed on
truncated task text. Eighteen phantom rows accumulated, real task rows never received
their gate flags, and `next_task` served work that had shipped months earlier. Only stub
rows could ever reach `unblocked=1`, since the mirror only ever wrote to stub ids.
`scripts/repair_task_graph.py` cleans up rows already created.

**Nine skills gitignored out of the repo (#112)**

`skills/*/*` excludes the self-referential symlink `install.sh` creates, and also matched
`SKILL.md`. Every skill added after that rule landed was dropped with no warning. Nine
were listed ACTIVE in SKILL-REGISTRY.md and present in no clone. Fixed with one negation.

**Fourteen repo skills unreachable at runtime (#89)**

Plus the gap audit that reported them as present.

**Checks that could not fail (#92, #105, #96, #86)**

- The three integrity checks compared a value against itself.
- `check_voice` and `render_coverage_view` were unenforced on their own output.
- The voice gate passed every commit made from a worktree.
- Langfuse instrumentation contained dead code and emitted fabricated traces.

**Correctness (#87, #91, #83, #82, #103, #111)**

- `route_task` returned null for omitted schema fields, breaking every call.
- State paths made redirectable; modules no longer write on import.
- `session_end` made idempotent; `promote_to_global_contracts` made atomic.
- youk-code read-only guard returns `BUSINESS_RULE` instead of a raw `Errno 30`.
- Audit-date fixtures no longer break main CI on a monthly boundary.
- Pasted bot and CI output now triggers `route_task`.

**Install and first run (#104, #107, #108)**

- `install.sh` crashed on stock macOS bash and on a cold-start server wait.
- `install.ps1` appended to CLAUDE.md once and never refreshed it on re-run.
- `doctor.sh` never checked for `pre_tool_use.py`.

**Self-improvement loop (#90, #93, #94, #81)**

Skill edits, tool contracts and stage timing now close. `org_score` is capped on
structural failure, and the coverage view surfaces evidence class so a reached-but-
unverified angle is distinguishable from a measured one. Every dangling proposal cleared.

### Changed

New drift sentinels, each verified against the broken state before being trusted:
every `@mcp.tool()` must appear in `docs/doc-map.yaml`, every `SKILL.md` on disk must be
tracked, and no shipped skill may contain a machine-absolute path. Six tools missing from
the doc map were added.

### Note on 1.1.0

The 1.1.0 section below was written and dated but never tagged, so `v1.1.0` did not exist
as a release. It is tagged retroactively at `41dfc97`, the commit that wrote it. Nothing
in that release changed; the tag makes the entry below true.

### Upgrade notes

`git pull --rebase && make update`. No breaking changes to MCP tool signatures or audit
format. Two new tools: `admit_comprehension_item`, `render_task_view`.

Run `python3 scripts/repair_task_graph.py` to clear phantom rows left by #109. It is a
dry run by default and snapshots the database before writing.

---

## [1.1.0] — 2026-08-26

### Added

**L9 programmatic enforcement (#78)**

Three gaps that were prompt-only are now Python-enforced:

- `ceremony_sequencer.py` (shared): tracks gate order per session slug. `check_nfr_gate` warns if `challenge` hasn't fired yet; `task_checkpoint` flags `dev_loop_not_registered` if dev-loop was skipped on M+ tasks. State written to `state/{slug}/ceremony-sequence.json`.
- `failure_pattern_detector.py`: scans `~/.claude/audit/` for recurring `FindingCategories` across sessions. When a domain hits threshold (default 3) in the lookback window, `session_start` prepends `⚠ PATTERN:` alerts to the session plan — before the developer starts a 4th attempt in a failing domain. Category clustering via `category_clusters.yaml` normalizes variants (`authentication`, `authz` → `auth`).
- `skill_reentry.py` (shared): `check_reentry()` reads `reentry_edges` from `skill-graph.yaml`. `write_skill_handoff` infers severity from handoff content (`BLOCKING` / `HIGH` / `MEDIUM`) and returns `reentry_suggestion` when the severity meets an edge's threshold.
- `translation_risk=medium` soft block: `route_task` now produces `SoftRuleWarning(rule_id="medium-translation-risk")` and writes `state/{slug}/medium-risk-question.json`. New tool `mark_medium_risk_surfaced()` sets `surfaced=True`. `task_checkpoint` returns `medium_risk_unsurfaced=True` if the question was never shown to the user.
- Session goal in compaction brief: `write_session_goal()` stores `success_criteria` and `observable_outcome` in `state/session-goal.json`. `build_brief()` includes them under `TIER:DECISION` so they survive compaction and `task_checkpoint` can re-evaluate `goal_met` after each task.

**Doc graph structural integrity (#78)**

`check_doc_graph()` runs four checks (previously only one):
1. Timestamp drift — authority file newer than derived (existing)
2. Broken links — derived file listed in `doc-map.yaml` no longer exists
3. Orphaned concepts — authority file listed but not on disk
4. Untracked docs — `docs/*.md` files not referenced anywhere in the map
5. Invariant match — optional per-concept string must appear in all derived files

Return shape gains `broken_links`, `orphaned_concepts`, `semantic_drift`, `untracked_docs` fields. Verdict: `COHERENT` / `DRIFT DETECTED` / `BROKEN`. `doc-map.yaml` now has `invariant` fields on 12 of 17 concepts.

**Operational resilience (#79)**

Architecture principles encoded in Python — not just in docs:

- `ErrorType` StrEnum + `RetryDecision` TypedDict in `schemas.py` — six machine-readable error categories: `TRANSIENT` and `RATE_LIMIT` are retryable with backoff; `INPUT`, `AUTH`, `BUSINESS_RULE`, `SYSTEM` are not retryable.
- `classify_error(error_type) → RetryDecision` in `guardrails.py` — pure function, no side effects. Retry strategy and reason without string parsing.
- `error_type` + `state_written` wired into 7 key tools: `route_task`, `check_nfr_gate`, `check_challenge_gate`, `save_contract`, `task_checkpoint`, `write_skill_handoff`, `check_commit_quality`.
- `_increment_tool_call_count` removed from read-only gate tools — counter now fires only on state-mutating calls.
- `knowledge/domain/operational-resilience.md` — 7 architecture principles with enforcement points and documented known debt.
- dev-loop SKILL.md Phase 3 AUDIT — 6-point operational resilience checklist catches future violations at implementation time.

### Changed

- `check_doc_graph()` return shape: `stale_concepts` is now inside the result alongside new fields. Callers reading only `stale_concepts` are unaffected (field name unchanged).

### Upgrade notes

`git pull --rebase && make update`. No breaking changes to audit format or MCP tool signatures.

---

## [0.6.0-alpha] — 2026-08-07

### Added

**Validated state store (#10)**
- SQLite-backed task graph with a `project` column and `next_task(project)` — "next task for youk" can no longer return another project's task. WAL + `busy_timeout` for concurrent sessions; deterministic `ORDER BY` selection.
- `session_end` derives the resume pointer from the project's own task graph — no manual pointer edits, no generic cross-project list.
- `check_intake_gate` — the last direction gate becomes machine-checkable, mirroring `check_nfr_gate` / `check_challenge_gate`.
- State schema layer (stdlib dataclasses, ADR-009) that raises on malformed writes; kills the recursive-resume corruption at the write boundary. Machine-checked seam test.

**Doc freshness (#11, #13, #14)**
- Graph-driven staleness: walks the full file-relation graph instead of a hand-maintained 13-file list — catches derived docs whose source changed.
- Auto-regenerates stale *generated* docs (via discovered generators, no hand-list); source code and hand-written prose are never auto-touched.
- Refreshes derivable data fields (skill counts, badges) in place across all docs; prose left alone.

**Self-revision meta-loop (#12)**
- A registry that lets youk's judgment-sets grow and prune from evidence, gated by challenge, with a versioned revert floor. Safety and fact sets are hard-blocked from enrollment by construction. Wired into the `learn` skill's self-revision sweep.

**Steering vocabulary (#15)**
- youk learns the concrete behaviors a quality label ("rigorous", "L9") decomposes into, tagged by confidence, filtered at read time. Wired into the `humanize` VOICE phase.

**Wiring pulse (#16)**
- Every `session_start` checks whether each built capability is actually invoked in the live loop — not just defined and tested. Orphans surface loudly. Autoruns unconditionally, decoupled from the N-session health counter.

### Changed

- README rewritten (630 → 126 lines), leading with impact rather than cross-session memory (#17).

### Fixed

- Health and verification vitals autorun every session instead of waiting for `session_end` or an every-N-session counter.

---

## [0.5.0-alpha] — 2026-08-05

*Backfilled — this version was tagged without a changelog entry.*

### Added
- Project isolation for proposals and task state; structured concept-graph extraction (#4).

### Fixed
- Concept graph correctness and self-owned invariants (#4).

---

## [0.4.0-alpha] — 2026-07-31

*Backfilled — this version was tagged without a changelog entry.*

### Added
- Shared SQLite file index — BM25 cross-project retrieval and impact analysis.
- SQLite task graph for gate-state persistence and cross-session recovery; `set_gate()` wired into gate tools for machine-recorded gate passage.
- `route_task` enriched with `file_context` (BM25) and `graph_state` fields.
- L10 skill hardening — scope-matrix enforcement, pre-output checks, A/B bench (#3).

---

## [0.3.0-alpha] — 2026-07-21

### Added

**Track A — Proactive skill generation**
- `review_required` flag on `Proposal` — secondary gate that blocks `apply_proposal` even when `safe_types` permits the change_type, until `review_required_override=True` is passed; prevents silent auto-apply of net-new skills
- `skill_generation_pending` field in `run_health_check_with_skill_signals` return — when a gap signal has count ≥ 2 and no SKILL.md exists, routes to generation queue instead of SKILL_EDIT proposal; closes the loop between audit signals and new capability creation
- `_queue_promotion_proposals` return type changed to `tuple[int, list[str]]` — skills without SKILL.md now populate `skill_generation_pending` rather than silently failing
- `apply_proposal` MCP tool: `review_required_override` parameter exposed — explicit human override for gated proposals
- SKILL vs MCP_CANDIDATE classification gate in `/improve` (Step 2c): each candidate classified before generation — SKILL routes to `generate_skill`, MCP_CANDIDATE routes to `add_proposal(CODE_EDIT)` only; prevents skill generation for capabilities that need a new persistent tool
- 4 new skills from Track A stack scan: `/self-heal`, `/install-experience`, `/namespace-safety`, `/dependency-audit` (roster 22 → 26)
- SKILL-REGISTRY.md updated: 4 new inventory entries, known gaps table, change log entry

**Track B — Goal-anchor drift detection**
- Goal-anchor lifecycle: `optimize_intent` with non-empty `stated_goal` writes `state/goal-anchor.json`; `task_checkpoint` marks `completed: true`; `session_end` deletes the file — per-session only, never carried across sessions
- Drift check behavioral contract in CLAUDE.md: before each `route_to_skill` on M+ tasks, synthesize last 3 exchanges against `stated_goal + success_criteria`; emit `DRIFT DETECTED` and write `DriftDetected:` audit line if direction diverges from all criteria
- `session_end` cleanup: deletes `state/goal-anchor.json` in the recovery file deletion loop

**Track C — Agile skill re-entry**
- `reentry_edges` section in `knowledge/skill-graph.yaml`: 4 directed edges — code-review→nfr-check (HIGH), security-review→nfr-check (HIGH), challenge→nfr-check (BLOCKING), adversary-loop→challenge (BLOCKING)
- Re-entry behavioral contract in CLAUDE.md: after any capability skill returns HIGH/BLOCKING findings, checks reentry_edges; once-per-directed-pair per session, cap 4 total; announces re-entry before routing
- `session_end` cleanup: deletes `state/reentry-log.json`

**Adversary loop hardening**
- Meta-adversary phase in adversary-loop skill: independent subagent attacks the adversary's own blind spots after primary loop exhausts
- Domain injection: adversary loop reads `knowledge/domain/` files to ground attacks in known failure patterns rather than generic objections
- Outcome feedback: `session_end(decision_retrospectives=...)` feeds prior decisions back to adversary loop as calibration signal

**Knowledge system**
- `knowledge/domain/reasoning-integrity.md`: new entries — Breadth Verified ≠ Concurrency-of-Trigger Verified; Registry Iteration Fixed ≠ Registry Membership Verified; Timestamp Drift ≠ Content Drift
- `skills/stress-test/references/attack-vectors.md`: First-Match-Wins on Multi-Trigger Input (Agent B); Registry Completeness / Unvalidated Membership Assumption (Agent C)
- `nfr-check/SKILL.md`: Q7 added (conditional) — measurement integrity for benchmark/eval/scoring tasks
- `improve/SKILL.md`: Track A classification gate (Step 2b–2d); proactive stack scan; MCP_CANDIDATE path

**Doc coherence**
- `check_doc_graph` concept graph: 12/12 concepts clean after full audit
- `doc-map.yaml`: task_contract / approve_task_contract / check_task_contract_gate added; org_score_definition authority/derived corrected (health.py is authority, not well-architected.md); intent_gated_brief token range corrected (100-200)
- `docs/well-architected.md`: org_score formula row added; 2 missing hard rules (no-destructive-without-confirm, lint-before-commit) added to Security table
- `docs/getting-started.md`: manual MCP registration commands updated with `/shared` volume mount
- `PHILOSOPHY.md`: 5 current hard rules enumerated inline in section 4
- `done/SKILL.md`: org_score weight claim corrected — skill invocation (2.0) is primary; close_cluster (0.5) is completion bonus
- `dev-loop/SKILL.md`: scope-collapse gate added as step 0 of UNDERSTAND — if `route_task` returned `blocked: true`, surface `collapsing_question` and refuse to proceed until scope is collapsed

### Fixed
- `check_challenge_gate`: slug mismatch when `state/session-open.json` absent — now reads slug from fallback path before returning blocked
- `install.sh`: use PIPESTATUS to detect `make build` failure, not grep exit code
- `recompute_org_score()` wired into `/done` close sequence so org_score updates on every session close, not only on self_heal runs

### Changed
- Adaptive nfr_check ceremony: `nfr_autonomy_mode: validate` fires when per-skill autonomy rate ≥ 0.4 — youk scans for gaps instead of asking questions already answered
- `developer_autonomy_rate` field in SessionState and session_start return
- `DeveloperCaught` audit field from `session_end(developer_caught=[...])`
- `depth_multiplier` in org_score — discounts early sessions (0.7× at ≤5, 1.0× at 21+)
- `compounding_verdict: EARLY | GROWING | ELITE` in self_heal return
- Goal-satisfaction loop: `task_checkpoint` returns `goal_check` — session continues until `goal_met=True`
- `framing_accuracy_rate` in org_score (0.5 weight) + `FramingCorrect: yes/no` audit field
- Intent-collapse gate in `route_task`: blocks on `translation_risk: high` (quality words without observable referent)
- `/learn` Phase 4.6 — framing retrospective → `knowledge/interpretation/user-intent.md`
- Multi-level traversal framework in `optimize_intent` and `challenge`: seven fixed angles, bottom-up first
- Convergence state tracking: pressure source tracked, convergence credited on external pressure only
- Outcome prediction logging + frame revalidation mechanism
- SECURITY.md: threat model, credential handling contract, rotation procedure
- Dockerfile base images pinned to digest
- Routing breadcrumb gate: `route_task` writes `state/routing-breadcrumb.json`; absent on M+ → `routing_missed: true`
- `force_learn` gate: session without /done → `state/pending-action.json` → `⚠ [BLOCKED]` at session_plan[0]
- Pending-action TTL: 24h — prevents stale blocks on multi-day breaks
- Skill rate threshold warning prepended to session_plan[0] when rate < 50%
- `docs/scheduling.md` + `CONTRIBUTING.md`: clarified install.sh wires auth into containers — no API key needed at install or runtime

### Fixed (continued)
- `session-goal-coverage.json` resets on `write_session_goal` — no premature `goal_met=True`
- Audit format regression: old entries without `DeveloperCaught` / `FramingCorrect` parse cleanly

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

### 0.1.0 → 0.3.0-alpha

**No breaking changes to audit format.** Old audit entries parse cleanly — new fields (`DeveloperCaught`, `FramingCorrect`) default to None when absent.

**Dockerfile base images now pinned.** If you have a local build cache, run `make rebuild` after pulling to pick up the pinned digest.

**`session-goal-coverage.json` reset behavior changed.** Coverage now resets each time a new goal is written. If you have an in-progress goal, it will re-evaluate from zero on the next `task_checkpoint` call.
