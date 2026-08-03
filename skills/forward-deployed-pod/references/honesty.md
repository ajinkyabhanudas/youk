# Honesty and Artifacts

Owned jointly by the **Evidence Lead** and the **Skeptic**. Read this before writing any
outward-facing artifact.

The premise: work that's genuinely good doesn't need inflation, and inflation is the thing
reviewers are best at detecting. Every rule here makes the output both more honest *and* more
persuasive, which is not a coincidence — the markers of honesty (stated n, named regressions,
bounded conclusions) are the same markers that distinguish someone who has actually shipped.

---

## Hard rules

1. **Never fabricate.** No placeholder metrics, no illustrative quotes presented as real, no
   plausible eval results. If a number is needed and doesn't exist, write `[MEASURE: task success
   rate, n TBD]` and leave it visible in the draft.
2. **Never backdate.** Don't write a PRD dated to when the code was written. Commit history is
   public and checking it is trivial. Label retrospective work as retrospective — it costs
   nothing and buys credibility.
3. **Never let a claim drift up a tier** between analysis and write-up. "3 of 5 users mentioned"
   must not become "users consistently report."
4. **Distinguish measured / estimated / aspirational** in the text itself, not in a footnote.
5. **Report the regression.** A write-up with only wins reads as incomplete measurement.
6. **Don't claim team outcomes as individual ones.** If it was a solo project, say so; solo scope
   done rigorously is a fine story.

---

## Evidence tiers in prose

| Tier | Phrasing that's honest | Phrasing that overclaims |
|------|------------------------|--------------------------|
| E0 hypothesis | "We assumed…" | "We knew…" |
| E1 anecdote | "One user described…" | "Users find…" |
| E2 coded qualitative | "6 of 9 raised this unprompted" | "The majority of users…" |
| E3 offline eval | "Pass rate 58%→81% on a frozen 120-case set" | "23% more accurate" |
| E4 pre/post usage | "Median TTFV fell 4.2→2.1 min, n=38 sessions" | "Cut time in half" |
| E5 controlled | "Variant B +6pp, p=0.03, n=1,200" | "B is better" |

The left column is longer and better. Specificity is the signal.

---

## Retrospective artifacts — how to do it legitimately

Adding product documentation to work already completed is fine, and often the right move. Doing
it dishonestly is disqualifying. The difference is entirely in the labelling.

**Legitimate:**
> *Retrospective product notes — written July 2026, reconstructing decisions made Jan–Mar 2026
> from commit history and notes. Reasoning is reconstructed; the decisions and their outcomes are
> as they happened.*

**Not legitimate:** a `PRD.md` committed today, written in future tense, presented as if it
preceded the code.

Reviewers respond well to retrospective analysis, because the thing they're evaluating is the
quality of the reasoning, not the existence of a document. What they punish is the attempt to
appear to have followed a process you didn't.

---

## Repo artifact layout

Match existing repo conventions; otherwise:

```
docs/product/
├── problem-frame.md          # Phase 1
├── discovery/
│   ├── synthesis.md          # Phase 2
│   └── notes/                # anonymised, consent-respecting
├── metrics.md                # Phase 4 — tree + definitions
├── decisions/
│   └── 0001-<slug>.md        # Phase 5 — one per real decision
├── results/
│   └── 2026-07-eval-v2.md    # Phase 6
└── product-notes.md          # Phase 7 — the readable front door
evals/
├── golden/v1.jsonl
├── taxonomy.md
├── graders/
└── README.md
```

`product-notes.md` is what a reviewer actually reads. Keep it under two pages and link outward.

---

## Decision record template

The most undervalued artifact. Rejected options are where judgment is visible.

```markdown
# [Decision]
**Date:** · **Status:** decided / superseded · **Type:** live / retrospective

## Context
[The situation and the constraint. What made this genuinely ambiguous.]

## Options considered
**A — [name]**  Pro: … Con: …
**B — [name]**  Pro: … Con: …
**C — do nothing**  [Always include this one.]

## Decision
[Chosen option and the reasoning.]

## What this costs us
[The real downside accepted. If there isn't one, the analysis is incomplete.]

## How we'll know if it was wrong
[The signal and the time horizon.]

## Outcome (filled in later)
[What actually happened, including if it was wrong.]
```

---

## Product notes template

```markdown
# [Project] — product notes
*[Retrospective / live] · [dates] · [solo / team of N]*

## The problem
[User's bad day, the population, the current workaround and its cost.]

## What I chose not to build
[Non-goals and why. Lead with this — it's the strongest section and almost nobody writes it.]

## The hardest call
[The one genuinely ambiguous decision, the options, what it cost.]

## How I defined "good"
[Failure taxonomy, golden set, grader choice, and why that grader.]

## What the numbers said
[Baseline, change, result, regression, n, evidence tier. Include what got worse.]

## What I got wrong
[Specific. This section is read more carefully than any other.]

## What I'd do differently
```

---

## Skeptic's audit checklist

Run before anything goes outward. For each claim:

- [ ] Traceable to a run, transcript, or log a reader could inspect
- [ ] n stated where a rate is given
- [ ] Denominator unambiguous
- [ ] Tier in the prose matches the tier of the evidence
- [ ] Regressions and negative results included
- [ ] Retrospective work labelled as such
- [ ] No metric that could rise 10x without a user being better off
- [ ] Nothing implies team scope that was solo, or live users that don't exist
- [ ] Sensitive-domain content respects consent and avoids unqualified clinical claims

Any unchecked box: demote the claim a tier or cut it. Cutting is usually better — the piece gets
shorter and more credible at the same time.
