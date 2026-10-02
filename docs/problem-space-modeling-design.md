# Problem-space modeling + bias-resistant edge-case elicitation

> Originally written to `state/problem-space-modeling/design.md` -- `state/*` is
> gitignored, so it never reached any checkout but the one it was written on,
> including CI and every dispatched agent's own worktree. Moved here (tracked)
> once that gap was caught during Phase 3 (CIR-164): that phase's own dispatch
> ticket told the implementing agent to read this file first, and it genuinely
> could not, on any checkout but the original author's. Phases 1-3 (CIR-162/163/
> 164) were still built correctly because each ticket also inlined the design
> directly, but a future phase or reader following only "read the design doc"
> would have hit a 404. `state/problem-space-modeling/progress.json` stays
> where it is -- real-time working state, not a durable design reference,
> same precedent as the verification pipeline's own progress.json.

## Problem statement (verbatim user goal, from earlier this session)
"Be able to understand the developer's problem space so well that it can define
edge cases, understand the boundaries of the problem space and develop complete
solutions, and make sure that it continuously grows and learns so it keeps
getting better -- all of this while making it agent agnostic."

## What already exists (don't rebuild)
- skill-forge: reactive, builds a skill after a gap is hit during a task.
- pattern-library (verification_contract.py): reactive, logs a missed sub-claim
  after a checker run finds it.
- challenge/stress-test: adversarial, but scoped to one task's direction, not
  standing domain knowledge.
- nfr_check: structured questions, generic across all projects, not
  domain-specific.
- claim verification pipeline (this session): makes youk's *self-reports*
  trustworthy. Does not make youk understand the project's domain better.

## The real gap
Nothing persists an explicit, structured model of a *specific project's*
domain (entities, invariants, boundaries, non-goals) that gets consulted
BEFORE work starts. Everything that exists today is reactive (after a miss)
or generic (same for every project).

## Research (bounded, cited, done before design -- not LLM intuition alone)
1. DDD / bounded contexts, 2026 sources: "AI-generated code may violate DDD
   invariants because LLMs lack persistent understanding of domain
   constraints." Bounded context is becoming the real unit of agent context
   scoping in practice, not just a human modeling tool.
2. Requirements engineering + LLMs, 2025-2026 sources: LLMs can genuinely
   surface unknown requirements, but flood engineers with false-positive
   candidates unless filtered. Elicitation quality depends heavily on the
   quality of domain context fed in, not just prompting technique.
3. LLM self-correction bias, 2026 sources ("Self-Correction Illusion" and
   related): self-correction is weak when the generator and the checker share
   training data/context -- shared blind spots. Correction rates jump
   23-93 percentage points when an identical claim is reframed as coming from
   an external source rather than the model's own prior output. Self-
   consistency ensembles converge on the FREQUENT answer, not the correct one.

## Design, directly shaped by the research (not decorated with it)

### 1. Domain Brief (persistent, structured, per project)
A file, not a prose doc: `state/domain-brief.json` (or project-scoped
equivalent). Fields: bounded_contexts (name, ubiquitous_language terms,
owned invariants), explicit_non_goals, known_boundaries. Populated and
refined ONLY from real decisions/corrections already on record (DECISIONS.md,
memory, task_contract history) -- never speculatively invented. Same
never-backfill discipline as events.jsonl: starts sparse, grows from real
signal only.

### 2. Edge-case elicitation pass (filtered, not a firehose)
Before M+ work: cross-reference the task against the Domain Brief's
invariants using a fixed taxonomy (boundary values, concurrency, partial
failure, authz, idempotency, locale/time, empty/null -- standard RE
taxonomy, not invented here). Every candidate gets scored against the
Domain Brief's actual invariants (is this invariant real and on record, or
speculative?) before surfacing -- directly answers finding #2 (don't flood).

### 3. Bias-resistant review -- the part the research made non-negotiable
The elicitation pass's own output does NOT get self-graded by the same
session/context that generated it (finding #3: shared blind spots).
Two concrete mechanisms, either used depending on stakes:
  a. Externalize the framing: route candidate gaps through the same
     abstract+dual-pass-research+diff machinery already built (Phase 2 of
     the verification pipeline) -- check against real external precedent,
     not self-report.
  b. Independent context: dispatch the adversarial pass to a fresh
     Explore/general-purpose subagent given ONLY the Domain Brief + task,
     with no access to the implementation session's accumulated
     self-justification -- breaks the shared-context blind spot directly.

### 4. Continuous refinement, agent-agnostic
Domain Brief is a flat file on disk, read by any host (Claude Code, Codex)
the same way verification claims already are. Growth happens only from real
signal (a real correction, a real decision, a real incident) -- same
discipline as every other real/never-fabricated mechanism built this
session.

## Explicit non-goals (Lens 2, scope discipline)
- Not a new ML model, not embeddings, not a vector DB -- same proportionality
  discipline as Phase 3 (RAG retrieval). Structured JSON + the taxonomy is
  enough at real project scale.
- Not replacing skill-forge/pattern-library/challenge -- this feeds them
  better context, doesn't duplicate their function.
- Phase 1 (below) is schema + minimal real population only. Elicitation
  and bias-resistant review are later phases, not built blind before the
  schema is proven against real data.

## Phased build (resumable, like the verification pipeline)
- Phase 1: Domain Brief schema + a real extractor that populates it from
  this project's own real DECISIONS.md/memory (not synthetic data).
- Phase 2: Edge-case elicitation pass, filtered, wired into nfr_check.
- Phase 3: Bias-resistant review (mechanism 3a and/or 3b above).
- Phase 4: End-to-end test against a real task, independently verified.
- Phase 5: see "Real gap found after Phase 4" below -- added after the
  founder caught that Phase 0's own research was a one-time pass, not a
  standing mechanism.

## Real gap found after Phase 4 (Phase 5)

Phase 0 ran a real, bounded research pass (DDD, requirements-engineering,
LLM self-correction bias) before designing Phases 1-3. That research
informed the design once. Nothing re-runs it. The assumptions it produced
("simple keyword matching is proportionate," "third-person reframing
reduces bias here," "this specific edge-case taxonomy is the right one")
have sat unchallenged since the day they were written, and nobody is
re-checking them against new evidence as the mechanism is actually used.

The founder's correction, specifically: naming "software engineering,
cognitive science, UX" as the relevant domains was ITSELF the same mistake
at one level up -- a fixed list, picked once, for this one initiative.
The real requirement is a mechanism that infers which knowledge domains
are relevant PER TASK, because a billing feature needs financial-
regulation + security research, a chat UI needs UX + cognitive-science
research, a data pipeline needs statistics research, and none of that is
knowable as a fixed list in advance.

### Why this cannot be a keyword-matching function

Domain inference from a free-text task description is a judgment call.
`if "payment" in task: return ["finance"]` is not an honest mechanism --
it degenerates immediately into either a huge brittle keyword table or
constant false negatives on tasks phrased differently. This has to be a
required REASONING step the session performs, the same way `challenge`
and `nfr_check` already require structured reasoning rather than pure
code -- not a new parallel system, an extension of the existing gate
chain.

### The real mechanism (Phase 5, to be built)

1. Before any M+ task is built, a step requires an explicit answer to:
   "which 2-4 knowledge domains, beyond generic software engineering, are
   actually relevant to this task's assumptions, and why?" -- answered
   fresh per task, never cached or reused from a prior task's answer.
2. The named domains scope a real, bounded research pass, reusing
   `youk-research`'s existing WebSearch -> extract -> propose loop (same
   mechanical pattern the `cto` skill's own ADR-C022 periodic-research
   section already uses) -- not new search infra.
3. Findings feed into `challenge`'s existing Lens 3 (hidden assumptions)
   so the task's assumptions get attacked with real outside evidence, not
   just internal reasoning.
4. Runs PER REAL TASK, every M+ build, not once at the start of an
   initiative and then forgotten -- which is exactly what happened to
   Phase 0's own research in this initiative.

### What was actually built (Phase 5, CIR-165)

Matches the plan above, with one clarification worth stating explicitly:
steps 1 and 3 are skill-content changes (prompt-driven reasoning), not
Python -- there is no function that can judge "which domains matter" or
"does this finding contradict that assumption," so that reasoning stays
in-session, same as `challenge` Lens 3 and `nfr_check` PROBE already work.
Step 2 (the wiring) is the one part that is real, callable, testable code,
because its job is mechanical: turn a list of domain strings into the
correct `/research [topic]` invocation. It does not call WebSearch itself.

- `skills/nfr-check/SKILL.md` Phase 1 CLASSIFY: added a "Domain scope"
  sub-step, right after the existing functional-edge-case sub-step,
  requiring 2-4 domains named fresh per task with justification, then
  calling the wiring function below.
- `servers/core/src/health.py`: added `build_domain_research_invocation(domains,
  task)` -- zero-API, same contract shape as the existing
  `run_health_check_with_skill_signals(research_mode=True)` /
  `research_topics` pattern. Takes the named domains + task text, returns
  the `/research {topics}` invocation string plus a note for the session to
  act on. Raises on 0 or >4 domains (judgment call, not a dumping ground).
  Exposed as the `youk-core.build_domain_research_invocation` MCP tool in
  `servers/core/src/server.py`. Real unit tests in
  `tests/test_health.py::TestBuildDomainResearchInvocation`.
- `skills/challenge/SKILL.md` Lens 3: added an "External-evidence
  assumption" bullet -- if domain research already ran for this task, Lens
  3 cites it before asserting an objection from internal reasoning alone;
  a no-op when no domain research ran (S-tasks, or nfr_check hasn't fired).

Worked example (one real task, traced through the mechanism):

> Task: "Add a billing feature that stores card tokens for repeat
> customers." (M-sized -- nfr_check fires.)
>
> **Domain scope:** `financial regulation` -- storing payment card data
> triggers PCI-DSS scope regardless of how the feature is implemented;
> `security` -- token storage is a credential-storage problem, not a
> generic data-storage one.
>
> **Wiring call:** `build_domain_research_invocation(["financial
> regulation", "security"], task)` returns `invocation: "/research
> financial regulation, security"`.
>
> **Research finding (illustrative):** running that invocation surfaces
> that PCI-DSS SAQ scope can often be reduced by never touching raw card
> data at all -- tokenizing via the payment processor's own vault instead
> of this service's database.
>
> **Lens 3 connection:** the plan's hidden assumption was "we store the
> token in our own `payment_tokens` table." The domain research gives Lens
> 3 a cited objection instead of a generic one: "domain research on
> financial regulation found that processor-side tokenization avoids
> SAQ-D scope entirely -- this plan's own-database storage assumes the
> harder compliance path without having compared it to the easier one."

Real progress tracked in `state/problem-space-modeling/progress.json`.
