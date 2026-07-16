---
name: adversary-loop
description: >
  Context-independent adversary loop for M+ challenge invocations. Spawns a subagent
  with stripped context (direction + constraints + resolved objections + learned patterns
  only — no proposer reasoning) to attack a direction until exhaustion. Loop continues
  until the adversary produces zero new objections across a full round. Breaks the
  satisfaction-bias root cause structurally: the adversary doesn't know what the proposer
  is satisfied with, so it cannot stop early because the proposer feels done. Use for M+
  tasks instead of in-session challenge. In-session challenge (challenge/SKILL.md) remains
  the fallback for S/quick. Do NOT use for: XS/S tasks, quick/silent mode, tasks where
  the direction has already survived adversary-loop this session.
---

# adversary-loop — Context-Independent Direction Attack

The in-session challenge skill has a structural limitation: the challenger shares context
with the proposer. It sees why the direction was chosen, what pressure led to it, what
the proposer is satisfied with. Satisfaction bias leaks through attention. The adversary
loop breaks this by spawning a subagent with stripped context — the adversary knows the
direction, the constraints, and learned failure patterns. Nothing else.

Two loops running until both exhaust: proposer revises, adversary attacks. Neither stops
while the other has unresolved objections. Inter-round reasoning is internal — only the
final verdict surfaces.

---

## When to Use

- M+ tasks at route_task time (replaces in-session challenge for M+)
- Explicit "adversary loop", "red team this direction", "attack until dry"
- After in-session challenge passes but user suspects shallow reasoning
- Any time SESSION_DEPTH > 10 and the direction hasn't been adversarially tested

Do NOT use:
- XS/S tasks (overhead exceeds value — use in-session challenge)
- quick/silent/plan modes (use challenge skill directly)
- When the direction has already survived adversary-loop this session

---

## Handoff Format (What the Adversary Receives)

The adversary subagent receives ONLY:
```
DIRECTION:          [the direction being challenged — verbatim, one paragraph max]
FIXED_CONSTRAINTS:  [what cannot change — so adversary doesn't attack walls]
RESOLVED:           [objections already raised and resolved in prior rounds — adversary
                    must not re-raise these; it must find NEW objections only]
PATTERNS:
  failure_patterns:   [shallowness signatures the adversary has been known to miss —
                      sourced from "Adversary Failure Patterns" in reasoning-integrity.md.
                      Adversary must not accept answers matching these patterns.]
  shortcut_patterns:  [angle-depth shortcuts from JUSTIFIED OVERRUN RCA — "when
                      [condition], go deep on [angle] in round 1-2." Adversary uses
                      these to front-load depth instead of discovering it in round 7+.]
ROUND:              [current round number]
MODE:               adversary — attack until you find zero new objections
```

The adversary receives NOTHING ELSE. No conversation history. No reasoning chain.
No context about why the direction was chosen. No indication of what the proposer
is satisfied with. This is the independence guarantee.

**Populating PATTERNS:** Before spawning, proposer reads
`knowledge/domain/reasoning-integrity.md` and extracts entries under
"Adversary Failure Patterns" and "Adversary Shortcut Patterns". On first invocation
both sub-fields are empty — they grow as RCA fires across sessions.

---

## Execution Protocol

### Phase 1 — PREPARE

Extract and format the handoff. Verify it contains no proposer reasoning — if any
sentence explains WHY the direction was chosen (rather than WHAT the direction is),
remove it.

```
[ADVERSARY LOOP — Round {N}]
Direction:    {verbatim direction, one paragraph}
Constraints:  {fixed constraints list}
Resolved:     {objections closed in prior rounds, one line each}
Patterns:     {failure_patterns and shortcut_patterns from reasoning-integrity.md}
```

### Phase 2 — SPAWN ADVERSARY

Call `Agent(description="Adversary round {N} — attack direction until exhaustion",
prompt=<handoff + adversary instructions below>)`.

**Adversary instructions (included in the Agent prompt):**

```
You are an adversary. Your only job is to find objections to the direction below.

Before attacking: read PATTERNS carefully. Do not accept any answer that matches
a known failure_pattern. Apply shortcut_patterns to front-load depth on flagged
angles in round 1 rather than discovering the need in round 7+.

Apply the challenge skill's four lenses + seven convergence angles (if direction
contains a quality word). For each lens:
1. State the strongest case that this lens SHOULD find an objection (steelman).
2. Either confirm the objection (specific: names what fails, when, who is affected)
   or argue why the steelman case doesn't hold.
3. CLEAR requires a positive claim: state why this lens does NOT block the direction.
   "Seems fine" is not a positive claim. Deferral ("team can decide") is not a claim.

Then run the inter-angle coherence check: do all lenses agree on what problem the
direction is solving? If they diverge, that divergence is an objection.

Rules:
- Do NOT raise objections already in the RESOLVED list.
- An objection is only valid if specific — names what fails, under what condition.
- If you find zero new objections across all lenses: emit [ADVERSARY DRY] and stop.
- If you find objections: list them in objection format, emit [ADVERSARY FOUND: N].

Objection format:
  Lens: {name}
  What: {specific failure}
  When: {condition under which it fails}
  Weight: BLOCKING | HIGH | LOW
```

### Phase 3 — PROCESS ADVERSARY OUTPUT

**If [ADVERSARY DRY]:** Direction survived. Call
`youk-core.mark_challenge_ran(task, angles_checked=[all angles run], mode="full")`.
On `recorded: true`: proceed to verdict emission (see Round Discipline below).

**If [ADVERSARY FOUND: N]:**
- BLOCKING: surface immediately, wait for user input before revision.
- HIGH: propose revision, add to next round's RESOLVED when closed.
- LOW: note it, carry forward, do not block.
- Revise direction, increment round, go to Phase 2.
- If only LOW survived: direction SURVIVES WITH NOTES. Call `mark_challenge_ran`, proceed.

### Phase 4 — RCA (fires when user pushes further after a passed verdict)

**Trigger condition:** User pushes further (asks "anything more?", "is this right?",
"keep going") after adversary-loop has passed.

**Step 1 — Re-run adversary:** Spawn one more adversary round with same handoff.

**If re-run returns [ADVERSARY DRY]:**
- Prior verdict was correct. User was exploring, not catching a failure.
- Emit: `[VERDICT CONFIRMED — adversary dry on re-run]`. No RCA fires.

**If re-run returns [ADVERSARY FOUND]:** RCA fires.
1. Identify the objection found that prior rounds missed.
2. Ask: "What property of the prior answer made this objection acceptable to the
   adversary?" — not which angle was missing (gate handles that), but what made
   the shallow/deferred/wrong-level answer pass.
3. Generalize to a reusable **failure pattern**:
   `"When [condition], adversary tends to accept [answer type] without catching [failure class]."`
4. Call `route_to_skill("learn", rca_pattern)` — encodes pattern into
   `reasoning-integrity.md` under "Adversary Failure Patterns".
5. Add to `failure_patterns` in next handoff — it is now a known risk.

---

## Round Discipline and Incentive System

**Exit condition:** `[ADVERSARY DRY]` — zero new objections from all angles. Always.
Round count is never the exit condition.

**Round cap:** 10 rounds (emergency brake only).

**Efficiency scoring (emitted in final verdict block — not per-round):**

| Rounds | Score | Action |
|--------|-------|--------|
| 1–3 | EFFICIENT | Silent — direction resolved cleanly |
| 4–6 | MODERATE | Silent — expected for complex directions |
| 7–9 | COSTLY | Surface in verdict: "Resolved in {N} rounds — direction may have been under-specified at start" |
| 10 (cap hit) | BLOCKED | Surface unresolved tension, require user input. Never exit silently. |

**Penalty signal:** Each round beyond 3 adds one INEFFICIENCY mark to the final verdict.
INEFFICIENCY marks indicate under-specified direction, proposer shallowness, or
non-converging adversary. They do not block the verdict or trigger RCA automatically.

**Justified overrun (> 10 rounds):**
If round 10 is hit and the unresolved tension is genuinely novel or complex, surface:
`"Round 10 reached. Unresolved: {tension}. Continue? (default: yes if BLOCKING, no if HIGH/LOW)"`

If user approves: continue. Emit `JUSTIFIED OVERRUN` in the final verdict with rounds
taken, what made the problem hard, what was resolved.

**DEPTH REWARD (significant — not a mark):**
A JUSTIFIED OVERRUN that resolves a BLOCKING tension earns a DEPTH REWARD. This is
logged as a top-tier `prevented_cost_score` entry in session_end — the highest-value
event the system can record. The loop ran harder than the standard expected, found
something real that would have shipped broken, and stopped it.

DEPTH REWARD also triggers **immediate RCA** (does not wait for user pushback):
"This direction required {N} rounds. What property of the direction or prior adversary
rounds made the path to depth this long?" The answer is a **shortcut pattern** —
forward-looking, not backward-looking:
`"When [condition], go deeper on [angle] in round 1-2 instead of waiting for rounds 7+."`

Shortcut patterns are written to `reasoning-integrity.md` under "Adversary Shortcut
Patterns" and added to `shortcut_patterns` in the next handoff. Over time, JUSTIFIED
OVERRUN events make the adversary reach the same depth faster — the reward incentivises
the hard run AND compresses future hard runs.

**Verdict format:**
```
[ADVERSARY LOOP PASSED — Round {N} | {EFFICIENT | MODERATE | COSTLY | JUSTIFIED OVERRUN} | {DEPTH REWARD?}]
```

---

## Silence Discipline

Inter-round reasoning is internal. Adversary attacks, proposer revises — these are
not surfaced unless:
- A BLOCKING objection is found (always surfaces immediately)
- Round 7+ is reached (COSTLY signal surfaces in verdict)
- Round 10 cap is hit (surfaces for user input)
- User explicitly asks to see rounds

The user sees only the final verdict line. Internal rounds are the mechanism, not the output.

---

## Tier Routing

| Task size | Mode | Mechanism |
|-----------|------|-----------|
| M/L/XL | full | adversary-loop (this skill) |
| S | quick | in-session challenge (challenge/SKILL.md) |
| XS | silent | in-session challenge, auto-quick |
| plan: | plan | in-session challenge plan coherence |

---

## Quality Bars

- **Handoff must be stripped.** No proposer reasoning. Re-check before every spawn.
- **PATTERNS must be populated.** Read reasoning-integrity.md before spawning. Empty
  PATTERNS on first session is expected; non-empty PATTERNS that aren't loaded is a miss.
- **Adversary must run all angles.** `mark_challenge_ran` validates. Full mode: 11 angles.
- **[ADVERSARY DRY] is the exit signal, not round count.** 10 rounds is the emergency brake.
- **Stuck = BLOCKING.** Recurring unresolved objection is the direction's fundamental flaw.
- **Proposer cannot declare dry.** Only the adversary declares [ADVERSARY DRY].
- **DEPTH REWARD is significant.** Log it to prevented_cost_score. Do not reduce it to a
  comment or annotation — it is a session-level achievement that compounds org_score.

---

## Example Flow

**Direction:** "Extend mark_challenge_ran to validate angle completeness before recording."

**Round 1 handoff (PATTERNS empty — first session):**
```
DIRECTION: Extend mark_challenge_ran(task, angles_checked, mode) to validate
           angles_checked against a mode-keyed required set before recording.
CONSTRAINTS: Must use existing MCP tool pattern. No new tools.
RESOLVED: (none)
PATTERNS: failure_patterns: [] | shortcut_patterns: []
ROUND: 1
```

**Adversary Round 1 → [ADVERSARY FOUND: 2]:**
- Lens 3 HIGH: gameable by passing all angle names without running them
- Lens 1 HIGH: assumes failure is "angles skipped" — depth failure is separate

**Proposer resolves both, adds to RESOLVED. Round 2.**

**Adversary Round 2 → [ADVERSARY DRY].**

`mark_challenge_ran(...)` → `recorded: true`

`[ADVERSARY LOOP PASSED — Round 2 | EFFICIENT]`
