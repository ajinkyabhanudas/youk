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

Real progress tracked in `state/problem-space-modeling/progress.json`.
