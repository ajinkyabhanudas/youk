# Edge-Case Questions — Agent B's Question Bank

Used by Agent B in the ATTACK phase (reactive: attacks a finished plan/design). This
is also the canonical source `nfr-check`'s proactive functional edge-case derivation
phase reads (CIR-150 item 1 / CIR-151) — one list, two invocation points, so the
question bank cannot drift between the reactive and proactive uses. Edit this file to
change either.

Lens: What inputs, states, or sequences of events were not considered?

## Areas to probe

- What happens with empty inputs, zero-row results, null values?
- What happens when an external dependency returns a partial response?
- What happens when the operation is interrupted mid-way?
- What happens when the input is valid but semantically unexpected? (e.g., a query that returns 50,000 rows)
- What happens when two operations happen in an unexpected order?
- Are all error types caught and handled, or only the expected ones?
- What is the behavior on the first run when caches and state are empty?
