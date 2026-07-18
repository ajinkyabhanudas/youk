# references/convergence.md — Loop Mechanics, Certificates, Caps

---

## Exit Condition (always)

A full frame pass produces zero new objections from ALL frames and angles that ran.

This is not a round count. Round count is an emergency brake.

Before surfacing any verdict, two checks must both pass:

1. **Did the last round produce zero new objections from every frame that ran?**
   If not — iterate.

2. **Is there any frame, angle, or dimension not yet run?**
   If yes — run it now before declaring convergence.

Only when both are true is the loop dry. "I ran F1–F7 and found nothing" is not the exit
condition if there are angles within a frame that weren't run, or if frame-generation
hasn't been attempted.

---

## What "Global Optimum" Means

Global optimum = optimum across ALL frames simultaneously.

A loop that exits because the frames it ran produced no objections, while leaving frames
unrun, is at a LOCAL optimum, not global. The self-check is:
> "Have I covered every frame that exists — including generated frames — and has every
> generated frame been applied to all items in its scope?"

If the answer is no: keep going internally. The user sees only the final verdict.

---

## Round Caps (emergency brakes — not exit conditions)

| Context | Cap | On cap hit |
|---------|-----|-----------|
| Per-item frame rounds | 10 | Surface unresolved tension explicitly. "Round 10 reached — objection X remains unresolved: [state it]. Human input needed before proceeding." Never exit silently. |
| Phase A total budget | Phase A.5 budget exhausted | Apply tiering rule: complete mandatory-full-protocol items (roadmap items + top-5 gaps + verdict-load-bearing claims) first. Inline-clear remaining items. Document in deviation log. |
| Stress-test attack rounds | 5 | Same: surface unresolved tension explicitly. |

**Never exit silently on cap hit.** The unresolved tension is surfaced to the human.
A silent exit on cap hit is a false convergence — the certificate cannot be honestly written.

---

## Convergence Certificate Format

```
[CONVERGENCE CERTIFICATE]
Items processed:    {N claims} + {M gaps} + {K CAP items} = {total} items
Rounds consumed:    Full 7-frame on {n} items; inline 3-angle on {m} items
Objections raised:  {N} material objections across full-round items
Objections resolved: {N} — all resolved before verdict (or: {N} unresolved — see CONTESTED)
Frames generated:   {N beyond F1-F7; each named and scoped}
Items CONTESTED:    {N — list them if >0; they appear in verdict as UNRESOLVED}
Honest ceiling:     "{The specific claim the loop cannot make stronger with the evidence
                    available — or: 'No frame we could construct produces a surviving
                    objection against the converged verdicts. The primary finding is
                    [X] and is consistent across F1–F{N} and the empirical evidence [Y].'}"
```

**CONTESTED items in the certificate:** Any item where a surviving objection could not be
resolved before the round cap was hit, or where two frames produce contradictory verdicts
that cannot be reconciled. CONTESTED items appear in the verdict as UNRESOLVED — not as
HOLDS or PARTIAL.

**Honest ceiling:** The honest ceiling is the statement of what the loop CAN legitimately
claim given the evidence quality and scope. It is the place where the analyst is honest
about the limits of the analysis:
- "This does not mean X is impossible — it means X has not been demonstrated"
- "This finding depends on [Y] remaining true — if [Y] changes, re-run the loop"
- "The primary finding is consistent but relies on [ASSUMED] comparables in the landscape
  scan — web search would strengthen or weaken [specific finding]"

---

## Material Objection Definition

A material objection is specific, not hypothetical:

**IS a material objection:**
- "When 100 users query simultaneously, the thread pool exhausts at 10 threads and new requests queue indefinitely"
- "The --cov-fail-under 88 threshold exceeds the measured 86% local coverage and would immediately break CI"
- "The developer_autonomy_rate denominator includes all 43 sessions, but DeveloperCaught was only recently instrumented — the effective measurement window is shorter than the denominator implies"

**IS NOT a material objection:**
- "This might fail under load"
- "The documentation could be clearer"
- "The team should think about this"
- Any objection that doesn't name what fails, when, and under what condition

---

## Inter-Frame Coherence Check

After all frames complete, before verdict:

```
[INTER-FRAME COHERENCE]
F1 assumed the problem being solved was: {one clause}
F2 assumed the implementation addressed: {one clause}
F3 evaluated evidence for: {one clause}
F4 evaluated the metric for: {one clause}
...
Coherence: ALIGNED | DIVERGED on {frames} — {the divergence, stated as an objection}
```

If DIVERGED: the divergence is a HIGH objection. The frames attacked different problems.
This must be resolved before the verdict is issued.

---

## Verdicts and What They Mean

| Verdict | Meaning |
|---------|---------|
| HOLDS | Claim is true as stated. Evidence is ≥ TRACED. No surviving objections across all frames. |
| PARTIAL | Claim is directionally true but overstated, contradicted in one direction, or only partially implemented. |
| UNVERIFIED-AS-STATED | No evidence beyond assertion or [READ] documentation. May be true — cannot confirm. |
| CONTESTED | Surviving objection from one or more frames that couldn't be resolved within round cap. Appears in verdict as UNRESOLVED. |

**HOLDS requires:** Evidence ≥ TRACED + zero surviving objections after full frame pass.
**PARTIAL requires:** At least one frame found a bounded but non-blocking objection.
**UNVERIFIED-AS-STATED requires:** Evidence is [READ] or [ASSUMED] only; or claim is empirical-only with no longitudinal data.
**CONTESTED requires:** Cap hit with surviving BLOCKING or HIGH objection that couldn't be resolved.
