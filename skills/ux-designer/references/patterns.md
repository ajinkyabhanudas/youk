# UI Patterns for Data-Heavy and Domain-Expert Tools

## Query → Result Pattern

Used by: database explorers, analytics dashboards, NL search tools.

Structure:
- Input area (question / filter) — top or left
- Status / progress — inline, replaces input area or appears below it
- Output area — prominent, tabbed if multiple views needed

Key decisions:
- Single-column (stacked) vs. two-column (side-by-side): use two-column when
  input and output are used simultaneously; single-column for mobile or simple flows
- Tab order: most important output first (answer before data before SQL)

## Progressive Result Display

For queries that take >5 seconds:
1. Show immediate acknowledgement ("Thinking…")
2. Show pipeline progress ("Executing query… 356 rows returned")
3. Show final result

Never: blank white screen during computation.

## Error State Patterns

**Guard/validation error** (bad input or bad generated output):
- Show what was rejected (the bad SQL, the invalid input)
- Explain why in plain language
- Suggest a corrective action

**Timeout / slow response**:
- Show elapsed time
- Offer a "try a simpler question" hint
- Don't leave the user guessing if the app is frozen

**Empty result** (valid query, 0 rows):
- Distinguish clearly from an error
- "No detections found for that filter" ≠ "Error"
- Suggest broadening the query

## History and Context Sidebar

For tools where users repeat similar queries:
- Show last N queries in reverse chronological order
- Clicking a history item re-populates the input (not re-runs it)
- "Clear history" is destructive — place it below the list, small, secondary style
- Never auto-run a history item; always require explicit submission

## Data Table Display

For result sets:
- Show row count prominently ("356 rows returned")
- Cap display rows (200 is a reasonable UI limit) and note truncation
- Column headers from DB: convert snake_case → "Snake Case" for display if non-technical user
- Wrap text in cells for long string columns
- Empty cells: show "—" not blank

## SQL Display

For transparency/audit use cases:
- Show in a code block with syntax highlighting
- Read-only — users inspect, don't edit
- Collapsible or in a secondary tab (not primary view)
- Include a copy button if the framework supports it

## Timing / Performance Indicators

Show timing info when:
- Queries regularly take >5 seconds (user needs to understand why)
- There's a multi-step pipeline (LLM + DB) with distinct phases

Format: concise status line, not a full performance dashboard.
Example: "⏱ 8.3s total · LLM 7.9s (2 calls) · DB 0.4s"

Don't show timing for sub-second queries — it adds noise.

## Confidence and Uncertainty

For AI-generated answers:
- If the model expresses uncertainty, surface it (don't hide it behind a confident summary)
- Show the SQL so users can verify the answer themselves
- Guardrail language ("This data cannot reliably indicate population trends") should
  appear in the response, not be filtered out

## Copy and Tone for Non-Technical Users

- Use the user's domain vocabulary, not the system's vocabulary
- "Recording sites" not "site_id values"
- "Validated detections" not "rows where validation_status = 'validated_true'"
- Questions the user might ask: "Which birds were seen at X?" not "GROUP BY species_id"
- Error messages: plain English, actionable, never expose internal exception names
