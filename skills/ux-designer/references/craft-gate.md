# The Craft Gate

Read during the CRAFT GATE phase. This gate can return **REJECTED**, and a
REJECTED verdict blocks implementation.

---

## 0. Why this gate exists

A design review that can only say "looks good, ship it" or "fix these three
things" is not a quality bar — it is a formality. This gate exists to make
rejection a real, expected outcome.

The standard: **an interface should be worth stopping to look at.** Not merely
usable, not merely inoffensive. If a demanding reviewer would glance at it and
move on without interest, it has failed, even with zero functional defects.

### 0.1 What this gate is honestly doing

It cannot simulate a person's taste. Nobody's judgment is reproducible, and a
gate that asks "is this beautiful?" returns yes every time.

What it *can* do is check the things that taste reliably punishes: unmade
decisions, visible seams, decoration without function, and the absence of a
single dominant idea. Those are observable. The gate scores those, and the score
is falsifiable — someone can look at the interface and disagree with a specific
dimension, which is exactly the property a vibes-based review lacks.

**The gate is strict about mechanics and honest about taste.** It never claims
the output is beautiful. It claims the output has no remaining unmade decisions.

---

## 1. Scoring

Nine dimensions, each scored 0–3.

| Score | Meaning |
|---|---|
| 0 | Absent. No decision was made. |
| 1 | Present but arbitrary. Values not derived from a system. |
| 2 | Systematic. Derived, consistent, defensible. |
| 3 | Considered. Systematic **and** a specific deviation was made deliberately, with a reason. |

The distinction between 2 and 3 matters most. A 2 follows the rules. A 3 knows
which rule to break for this particular content — and that is the difference
between a design that is correct and one that is right.

| # | Dimension | Scored on |
|---|---|---|
| D1 | Typographic system | Scale derived from a ratio; ≤6 sizes; leading tuned per size; tracking corrected at display sizes; tabular numerals where columnar |
| D2 | Spatial system | Single base unit; every value on the scale; proximity encodes grouping with a clear factor |
| D3 | Colour discipline | Ramp not palette; semantic tokens; one accent; contrast above floor not at it |
| D4 | Hierarchy | Survives the squint test; one dominant element per screen |
| D5 | Restraint | Survives the removal test; nothing decorative remains |
| D6 | Depth and surface | Consistent elevation set; radius proportional and nested correctly; light modelled coherently |
| D7 | Motion | Purposeful; duration banded; easing non-linear; reduced-motion handled |
| D8 | Dark mode | Not inverted; elevation re-modelled; colours re-tuned; screenshot verified |
| D9 | The unified idea | One thing this screen is for, stated in a sentence, and structurally evident |

---

## 2. Verdicts

Compute the total (max 27) and apply **all** conditions.

| Verdict | Conditions |
|---|---|
| **APPROVED** | Total ≥ 22 **and** no dimension scored 0 or 1 **and** D4, D5, D9 each ≥ 2 |
| **REVISE** | Total 15–21, or any single dimension at 1 |
| **REJECTED** | Total < 15, **or** any dimension at 0, **or** D9 < 2 |

**D9 is an independent veto.** A design can score well everywhere else and still
be rejected for having no centre. That is the specific failure this gate exists
to catch, because it is the one that passes every conventional review.

### 2.1 Required output format

```
[CRAFT GATE]
D1 typography    {0-3}  — {one line of evidence}
D2 space         {0-3}  — {…}
D3 colour        {0-3}  — {…}
D4 hierarchy     {0-3}  — {…}
D5 restraint     {0-3}  — {…}
D6 depth         {0-3}  — {…}
D7 motion        {0-3}  — {…}
D8 dark mode     {0-3}  — {…}
D9 unified idea  {0-3}  — {…}
TOTAL: {n}/27
VERDICT: APPROVED | REVISE | REJECTED

{If not APPROVED — the single highest-leverage change, stated concretely.}
```

Scores MUST cite evidence from the spec. "D1: 3 — good typography" is not a
score; it is an assertion. "D1: 2 — 1.25 scale, 5 sizes, tabular nums on the
results column; no display tracking correction at 39px" is a score.

---

## 3. The three tests

Run these before scoring. They are faster than the rubric and catch most failures.

**Squint test → D4.** Blur until text is illegible. What remains dominant? If
nothing, or the wrong thing, D4 ≤ 1.

**Removal test → D5.** For every element, ask what breaks if deleted. Anything
that survives deletion without loss is decoration. If more than two such elements
exist, D5 ≤ 1.

**One-sentence test → D9.** Complete: *"This screen exists so the user can
______."* If the sentence needs "and" to be accurate, the screen has two jobs and
D9 ≤ 1. Split the screen or subordinate one job.

---

## 4. What this gate does not check

Stated plainly, so the verdict is not over-read.

- **Whether the underlying product idea is good.** A beautifully resolved
  interface to a pointless feature scores 27.
- **Whether real users can complete real tasks.** That is the existing CRITIC
  REVIEW plus actual testing. This gate is craft, not usability.
- **Whether it is original.** Systematic, restrained design converges on similar
  answers. That is fine.
- **Whether a specific person would like it.** Not knowable. See §0.1.

A design that passes this gate and fails a usability test is a failed design. The
gates are independent and both bind.
