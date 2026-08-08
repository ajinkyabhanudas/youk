---
name: coverage-tree
description: Post-task completeness surface. After an M+ task, render a MECE coverage tree of the concepts the task's domains require, mark what was covered, then (stakes-gated) spawn a STRIPPED adversary subagent to attack the tree for missed concepts. Gaps and contested nodes surface at the top of review — a missed CONCEPT is caught cheaply before anyone descends into a diff. Triggers on: M+ task completion before code-review, "coverage tree", "what did we miss", "completeness check", any review where a concept (not just a bug) could have been skipped. Does NOT trigger on XS/S tasks or pure Q&A. Distinct from code-review (which checks correctness of what was done) — this checks completeness of what was considered.
---

# coverage-tree — completeness before correctness

The point: a diff shows what's wrong; it cannot show what isn't there. The costliest miss is a
CONCEPT never considered (no secrets handling, no idempotency). This surfaces that at the top,
cheaply, so review checks *concepts first* and descends into code only for branches that pass.

The intelligence is the HARNESS (you), never an outbound API call. The MCP module
`coverage_tree.py` does the local compute (templates, MECE check, spawn decision, persistence);
you supply the reasoning content and spawn the adversary subagent.

## Phase 1 — populate (you are the Builder)

1. Identify the in-scope domains for the completed task (subset of: security, correctness, data,
   nfr). Read `TEMPLATES[domain]` from coverage_tree.py for each — those are the required concepts.
2. For each concept, mark Coverage: COVERED / PARTIAL / MISSING / NA, with one-line detail.
   Be honest — marking MISSING is the feature, not a failure. This is the Builder's self-claim.

## Phase 2 — spawn the adversary (STAKES-GATED, spawn-don't-fake)

3. Call `must_spawn_adversary(domains, high_stakes, budget_available)`:
   - `high_stakes` = warrants_forcing(signal) for the task's overall signal.
   - `budget_available` = the session ForcingBudget still has a slot.
   - SAFETY FLOOR: security or data in scope → it returns True unconditionally. Never override.
4. If it returns True: **SPAWN A REAL HARNESS `Agent` SUBAGENT.** Give it ONLY the task
   description + the domain templates + the Builder's node list. Do NOT give it your populate
   reasoning — stripped context is the whole point; an adversary that sees why you were satisfied
   cannot independently catch what you missed. Prompt it: "Attack this coverage tree. What concept
   for these domains is MISSING or wrongly marked COVERED? Return only nodes to add/contest."
   - CONTRACT — spawn-don't-fake: inline self-critique is NOT the adversary. Prompt-level "now
     act as a critic" is not isolation (a single context cannot run two independent layers). If
     you do not spawn a separate subagent, the tree is UNVERIFIED — say so; never claim otherwise.
5. If it returns False: render the tree UNVERIFIED. That is the true state, and it is cheap for
   the human to override ("adversary this"). Do not manufacture a clean result.

### Cognitive forcing (predict-before-reveal) — the germane-load moment

The forcing gate is the ONLY channel that actively builds the human's understanding (everything
else in the rework REDUCES load). It is rationed by the same stakes/budget as the adversary
(ForcingBudget, default 2/session) so it stays rare — Buçinca: forcing works but is disliked, so
a too-frequent gate decays into skimmed ceremony (the original disease reborn).

When `warrants_forcing(signal)` is True AND a budget slot remains (`ForcingBudget.try_spend()`):
before revealing the change's outcome, surface a ONE-LINE predict-before-reveal prompt and WAIT —
e.g. "this changes retry semantics on the payment path — expected effect on idempotency?" Then
reveal. The prediction is what exercises the human's schema; the gate is placed exactly where
over-trust is most expensive (high-blast / irreversible / novel). Never fire it on low-stakes
work — a spent budget or low stakes means no gate, silently.

## Phase 3 — surface (Level-1 review)

6. Render the tree (`CoverageTree.render()`). Gaps and contested nodes are already ordered first
   (cheapest to check, security/data ahead of nfr). The human checks CONCEPTS here — "should this
   task have handled X?" — answerable from the task, without opening a file.
7. The adversary RAISES, it does not RULE. A contested node is a forced human glance, not a
   verdict. The human rules.

## Phase 4 — self-revise (the accumulator)

8. When the human catches a concept BOTH you and the adversary missed, call
   `add_concept_to_template(domain, concept)` — it persists so the class cannot recur. This is
   the only way the template earns completeness over time. Only mechanical/safety nodes are frozen.

## The one honest limit

The spawn itself is behaviorally proven only on a live run — there is no unit test for "the
harness actually spawned a subagent." The spawn DECISION (`must_spawn_adversary`) is tested; the
spawn EXECUTION is a discipline you enforce every time. Skipping the spawn while claiming
verification is the false-green failure this whole surface exists to prevent.
