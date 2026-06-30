# Spec Quality Bar — The "I'd Hire You" Standard

Used in REVIEW mode and ACCEPTANCE CRITERIA phase. This is the bar a senior director
would apply. Not a checklist for ceremony — a lens for catching what makes specs fail.

---

## The Three Ways Specs Fail

### 1. Ambiguous Requirements

Signs:
- "The system should support X" — "support" is undefined
- "Handle errors gracefully" — what does graceful mean specifically?
- "Fast response times" — what is fast?
- "User-friendly interface" — this is preference, not a requirement

Fix: Every requirement uses "must" or "does not". Every constraint is a number.

---

### 2. Missing Scope Boundaries

Signs:
- No "out of scope" section
- "Out of scope" section has items without reasons
- Requirements that imply an adjacent feature that wasn't discussed

Fix: For every functional requirement, ask "what would someone reasonably expect to
come with this that we're not doing?" Document each one.

---

### 3. Untestable Acceptance Criteria

Signs:
- "Users find it easy to use" — not testable
- "The feature works correctly" — circular
- "Performance is acceptable" — no number
- Happy path only, no edge cases

Fix: Each AC follows Given/When/Then. Numbers replace adjectives. At least one AC
tests what happens when something goes wrong.

---

## Spec Review Checklist

Run this when using `review` mode:

**Problem:**
- [ ] Written as one sentence
- [ ] Names a specific user (not "users")
- [ ] Names a specific constraint (not "it's hard")
- [ ] Names a consequence (not just a description)

**Users:**
- [ ] Primary user is a specific person or precisely defined role
- [ ] "Out of scope" users are named
- [ ] Secondary users don't accidentally become primary users in the requirements

**Scope:**
- [ ] Every "out of scope" item has a reason
- [ ] Nothing in scope is implied but unstated
- [ ] Scope matches the problem — not larger, not smaller

**Requirements:**
- [ ] All use "must" or "does not" — no "should" or "could"
- [ ] All are verifiable — a person can check each one against the implementation
- [ ] Count is ≤10 — if more, split the spec
- [ ] No requirement duplicates another

**Success Metrics:**
- [ ] Primary metric is quantifiable or has a named proxy
- [ ] A counter-metric exists to guard against regressions
- [ ] Measurement method is defined — someone knows how to get the number

**Acceptance Criteria:**
- [ ] All follow Given/When/Then
- [ ] At least one edge case is covered
- [ ] "Definition of done" is stated

**Open Questions:**
- [ ] Count is ≤3
- [ ] Every question has a default answer
- [ ] Every question has an owner and a deadline

**Exec Brief:**
- [ ] ≤5 sentences
- [ ] No technical jargon a non-technical reader wouldn't know
- [ ] Names the trade-off or constraint honestly

---

## Hire vs. No-Hire Signals

**Hire signals (a senior director sees these and trusts the work):**
- Requirements use precise language with no wiggle room
- Scope section has items you wouldn't have thought to exclude — they anticipated scope creep
- Success metrics have a counter-metric (they thought about regressions)
- Acceptance criteria include what happens when it fails, not just when it succeeds
- Open questions are numbered, owned, and have defaults — work can proceed without answers

**No-hire signals (a senior director flags these):**
- Any requirement using "should", "could", "might", or "allow"
- "Out of scope" section is missing or has unexplained items
- Acceptance criteria written as "the feature works as expected"
- Success metric is "user satisfaction" with no measurement method
- Open questions list is empty when there are clearly unresolved ambiguities

---

## The Handover Test

If this spec were handed to a new team tomorrow with no verbal briefing, could they:
1. Build it? (Requirements test)
2. Know what they're not building? (Scope test)
3. Know when it's done? (Acceptance criteria test)
4. Know if it worked after a month? (Success metrics test)

If all four are yes, the spec passes the handover test.
