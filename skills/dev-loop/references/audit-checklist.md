# Audit Checklist

Used in the AUDIT phase of dev-loop. Work through every category. Skip a category
only if it is clearly not applicable to the language/runtime in context.

---

## 1. Security

| Check | Severity if failed |
|-------|--------------------|
| No hardcoded secrets, API keys, passwords, tokens | CRITICAL |
| SQL/NoSQL queries use parameterized inputs or ORM — no string concat | CRITICAL |
| Command execution sanitizes all user input | CRITICAL |
| File paths validated — no path traversal (`../`) possible | CRITICAL |
| Auth: every endpoint/function checks permissions before acting | CRITICAL |
| Sensitive data not logged (PII, tokens, passwords) | HIGH |
| Cryptography: uses standard library — no homebrew crypto | HIGH |
| Dependency versions checked for known CVEs (note if unknown) | HIGH |
| Error messages do not leak stack traces or internal state to callers | MEDIUM |
| Rate limiting / DoS surface considered for public-facing code | MEDIUM |
| CSRF protection present for state-mutating web endpoints | MEDIUM |
| Redirect targets validated (open redirect prevention) | MEDIUM |

---

## 2. Correctness

| Check | Severity if failed |
|-------|--------------------|
| Null / nil / undefined handled at every dereference point | HIGH |
| Integer overflow / underflow possible? (especially in loops, indices) | HIGH |
| Off-by-one errors in loop bounds, slice indices, range checks | HIGH |
| Return values / errors checked — no silent discards | HIGH |
| Async code: all promises/futures awaited; no floating promises | HIGH |
| Concurrency: shared state protected by locks / channels / atomics | HIGH |
| Type coercions correct (implicit widening, signed vs. unsigned) | MEDIUM |
| Edge cases: empty input, single element, max-size input handled | MEDIUM |
| Recursive functions have a termination guarantee | MEDIUM |
| State machines / enums: all variants handled in switch/match | MEDIUM |

---

## 3. Performance

| Check | Severity if failed |
|-------|--------------------|
| No N+1 query patterns in loops | HIGH |
| No blocking I/O on hot paths in async runtimes | HIGH |
| Allocations in tight loops (unnecessary object creation) | MEDIUM |
| Algorithmic complexity: flag anything O(n²) or worse in unbounded input | MEDIUM |
| Caching opportunity missed for expensive repeated computation | HIGH |
| Caching: for LLM/external API calls, missing cache = CRITICAL if no /nfr-check NFR block | CRITICAL |
| String concatenation in loops (use builder/join instead) | LOW |
| Unnecessary serialization/deserialization round-trips | LOW |

---

## 4. Maintainability

| Check | Severity if failed |
|-------|--------------------|
| Functions > 30 lines — consider splitting | MEDIUM |
| Cyclomatic complexity > 7 (too many branches) | MEDIUM |
| Deep nesting > 3 levels — consider early return / extraction | MEDIUM |
| Duplication: same logic appears 3+ times without abstraction | MEDIUM |
| Magic numbers / strings without named constants | LOW |
| Dead code: unreachable branches, unused variables/imports | LOW |
| Inconsistent naming conventions within the same file | LOW |
| Public API surface undocumented (missing docstrings/JSDoc) | LOW |

---

## 5. Error Handling

| Check | Severity if failed |
|-------|--------------------|
| Errors propagated — not silently swallowed | HIGH |
| Error types meaningful — not just generic `Error("something failed")` | MEDIUM |
| Resources closed/freed in error paths (files, DB connections, locks) | HIGH |
| Panics / fatal calls appropriate for context (not in library code) | MEDIUM |
| Retry logic present where transient failures are expected | LOW |
| Structured logging on errors (includes context, not just message) | LOW |

---

## 6. Testing Gaps (when code already has tests)

| Check | Severity if failed |
|-------|--------------------|
| Happy path not covered | HIGH |
| Error path not covered | HIGH |
| No tests at all for public API surface | HIGH |
| Edge cases (empty, nil, max) not covered | MEDIUM |
| Tests assert on implementation details (too brittle) | LOW |
| Test setup/teardown leaks state between tests | MEDIUM |

---

## 7. Language-Specific Spot-Checks

### TypeScript / JavaScript
- `any` used without justification → MEDIUM
- `as` type assertions masking real type errors → MEDIUM
- Async function returned but not awaited → HIGH
- `==` used instead of `===` → LOW

### Python
- Mutable default arguments (`def f(x=[])`) → HIGH
- Exception caught with bare `except:` → MEDIUM
- `eval()` / `exec()` on untrusted input → CRITICAL
- `global` / `nonlocal` overused → LOW

### Go
- `err` ignored with `_` on non-trivial calls → HIGH
- Goroutine leak (goroutine started without a cancel path) → HIGH
- `defer` inside a loop (defers stack until function returns) → MEDIUM
- Mutex not unlocked on all error paths → HIGH

### Rust
- `unwrap()` / `expect()` in non-test code without justification → MEDIUM
- `unsafe` block without safety comment → HIGH
- Cloning unnecessarily in hot paths → LOW

### SQL
- `SELECT *` in production queries → LOW
- Missing index on foreign key / join column (note if unknown) → MEDIUM
- Transaction boundary missing for multi-step mutations → HIGH

---

## Severity Reference

| Level | Meaning |
|-------|---------|
| CRITICAL | Fix before any use. Correctness failure or security vulnerability. |
| HIGH | Fix before shipping. Likely causes bugs or degraded behaviour. |
| MEDIUM | Fix in this sprint. Technical debt with real impact. |
| LOW | Address in next pass. Style, clarity, or minor efficiency. |
| INFO | Observation only. No action required. |
