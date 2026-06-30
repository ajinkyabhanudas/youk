# UX Review Checklist

Use during CRITIC REVIEW phase. Work through every category.

---

## State Coverage

- [ ] Idle state designed (empty input, no results yet)
- [ ] Loading state designed (immediate feedback + progress updates)
- [ ] Success state designed (result + supporting data)
- [ ] Empty result state designed (0 rows — distinguished from error)
- [ ] Guard/validation error state designed (what went wrong + bad input shown)
- [ ] System error state designed (DB down, API timeout, etc.)
- [ ] Each state has explicit copy — no placeholder text in the spec

---

## Copy and Language

- [ ] No internal system terms in user-facing copy (no column names, no exception classes)
- [ ] Error messages say what happened AND what to do next
- [ ] Loading messages say what is happening, not just "loading"
- [ ] Empty states explain WHY and suggest a next action
- [ ] Domain vocabulary matches the user's vocabulary (not the DB schema)
- [ ] Tone is calm and helpful — no alarming language for routine errors

---

## Cognitive Load

- [ ] Happy path requires ≤3 interactions from page load
- [ ] User never needs to hold more than 3 things in working memory
- [ ] Most important information is shown first (primary → secondary → tertiary)
- [ ] Unrelated information is visually separated
- [ ] No extraneous UI elements that add load without adding value

---

## Feedback Loops

- [ ] Queries >1s have visual acknowledgement within 100ms of submission
- [ ] Queries >10s show progress updates (what is happening)
- [ ] Final result replaces loading state cleanly (no flash / layout shift)
- [ ] Button state changes during loading (disabled or loading indicator)

---

## Error Recovery

- [ ] Every error state has a clear recovery path (what should the user do?)
- [ ] Guard errors show the rejected content (so user can diagnose)
- [ ] Errors do not expose raw stack traces or exception messages to user
- [ ] User can always return to the idle state without a page reload

---

## Information Hierarchy

- [ ] Primary output (the answer) is the first thing seen on success
- [ ] Technical details (SQL, raw data) are accessible but not primary
- [ ] Row count / result size is visible without opening a separate tab
- [ ] History is accessible without obscuring the current result

---

## Accessibility (Minimum Bar)

- [ ] All interactive elements are keyboard-accessible
- [ ] Loading states communicate to screen readers (aria-live or equivalent)
- [ ] Error messages are associated with their input (aria-describedby or equivalent)
- [ ] Colour is not the sole indicator of state (use icons or text too)
- [ ] Text contrast ratio ≥ 4.5:1 for normal text

---

## Rendering Environment (Non-Negotiable)

- [ ] Supported color modes stated: light-only / dark-only / both / system-default
- [ ] If light-only: enforcement mechanism documented (JS class removal + CSS color-scheme override); decision recorded as an ADR
- [ ] No hardcoded hex color values in component spec unless dark-mode variant is also specified
- [ ] Framework dark-mode behavior confirmed: does the UI framework auto-apply a dark class or theme on OS preference?
- [ ] If "both modes": Playwright dark-mode screenshot test is required before the spec is marked READY TO IMPLEMENT

---

## Consistency

- [ ] Same action always produces the same visual result
- [ ] Button labels are verbs ("Run Query", "Clear", not "Query" or "OK")
- [ ] Destructive actions (clear history) are visually distinguished from primary actions
- [ ] Tab / panel order is consistent with reading direction (left-to-right, top-to-bottom)
