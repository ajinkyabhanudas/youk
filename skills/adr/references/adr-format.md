# ADR Format — Canonical DECISIONS.md Entry

Used in the DOCUMENT phase. Every DECISIONS.md entry must follow this format exactly.
This consistency is what makes the document scannable and queryable across sessions.

---

## Full Entry Format

```markdown
## D{N} — {Title: what was decided, in noun form}

**Status:** ACTIVE | DEFERRED | REVERSED (superseded by D{M})
**Date:** {YYYY-MM-DD}
**Trigger:** {what prompted this decision — feature, incident, NFR output, refactor}
**Reversibility:** Easy | Medium | Hard | Very Hard
**Reversal conditions:** {specific trigger for when to revisit — not "if it's wrong"}

### Context

{2-4 sentences: why did this decision need to be made now? What was the state of the
system, the constraint, or the requirement that forced a choice? Avoid restating what
the decision is — that's in the title.}

### Options Considered

**Option A — {name}**
{1-2 sentences describing what this option is and how it addresses the need.}

**Option B — {name}**
{1-2 sentences.}

**Option C — {name}** *(if applicable)*
{1-2 sentences.}

### Decision

We chose **{Option X}**.

Reason: {specific, testable reason — not a truism. "It's simpler" is not specific.
"It requires zero new infrastructure, which is critical for Docker-only deployment" is specific.}

### Why Not

**Not Option A:** {specific reason — one sentence minimum. "It was worse" is not acceptable.}
**Not Option B:** {specific reason.}
**Not Option C:** {specific reason, if applicable.}

### Consequences

**Enables:** {what this decision makes possible}
**Forecloses:** {what this decision rules out — be honest about the trade-off}
**Creates:** {new decisions that must now be made as a result of this one}
**Risk:** {what could go wrong, and how we'd know}

### Links

- Depends on: D{X} *(must remain ACTIVE for this decision to hold)*
- Conflicts with: *(none | D{Y} — explain how resolved)*
- Supersedes: *(none | D{Z})*
- Related NFRs: *(none | list)*
```

---

## Abbreviated Entry Format (for `quick` mode)

Used when the decision is low-reversal-cost and the full debate is not warranted.

```markdown
## D{N} — {Title}

**Status:** ACTIVE
**Date:** {YYYY-MM-DD}
**Reversibility:** Easy | Medium

### Decision

{One sentence: what was decided and the primary reason.}

### Why Not

{One sentence per rejected option: what was considered and the specific reason it was not chosen.}

### Reversal Conditions

{One sentence: when to revisit.}
```

---

## Reversal Entry Format

When an existing decision is reversed, update the original entry AND add a new entry.

**Update the original entry:**
```markdown
**Status:** REVERSED (superseded by D{M}, {YYYY-MM-DD})
```

**New entry:**
```markdown
## D{M} — {Title: what the new decision is}

**Status:** ACTIVE
**Date:** {YYYY-MM-DD}
**Reverses:** D{N} — {original title}

### Why Reversed

{What changed since D{N} was made? What condition was met that D{N} said would trigger reversal?
If no reversal condition was met, explain why the original reasoning no longer holds.}

### New Decision

{Follow full or abbreviated format.}
```

---

## Status Reference

| Status | Meaning |
|---|---|
| ACTIVE | This decision is in effect. Code reflects it. |
| DEFERRED | Decision was considered but deferred. Trigger for revisit is documented. |
| REVERSED | Decision was active but has been superseded. Old entry kept for history. |
| PROPOSED | Decision is under debate. Not yet binding. |

---

## Numbering Rules

- IDs are assigned sequentially: D1, D2, D3...
- IDs are never reused, even if an entry is reversed.
- A reversed entry retains its ID and is updated with REVERSED status.
- New entries replacing reversed ones get new IDs.

---

## DECISIONS.md File Structure

The full DECISIONS.md file should be organized:

```markdown
# Architecture Decisions

*This document records significant technical decisions made during development.
Entries are never deleted — reversed decisions are marked REVERSED and kept for history.*

---

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| D1 | ... | ACTIVE | YYYY-MM-DD |
| D2 | ... | REVERSED | YYYY-MM-DD |

---

## D1 — {Title}
...

## D2 — {Title}
...
```

---

## Quality Checks Before Filing

Before finalizing a DECISIONS.md entry, verify:

- [ ] Title is a noun phrase describing what was decided, not a question
- [ ] "Why Not" section has at least one non-trivial sentence per rejected option
- [ ] Reversal conditions are specific — not "if the decision turns out to be wrong"
- [ ] Consequences section is honest — "Forecloses" must name at least one trade-off
- [ ] Date and status are set
- [ ] Any DEFERRED entries from a prior session that this supersedes are updated

---

## Anti-Patterns

**Too vague:**
```
We chose PostgreSQL because it's a good database.
Why not SQLite: it's not as powerful.
```

**Correct:**
```
We chose PostgreSQL because VAJocotoco already runs on a PostgreSQL instance, and
re-using it avoids introducing a second database technology.
Why not SQLite: SQLite is single-writer, which would block concurrent Gradio requests
if two users query simultaneously. Also, the production PostgreSQL instance is already
managed by Jocotoco's infrastructure — no new ops burden.
```

**No reversal conditions:**
```
Reversal conditions: if this turns out to be a bad decision.
```

**Correct:**
```
Reversal conditions: if concurrent user load exceeds 10 simultaneous queries and
connection pool exhaustion is observed in production logs.
```
