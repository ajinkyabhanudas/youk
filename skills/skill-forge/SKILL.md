---
name: skill-forge
description: >
  Proactive stack→skill convergence loop — the forward half of youk's self-improvement loop
  (self_heal is the reactive half). Given any stack, derives the skills an elite engineer would
  need by deep repo + live internet search, looping at a RISING standard until even an imagined
  superior engineer has nothing to add, then sharpens each skill's definition to that standard.
  Auto-applies SKILL_EDIT/FILE_CREATE only (CODE/CONFIG stay hard-gated). Triggers on: "/forge",
  "forge skills for this stack", "what skills would an elite need here", "raise the skill bar",
  new stack detected at session start.
---

# skill-forge — Proactive Stack→Skill Convergence Loop

Two loops. Loop A (breadth): which skills does an elite engineer in this stack need. Loop B
(depth): how must each be defined to produce legendary output, not merely competent output.

The convergence target is **the standard rising to stable** — not skill-count settling. This
is what "elite" names: refuse the current ceiling until a hypothetically superior reviewer is
silent.

self_heal corrects from past session evidence (reactive). skill-forge anticipates from stack
analysis (proactive). Together they close the loop from both ends.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full: SCOPE → DISCOVERY (Loop A) → DEFINITION (Loop B) → REPORT |
| `discover only` | SCOPE → Loop A, then stop (skills created, none sharpened) |
| `sharpen: [skill]` | SCOPE → Loop B on one existing skill only |
| `stack: [name]` | Force the stack instead of detecting it |
| `dry-run` | Run both loops but propose only — no auto-apply, surface the batch for review |

---

## Safety rails (non-negotiable — the loop refuses to violate these)

- **Auto-apply is SKILL_EDIT / FILE_CREATE only.** Never pass a `safe_types` that includes
  CODE_EDIT or CONFIG_EDIT. A derived skill implying a code change becomes a proposal-only item
  in REPORT — never auto-applied. Server code and guardrails are never touched by this loop.
- **Convergence is measured by delta, not iteration count.** The adaptive ceiling is a safety
  stop, not the goal. A run that hits the ceiling reports `converged=False` — it never claims a
  convergence it didn't reach.
- **Every derived skill cites sources** (repo path or URL). No source → not in the batch.
- **The forge-run batch is one atomic reviewable unit** — the whole run reverts together.

---

## PHASE 0 — SCOPE

1. Detect stack/framework/domain from `session_start` context, or take it from `stack:`.
2. Set the adaptive ceiling: `soft_cycles=5`, `hard_cap=10`. Past soft_cycles, continue only
   while each cycle's bar-lift is substantial; stop at marginal lift or hard_cap.
3. Open the forge-run batch: `state/skill-forge-run.json` with `{stack, started_at, cycles:0,
   skills_created:[], skills_sharpened:[], converged:false, ceiling_hit:false, revert_manifest:[]}`.

> Compact: "Forging skills for {stack}. Adaptive ceiling {soft}/{hard}. Batch open."

---

## PHASE A — DISCOVERY LOOP (breadth, until the standard stops rising)

Maintain `standard` = the current written bar for "what elite means for this stack." Starts empty.

Repeat:
1. `analyze_stack_for_skills(stack, framework, repo_paths, known_skills, standard)`.
2. Do the deep repo + live internet search the returned directive asks for.
3. **RAISE-THE-BAR** (the core step): read `standard`, ask "what would an engineer BETTER than
   the one who wrote this bar object to or add?" Rewrite `standard` upward. This is the loop's
   real variable — a rising bar surfaces skills the old bar couldn't see.
4. Under the raised bar, derive candidates: `{name, why, how_it_matters, sources, covered_by}`.
5. Drop candidates already `covered_by` an existing skill.
6. Each genuinely new skill: `generate_skill(signal_type='stack_analysis')` → write the SKILL.md
   → `add_proposal(FILE_CREATE)` → `apply_proposal(confirmed=True, safe_types=["FILE_CREATE"])`.
   Log each to the batch.
7. **STANDARD-DELTA CHECK:** did step 3 raise the bar this cycle?
   - Bar rose → loop again.
   - Bar stable AND no new skill → converged (even a better engineer is silent). Exit.
8. **ADAPTIVE CEILING CHECK:** past soft_cycles, continue only on substantial bar-lift; stop at
   marginal lift or hard_cap. If stopped un-converged → set `ceiling_hit=true`, report honestly.
9. **COST-PER-VALUE CHECK:** a cycle that spent tokens but neither raised the bar nor added a
   skill is a wasted cycle — record it in the batch and tighten the raise-the-bar prompt or stop.

> Compact: "Loop A: {N} cycles, bar raised {M} times, {K} skills created, converged={bool}."

---

## PHASE B — DEFINITION LOOP (depth, per skill, until definition converges)

For each skill in scope (new from A + any existing skill named for sharpening):

Repeat:
1. `assess_skill(skill_name)`.
2. Sharpen against the ELITE bar from `standard`, not the competent bar: "what definition —
   phases, quality bars, exit conditions, failure modes — produces legendary output vs. merely
   correct output for THIS skill?"
3. Run the **signal/noise framework** (`humanize/references/signal-noise-framework.md`) on every
   line being added: SUBTRACT keeps the skill from bloating while "improving," REVEAL adds the
   elite-caught-but-unstated quality bar the old definition missed. An addition must survive both.
4. Proposed additions exist → `add_proposal(SKILL_EDIT)` → `apply_proposal(confirmed=True,
   safe_types=["SKILL_EDIT"])`. Log to batch.
5. **DELTA CHECK:** coverage_score stopped rising AND no new proposed_addition → this skill's
   definition converged. Next skill.
6. **CEILING CHECK:** per-skill cycle cap reached → stop, flag.

> Compact: "Loop B: {N} skills sharpened, coverage {before}→{after} each."

---

## PHASE C — REPORT

Close the batch (`converged`, `ceiling_hit`, final counts). Emit:

```
[FORGE RUN — {stack}]
Standard: {final elite bar, 1-2 lines}
Skills created:   {name — why — sources}  (×N)
Skills sharpened: {name — coverage before→after}  (×M)
Cycles: Loop A {a} (converged={bool}), Loop B {b}
Wasted cycles: {n}  ← if >0, the raise-the-bar prompt needs tightening
Proposal-only (not auto-applied): {any CODE/CONFIG-implying items}
Revert: {how to roll back the whole batch}
```

If `ceiling_hit=True`: state plainly the run did not converge and can be resumed next session.

---

## Quality Bars (Non-Negotiable)

- The RAISE-THE-BAR step must actually change `standard`, or the cycle counts as wasted. A loop
  that re-derives the same skills without lifting the bar is spinning, not converging.
- No skill enters the batch without `sources`. A why you can't trace is a why you can't trust.
- REPORT never claims `converged=True` unless the bar was stable on the final cycle.
- Auto-apply `safe_types` is checked on every call — CODE_EDIT/CONFIG_EDIT in the list is a bug,
  not a judgment call.

---

## When NOT to invoke

- No stack detected and none supplied → ask for the stack, don't guess.
- A single known skill needs one fix from session evidence → that's `/improve` (reactive), not a
  full forge run.
- Mid-implementation of an unrelated task → forge is a deliberate act, not an ambient one.

---

## Reference Files

| File | When to read |
|------|--------------|
| `humanize/references/signal-noise-framework.md` | PHASE B — SUBTRACT + REVEAL on every added line |
| `knowledge/skill-schema.md` | PHASE A step 6 — SKILL.md structure when generating |
