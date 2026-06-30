# Executive Brief Test

## The reader model

The exec brief must work for a **domain expert who is non-technical** — someone who knows the problem space deeply (the users, the goals, the domain vocabulary) but has no knowledge of the implementation stack, architecture, or engineering trade-offs.

This is not "a generic non-technical person." A domain expert has strong opinions about whether the problem is real, whether the solution fits the users' actual behaviour, and whether the trade-off makes sense. They will push back on vague answers.

## The test

Read the brief aloud as if explaining in a 30-second conversation.

The reader must be able to answer all three without asking a follow-up:

1. **What was built?** — in domain language, not engineering language
2. **Who does it help, and how?** — the actual user and the actual change to their workflow
3. **What did we decide not to do, and why?** — the trade-off that shaped the scope

## Pass / fail signals

| Signal | Verdict |
|--------|---------|
| "Got it — so users can now do X without needing Y" | PASS |
| "What does [technical term] mean?" | FAIL — jargon leaked in |
| "Why didn't you just [obvious alternative]?" | FAIL — trade-off not stated |
| "I'm not sure who this is for" | FAIL — user not named |
| "That sounds like a lot" | FAIL — brief is too long or scope too wide |

## Common failure modes

- **Engineering framing:** describe the user-visible outcome, not the implementation change
- **Missing the user:** name the actual person or role whose workflow changes — not "users"
- **Unstated trade-off:** if scope was cut, say what was cut and why — not just what was included
- **Scope creep in the brief:** if the brief covers more than one decision or feature, the implementation scope was too large or the brief needs to split alongside it

## When this test applies

Any time a skill produces a `[BRIEF]` block. The domain-expert reader test is the quality bar for that block — not for the technical implementation, which is reviewed separately.
