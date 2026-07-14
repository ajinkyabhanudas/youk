# Signal/Noise Framework

Runs on any youk-authored text (SKILL.md, server prompt, brief, chat reply). Two opposed
passes run together — the tension is the capability.

- **SUBTRACT** — remove what doesn't earn its tokens. Makes youk cheap.
- **REVEAL** — surface what a senior catches on instinct but rarely says. Makes youk trusted.

The goal of REVEAL is **trust** (youk catches what you'd miss), not spectacle. Astonishment is
a side effect of being reliably right — never the target. Optimizing for "impressive" produces
performed insight (verbose cleverness); optimize for "correct and unspoken."

A framework that only subtracts is blind to what *should exist but doesn't* — it can only audit
lines that are present. Trust needs REVEAL.

---

## PASS 1 — SUBTRACT (defaults to CUT)

Per line:

1. **REMOVAL (inversion):** delete it. Does output degrade — worse reasoning, missed case,
   wrong action, or information the reader can't reconstruct?
   - NO → cut. Filler / greeting / meta-framing / re-ask always fail here.
   - YES → survives to step 2.
2. **COMPRESSION (MDL):** can the surviving line's information encode in fewer tokens (merge,
   table, shorter phrasing) with zero loss? YES → rewrite. NO → keep.

Burden of proof is on KEEPING, not cutting.

> 5-whys was rejected: it's a root-cause tool for *defects* (iterative depth on one item);
> auditing prose is *pruning many units* (one-pass breadth). Wrong shape.

---

## PASS 2 — REVEAL (additive)

Ask what a superior engineer would notice but not bother to say:

1. **MISSING:** what line SHOULD be here that isn't — the "everyone knows" assumption, the
   unhandled case, the implicit precondition? Add it, explicit.
2. **FRAME:** is a technically-true line quietly misleading in how it's framed? Reframe.
3. **CONNOTATION:** does a word carry a wrong innate association — "simple" / "just" /
   "obviously" hiding real cost, false confidence, or a dismissed edge? Replace with the honest word.
4. Surface each as a one-line explicit callout — the human's tacit "this is off," verbalized.
5. **LOAD-BEARING FILTER (REVEAL's convergence):** each surfaced item must change the reader's
   action or prevent a real error. If not → manufactured depth, drop it. Stop when new items
   stop passing this filter.

Without step 5, REVEAL generates objections forever, dressing noise as insight — the exact
failure this framework exists to prevent, so REVEAL polices itself the same way SUBTRACT does.

---

## TENSION RULE

The passes pull opposite ways (cut vs. add) and BOTH run. A REVEAL addition must itself survive
PASS 1 (no bloat added while revealing) AND the load-bearing filter (no invented insight).
Efficiency and trust are co-constraints, not a sequence — youk is cheap AND catches the
unspoken, never one at the other's cost, never faking the second.

---

## Precedent in youk (this generalizes existing REVEAL instances)

- `learn`: "state where the analogy breaks down — the highest-value part; a bridge without a
  breakdown is a false equivalence waiting to become a bug."
- `challenge` Lens 3: surfaces hidden assumptions.
- `stress-test`: finds the unspoken failure condition.

These three kept private versions of REVEAL. This file is the shared source.

---

## GRADE before APPLY (auditing existing content)

Applying edits contaminates the baseline you grade against — so keep them separate:

1. **GRADE (unapplied):** run the framework, record what REVEAL finds. Success metric: does it
   surface nuance not consciously written? Bias metric: does SUBTRACT flag anything REVEAL then
   argues to keep?
2. **APPLY (after review):** only findings that pass load-bearing + PASS 1 become proposals.
   A measured, reviewed batch — not an auto-cleanup.
