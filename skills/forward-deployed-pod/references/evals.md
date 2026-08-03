# Eval Design

Owned by the **Eval Engineer**. This is the highest-differentiation artifact the pod produces,
because most people claiming AI product experience have never built one.

The sequence is fixed and the order matters: **collect outputs → build taxonomy → assemble golden
set → choose graders → baseline → improve → re-measure**. Skipping to "improve" is the standard
mistake, and it's why teams fix the failure they imagined rather than the one they have.

---

## 1. Collect real outputs first

Gather 30–50 real outputs from the current system before theorising. Sources, in order of value:
actual user sessions, your own realistic usage, adversarial inputs you construct last.

If the project has no users, generate inputs that reflect the real distribution — including the
boring middle, not just the hard cases. A golden set made only of hard cases produces a scary
baseline that improves easily and means nothing.

**Log for each:** input, full output, any retrieval or tool calls, latency, cost, and your own
verdict. Store as JSONL so it's greppable and diffable.

---

## 2. Build the failure taxonomy

Read every output. Sort the failures into named classes. Rules that make taxonomies useful:

- **Derive classes from observed failures**, never from a generic list. If your taxonomy could
  have been written before looking at the data, it's not a taxonomy, it's a vocabulary.
- **Classes must be mutually exclusive enough to count.** If one output lands in three classes,
  the classes are wrong.
- **Record frequency per class.** The distribution is the finding — usually one or two classes
  dominate and the rest are noise.
- **Separate quality failures from safety failures.** These have different thresholds: quality
  is a rate you improve, safety is often a rate that must be near-zero regardless of frequency.

**Common class families** (adapt, don't copy):

| Family | Looks like |
|--------|-----------|
| Retrieval | Right answer exists in the corpus, system didn't find it |
| Grounding | Answer not supported by retrieved context; fabricated specifics |
| Instruction adherence | Ignored format, length, or constraint in the prompt |
| Scope | Answered a different question; over-answered; refused something valid |
| Calibration | Confident when wrong; hedged when it should have committed |
| Reasoning | Correct inputs, wrong inference or arithmetic |
| Tone / register | Correct content, wrong for the context or user state |
| Safety | Harmful, unsafe advice, privacy leak, inappropriate for a vulnerable user |
| Operational | Timeout, malformed output, tool call failure, cost blowout |

**Sensitive domains need domain-specific safety classes.** A fertility product needs classes for
clinically misleading claims, false reassurance, and inappropriate certainty about outcomes — and
those cannot be traded off against quality metrics.

---

## 3. Assemble the golden set

A fixed, versioned set of cases with known-good expectations. Properties that matter:

- **Frozen.** Changing the set between measurements invalidates the comparison. Version it; if
  you add cases, report both the old-set and new-set numbers for one cycle.
- **Distribution-matched.** Roughly mirror real input frequency, then add a deliberately
  over-weighted slice of each failure class so you can detect movement in rare classes.
- **Sized for the budget.** 50 cases hand-graded well beats 500 graded carelessly. 100–200 is a
  good target if grading is automated.
- **Expectations, not exact strings.** For generative outputs, store the rubric or the required
  properties, not one blessed answer.
- **Held-out slice.** Keep 20% you don't look at while iterating, to catch overfitting to the
  cases you've been staring at.

Store as `evals/golden/vN.jsonl` with a short `README` explaining provenance and what each field
means. Provenance is what makes it credible to a reviewer.

---

## 4. Choose graders — trust order matters

| Grader | Use when | Trust |
|--------|----------|-------|
| **Deterministic assertion** | Format, schema, presence of required field, numeric match, latency budget | Highest — use wherever possible |
| **Programmatic heuristic** | Citation present and resolves; no PII in output; length bounds | High |
| **Rubric + human** | Subjective quality, tone, clinical appropriateness | High but expensive; the honest choice for small sets |
| **Model-graded (LLM judge)** | Scale beyond human capacity | Lowest — requires validation |

**If you use a model as judge, validate it.** Hand-grade 30 cases, compare to the judge, report
agreement. An unvalidated judge is a number-generator, not a measurement, and a good reviewer
will ask. Reporting "judge agreed with human on 27/30, disagreements clustered in tone cases" is
itself a strong signal of seniority.

Guard against known judge failure modes: position bias in pairwise comparison (randomise order),
length bias (longer answers score higher — check), and self-preference.

---

## 5. Baseline before touching anything

Run the full suite against the current system. This number is the most valuable single artifact
in the project, because every later claim is relative to it. Record: date, model version, prompt
version, retrieval config, pass rate overall and per failure class, cost, p50/p95 latency.

Without a baseline there is no improvement claim, only an assertion.

---

## 6. Improve, then re-measure honestly

- Change **one thing** per cycle where possible, so attribution is clean.
- Re-run the **whole** suite, not just the class you targeted. The interesting result is usually
  the regression elsewhere.
- Report **per-class movement**, not just the aggregate. Aggregate improvement hiding a safety
  regression is the failure mode this whole structure exists to prevent.
- Report the **held-out slice separately**.

**Write-up template:**

```
Baseline (v1, 2026-07-14): 58% pass, n=120
  retrieval-miss 22 · grounding 14 · format 9 · tone 5
Change: reranking step added to retrieval
Result (v2, 2026-07-21): 79% pass, n=120
  retrieval-miss 4 · grounding 11 · format 9 · tone 12
Regression: tone failures 5→12. Reranked context is denser and more
clinical; the model mirrors register. Not yet fixed.
Held-out (n=24): 75% — consistent with the main set.
Cost: +18% per query. p95 latency +340ms.
```

The regression line is what makes this credible. A write-up with no regressions reads as
incomplete measurement, not as a flawless system.

---

## 7. Make it a regression suite

Once it exists, wire it to run on every change. `make eval` or a CI job. The claim "we caught a
regression before shipping it" requires having been in a position to catch one.

---

## Anti-patterns

- Building the harness before looking at outputs
- A taxonomy that matches a blog post rather than your data
- Changing the golden set to make the number improve
- Reporting only the aggregate
- Model-as-judge with no human validation
- Evaluating only the happy path
- Treating safety classes as tradeable against quality classes
