# youk — Repair Quality Definition

## What a repair is for

A repair prevents a developer from correcting the same gap in youk's behaviour across
multiple sessions. Without it, the developer becomes the memory: they re-explain the
same thing, youk re-makes the same mistake, and the compounding that is youk's core
claim never materialises.

**Concrete failure:** a skill is invoked but produces wrong output because SKILL.md
did not encode a decision made three sessions earlier. Developer catches it, explains
it, closes the session. Next session it happens again.

---

## Primary measure

**Gap non-recurrence rate:** the SkillGap audit signal for a repaired skill must not
reappear within the 5 sessions following a confirmed SkillPatch.

Computed from audit logs: after `SkillPatch: {skill}` is written, scan the next 5
session blocks for `SkillGap: {skill}`. A repair passes if the gap does not recur.

Why this over the alternatives:
- Human-judged correctness is necessary but not sufficient — a correct repair that
  doesn't stick is useless.
- "Fewer corrections next session" is too diffuse; task type affects it as much as
  repair quality.
- "User never notices" is not measurable and a bad silent repair is worse than a
  visible failed one.

---

## Secondary measures

- **Patch-cycle rate:** proportion of skills where SkillPatch was written but SkillGap
  reappeared within 5 sessions. Already computed in `_analyze_promotion_candidates`
  as `patch_cycle=True`. Aggregated across repairs per quarter.
- **Proposal acceptance rate:** ratio of proposals the developer confirms vs rejects.
  A low rate means the health check is generating noise, not signal.

---

## The intolerable failure

A repair that overwrites a decision that was correct — a previously-working pattern
breaks after the patch is applied. This is worse than a failed repair (gap persists,
visible) because a destructive repair is invisible until something downstream breaks,
possibly sessions later.

**Threshold asymmetry:** false negatives (repair doesn't fix the gap) are acceptable.
False positives (repair breaks something true) are not. The `apply_proposal(confirmed=True)`
hard gate exists for this reason. The eval should separately track post-repair regressions
(a skill that was working stops working after a patch).

---

## Cheap proxy (diagnostic only)

**Patch-cycle rate** computed on every `run_health_check_with_skill_signals` call.
Already live in `health.py:_analyze_promotion_candidates`. High rate = repairs not
sticking. Low rate ≠ repairs are good (gap may not have been triggered yet).

Labelled explicitly as a diagnostic, not the criterion. The criterion requires 5
post-repair sessions of audit data; the proxy is available immediately.

---

## What this definition lets through that shouldn't pass

A repair that is never triggered again because the task type changes — the gap would
appear to be fixed when it was never tested. The non-recurrence rate is only meaningful
if the skill was actually invoked post-repair. The eval must filter to sessions where
the repaired skill was invoked; if it wasn't invoked, the data point is excluded.
