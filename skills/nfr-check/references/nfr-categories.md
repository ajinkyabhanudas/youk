# NFR Categories — Probe Questions and Decision Criteria

Used in the PROBE phase. Read the section for each mandatory NFR category identified
in CLASSIFY. Work through questions in order; stop when you have enough to force a
DECIDE-phase decision. Do not ask questions whose answers are already clear from context.

---

## 1. Caching

**Purpose:** Avoid re-computing or re-fetching expensive results. Particularly critical
for external API calls (LLMs, REST), database queries on stable data, and any path
where the same input produces the same output within a known time window.

**Probe questions (ask only what's missing):**
1. Is the output deterministic for the same input within a reasonable time window?
2. What is the cost of a cache miss vs. a cache hit? (API cost, latency, DB load)
3. What makes a cache key unique? (exact input? normalized? user-scoped?)
4. What is the acceptable staleness window? (TTL in hours/minutes/seconds)
5. What triggers invalidation? (time expiry only? data change? manual purge?)
6. What is the expected hit rate? (high = semantic similarity, low = unique queries)
7. How much memory/storage is acceptable for the cache?
8. What happens when the cache is full? (LRU evict? refuse new entries? grow unbounded?)

**Decision criteria:**
- External API / LLM call: caching is MANDATORY unless the output must be real-time
- DB read on stable data (reference tables, config): caching is MANDATORY
- User-specific, always-fresh data: caching may be N/A — state why
- Writes / mutations: caching is N/A for the write itself; invalidation policy needed for reads

**Common mistakes:**
- Key too broad: caches results for "different" queries that hash the same
- Key too narrow: cache misses on equivalent queries (e.g., case difference)
- No TTL: cache grows unbounded or returns stale data indefinitely
- No invalidation: cache serves wrong data after schema/data change
- TTL mismatched to semantic decay rate: a TTL appropriate for slowly-changing data
  is too long for live-count or time-relative outputs. Ask: "Does the cached answer
  remain correct for the full TTL window, regardless of when within that window it
  is read?" If not, the staleness window must be shorter, or the limitation must be
  documented to users.

---

## 2. Retry + Timeout

**Purpose:** Tolerate transient failures from external dependencies without causing
cascading failures or data corruption.

**Probe questions:**
1. Can the operation fail transiently? (network blip, rate limit, 503)
2. Is the operation idempotent? (safe to call twice with same result)
3. What is the maximum acceptable wait time for a caller? (timeout)
4. How many retries before giving up? (max_retries)
5. What is the backoff strategy? (fixed / exponential / exponential with jitter)
6. What happens after max retries? (raise exception / log-and-continue / circuit break)
7. Does the caller need to know about retries, or are they transparent?

**Decision criteria:**
- External API / LLM: retry is MANDATORY; timeout is MANDATORY
- Database operations: timeout is MANDATORY; retry only if connection-level (not query-level)
- Idempotent mutations: retry safe; non-idempotent mutations: retry DANGEROUS — decide explicitly
- Internal in-process calls: retry usually N/A

**Standard defaults (adjust with reasoning):**
- Timeout: 30–60s for LLM calls; 5–10s for REST APIs; 3–5s for DB queries
- Max retries: 3 for transient errors
- Backoff: exponential with jitter (base 1s, max 30s)
- After exhaustion: raise exception with context; never silently continue

---

## 3. Observability

**Purpose:** Know what the system is doing in production without being there. Includes
logging, timing, error rates, and alerting thresholds.

**Probe questions:**
1. What events must be logged for debugging? (inputs, outputs, errors, timing)
2. What must NOT be logged? (PII, credentials, full query results with sensitive fields)
3. What is the latency SLO? (what response time is "acceptable"?)
4. What constitutes an alert-worthy failure? (error rate threshold, latency spike)
5. Does the operation have a business metric that should be tracked? (query count, cache hit rate)
6. Is the operation in a critical path where silent failure is unacceptable?

**Decision criteria:**
- User-facing operations: log start, completion, timing, and errors — MANDATORY
- LLM calls: log token counts and latency — cost tracking requires this
- Background jobs: log run start, end, row count processed, error count
- Internal helpers: log errors only unless on a hot path

**What to log (structured):**
```
operation: "run_query"
duration_ms: 1234
cache_hit: false
result_rows: 42
model: "claude-sonnet-4-6"
error: null
```

**What never to log:**
- Raw API keys or tokens
- Full SQL with embedded PII
- User passwords or session tokens
- Coordinate data (latitude/longitude for sensitive locations)

---

## 4. Authentication + Authorization

**Purpose:** Ensure only the right callers can perform operations, and that access
decisions are auditable.

**Probe questions:**
1. Who can call this operation? (any user / authenticated user / specific role / service-to-service / internal only)
2. What authentication mechanism is in use? (session token / API key / JWT / none for internal)
3. Is there per-resource authorization? (can user A access user B's data?)
4. What happens on an unauthorized call? (401 / 403 / silent rejection)
5. Does this operation need to be audited? (who called it, when, with what inputs)
6. Does this change the attack surface? (new public endpoint, new permission scope)

**Decision criteria:**
- New public-facing endpoint: auth is MANDATORY
- Internal service call: "internal only" is a valid decision but must be stated
- Admin operations: audit logging is MANDATORY
- Read-only on non-sensitive data: lighter-weight auth may be acceptable

---

## 5. Rate Limiting

**Purpose:** Protect against abuse, control costs on external APIs, and prevent a
single caller from degrading service for others.

**Probe questions:**
1. Is this operation exposed to external callers or user input?
2. Does this operation have a per-call cost? (LLM tokens, external API credits)
3. What is the maximum sustainable call rate? (per user? per IP? global?)
4. What happens when the rate limit is exceeded? (429 Too Many Requests / queue / drop)
5. Does the external API this calls have its own rate limit we must respect?

**Decision criteria:**
- LLM-backed endpoints: rate limiting MANDATORY — token costs compound
- External API calls: rate limiting MANDATORY — protect against hitting upstream limits
- Internal operations: rate limiting usually N/A unless resource-intensive
- Public endpoints: rate limiting MANDATORY

---

## 6. Idempotency

**Purpose:** Ensure that retrying or replaying an operation produces the same result
as the first execution. Critical for reliability and safe retry logic.

**Probe questions:**
1. Can this operation be safely called twice with the same inputs?
2. Does this operation create, mutate, or delete state?
3. If called twice: is the second call a no-op, an error, or does it produce a duplicate?
4. Is there a natural idempotency key? (request ID, content hash, timestamp)

**Decision criteria:**
- Read-only operations: idempotent by definition — state N/A explicitly
- Writes / mutations: idempotency decision MANDATORY — define what "duplicate" means and how it's handled
- Background jobs: MANDATORY — schedulers retry failed jobs; jobs must handle re-execution

---

## 7. Consistency

**Purpose:** Define the correctness guarantee when the system has multiple copies of
data or reads after writes.

**Probe questions:**
1. Does this operation read data that another operation may have just written?
2. Is eventual consistency acceptable? (cache may serve stale data)
3. Are there transactions needed? (all-or-nothing for multi-step writes)
4. What is the acceptable staleness window for reads?

**Decision criteria:**
- Caching reads: eventual consistency is explicitly chosen — must state the staleness window
- Financial or identity data: strong consistency MANDATORY
- Reporting / analytics: eventual consistency usually acceptable
- Most web application reads: eventual consistency acceptable, state it explicitly

---

## 8. Data Volume + Pagination

**Purpose:** Ensure the system doesn't break, slow down, or exhaust memory as data
grows beyond initial assumptions.

**Probe questions:**
1. What is the expected number of rows / items returned?
2. What is the maximum size response the caller can handle?
3. At what row count does performance degrade?
4. Is pagination needed? (offset / cursor / page number)
5. Is there a hard limit that should be enforced? (MAX_ROWS constant)

**Decision criteria:**
- Any operation returning DB results: data volume decision MANDATORY
- Results > 1000 rows: pagination MANDATORY
- Variable-size results: hard limit MANDATORY (even if high)
- Fixed-size reference data: N/A — state the fixed size

---

## 9. Error Propagation

**Purpose:** Define what callers receive when this operation fails, and ensure errors
carry enough context to be debuggable without leaking internals.

**Probe questions:**
1. What exception types can this operation raise?
2. Should errors be re-raised, caught, or wrapped?
3. What context must an error carry? (operation name, inputs, upstream error)
4. Should errors be logged at this layer or left for the caller to log?
5. Are there error types that should be handled differently? (transient vs. permanent)

**Decision criteria:**
- Library/module code: propagate errors upward; don't log here (callers will)
- Entry points (endpoints, UI handlers): catch, log, and return user-friendly message
- Background jobs: catch, log, and decide: retry or fail the job run

---

## 10. Security Surface

**Purpose:** Identify whether this feature adds new attack vectors.

**Probe questions:**
1. Does this accept user-controlled input that reaches a SQL query, file path, or shell command?
2. Does this expose new data that wasn't previously accessible?
3. Does this create a new network endpoint, open port, or credential?
4. Does this change what an unauthenticated caller can do?

**Decision criteria:**
- Any user-controlled input to DB / file / shell: parameterization review MANDATORY
- New network exposure: threat model update MANDATORY
- No new exposure: state N/A explicitly

---

## 11. Rendering Environment

**Purpose:** Ensure UI components render correctly across all supported color modes and
rendering environments. Hardcoded colors that look correct in light mode produce jarring
artifacts in dark mode — this class of failure reaches the user without triggering any
functional test.

**Applies to:** Any task that changes, adds, or renames a CSS rule, UI component, or
visual style property.

**Probe questions:**
1. What color modes does this UI support? (light only / dark only / both / system-default)
2. Are there hardcoded hex color values in the spec or CSS? (if yes: are dark-mode variants defined?)
3. Does the UI framework auto-apply a dark theme based on OS color-scheme preference?
4. Has the component been visually verified in the non-primary color mode?

**Decision criteria:**
- Light-only pin: must be a stated decision, must have a JS/CSS enforcement mechanism, must become an ADR entry
- Both modes supported: Playwright dark-mode screenshot test is MANDATORY before shipping
- Framework auto-dark without override: treat as "both modes active" — verify explicitly

**Common mistakes:**
- CSS uses hardcoded `background-color` hex that looks fine in light mode, white-boxes in dark
- Framework adds `.dark` class to `<html>` on OS dark-mode preference — not caught in local light-mode dev
- `color-scheme: light` declared in CSS but framework JS re-applies a dark theme class after page load, overriding it
