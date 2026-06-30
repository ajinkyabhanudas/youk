# Cognitive Design Reference

## Working Memory

- Humans hold 4 ± 1 chunks in working memory at once (Miller's Law, updated)
- Each UI element that requires interpretation costs a chunk
- Design implication: never ask the user to track more than 3 active states

## Cognitive Load Types

**Intrinsic** — complexity inherent to the task (can't reduce, only scaffold)
**Extraneous** — complexity added by poor design (always eliminate)
**Germane** — cognitive effort that builds understanding (invest here)

For domain-expert tools: intrinsic load is high (complex data). Ruthlessly
eliminate extraneous load. Don't add explanations the expert already knows.

## Progressive Disclosure

Show only what's needed at each moment. Reveal more on demand.

Levels:
1. Primary: the answer in plain language
2. Secondary: supporting data (table, counts)
3. Tertiary: technical details (SQL, timing, raw columns)

Canopy application: Response tab (primary) → Results tab (secondary) →
SQL tab (tertiary). User gets the answer first; SQL is there if they want it.

## Mental Models

Users approach new tools with a pre-existing mental model from analogous
experiences. Match the interface to the expected model rather than the
internal implementation.

Non-technical conservation director mental model:
- "I ask a question, I get an answer" (like asking a colleague)
- NOT "I submit a query, the model generates SQL, the DB executes it"
- Design implication: hide the pipeline; show only question → answer

## Feedback Loops and Wait Time

- 0–100ms: feels instant, no feedback needed
- 100ms–1s: show a visual change (button state)
- 1–10s: show a spinner and "working" label
- 10s+: show progress — what is happening and why it takes this long

For canopy (10–90s queries):
- Immediate: "Thinking…"
- During loop: "Calling model (attempt 2 of up to 5)…"
- After SQL runs: "Query returned 356 rows — refining response…"
- Never: silent blank screen

## Error Recovery

Users tolerate errors if they understand what happened and have a clear path forward.

Required for every error state:
1. What went wrong (plain language, no error codes)
2. Why it happened (optional, if non-obvious)
3. What the user can do next (always required)

Anti-pattern: "Error: ValueError: Only SELECT queries are permitted"
Good pattern: "I couldn't process that question. The generated SQL wasn't a
valid read-only query. Try rephrasing — for example, 'Which sites have the
most detections?' instead of 'Delete all sites with zero detections.'"

## Chunking and Grouping

Related information should be visually grouped. Unrelated information should
be separated. Use spatial proximity as the primary grouping signal.

Canopy layout: [question input + history] | [answer tabs] — the input/context
group is left; the output group is right. Consistent with reading direction.

## Anchoring

The first thing a user sees anchors their interpretation of everything else.
Lead with the most important information.

For canopy: the Response tab should be the default/first tab. The answer comes
first, SQL comes last. A conservation director cares about "how many birds?"
not "SELECT COUNT(*) FROM...".
