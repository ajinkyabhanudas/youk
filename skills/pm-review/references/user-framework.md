# User Framework — Impact Assessment for Real Users

Used in the USER phase. Grounds feature decisions in specific, named users rather than
abstract personas. The goal is to ask: "does this specific person's life get meaningfully
better because of this specific feature?"

---

## The Three User Questions

Every feature assessment must answer:
1. **Who** is the primary user — not a category, a specific person/role
2. **What changes** — what can they do that they couldn't before
3. **So what** — why does that matter to their outcome, not just their experience

---

## User Impact Levels

### Level 1 — Outcome Change

The user can accomplish something they previously could not.

Examples:
- "Jajean can now answer donor questions about species trends without needing Pedro's help"
- "Jajean can generate grant reports directly from the database instead of asking for a spreadsheet"

This is the highest-value impact. Features that change outcomes are P1 or P0 candidates.

---

### Level 2 — Experience Change

The user can accomplish the same thing, but faster, with less friction, or with more confidence.

Examples:
- "Jajean gets her answer in 2 seconds from cache instead of 10 seconds from the model"
- "Jajean sees a clear progress indicator instead of a blank screen while waiting"
- "Jajean gets a plain-English error message instead of a Python traceback"

These are important but typically P1 or P2 unless they're currently causing the user to abandon the tool.

---

### Level 3 — Delight / Quality of Life

The user experiences the same outcome with the same friction, but something about the
experience is more pleasant.

Examples:
- "Jajean sees the results in a nicer table format"
- "Jajean can resize the input box"

These are P2 at best unless the current experience is actively harmful to trust.

---

## User Cards (for recurring users)

Define once, reference by name. Update as understanding of the user deepens.

---

### Jajean Rose-Burney

**Role:** Director (non-technical)
**Use case:** Asks natural-language questions about species monitoring data for
donor communications and grant proposals
**Technical level:** Low — not comfortable with SQL, data formats, or error codes
**Frequency of use:** Estimated weekly (1-3 times/week during grant/donor season)
**What she needs to trust the tool:**
  - Answers in plain English (no jargon)
  - Clear indication when the system is working vs. broken
  - Ability to see the underlying data (Results tab) for verification
  - SQL visible for technical review by Pedro
**Pain points:**
  - Blank screen during query (fixed by streaming)
  - Confusing error messages (partially fixed by Guard error handling)
  - Queries that look right but return wrong results (trust issue)
**What makes her successful:**
  - Gets an accurate answer in ≤15 seconds
  - Can share the answer with confidence (she verified it)
  - Doesn't need to ask Pedro to run queries for her

---

### Pedro (Lead Data Scientist)

**Role:** Technical reviewer, not primary user
**Use case:** Reviews canopy outputs for scientific accuracy; validates SQL
**Technical level:** High — expert in the database, species data, SQL
**Frequency of use:** Low — review mode only, not daily
**What he needs:**
  - SQL visible for review
  - Confidence that the SELECT guard and read-only connection are enforced
  - Ability to identify when the model made an incorrect inference
**Pain points:**
  - Model making statistical inferences it's not qualified to make (already out of scope)
  - Coordinate data leaking to model context (already fixed)
**What makes him successful:**
  - SQL is always visible and reviewable
  - Model stays within its lane (query, don't infer trends)

---

### Ajinkya Dessai (Developer / AI PM)

**Role:** Builder, decision-maker, owner of all scoping and design decisions
**Use case:** Developing, testing, iterating on canopy; managing the handover
**Technical level:** High — Python, cloud, data science, MCP, React
**What he needs:**
  - Clear decision documentation (why things were built as they were)
  - Test coverage that catches regressions
  - Context files that make each session efficient
  - Learning layer that builds his knowledge across projects
**Pain points:**
  - NFRs getting decided too late (after code is written)
  - Context being rebuilt from scratch each session
  - Decisions being re-debated because reasoning wasn't documented

---

## User Impact Assessment Template

```
PRIMARY USER: {specific person / role from the user card above, or define a new card}

WHAT CHANGES FOR THEM:
  Before this feature: {what they currently experience / do}
  After this feature:  {what they will experience / do}

IMPACT LEVEL:
  [ ] Outcome change — they can now accomplish X that was impossible before
  [ ] Experience change — they accomplish the same thing better/faster/with more confidence
  [ ] Delight / QoL — same outcome, better experience

FREQUENCY:
  [ ] Every use — they encounter this every time they use the product
  [ ] Regular — they encounter this most sessions
  [ ] Occasional — they encounter this sometimes
  [ ] Rare — they encounter this only in specific circumstances

CRITICALITY:
  [ ] Product fails without this — current experience is broken or misleading
  [ ] Product works better — current experience is suboptimal but functional
  [ ] Nice to have — current experience is acceptable

SECONDARY USERS AFFECTED (if any):
  {other users who benefit or are impacted, with brief description}
```

---

## The "So What" Test

After describing the user impact, always ask "so what?" once:

"Jajean gets a faster response from cache."
So what?
"She's less likely to think the tool is broken and abandon the query."
So what?
"She asks more questions, gets more value, and tells other directors the tool works."

If you can't complete two rounds of "so what" without reaching a business or human
outcome, the feature may be a solution in search of a problem.
