---
skill: verify
version: "1.0"
description: Test that what was built actually works — golden path, edge cases, error states, dark mode.
phases: [UNDERSTAND, PLAN, EXECUTE, REPORT]
fast_path: |
  For XS/S browser changes: screenshot golden path + dark mode screenshot. Pass if both render correctly. No Playwright setup needed for pure CSS/text changes.
integrates_after: [dev-loop]
integrates_before: [humanize]
references:
  - playwright-protocol.md
---

# verify

Verify is the gate between "implemented" and "done." It catches what the diff can't show: a loading state that never ends, an error message that says `undefined`, a component that looks correct in light mode and broken in dark.

Never call something VERIFIED without evidence. Never call it BLOCKED without a specific reason.

---

## Phase 1: UNDERSTAND

Answer these before writing any tests:

1. **What changed?** List the files modified and the user-visible behaviour that changed.
2. **App surface type:** server-rendered HTML / client-side SPA / CLI / API / library / TUI
3. **Golden path:** One sentence — what must work for this to be shippable?
4. **Top 3 failure modes:** What are the three most likely ways this breaks in production?
   - Think: empty state, error state, boundary conditions (0 items, 1 item, max items)
   - Think: concurrent requests, slow network, missing permissions

Output: `[UNDERSTAND]` block with the four answers.

---

## Phase 2: PLAN

Produce a test list before executing anything.

| # | Test | Method | Severity |
|---|------|--------|----------|
| 1 | Golden path | browser/curl/CLI | must-pass |
| 2 | {failure mode 1} | ... | must-pass |
| 3 | {failure mode 2} | ... | must-pass |
| 4 | Dark mode (if UI change) | browser screenshot | must-pass |
| 5 | Error state (if applicable) | browser/curl | must-pass |
| 6+ | Edge cases | ... | nice-to-have |

**Mandatory tests — never skip:**
- If any UI changed: dark mode screenshot
- If any data fetch changed: empty result state
- If any mutation changed: error state (what happens when it fails?)
- If any auth changed: unauthenticated + insufficient-permission paths

**Performance regression check:** If this change touches request handling, rendering, or data loading — note the baseline (if known) and flag if the new behaviour is measurably slower.

Output: `[PLAN]` block with the test table.

---

## Phase 3: EXECUTE

Run every must-pass test. For each test:

**Browser / UI:** Follow `playwright-protocol.md`. Capture a screenshot as evidence. For dark mode, toggle the OS or browser colour scheme and capture a second screenshot — do not skip this.

**Server / API:** Use `curl`, the SDK, or the framework's test client. Log the response body and status code.

**CLI:** Run the command, capture stdout/stderr, exit code.

**Evidence format per test:**
```
Test N: {name}
Result: PASS / FAIL
Evidence: {screenshot path OR response body OR command output}
Notes: {anything unexpected}
```

**Hard rules:**
- PASS requires evidence — a screenshot, a response, a log line. "It seemed to work" is not evidence.
- FAIL is acceptable if documented. An undocumented FAIL is a blocked ship.
- If a must-pass test fails: stop, do not run nice-to-have tests, return NEEDS FIX.
- Performance: if response time >2× the known baseline, flag it even if the test passes.

Output: `[EXECUTE]` block with per-test evidence.

---

## Phase 4: REPORT

```
[VERIFY REPORT]

Verdict: VERIFIED / NEEDS FIX / BLOCKED

Tests run: {N} must-pass, {M} nice-to-have
Passed: {N}
Failed: {N}

| # | Test | Result | Evidence |
|---|------|--------|---------|
| 1 | Golden path | PASS | screenshot: ... |
| 2 | Dark mode | PASS | screenshot: ... |
| 3 | Error state | FAIL | response: 500 {"error": "unhandled"} |

Regressions: {none / list anything that worked before and now doesn't}

Next: {COMMITTED (if all must-pass) / FIX {test N} then re-verify / BLOCKED because {reason}}
```

**Verdict rules:**
- `VERIFIED`: all must-pass tests pass with evidence
- `NEEDS FIX`: one or more must-pass tests fail — do not proceed to humanize/commit
- `BLOCKED`: cannot run tests (environment down, missing dependency, permissions) — surface the specific blocker, not a generic "can't test"

---

## Quality bars

1. Every error state in the implementation must have a corresponding test.
2. Dark mode is not optional for any UI change — it is a must-pass test.
3. Loading states must be verified, not assumed. If the UI shows a spinner, prove it resolves.
4. No green-without-evidence. A test that "passed" with no captured output did not pass.
5. Performance regression check is required when touching request paths, queries, or rendering.
6. FAIL is better than untested. Document failures — they become the bug list.
