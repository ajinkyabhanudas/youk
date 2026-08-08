# Agentic-UX Rework — Build Spec

**Status:** ready to build. Derived via twin derivation (research + first-principles, converged), recorded in
[agentic-ux-rework-spec.md](agentic-ux-rework-spec.md). This file is the *buildable* spec: what to build, the
resolved decisions, and the acceptance bar. Written session #73 (2026-08-08).

## Executive brief (one paragraph)

youk narrates all reasoning at max depth every task. The expert developer can't separate the load-bearing 10%
from the routine 90%, stops reading, trusts-and-skims, and pays comprehension debt later. Research (Buçinca 2021,
verified) proves *more explanation increases over-reliance* — so the fix is not explaining better, it is
**explaining less and forcing attention only where it repays understanding.** This rework splits youk's output
into two channels (execution = quiet/expandable, comprehension = filtered/paced), puts the depth dial in the
human's hands, surfaces a glanceable per-step confidence/risk signal, spends a small budget of cognitive-forcing
gates on the highest-stakes changes, and adds a MECE **coverage tree** — built by one subagent, adversarially
checked by a second — so a *missed concept* surfaces at the top of review before anyone reads a diff. The tree
generalizes as a glanceable view across challenge / stress-test / nfr-check.

## Problem (verbatim goal — the anchor, do not drift)

Write less. Surface goals + correctness + gaps HIGH. Invite inquiry. Hierarchical MECE coverage where a miss at
the top costs nothing to find (you never descend into code for a branch that failed the concept check). Tree must
be MECE, complete, and expandable on demand. Everything an L9 team does to build must happen — but be *auditable
at a glance*, not read linearly.

## The core principle (one move, applied everywhere)

**Separate the cheap completeness check from the expensive correctness check; make the cheap one glanceable.**
Two-channels is this. The confidence signal is this. The coverage tree is this. Generalizing to all modes is this.

## Resolved decisions (do not re-litigate)

| # | Decision | Basis |
|---|---|---|
| D1 | Two channels split **by consumer** (execution=youk, comprehension=human), not by topic | twin-derivation convergence |
| D2 | Execution channel **default near-silent**, auditable, expand-on-demand | CLT extraneous load; Nielsen progressive disclosure; Amershi G11 |
| D3 | Comprehension channel **filtered** (load-bearing only) + **paced** (digest at natural boundary), never per-step | CLT germane load; per-step teaching = the firehose |
| D4 | **Human owns the depth dial**; quiet default; youk never picks the human's cognitive depth | Parasuraman/Sheridan/Wickens; Amershi G17 |
| D5 | Per-step signal is **layered**: structural proxy (blast-radius, reversibility, area-familiarity) from day 1 + measured calibration overlaid as track-record accrues; honest `uncalibrated` state until N samples | user decision (session 73); Lee & See calibration |
| D6 | **Stakes-gated cognitive forcing** is the *only* germane-load channel — rare, budgeted, predict-before-reveal on high-blast/irreversible/unfamiliar | Buçinca 2021 (VERIFIED: forcing beats explanation, but is disliked → must be rationed) |
| D7 | Coverage tree = **builder subagent → adversary subagent** (stripped context); adversary **raises, does not rule**; contested/gap nodes surface at Level-1; human-caught misses update the branch template | user decision; "independence needs separate context" contract; self-revising-set contract |
| D8 | Tree is a **view generated from the pass**, never a second hand-authored artifact | anti-decoration; the "write less" goal |
| D9 | Tree generalizes across **challenge / stress-test / nfr-check** as the same view over their reasoning | user decision |

## Open questions — resolved this session (L9 calls, user may veto)

- **OQ1 — signal number basis** → RESOLVED D5 (layered). Cold-start handled by honest `uncalibrated` + structural-only.
- **OQ2 — forcing-gate frequency** → **budget, not fixed rate.** Max N gates/session (default 2), spent highest
  stakes×irreversibility first. Prevents ceremony-decay (too many → skimmed) and atrophy (too few). *Sharpest risk —
  flagged for user tuning after real use.*
- **OQ3 — expertise-indexing granularity** → **module-level** (file=too noisy, concept=not machine-derivable yet),
  and **legible** (the familiarity map is inspectable) — an unpredictable depth policy is itself extraneous load.
- **OQ4 — comprehension measurement** → no honest online metric exists. Use **override-rate + pull-depth as
  labeled proxies** feeding ADR-010 metric C (`_compute_autonomy_rate`, health.py:391). NEVER claim "understanding
  measured." Enriches metric C from raw autonomy → (oversight-decrease ∧ understanding-current-proxy).
- **OQ5 — Channel-2 form** → **output-contract change + a paced digest**, not a new subsystem. Reuses existing
  render path; the coverage tree is a rendered view, not a stored artifact (D8).

## Anti-patterns (named, must be prevented by test)

1. **False-green** — the `wiring_pulse.py` disease: a signal that shows "all good" when it hasn't actually checked.
   The coverage tree MUST render `adversary: not-run` honestly when the API is down; it must never show a clean
   all-covered tree it didn't adversarially verify.
2. **Self-assessed completeness** — a single agent building AND judging its own tree can only mark nodes it thought
   of; its blind spot = the tree's blind spot. Independence (stripped subagent) is load-bearing, not optional.
3. **Frozen template** — a branch template asserting completeness is an unchallenged wall. Templates self-revise
   (grow at frontier when a human catches a missing node, prune dead weight), gated by challenge discipline; only
   mechanical-fact and safety nodes stay frozen.
4. **Decoration** — the tree/digest as a second thing to hand-write = more writing = the original disease. Generated
   from the pass only (D8).
5. **Ceremony-decay** — too-frequent forcing gates get skimmed, recreating the original failure (Buçinca: forcing is
   disliked). Budget-gate them (OQ2).

## No-API degraded path (first-class, tested — built API-down on purpose)

- Structural signal (D5 layer 1): pure local, always works.
- Calibration overlay (D5 layer 2): reads local track-record store; works offline.
- Coverage-tree **builder/adversary subagents**: LLM calls. When API unavailable → tree renders with
  `adversary: not-run (no API)`, gaps from the *structural template only*, and an explicit "completeness
  UNVERIFIED" banner. Fail-safe per contract: adversary-produces-no-output → inline structural fallback, never
  false-green. This degraded state is a TESTED behavior.

## Components & acceptance

| Component | File(s) | Acceptance |
|---|---|---|
| Two-channel render | new `output_channels.py` | execution collapses to 1 line by default; expand token returns full trace; comprehension digest accrues + emits at boundary |
| Layered signal | new `confidence_signal.py` | structural score from blast-radius/reversibility/familiarity; calibration overlay when ≥N samples else `uncalibrated`; no false-green |
| Cognitive forcing | extend routing/gate path | fires only on high stakes×irreversibility; respects per-session budget; predict-before-reveal prompt |
| Coverage tree | new `coverage_tree.py` | MECE template per task-type; builder subagent populates; adversary subagent (stripped) adds/contests nodes; gaps+contested surface first; degraded no-API path; template self-revises on human-caught miss |
| Mode generalization | extend challenge/stress-test/nfr-check skills | each renders its reasoning as the same tree view, generated from the pass |
| Metric C enrichment | `health.py:391` | proxies (override-rate, pull-depth) feed metric C, labeled as proxies |

## Test bar (contract: tests for everything, no oversight gaps)

- Two-channel: default-quiet assertion; expand round-trips full trace; digest fires at boundary not per-step.
- Signal: structural monotonic in blast-radius; `uncalibrated` below N; **false-green prevention test** (signal
  cannot read "confident" without a basis).
- Forcing: budget cap enforced; fires on high-stakes, silent on low-stakes.
- Coverage tree: MECE (no overlap, exhaustive vs template); adversary adds a node the builder missed (fixture);
  **degraded no-API path test** (renders `not-run`, never false-green); template gains a node on simulated
  human-caught miss.
- Drift sentinel: SKILL.md content assertions for the new mode-view sections.
- `ruff check servers/ tests/` clean; full pytest green; CI passes before push.

## Build order (dependency-ordered)

1. `confidence_signal.py` (structural layer) — no deps, unblocks the tree's degraded path.
2. `output_channels.py` (two-channel render) — consumes signal.
3. `coverage_tree.py` (template + builder/adversary + degraded path) — consumes signal + channels.
4. Cognitive-forcing gate — consumes signal (stakes) + tree (gap surfacing).
5. Mode generalization (challenge/stress-test/nfr view) — consumes tree.
6. Metric C enrichment — consumes channel pull-depth/override data.

Each step: build → test → ruff → commit (small logical commit). Steps 3+ subagent paths built with degraded
fallback FIRST so nothing ships that only works API-up.

## Build status (session #73 — API was down, local + degraded paths built)

DONE (built, tested, committed on `feat/agentic-ux-rework`):
- `confidence_signal.py` (12 tests) — layered signal, false-green impossible, forcing budget+predicate.
- `output_channels.py` (9 tests) — two-channel render, paced digest.
- `coverage_tree.py` (10 tests) — MECE tree, builder+adversary (injected), degraded no-API path first-class.
- `mode_coverage_view.py` (5 tests) — coverage view generalized across challenge/stress-test/nfr-check.
- Full suite: 1819 pass, 0 fail. ruff clean.

OPEN — API-blocked (do when credit restored):
- LIVE builder/adversary subagents: the injected callables' real LLM implementations. Degraded path tested;
  live path is AUDITED-NOT-RUN. This is the largest open boundary.
- SKILL.md wiring: `mode_coverage_view` adapter exists but no mode flow calls it yet (wiring it to a
  capability that can't execute would be a wiring_pulse orphan). Wire challenge/stress-test/nfr-check +
  code-review to emit the view once subagents are live.
- Cognitive-forcing PROMPT flow: budget + predicate live in `confidence_signal`; the predict-before-reveal
  prompt/interaction is not yet wired into the routing loop.

OPEN — follow-ups surfaced by dogfood self-review (coverage tree run on its own build):
- [GAP/data] `TEMPLATES` and `MODE_ANGLES` are mutable MODULE globals. Self-revision (add_concept_to_template)
  does NOT persist across sessions — the accumulator leaks on restart. Persist to a state file
  (state/coverage-templates.json) so human-caught misses durably accumulate. Also removes the test-isolation
  fragility (currently manual restore).
- [correctness] `ForcingBudget` is shared-mutable; fine for the single-session single-thread runtime, race-prone
  if ever shared concurrently. Named, low priority.

METRIC C: `_compute_autonomy_rate` (health.py:391) enrichment (override-rate + pull-depth proxies) — NOT yet
wired; requires the channels to be emitting in the live loop first.
