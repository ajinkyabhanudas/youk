# Error UX Design — Knowledge File

*Domain: Product / UX / System Design*
*CTO relevance: non-technical users need actionable feedback; generic errors are a product failure, not just a dev oversight*

---

## Error States Are First-Class UX

*Added: 2026-06-30*
*Source: canopy — error message differentiation*

**What it is:** Every failure mode a user can encounter deserves the same design attention as the happy path — a message that names what happened and what to do next.

**The failure pattern:** A single `except Exception → "Something went wrong"` handler is the default for most implementations. It passes all tests (the exception is caught), but it tells the user nothing. For non-technical users, a generic error is a dead end.

**Analogy:** An AWS CloudWatch alarm that fires "something is wrong with the system" instead of "p99 latency on /api/detections exceeded 2s". The signal exists; the actionability is zero.

**Where the analogy breaks:** In monitoring, you have time to investigate. In a real-time UI, the user is sitting there. They can't run `kubectl logs` — they need the diagnosis handed to them.

**The design question to ask for every failure mode:**
1. What context is already available? (exception fields, input text, error type)
2. What does the user need to do next?
3. Does the message answer both?

**Canopy implementation:**
- `SQLGuardError.operation` — uppercased first SQL token — turns "wasn't able to run safely" into "DELETE is not permitted — this tool is read-only"
- `psycopg2.errors.QueryCanceled` → "ran for too long — try a smaller date range"
- `RuntimeError("Query loop exceeded maximum iterations")` → "too many steps — try breaking into smaller questions"
- `psycopg2.OperationalError` → "couldn't reach the database — try again"

**When to apply:** Any time a user-facing tool can fail for multiple distinct reasons. Map failure modes before writing the success path. For each: what's the cause, what can the user do, and does the current message tell them?

---

## Unit Tests Do Not Verify UX

*Added: 2026-06-30*
*Source: canopy — Playwright E2E infrastructure added after unit coverage was at 100%*

**What it is:** Unit tests for a UI handler verify that the handler function returns the right values. They do not verify that those values are rendered correctly in the browser, that the right component is active, or that the message is visible to the user.

**The gap:** In canopy, all error path unit tests passed throughout the project. The UX problem — generic, unhelpful messages — was only caught when a human asked "what does Jajean actually see?" A 100% unit-test pass rate on a UI module is not evidence that the UI works for users.

**Analogy:** An ML model that has 95% accuracy on the training set but wasn't evaluated on the deployment distribution. The tests pass; the system fails where it matters.

**The two-layer test requirement for user-facing tools:**

| Layer | What it verifies | Tool |
|---|---|---|
| Unit | Handler function returns the right values | pytest |
| E2E | Browser renders the right content to the user | Playwright |

Neither replaces the other. Unit tests are fast and run on every commit. E2E tests catch rendering and routing issues unit tests can't see.

**Canopy implementation:**
- Unit: `assert "DELETE is not permitted" in response` — checks the tuple value
- E2E: `expect(page.get_by_text("DELETE is not permitted")).to_be_visible()` — checks the browser DOM

**Smart mock pattern for E2E without live dependencies:**
Route by keyword prefix in the question text. `e2e-delete` → guard error, `e2e-timeout` → timeout, `e2e-overflow` → loop exhaustion. One mocked server, one session-scoped fixture, no credentials needed.

```python
def _smart_mock(question, status_cb=None):
    q = question.lower()
    if "e2e-delete" in q:
        raise SQLGuardError(..., sql="DELETE FROM ...")
    if "e2e-timeout" in q:
        raise _QueryCanceled()
    ...
    return _SUCCESS_RESULT
```

**When to apply:** Any system where the output is rendered in a browser and the intended audience is non-technical. Add E2E tests for at least: the happy path, the primary error paths, and any message that is specifically intended to be actionable.

---

## "Limitation" Framing Deserves Scrutiny

*Added: 2026-06-30*
*Source: canopy — history isolation, shared cache, VPN/firewall notes*

**What it is:** Before documenting something as a limitation, verify it genuinely can't be addressed with available tools, and that it's actually a problem in the real deployment context.

**Three patterns where the label was wrong:**

**Pattern 1: Solvable with available tools**
"No per-user history isolation" → labelled limitation for weeks. Solved in one session with `gr.BrowserState` (browser localStorage). The tool existed; the question was never asked.

**Pattern 2: Described as a problem when it's correct behaviour**
"Shared result cache" → listed as a limitation. For a read-only deterministic tool, all users asking the same question should get the same answer. Caching is correct; it was mislabelled as a problem.

**Pattern 3: Current-limitation framing for future-deployment guidance**
VPN/firewall notes → described as a current blocker. These are escalation guidance for when the tool moves beyond internal network use. The correct framing: "if you need to go further, here's what to do."

**The test before writing a limitation:**
1. Can this be solved with what's already available? (Check the framework docs, look at what the runtime exposes)
2. Is this actually a problem in the real deployment context, or a hypothetical concern?
3. If it's forward-looking guidance, does it belong in "escalation paths" rather than "current limitations"?

**CTO relevance:** A LIMITATIONS.md file read by a handover recipient signals scope and known risk. Mislabelling solvable problems or non-problems as limitations either under-sells the system or sets wrong expectations. Scrutinise every entry before adding it.
