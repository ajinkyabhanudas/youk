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

## Precondition Verification Before Implementation
*Added: 2026-07-19*
*Source: youk — cross-project pattern observed during delivery sessions*

**What it is:** Before implementing a fix for a documented gap (a plan item, a
DECISIONS.md entry, a LIMITATIONS.md line), run the actual failure case live
first. Written claims about system behavior decay as the system underneath them
changes — the documented gap may not reproduce, and the empirical check redirects
the actual work toward a real, previously-uncovered gap instead of a stale one.

**Analogy:** ICE/MoSCoW prioritization — never commit resources to an
unvalidated assumption; check the premise before scoring the work.

**Where the analogy breaks:** ICE assumes the feature/problem is real and
asks "how urgent, how confident." This pattern asks a prior question ICE has
no slot for: "does the reported problem still exist at all?" A written claim
(a backlog item, a decision record) decays as the system underneath it
changes — the claim being false isn't a scoring input, it's a reason to
redirect the whole task.

**Project example:** youk challenge gate — `check_challenge_gate` documented
as relying on `session-open.json` for slug correlation. Before writing a
workaround, verified empirically: the gate returned `blocked=true` after
`mark_challenge_ran` returned `recorded=true`. Root cause was a missing file,
not a logic bug. The live check redirected the fix from a workaround to a
proper fallback in `session_slug.py`.

**When to reach for this:** Any time a task is framed as "fix documented gap
X" — run X's actual failure case live before writing the fix, not after.
The tell that this pattern applies: a task's premise rests on a *written*
claim about system behavior (a doc, a backlog item, a prior session's
finding) rather than something just observed live in the current session.

---

## Breadth Verified ≠ Concurrency-of-Trigger Verified
*Added: 2026-07-20*
*Source: canopy — fuzzy-match multi-column typo design review miss*

**What it is:** A design/stress-test pass validated "does this generalize
across N possible cases" (a per-column fuzzy-match registry, tested against
species names and site names independently) and correctly converged with zero
new objections. It never separately asked "what happens when more than one of
those N cases is simultaneously true in a single input" — a genuinely
different question that the breadth check does nothing to answer. The bug
(first-match-wins across two typo'd columns in one query) shipped past a
stress-test pass that was run correctly, on the wrong axis.

**Analogy:** Constraint verification (existing pattern in this file) — never
commit resources to an unvalidated premise; check the premise before scoring
the work.

**Where the analogy breaks:** Constraint verification is a one-time gate at
task start, checking whether the premise itself is real. This gap is
different: the premise WAS real, the design DID correctly generalize to N
columns, and the stress-test loop DID run to "zero new objections from all
angles" — and it still missed the bug, because "concurrency-of-trigger" was
never in the set of angles being run. Youk's own Run-to-Dry Exit Condition
entry says a loop is only dry when zero new objections survive from ALL
angles — this is a concrete instance where the angle set itself had a gap,
so "dry" was reached on an incomplete search space without anyone noticing.

**Project example:** `find_candidates()` in canopy was stress-tested for
"does this work for any registered column" and passed. It was never asked
"does this work when two registered columns are simultaneously typo'd in one
query" until a human asked that exact question after the feature shipped.
Fixed in code (loop collects all matches, not just the first) and fixed in
process (added "First-Match-Wins on Multi-Trigger Input" as a named vector
in `skills/stress-test/references/attack-vectors.md`, Agent B section) —
the second fix is the one that prevents this from being a one-off catch.

**When to reach for this:** Before declaring any stress-test or challenge
loop "dry," ask explicitly, as its own question separate from breadth:
"if this handles case A and case B independently, have I tested what happens
when A and B are both true in the same single call?" This applies to any
design with a registry, dispatch table, or loop over independent trigger
conditions — not just canopy's fuzzy-match feature.

---

## Registry Iteration Fixed ≠ Registry Membership Verified
*Added: 2026-07-20*
*Source: canopy — fuzzy-match column registry, second miss same session*

**What it is:** A second, distinct miss on the exact same feature within the
same session as "Breadth Verified ≠ Concurrency-of-Trigger Verified" above —
worth recording separately because it is genuinely a different failure, not a
recurrence of the first. After fixing `find_candidates()` to correctly check
every column already in `FUZZY_COLUMNS` (the first miss), the registry itself
— just 2 entries, `species.scientific_name` and `sites.name` — was never
re-validated against the actual domain it claims to cover. The live database
schema (`schema.py`'s `SCHEMA_CONTEXT`, read multiple times over the session
for unrelated reasons) plainly listed a third free-text column,
`detections.management_unit`, with 54 real distinct values and an existing
near-duplicate already in the data (`"Wamani"` vs `"Wamaní"`). It was missed
until the user asked directly: "are there no more fuzzy-type columns?"

**Analogy:** First-Match-Wins (this file, above) fixed a broken `for` loop —
a control-flow bug. This is a data-completeness bug: the loop is now
perfectly correct, and still misses real cases, because the thing it's
looping *over* was never checked against the domain it claims to represent.
Closer to an unstated assumption ("this allowlist is complete") than an
execution bug — confirmed by stress-testing the fix itself: the correct
detection method is diffing a static registry against a static domain
listing, not tracing code execution, which is why this landed under Agent C
(Hidden Assumptions) in `attack-vectors.md`, not Agent B (Edge Cases) where
First-Match-Wins lives.

**Where the analogy breaks:** Agent B vectors are caught by constructing
inputs and watching behavior. This vector is caught by a different method
entirely — reading two static artifacts (the registry's source file, the
domain's full listing) side by side and checking set membership. No input
construction, no execution trace, catches this. A stress-test pass that only
runs Agent B-style input simulation will never surface this class of miss no
matter how many rounds it runs — the angle itself requires the auditor to sit
down and read the schema/spec/ruleset in full, independent of any test case.

**Project example:** `FUZZY_COLUMNS` in `src/canopy/query/fuzzy_match.py`
registered 2 columns at initial design time. `schema.py`'s full table
listing — which includes `detections.management_unit varchar — conservation
/ territorial management unit name` — was read multiple times afterward
(code review, doc updates) without anyone re-running the one-sentence
inclusion test ("any free-text column a user might search by name") against
it. Fixed in process: added "Registry Completeness (Unvalidated Membership
Assumption)" as a named vector under Agent C in `attack-vectors.md`, Data
Assumptions section — the concrete instruction is to state the registry's
inclusion criteria in one sentence and apply it mechanically against an
independently-read full domain listing, not against test inputs.

**When to reach for this:** Any time a registry, allowlist, or dispatch table
is fixed for HOW it's iterated — ask the separate question of whether its
MEMBERSHIP was ever re-checked against the full domain, especially if the
domain's source (a schema file, an API spec, a ruleset) has been read for any
other reason since the registry was last populated. "I fixed the loop" and "I
verified the list is complete" are two different claims; shipping the first
does not imply the second.

---
