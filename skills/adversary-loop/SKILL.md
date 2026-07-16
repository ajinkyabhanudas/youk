---
name: adversary-loop
description: >
  Context-independent adversary loop for M+ challenge invocations. Spawns a subagent
  with stripped context (direction + constraints + resolved objections only — no proposer
  reasoning) to attack a direction until exhaustion. Loop continues until the adversary
  produces zero new objections across a full round. Breaks the satisfaction-bias root cause
  structurally: the adversary doesn't know what the proposer is satisfied with, so it
  cannot stop early because the proposer feels done. Use for M+ tasks instead of in-session
  challenge. In-session challenge (challenge/SKILL.md) remains the fallback for S/quick.
  Do NOT use for: XS/S tasks, quick/silent mode, tasks where the direction has already
  survived adversary-loop this session.
---

# adversary-loop — Context-Independent Direction Attack

The in-session challenge skill has a structural limitation: the challenger shares context
with the proposer. It sees why the direction was chosen, what pressure led to it, what
the proposer is satisfied with. Satisfaction bias leaks through attention. The adversary
loop breaks this by spawning a subagent with stripped context — the adversary knows the
direction and the constraints, nothing else.

Two loops running simultaneously until both exhaust: proposer revises, adversary attacks.
Neither stops while the other has unresolved objections.

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
ROUND:              [current round number]
MODE:               adversary — attack until you find zero new objections
```

The adversary receives NOTHING ELSE. No conversation history. No reasoning chain.
No context about why the direction was chosen. No indication of what the proposer
is satisfied with. This is the independence guarantee.

---

## Execution Protocol

### Phase 1 — PREPARE

Extract and format the handoff:

```
[ADVERSARY LOOP — Round {N}]
Direction:    {verbatim direction, one paragraph}
Constraints:  {fixed constraints list}
Resolved:     {objections closed in prior rounds, one line each}
```

Verify the handoff contains no proposer reasoning. If any sentence explains WHY the
direction was chosen (rather than WHAT the direction is), remove it. The adversary
must attack the direction, not the reasoning chain behind it.

### Phase 2 — SPAWN ADVERSARY

Call `Agent(description="Adversary round {N} — attack direction until exhaustion",
prompt=<handoff + adversary instructions below>)`.

**Adversary instructions (included in the Agent prompt):**

```
You are an adversary. Your only job is to find objections to the direction below.

Apply the challenge skill's four lenses + seven convergence angles (if the direction
contains a quality word). For each lens:
1. State the strongest case that this lens SHOULD find an objection.
2. Either confirm the objection (specific: names what fails, when, who is affected)
   or argue why the steelman case doesn't hold.

Then run the inter-angle coherence check: do all lenses agree on what problem the
direction is solving? If they diverge, that divergence is an objection.

Rules:
- Do NOT raise objections already in the RESOLVED list.
- An objection is only valid if it is specific — names what exactly would go wrong
  and under what condition. "This might fail" is not an objection.
- CLEAR requires a positive claim: state why this lens does NOT block the direction.
  "Seems fine" is not a positive claim.
- If you find zero new objections across all lenses: emit [ADVERSARY DRY] and stop.
- If you find objections: list them in objection format, emit [ADVERSARY FOUND: N].

Objection format:
  Lens: {name}
  What: {specific failure}
  When: {condition under which it fails}
  Weight: BLOCKING | HIGH | LOW
```

### Phase 3 — PROCESS ADVERSARY OUTPUT

When the subagent returns:

**If [ADVERSARY DRY]:**
- The direction has survived a full adversary round with zero new objections.
- Call `youk-core.mark_challenge_ran(task, angles_checked=[all angles run], mode="full")`.
- On `recorded: true`: verdict confirmed. Emit `[ADVERSARY LOOP PASSED — Round {N}]`.
- Proceed to implementation.

**If [ADVERSARY FOUND: N]:**
- Surface the objections to the proposer (main session).
- For each objection:
  - BLOCKING: direction must be revised or abandoned. Surface immediately, wait for user.
  - HIGH: propose a revision that addresses it. Add to next round's handoff.
  - LOW: note it, carry forward, do not block.
- If any HIGH/BLOCKING survived: revise the direction, add closed objections to RESOLVED,
  increment round number, go to Phase 2.
- If only LOW survived: direction SURVIVES WITH NOTES. Call `mark_challenge_ran`, proceed.

### Phase 4 — EXIT CONDITIONS

**Loop exits when:**
1. Adversary round returns [ADVERSARY DRY] — zero new objections from all angles.
2. All outstanding HIGH objections are resolved and re-confirmed dry by the adversary.

**Emergency brake — 5 rounds:**
If round 5 completes and objections remain unresolved: surface the unresolved tension
explicitly. "Round 5 reached — objection [X] remains unresolved across [N] adversary
rounds. User input needed before proceeding." Do not exit silently. Do not propose
further revisions autonomously.

**Stuck-loop detection:**
If the same objection recurs in consecutive adversary rounds without resolution: it is
a BLOCKING objection regardless of original weight. Surface it. The loop is stuck because
the direction cannot address this objection — that IS the finding.

---

## Tier Routing

| Task size | Mode | Mechanism |
|-----------|------|-----------|
| M/L/XL | full | adversary-loop (this skill) |
| S | quick | in-session challenge (challenge/SKILL.md) |
| XS | silent | in-session challenge, auto-quick |
| plan: | plan | in-session challenge plan coherence |

The tier boundary is M: anything route_task sizes as M or above uses adversary-loop.
Anything below uses the in-session challenge skill.

---

## Quality Bars

- **Handoff must be stripped.** If the adversary receives proposer reasoning, the
  independence guarantee is broken. Re-check before every spawn.
- **Adversary must run all angles.** The same angle-completeness requirement applies:
  `mark_challenge_ran` validates angles. If the adversary ran quick mode, only 4 lenses
  are required. Full mode requires all 11.
- **[ADVERSARY DRY] is the exit signal, not round count.** Five rounds is the emergency
  brake. The loop exits on silence, not on exhaustion of rounds.
- **Stuck = BLOCKING.** A recurring unresolved objection is not a nuisance — it is the
  direction's fundamental flaw. Surface it, don't route around it.
- **Proposer cannot declare dry.** Only the adversary can declare [ADVERSARY DRY]. The
  proposer's satisfaction state is irrelevant to the exit condition.

---

## Example Flow

**Direction:** "Extend mark_challenge_ran to validate angle completeness before recording."

**Round 1 handoff:**
```
DIRECTION:         Extend mark_challenge_ran(task, angles_checked, mode) to validate
                   angles_checked against a mode-keyed required set before recording.
                   Returns blocked: true with missing angles if incomplete.
FIXED_CONSTRAINTS: Must use existing MCP tool pattern. No new tools.
RESOLVED:          (none)
ROUND:             1
```

**Adversary Round 1 returns [ADVERSARY FOUND: 2]:**
- Lens 3 HIGH: assumes Claude will pass honest angle lists. Gameable by passing all
  names without running them.
- Lens 1 HIGH: assumes the failure mode is "angles skipped" — what if the failure is
  "angles run shallowly"? Breadth gate doesn't address depth.

**Proposer revision:**
- Depth failure: acknowledged as separate problem, to be addressed by SKILL.md fixes.
  Breadth gate is correct for breadth failures.
- Gameability: acknowledged as irreducible floor — active deception vs. passive omission
  is a different failure mode class. Gate closes passive omission.

**Round 2 handoff adds to RESOLVED:**
- "Gameability by fake list: acknowledged floor — active deception vs. passive omission"
- "Depth failure: separate problem addressed by SKILL.md fixes"

**Adversary Round 2 returns [ADVERSARY DRY].**

`mark_challenge_ran(task, angles_checked=[...], mode="full")` → `recorded: true`

`[ADVERSARY LOOP PASSED — Round 2]`
