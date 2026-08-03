# Measurement

Owned by the **Measurement Lead**. The job is not to produce numbers — it's to produce numbers
that would survive someone asking where they came from.

---

## The metric tree

One north star, 2–4 drivers you can actually influence, guardrails that must not degrade.

```
North star:   the thing that means the product worked for a user
  ├── Driver: an input you can change this month
  ├── Driver: another one
  └── Driver: another one
Guardrails:   cost, latency, safety-class rate, escalation rate
```

Rules:
- **The north star must be a user outcome, not a system output.** "Queries answered" is a system
  output. "Sessions ending in an accepted answer" is closer to an outcome.
- **Drivers must be movable in the time budget.** A driver you can't influence in a month is a
  north star in disguise.
- **Every guardrail must have a stated threshold** before you start, or it will be rationalised
  after.

---

## Every metric needs five fields

Anything missing these is not a metric, it's a number.

1. **Name**
2. **Numerator** — precisely what counts as the event
3. **Denominator** — the population, and who's excluded from it and why
4. **Collection method** — logged, hand-coded, eval-derived, estimated
5. **Evidence tier** — E0–E5 (see `honesty.md`)

Bad: "80% success rate."
Good: "Task success = sessions where the user accepted or lightly edited the output ÷ sessions
with ≥1 submitted query. Excludes sessions <5s (bot/misfire). Hand-coded from 40 sessions. E2."

---

## AI product metric library

Pick a few. A tree with four defensible metrics beats a dashboard with twenty.

### Outcome
- **Task success rate** — share of attempts reaching the user's actual goal. Needs an explicit
  definition of "success" you set *before* looking at data.
- **Time to first value** — from session start to first output the user keeps. Brutally
  informative and usually easy to instrument.
- **Acceptance rate** — outputs accepted without modification.
- **Edit distance to accepted output** — how much the user had to fix it. The single best proxy
  for quality in generative products, and a strong one to show you know.
- **Retry rate** — user re-asking the same thing. High retry means low trust in the first answer.
- **Containment rate** — resolved without escalating to a human or another tool.
- **Abandonment point** — where in the flow people leave. A distribution, not a number.

### Quality (eval-derived)
- **Pass rate overall and per failure class**
- **Regression rate** — share of previously-passing cases that now fail
- **Grounding / citation-supported rate**
- **Calibration** — accuracy at each stated confidence level
- **Judge–human agreement** — validation of your grader, not the product

### Guardrail
- **Cost per successful task** (not per call — per *successful* task, which exposes retry costs)
- **p50 / p95 latency** — p95 is where users churn
- **Safety-class incidence** — near-zero targets, tracked separately, never traded off
- **Escalation rate**
- **Coverage** — share of real inputs the system will even attempt

### Discovery / qualitative
- **Problem incidence** — n of interviewees who raised it unprompted (unprompted is the key word)
- **Current workaround cost** — self-reported time or money, tier E2 at best
- **Switch trigger frequency** — what actually made people change tools

---

## Leading vs lagging

Lagging metrics tell you whether it worked; leading metrics tell you in time to do something.
For a project with a 10-week horizon, weight toward leading: eval pass rate, time-to-first-value,
edit distance. Retention is lagging and mostly unmeasurable at side-project scale — don't claim it.

---

## Instrumentation

- Log **events with properties**, not aggregates. You can always aggregate later; you can never
  disaggregate.
- Include a **session id**, **timestamp**, **version tags** (model, prompt, retrieval config).
  Version tags are what let you attribute a change later.
- Log the **denominator events** too — the attempts, not just the successes. The most common
  instrumentation failure is logging only wins.
- **Decide what not to log.** In sensitive domains, log the event and the outcome, not the
  content. Write down that decision; it's evidence of judgment.

---

## Small-n honesty

Side projects live at n=8 to n=200. Rules that keep you credible:

- **Always state n** next to the number. Every time.
- **Below ~30, report counts, not percentages.** "7 of 9" not "78%" — percentages imply a
  precision the sample doesn't have.
- **Don't run significance tests you can't power.** At n=40 per arm you can detect large effects
  and nothing else. Say so: "n supports detecting only large differences; this result is
  directional."
- **Prefer within-subject comparison** at small n — same cases before and after, which removes
  between-group variance and is exactly what a frozen golden set gives you.
- **Watch selection effects.** People who finished the flow are not people who started it.
- **Don't peek and stop.** Decide the sample size before looking, or acknowledge that you didn't.

The senior move is stating the limit clearly. "Our n only supports directional conclusions" reads
as competence; a confident p-value from n=12 reads as not knowing better.

---

## Vanity metrics to kill on sight

The Skeptic seat should flag these automatically: total users ever, cumulative anything, page
views, GitHub stars, "engagement time" in a product where less time is the goal, model API calls,
lines of code, and any percentage without a denominator.

The test: *if this number went up 10x, would a user's life be better?* If not, it's vanity.
