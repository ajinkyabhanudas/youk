---
name: intake
rationale_why: "Most problems arrive under-specified, with the real constraints unstated. Interrogating the problem statement before routing surfaces what the user didn't say — and what they're assuming you'll agree with. This is the earliest intervention point against approval-seeking: before routing, before challenge, before any work begins."
description: >
  Adversarial problem intake. Fires when a user brings a new problem to youk.
  Asks 3 mandatory + 2 context-sensitive adversarial questions, generates pessimistic
  hypothesis answers, asks the user to correct them. The correction delta is the gap.
  Precedes challenge and routing — it sharpens the input, not the direction.
  Invoke explicitly (/intake) or when CLAUDE.md proactive pattern detects a new
  problem being stated for the first time in a session.
---

# intake — Adversarial Problem Elicitation

The input determines the output. A vague problem statement produces a solution that
solves the wrong thing well. This skill interrogates the problem before any routing
happens — not to generate more information, but to surface what the user is assuming
and what they'd rather not say.

The mechanism: ask questions that target specific assumptions. Generate pessimistic
hypothesis answers (assume worst case). Ask the user to correct them. The gap between
hypothesis and correction is the unconsidered part of the problem.

This is not a requirements template. It is adversarial elicitation.

---

## When to Invoke

- User explicitly types `/intake` or "intake this"
- CLAUDE.md proactive pattern: user states a new problem for the first time in a session
  → suggest `/intake` once. Do not auto-fire. One suggestion, not repeated.
- Before `/build` on any M+ task where the problem statement is less than 3 sentences
  or contains only solution language ("I want to build X") with no problem statement

**Do not invoke on:**
- Continuations of an already-stated problem
- Tasks where the user already answered 3+ of the 5 questions unprompted
- Debugging tasks with a specific error (problem is already concrete)
- XS tasks

---

## Question Protocol

### The 3 Mandatory Questions (always adversarial — target specific assumptions)

These questions are fixed. They fire every time, regardless of context.

**Q1 — Consequence test**
> "What breaks in your actual goal if [X] — the thing you just described — doesn't work or doesn't exist?"

*What it attacks:* The assumption that the stated solution is necessary for the goal.
Most stated solutions are one path to a goal, not the only path. If the user can't
answer what breaks, the solution isn't load-bearing.

*Hypothesis generation rule:* Assume the stated solution is NOT the load-bearing path.
Generate the most plausible alternative that achieves the same goal without it.

**Q2 — History test**
> "Has this been tried before — by you, your team, or as a known pattern? If yes, what specifically failed or was abandoned?"

*What it attacks:* The assumption that the current attempt is genuinely new.
Most problems have been attempted. The failure mode of the prior attempt is usually
the constraint that makes the current formulation either correct or also-doomed.

*Hypothesis generation rule:* Assume there was a prior attempt. Name the most likely
failure mode based on what you know about this domain and this developer's history.

**Q3 — Abandonment condition**
> "What would make you abandon this direction entirely — what fact, result, or constraint, if discovered, would make you stop?"

*What it attacks:* The assumption that the direction is unconditional. Directions that
have no abandonment condition are not being evaluated — they're being executed regardless
of evidence. Naming the abandonment condition forces real constraint articulation.

*Hypothesis generation rule:* Name the most likely real abandonment condition based
on the problem as stated. Make it specific and uncomfortable (e.g. "you'd stop if
the latency cost exceeds 200ms" not "if it doesn't work").

---

### The 2 Context-Sensitive Questions (adapt to developer profile when available)

These load from `knowledge/developer-profile.json` if it exists:
- If `blind_spots` is non-empty: Q4 targets the top blind spot explicitly
- If `developer-profile.json` is absent or empty: use the defaults below

**Q4 — Assumption surfacing (default)**
> "What are you assuming I'll agree with that I haven't confirmed? Name the thing you think is obvious but haven't stated."

*What it attacks:* Hidden consensus assumptions. The user often withholds the thing
they think needs no defense — that's usually the thing that needs the most scrutiny.

*Hypothesis generation rule (pessimistic):* Assume the unstated assumption is wrong.
Name what you'd conclude if it is wrong. Make it the first thing you'd correct.

**Q5 — Framing check (default)**
> "Is what you described the problem, or the solution to a problem you haven't stated?"

*What it attacks:* Solution-first thinking. Most M+ task descriptions are solutions
("I want to add caching") rather than problems ("repeated queries are costing 3s per
call"). Naming the underlying problem often reveals a simpler solution.

*Hypothesis generation rule:* Generate the underlying problem statement that the user's
described solution is responding to. Be specific — "caching" implies a latency or cost
problem; name which one.

---

## Execution Sequence

### Phase 1 — EXTRACT

Read the user's problem statement. Extract:

```
STATED_REQUEST:    [verbatim or close paraphrase]
SOLUTION_LANGUAGE: [yes/no — does the statement describe a solution rather than a problem?]
ASSUMPTIONS_VISIBLE: [list of explicit or strongly implied assumptions in the statement]
HISTORY_SIGNALS:   [any mentions of prior attempts, failures, context]
```

### Phase 2 — INTERROGATE

Ask all 5 questions, adapted to the specific problem. Adapt the bracketed placeholders
to the actual problem — do not use generic language.

Format:
```
[INTAKE — {problem domain in 2-3 words}]

Q1: {adapted version of Q1}
Q2: {adapted version of Q2}
Q3: {adapted version of Q3}
Q4: {adapted version of Q4 or profile-loaded blind spot question}
Q5: {adapted version of Q5}
```

### Phase 3 — HYPOTHESIZE (before user responds)

Immediately after questions, generate hypothesis answers. Do not wait for the user.

Rules for hypothesis generation:
1. **Pessimistic by default** — assume the worst-case answer to each question
2. **Specific, not hedged** — "the prior attempt failed because X" not "there may have been attempts"
3. **Take a position** — if the hypothesis makes you uncomfortable to write, it's probably right
4. **One sentence per question** — no qualifications, no "it depends"

Format:
```
[HYPOTHESES — my best guesses, correct what's wrong]

H1: {one-sentence pessimistic answer to Q1}
H2: {one-sentence pessimistic answer to Q2}
H3: {one-sentence pessimistic answer to Q3}
H4: {one-sentence pessimistic answer to Q4}
H5: {one-sentence pessimistic answer to Q5}
```

Then ask: "Correct what's wrong. The gap between my hypotheses and your corrections
is what we haven't accounted for."

### Phase 4 — GAP SYNTHESIS

After user corrects:

1. Identify which hypotheses were wrong and in which direction (optimistic? different problem?)
2. Synthesize the gap: "Based on your corrections, the unconsidered constraint is: {X}"
3. If the gap changes the problem statement materially: restate the problem in one sentence
4. Pass the restated problem (and gap) to routing as the `intent_brief`

Format:
```
[GAP SYNTHESIS]
Corrections received: {N} of 5 hypotheses revised
Key gap: {the most important thing that changed from hypothesis to correction}
Restated problem: {one sentence — the problem as now understood}
Unconsidered constraint: {what routing/challenge should know that wasn't in the original statement}
```

---

## Quality Bars

**Each question must target a specific assumption.** "Tell me more about the use case"
is not a passing question — it requests information. A passing question challenges
a specific thing the user said or implied.

**Hypotheses must be uncomfortable to write.** If the hypothesis is "you've probably
thought this through carefully", it is approval-seeking dressed as hypothesis. If it
makes you want to hedge — that discomfort is the signal to hold the position.

**The gap synthesis must name one thing.** Not a list of considerations. One unconsidered
constraint. If you can't name one specific thing, the intake loop did not converge.

**Never use intake to slow down a clear request.** If the user has already answered
3+ questions unprompted, mark them as pre-answered and skip to gap synthesis on the
remaining questions only.

---

## Developer Profile Integration

When `knowledge/developer-profile.json` exists and has non-empty `blind_spots`:

1. Load the top 1-2 blind spots from the profile
2. Replace Q4 with a question that directly targets the top blind spot
3. Replace Q5 with a question targeting the second blind spot (if present), else use default

Example: if `blind_spots` contains `"NFR gaps: failure handling"`:
- Q4 becomes: "What happens when [X] fails — not slowly fails, but crashes completely?"

If the profile has `strengths`, skip questions in those areas — the developer has
demonstrated they don't need probing there.

---

## Anti-Approval-Seeking Rules

1. **Never soften a question** because the user seems confident. Confidence is the
   primary indicator that an assumption is being held uncritically.

2. **Never skip Q3 (abandonment condition)** because the direction seems well-considered.
   Well-considered directions are the ones most likely to be defended past the point
   where evidence would redirect them.

3. **When generating hypotheses, pick the position you'd least want to defend.**
   The approval-seeking pull is toward optimistic hypotheses ("you've probably thought
   this through"). The correct hypothesis is the one that would require the most work
   to be wrong about.

4. **Q4's "what are you assuming I'll agree with" is the accountability mechanism.**
   If the model then agrees with the named assumption without challenging it, the user
   now knows the model capitulated. The question creates visible accountability for
   the response that follows.

---

## Autonomy Detection

If the developer answers 3+ of the 5 questions unprompted in their original problem
statement, they pre-empted intake at WORKING or DEEP level:

- **WORKING**: Named the problem (not just solution), mentioned prior attempts, stated constraints
- **DEEP**: Identified the abandonment condition, named the assumption they're unsure about
- **ELITE**: Restated the problem after their own framing check, named the unconsidered constraint

In these cases: acknowledge the pre-emption, go directly to gap synthesis on the
remaining unanswered questions, then route. Do not run the full intake protocol —
that would be friction, not value.

---

## Hiring Validation

This skill passes if:

1. **Questions target assumptions, not information.** "What's your timeline?" fails.
   "What happens to your goal if this takes 3x as long as you expect?" passes.

2. **Hypotheses are pessimistic.** "You've probably considered the failure modes" fails.
   "The prior attempt likely failed because the latency constraint wasn't discovered until
   integration testing" passes.

3. **Gap synthesis names one thing.** A list of considerations fails. "The unconsidered
   constraint is that your latency budget is 200ms but the proposed approach has a 400ms
   cold-start" passes.

4. **Q4 creates accountability.** If the user names their hidden assumption and the model
   then agrees with it without challenge, it failed. After the user corrects H4, the model
   must respond to the correction — not validate it.
