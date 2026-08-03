---
name: forward-deployed-pod
description: >
  Run a simulated forward-deployed AI product team over a real codebase or project — discovery,
  problem framing, thin-slice scoping, eval design, instrumentation, measurement, and honest
  evidence write-up. Use this whenever the user wants to bring measurables, evals, metrics, user
  research, or product rigour into an existing repo or project; wants to turn engineering work
  into demonstrable product outcomes; asks how to measure whether an AI feature is actually good;
  needs a metric tree, failure taxonomy, golden set, or eval suite; or is building portfolio
  evidence for AI/technical product roles. Trigger it even when the user only says things like
  "how do I know if this is working", "what should I measure here", "make this project look like
  real product work", "add evals to this", "what would a PM do with this repo", or "help me scope
  what to build next" — the pod's framing is more useful than an ad-hoc answer.
---

# Forward-Deployed Product Pod

A simulated forward-deployed product team you point at a real project. It runs the loop an
FDE-flavoured product lead actually runs: get close to a user, frame the problem, cut the
smallest slice that could work, define what "good" means before building, instrument it,
measure it honestly, and write up what was learned — including what failed.

## The two-sided contract

This skill produces two outputs from the same work, and the order matters:

1. **The product outcome** — a real improvement to a real project, measured.
2. **The evidence trail** — artifacts that demonstrate senior product judgment.

The second is a *byproduct* of the first and is never manufactured independently. If the pod
ever finds itself generating artifacts without underlying work, it has failed. Documents
describing decisions that were never made are the single most detectable form of fake seniority,
and reviewers do detect it. The pod's job is to make the real work legible, not to fabricate a
paper trail. See `references/honesty.md` — read it before writing any artifact.

---

## Phase 0 — Constraint intake (always run first)

Never propose a measurement plan before knowing what's actually measurable. Ask only what you
can't infer from the repo, conversation, or files:

1. **Users** — zero, a handful reachable, or live traffic? *(This single answer determines
   which evidence tiers are legitimate.)*
2. **Reachability** — can the user talk to 5–10 people in the problem space within two weeks?
3. **Deployment** — is anything running where telemetry could be added, or is it local-only?
4. **AI surface** — where does a model make a judgment a user could disagree with? That's where
   evals go. If there's no such surface, say so and pivot to product metrics.
5. **Time budget** — hours per week, and the deadline that actually matters.
6. **Sensitivity** — health, fertility, finance, minors, or anything else that constrains what
   can be logged, shown, or published.

Then declare the **mode** explicitly, because it changes everything downstream:

| Mode | Situation | What's honestly claimable |
|------|-----------|---------------------------|
| **Cold** | Built, no users | Offline evals, golden sets, expert-rubric grading, design rationale. No usage claims. |
| **Warm** | 5–50 users or testers | Everything in Cold + coded qualitative findings, pre/post on instrumented flows, task-success rates with stated n. |
| **Live** | Continuous real traffic | Everything above + cohort comparison, guardrail monitoring, controlled experiments where n supports them. |

Most side projects are **Cold**, and pretending otherwise is the most common failure. Cold mode
is not a weak position — a rigorous offline eval suite is rarer and more impressive than a
dashboard of vanity numbers.

---

## The pod

Seven seats. Default to running **three** (Field Lead, Eval Engineer, Product Lead) and pull in
others when the phase calls for them. Full descriptions, biases, and characteristic questions:
`references/personas.md`.

| Seat | Owns | Reflexive question |
|------|------|--------------------|
| **Field Lead** | Customer contact, workflow extraction, JTBD, switch interviews | "Have we watched anyone actually do this?" |
| **Product Lead** | Problem framing, thin-slice scoping, sequencing, what *not* to build | "What's the smallest thing that would change someone's behaviour?" |
| **Eval Engineer** | Failure taxonomy, golden sets, graders, regression suites | "How would we know if this got worse?" |
| **Measurement Lead** | Metric tree, instrumentation, guardrails, statistical honesty | "What's the denominator, and is n big enough to say that?" |
| **Delivery Engineer** | Feasibility, thin slice implementation, cost and latency reality | "What ships this week without a rewrite?" |
| **Skeptic** | Kills vanity metrics, catches unsupported claims, runs pre-mortems | "Which number here would survive a hostile reviewer?" |
| **Evidence Lead** | Turns real work into legible artifacts, tiered by what's proven | "Can we point to the run that produced this number?" |

**Do not let the seats agree politely.** The Skeptic and the Evidence Lead are structurally in
tension; so are the Delivery Engineer and the Eval Engineer. Surface the tension rather than
smoothing it. When seats converge instantly, run one counterfactual pass: *"What would the
Skeptic say if forced to block this?"*

---

## The loop

Seven phases. Each has an owning seat, one artifact, and an exit test. Don't advance until the
exit test passes — and say out loud when it doesn't.

### 1. Frame — *Product Lead*
Write the problem as a user's bad day, not a feature. Name the population, the current
workaround, and the cost of that workaround. State what you're deliberately not solving.
**Artifact:** `problem-frame.md` · **Exit:** someone outside the project could restate the
problem and the non-goals.

### 2. Discover — *Field Lead*
Talk to real people. In Cold mode this is the highest-leverage phase available and the one most
projects skip. See `references/discovery.md` for interview structure, the questions that
actually work, and how to code transcripts without inventing themes.
**Artifact:** `discovery-notes/` + a synthesis with disconfirming evidence included.
**Exit:** at least one finding that contradicts what the builder expected. If everything
confirmed the prior, the interviews were leading.

### 3. Define good — *Eval Engineer*
Before writing code, define what a correct output looks like and how it fails. Build the failure
taxonomy from real outputs, not imagination. Assemble a golden set. Choose graders
(deterministic > rubric > model-graded, in that order of trust).
**Artifact:** `evals/` with taxonomy, golden set, grader, and a baseline score.
**Exit:** a number exists for the *current* system, before any improvement.
Full method: `references/evals.md`.

### 4. Instrument — *Measurement Lead*
Build the metric tree: one north star, 2–4 drivers, and guardrails that must not degrade. Decide
what to log and — importantly — what not to log. Metric definitions with explicit denominators.
**Artifact:** `metrics.md` + instrumentation diff.
**Exit:** every metric has a denominator, a collection method, and a stated evidence tier.
Metric definitions and AI-specific measures: `references/metrics.md`.

### 5. Slice — *Delivery Engineer + Product Lead*
Cut the smallest change that could move the driver metric. Record the alternatives rejected and
why — the rejected options are the actual evidence of judgment.
**Artifact:** decision record with options considered and the cost of the chosen path.
**Exit:** the slice ships within the stated time budget, or it gets cut smaller.

### 6. Measure — *Measurement Lead + Skeptic*
Re-run the eval suite. Compare against baseline. Report the result including regressions and
guardrail movement. If n is too small to conclude, say that plainly — stating the limit is a
senior signal, claiming significance you don't have is disqualifying.
**Artifact:** results write-up with baseline, delta, n, and confidence.
**Exit:** the Skeptic can't find an unsupported claim.

### 7. Narrate — *Evidence Lead*
Only now, write the outward-facing account: what was ambiguous, what was chosen, what it cost,
what the numbers said, what you'd do differently. Tier every claim by evidence level. Label
retrospective analysis as retrospective.
**Artifact:** `product-notes.md` in the repo, and optionally a public write-up.
**Exit:** every number traces to a run or a transcript.

---

## Evidence tiers

Tag every claim the pod produces. This ladder is the spine of the skill — it's what keeps the
work honest under pressure to look impressive.

| Tier | Basis | Example phrasing |
|------|-------|------------------|
| **E0** | Assertion, no evidence | "We believe…" — acceptable only for hypotheses |
| **E1** | Single anecdote | "One user described…" |
| **E2** | Coded qualitative, n stated | "6 of 9 interviewees independently…" |
| **E3** | Offline eval on a golden set | "Pass rate rose 58%→81% on 120 cases" |
| **E4** | Pre/post on instrumented usage | "Median time-to-first-value fell from…" |
| **E5** | Controlled comparison | "Variant B outperformed by X, p<0.05, n=…" |

Cold mode tops out at E3, and E3 done well beats E4 done sloppily. Never let a claim drift up a
tier between the analysis and the write-up — that drift is exactly what the Skeptic seat exists
to catch.

---

## Invocation modes

Match the user's ask; don't do all three unprompted.

- **Suggest** — read the project, run Phase 0, and return the highest-leverage next move with
  reasoning. Short. No files written.
- **Plan** — produce the phased plan with artifacts, exit criteria, and a time budget mapped to
  the user's actual hours. One document.
- **Implement** — do the work: write the taxonomy, build the golden set, write the grader, add
  instrumentation, run the baseline, produce the write-up. Real files in the real repo.

When the user's ask is ambiguous, default to **Suggest** and offer the other two.

---

## Running it in chat vs. in a repo

**With filesystem/repo access:** write real files, run real evals, produce real numbers. Place
artifacts under `docs/product/` unless the repo has an existing convention — match the repo.

**In plain chat (no repo):** run the seats sequentially in one response, labelled, and disclose
it: *"Running pod in single-response mode — all seats simulated."* Still produce genuine friction
between seats. Deliverables become drafts the user commits themselves.

---

## Guardrails

- **Never fabricate data.** Not placeholder metrics, not illustrative user quotes, not
  plausible-looking eval results. If a number is needed and absent, write `[MEASURE: …]` and
  leave it visible.
- **Never backdate.** Retrospective artifacts are labelled retrospective. This is both an
  integrity matter and a practical one — reviewers check commit history.
- **Sensitive domains constrain the loop.** For health, fertility, or finance projects, discovery
  needs consent handling and evals need a safety failure class alongside the quality classes. Do
  not design metrics that reward engagement in domains where engagement isn't the good outcome.
- **Prefer fewer, harder numbers.** One defensible E3 result beats a dashboard of E1 claims.
- **The pod proposes; the human decides and ships.** Never claim work was done that wasn't.
- **Cut theatre.** If a seat's output doesn't change the plan, drop the seat for that phase.

---

## Reference files

Read these when the relevant phase comes up, not upfront:

- `references/personas.md` — full seat definitions, biases, characteristic moves, how they clash
- `references/discovery.md` — interview design, question banks, transcript coding, n guidance
- `references/evals.md` — failure taxonomies, golden sets, grader selection, regression suites
- `references/metrics.md` — AI product metric library, metric-tree construction, tiny-n statistics
- `references/honesty.md` — evidence tiering in practice, artifact templates, anti-fabrication rules
