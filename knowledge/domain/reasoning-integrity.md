## Constraint-Aware Pre-Mortem Loop
*Added: 2026-07-13*
*Source: youk — challenge skill design session*

**What it is:** A direction gate that fires before work starts. Extracts fixed constraints
from context first, then runs independent challenge lenses against the interpretation.
Iterates until a challenge round produces no new objections. Hard exit: 5 rounds max (emergency brake only — exit condition is zero new objections from all angles).

**Analogy:** AWS CAB (Change Advisory Board) change window review — constraints listed
first (frozen components), review attacks only what's in scope, approval requires no
new objections in the final round.

**Where the analogy breaks:** CAB reviews a fully-specified change. The pre-mortem fires
before the change is specified — it challenges the interpretation of the request, not a
plan. CAB has multiple independent human reviewers; the pre-mortem uses one reasoner
approximating independence across lenses. CAB can cycle indefinitely; the 2-round cap
is a deliberate anti-paralysis design choice with no CAB equivalent.

**Project example:** `skills/challenge/SKILL.md` — 4 lenses (framing, scope, assumptions,
opportunity cost), constraint capture in Context Capture block, `[CHALLENGE PASSED]` token
as exit signal, `DIRECTION WRONG` as BLOCKING hard stop.

**When to reach for this:** Any M+ task where the interpretation hasn't been confirmed
by the user this session. Especially: open-ended requests ("what next?", "improve this"),
requests that imply large scope ("build a two-level reasoning system"), and requests that
repeat a question already answered this session (signals the prior answer wasn't right).

## Dual-Process Simulation Failure
*Added: 2026-07-13*
*Source: youk — stress-test of two-level reasoning system*

**What it is:** A single LLM cannot run two genuinely independent reasoning layers in
one context window. Instruction-following for context suppression ("ignore the framing")
doesn't suppress the framing — attention leaks it into both layers. The independence
is a naming convention, not an architectural reality.

**Analogy:** AWS Lambda-in-Lambda — calling a Lambda from inside the same invocation
looks like spawning an independent process, but both functions share the same account,
role, and VPC. More isolated than in-process, but not truly independent.

**Where the analogy breaks:** Lambda B genuinely doesn't see Lambda A's local variables —
there is a real execution boundary. For LLMs, the "boundary" is only a prompt instruction.
Layer 2 sees the entire conversation including Layer 1's output. The Lambda analogy
*undersells* how total the context bleed is. There is no execution boundary at all —
it's one forward pass through one set of weights.

**Project example:** Stress-test of the two-level reasoning system (this session) found
CRITICAL: layers are correlated, not independent. Reconciliation gate compares two outputs
that were never independent — systematically underdetects divergence.

**Correct solution:** Constraint-aware single pre-mortem pass (the challenge skill) achieves
80% of the stated goal at zero extra cost. True independence requires a subagent with
stripped context — achievable but costs tokens per invocation.

**When to reach for this:** Any design that claims "two independent agents" but uses
a single LLM session. Ask: is there a real execution boundary, or just a prompt boundary?
If prompt only, the independence doesn't hold under adversarial conditions.

## Run-to-Dry Exit Condition
*Added: 2026-07-15*
*Source: youk — challenge/stress-test skill hardening session*

**What it is:** A reasoning loop (challenge, stress-test, convergence) must iterate until
the last full round produces zero new objections from ALL angles simultaneously — not
until a round count is reached. Round count is an emergency brake (5 rounds), not an exit
condition. On cap hit, surface the unresolved tension explicitly; never exit silently.

**Analogy:** Gradient descent convergence — stop when loss delta < epsilon, not after N steps.
Emergency brake = max_iterations to prevent infinite loops on flat loss surfaces.

**Where the analogy breaks:** Gradient descent converges monotonically (loss only decreases).
Challenge loops can oscillate — a round produces zero objections, then a new angle introduced
in the next round reopens the field. "Dry" requires ALL angles to produce zero new objections
simultaneously, not just the most recently run angle. Local convergence ≠ global convergence.

**Project example:** `skills/challenge/SKILL.md` — Phase 2 hardened from 2-round hard cap
to "5 rounds emergency brake; exit on zero new objections from all angles." Same pattern
applied to `skills/stress-test/SKILL.md` Phase 4b.

**When to reach for this:** Before surfacing any verdict, finding, or direction. Self-check:
(1) did the last round produce zero new objections? (2) is there any angle not yet run?
If either is false — keep going internally.

## Challenge-Before-Surfacing Gate
*Added: 2026-07-15*
*Source: youk — global behavioral enforcement session*

**What it is:** Any output that proposes a direction must be challenged silently before
reaching the user. This is a structural gate, not a guideline. BLOCKING → drop and surface
the objection. HIGH → revise before surfacing. LOW → surface with caveat. PASSED → as-is.
The user catching a skipped challenge is a system failure, not a feature.

**Analogy:** AWS CodePipeline approval gates — a pipeline stage cannot advance until the
preceding gate token is issued. The deploy never sees unreviewed artifacts.

**Where the analogy breaks:** CodePipeline gates are manual human approvals with audit
trails. This gate is self-applied by the reasoner in silent mode — no external reviewer
and no audit trail unless the loop surfaces a BLOCKING objection. The gate is only as
strong as the reasoner's willingness to apply it to its own outputs.

**Project example:** `~/.claude/CLAUDE.md` — "Reasoning loop discipline" section; 
`knowledge/projects/youk/contracts.md` — "never surface a finding... that has not survived
challenge" contract.

**When to reach for this:** Every response that contains a recommendation, plan, finding,
or direction. The self-check question: "Have I run challenge on this?" If not — run it now,
silently, before emitting the response.

---

## Adversary Failure Patterns
*Populated by RCA when user pushback reveals an objection the adversary missed.*
*Format: "When [condition], adversary tends to accept [answer type] without catching [failure class]."*

<!-- RCA entries appended here by learn skill -->

---

## Adversary Shortcut Patterns
*Populated by DEPTH REWARD RCA after JUSTIFIED OVERRUN events.*
*Format: "When [condition], go deeper on [angle] in round 1-2 instead of waiting for rounds 7+."*

<!-- Shortcut entries appended here by learn skill -->
