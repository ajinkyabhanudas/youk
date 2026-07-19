# Domain Angles — API & External Calls

Load when direction involves: HTTP endpoints, LLM API calls, third-party integrations,
webhooks, external service dependencies, or any I/O that crosses a process boundary.

These angles supplement the 11 standard angles — they do not replace them.
Run standard angles first, then inject these as additional attack surfaces.

---

## AE-1 — Failure Modes of the External Dependency

**Angle:** What happens to this direction when the external service is slow,
returns an error, or returns a valid but unexpected response?

Attack questions:
- Is there a timeout on the external call? What is it? Is it realistic?
- Does the code handle 429 (rate limit), 503 (unavailable), and 5xx separately from 4xx?
- What happens when the external service returns a valid response in an unexpected shape
  (new field added, field renamed, field missing)?
- Does the error path surface a useful message, or does it swallow the error silently?
- If the call fails mid-operation, is the system left in a partially-updated state?

Weight signal: BLOCKING if silent swallow. HIGH if no timeout. HIGH if partial state on failure.

---

## AE-2 — Retry and Idempotency

**Angle:** Is it safe to retry this call, and does the retry logic create
unintended side effects?

Attack questions:
- Is the external operation idempotent? (safe to call twice with the same inputs?)
- If not idempotent, does the retry logic have a mechanism to detect and skip already-succeeded calls?
- Does exponential backoff exist, or does retry create a thundering herd on failure?
- Does the retry count have an upper bound? What happens after exhaustion?
- Can a retry of a write operation create duplicate records or double-charges?

Weight signal: BLOCKING if duplicate write with real-world consequence (payment, email, record creation). HIGH if unbounded retry.

---

## AE-3 — Rate Limits and Quota

**Angle:** Does this direction assume available capacity that may not exist
under concurrent or sustained use?

Attack questions:
- What are the rate limits of the external API? Are they per-key, per-IP, or per-account?
- Does the code back off correctly on 429, or does it retry immediately?
- Does concurrent usage from multiple sessions share the same quota?
- Is there a cost-per-call? What is the cost at 10x current usage?
- Does the code cache results that could be cached to reduce call volume?

Weight signal: HIGH if no backoff on 429. HIGH if no caching on expensive LLM calls.

---

## AE-4 — Authentication and Credential Handling

**Angle:** Are credentials for the external service handled safely?

Attack questions:
- Are API keys read from environment variables, not hardcoded?
- Are credentials logged anywhere (request logs, error messages, debug output)?
- Does the code handle expired or rotated credentials gracefully, or does it crash?
- Is there a fallback or circuit breaker if credentials are invalid?
- Are credentials scoped to minimum required permissions?

Weight signal: BLOCKING if credentials could be logged or hardcoded.

---

## AE-5 — Contract Versioning

**Angle:** Does this direction assume a stable API contract that may change?

Attack questions:
- Is the external API versioned? Is the version pinned in the call?
- Does the code parse the response defensively (handles missing fields) or rigidly (crashes on schema change)?
- Is there a test that detects when the external API's response shape changes?
- If the external service is deprecated, what is the migration path?

Weight signal: HIGH if no version pinning. HIGH if response parsed rigidly without field-missing handling.

---

## Promotion history
Generated: 2026-07-19 | Source: seed domain file
