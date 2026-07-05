# Severity Guide — Borderline Calls

Use this when you are uncertain whether a finding is CRITICAL, HIGH, MEDIUM, or LOW.
Default to the higher severity when evidence is ambiguous.

---

## Decision Rules

**Promote to CRITICAL if any of:**
- Can cause data loss, data corruption, or unrecoverable system state
- Security breach: credential exposed, auth bypassed, privilege escalated
- youk hard rule violated (write outside /youk/, raw transcript stored, confirmed=True bypassed)
- Silent failure in a code path the caller depends on for correctness

**Promote to HIGH if any of:**
- Logic error that produces wrong output (not just edge-case — main path)
- Changed behavior with no test coverage (risk tier MED+)
- Error path that succeeds silently — caller assumes operation completed
- Shared state mutated without synchronization in an async context
- Missing cleanup in error path: open file handle, DB connection, lock, or resource leak
- Magic string/number in auth or routing decision

**Demote to MEDIUM if all of:**
- Issue exists but is caught by existing test coverage → bump down one level
- Issue affects only code quality or readability, not correctness or safety
- Pattern is isolated — one callsite, not systemic

**LOW or INFO if:**
- Purely stylistic (naming, whitespace, formatting inconsistency)
- Optional improvement with no risk if deferred
- Suggestion the author may already have considered

---

## Borderline Scenarios

| Scenario | Verdict | Reason |
|---|---|---|
| `bare except` that swallows exception | HIGH | Silent failure — caller can't detect error |
| `bare except` but exception is re-raised | MEDIUM | Caught and re-raised is acceptable, but lose type info |
| `TODO` left in auth code | HIGH | Incomplete security implementation |
| `TODO` left in utility function | MEDIUM | Deferred work with no immediate risk |
| Missing test for changed function | HIGH (MED+ risk tier) / MEDIUM (LOW tier) | Risk-tier dependent |
| Magic number in routing logic | HIGH | Hard to audit, easy to misconfigure |
| Magic number in UI padding | INFO | No correctness or security risk |
| Broad `Exception` catch with logging | MEDIUM | Not ideal, but logged — not silent |
| N+1 query in a loop | MEDIUM unless in hot path | LOW risk unless it's a high-traffic endpoint |
| N+1 query on a high-traffic endpoint | HIGH | Performance degradation under real load |
| Hardcoded timeout of 30s | LOW | Suboptimal but not dangerous |
| Hardcoded timeout of 0 (no timeout) | HIGH | Unbounded wait — denial of service vector |
| Unused import | INFO | No risk; clean-up is optional |
| Dead code (unreachable branch) | MEDIUM | Confusing; may mask a logic error |
| Missing docstring on public function | LOW (utility) / MEDIUM (public API) | API discoverability matters for public surfaces |

---

## Severity → Action Map

| Severity | Action required |
|---|---|
| CRITICAL | Block immediately. Must fix before any further review or merge. |
| HIGH | Must fix before merge. List in "Must fix" section of VERDICT. |
| MEDIUM | Should fix. List in "Should fix" section. Merge allowed with acknowledgment. |
| LOW | Author's call. List in "Notes" section only. |
| INFO | Optional. Mention briefly in "Notes" or omit if noise. |
