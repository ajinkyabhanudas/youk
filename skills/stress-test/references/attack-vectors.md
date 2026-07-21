# Attack Vectors — Taxonomy of System Failure Modes

Used in the ATTACK phase. Each agent reads the section relevant to their lens.
For each vector listed, ask: "does the subject have a weakness here?"

---

## Agent A Vectors — Scale & Load

### Throughput Bottlenecks
- **Thread pool exhaustion**: fixed thread pool + slow downstream = requests queue indefinitely
- **Connection pool exhaustion**: DB connections held during long operations block others
- **Queue unbounded growth**: work queued faster than consumed → memory exhaustion
- **Event loop blocking**: sync I/O on async event loop stalls all coroutines

### Data Volume Bottlenecks
- **N+1 query pattern**: one DB query per item in a list = O(n) queries for O(1)-looking code
- **Unbounded result sets**: query returning 100 rows in dev returning 100,000 in prod
- **Memory-loaded datasets**: loading full table to filter in Python instead of in SQL
- **Cache size unbounded**: in-process cache grows without eviction → OOM

### Latency Amplification
- **Thundering herd**: cache miss at high concurrency → all callers hit the origin simultaneously
- **Retry storm**: retries at failure time increase load on already-struggling downstream
- **Synchronized timeouts**: all clients timeout at the same moment → surge on retry
- **Slow outlier blocking fast queries**: no timeouts → slow queries hold resources

### Scaling Discontinuities
- **Horizontal scaling breaks state**: in-process cache/session state not shared across instances
- **Single writer bottleneck**: file I/O or singleton mutex becomes the limiting factor
- **Batch size cliffs**: system works fine for batches < N, fails suddenly at N+1

---

## Agent B Vectors — Edge Cases & Error Paths

### Input Edge Cases
- **Empty input**: zero-length strings, empty lists, zero-row results — often never tested
- **Single element**: boundary conditions at n=1 often different from n=0 and n=2
- **Maximum size**: the largest valid input — do we have a hard limit? what breaks if not?
- **Unicode / encoding**: non-ASCII, emoji, zero-width characters, right-to-left text
- **Null / None / undefined**: dereferenced without guards at call sites
- **Whitespace-only**: "   " treated as non-empty but produces unexpected behavior

### State Edge Cases
- **First run / cold start**: cache is empty, history is empty, no prior state
- **Corrupted state**: cache file is malformed JSON, history file has truncated line
- **Partial write**: process killed mid-write → next read gets corrupted file
- **Concurrent access**: two processes read-modify-write the same file simultaneously
- **State explosion**: long-running process accumulates unbounded state

### Error Path Coverage
- **Unhandled exception type**: code catches `DatabaseError` but not `ConnectionError`
- **Error swallowing**: `try: ... except: pass` — the worst kind of error handling
- **Error context loss**: re-raising without context ("something failed" with no location)
- **Partial success**: 3 of 5 operations succeed — is this treated as success or failure?
- **Cleanup on error**: connection/file/lock not released when exception is raised mid-operation

### First-Match-Wins on Multi-Trigger Input
- **Loop returns/breaks on first match instead of collecting all matches**: when a
  loop iterates over N candidates and any candidate can independently satisfy the
  trigger condition, an early `return`/`break` silently discards correct results
  for every other candidate that also matched in the same call (e.g. two typos in
  one query, two validation errors in one form, two matching rules in one
  dispatch table). Test by constructing an input where ≥2 candidates trigger
  simultaneously — not just "does this generalize across many candidates" but
  "what happens when several trigger in the same pass."
- **Detection heuristic**: a return type of `Optional[X]` (or a single value) on a
  function whose triggering condition can legitimately fire more than once per
  call is a signal this vector applies — check whether "at most one" was ever
  actually verified true, or just assumed.

### Sequencing / Ordering
- **Out-of-order operations**: B called before A completes setup
- **Re-entrant calls**: function called while it's already running (recursion, threading)
- **Race conditions**: two threads read-then-write the same value
- **Event ordering assumptions**: assumes events arrive in order, but they don't

### External Dependency Failures
- **External API returns 200 but wrong shape**: JSON parsed but keys missing
- **External API returns partial response**: stream cut off mid-way
- **External API returns valid but unexpected value**: null where string expected
- **Timeout with no response**: connection hangs instead of timing out cleanly

---

## Agent C Vectors — Hidden Assumptions

These are organized by assumption category. Read `references/assumption-taxonomy.md`
for the full framework; this is the quick-reference for the attack phase.

### User Assumptions
- Assumes user provides well-formed natural language queries
- Assumes user is in a specific locale/timezone
- Assumes single concurrent user (load assumptions)
- Assumes user will read error messages before retrying
- Assumes user won't intentionally probe the system

### Data Assumptions
- Assumes the DB schema won't change mid-operation
- Assumes row counts stay within the range seen in development
- Assumes data is clean (no nulls in non-nullable columns)
- Assumes enumeration values are stable (won't add new values)
- Assumes foreign key relationships are consistent

### Registry Completeness (Unvalidated Membership Assumption)
- **Assumes a candidate registry (allowlist, dispatch table, column/field list) is
  complete, without ever diffing it against the domain it claims to cover.** The
  registry was populated once — from an initial example or two — and its iteration
  logic may be perfectly correct, but a correct loop over an incomplete registry
  still misses real cases (distinct from First-Match-Wins under Agent B: that vector
  is about broken iteration over a registry; this one is about unverified membership
  of the registry itself, before iteration even starts).
- **Detection heuristic**: state the registry's inclusion criteria in one sentence
  (e.g. "any free-text column a user might search by name"), then apply that
  sentence mechanically against an independently-read full domain listing (the
  actual schema.py / OpenAPI spec / ruleset source) — not against test inputs, which
  only exercise what's already registered. Flag if the domain source was read or
  changed after the registry was last updated, with no corresponding "does this need
  a new entry?" pass.

### Infrastructure Assumptions
- Assumes single process / single instance
- Assumes filesystem is writable and has sufficient space
- Assumes network is reliable (no packet loss, no DNS failures)
- Assumes clock is accurate and monotonic
- Assumes environment variables are set and correct

### Dependency Assumptions
- Assumes external API contract is stable (no breaking changes)
- Assumes external API is available (no downtime)
- Assumes external API has the same rate limits as documented
- Assumes library behavior matches documentation for the installed version

### Team / Process Assumptions
- Assumes someone will notice silent failures (no alerting)
- Assumes the next developer knows why this works (no documentation)
- Assumes this code will only be run by the original author
- Assumes the deployment process won't change

### Time Horizon Assumptions
- Built for now but assumes it doesn't need to scale
- TTL values chosen for current data freshness, not future data change rate
- Hardcoded limits (MAX_ROWS = 5000) that will become wrong as data grows

---

## Severity Calibration for Findings

| Severity | Condition |
|---|---|
| CRITICAL | System produces incorrect results or data loss; security vulnerability |
| HIGH | System fails, hangs, or degrades significantly under realistic conditions |
| MEDIUM | System fails under rare but plausible conditions; not production-safe |
| LOW | System has technical debt that doesn't cause immediate failures |
