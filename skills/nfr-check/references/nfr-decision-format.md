# NFR Decision Block — Format Templates

Used in the DOCUMENT phase. Copy the relevant template, fill in all fields.
Empty fields are not allowed — use N/A with a reason or DEFER with a trigger.

---

## Full NFR Decision Block (for new modules / major features)

```
[NFR DECISION BLOCK — {FEATURE NAME}]
Generated: {YYYY-MM-DD}
Feature type: {type}

CACHING
  Decision:   DECIDED | DEFER | N/A
  Key design: {what makes a cache key unique, e.g. sha256(casefold(query))}
  TTL:        {e.g. 24h — because LLM responses don't change for the same question}
  Eviction:   {LRU with max 500 entries | LFU | none}
  Invalidate: {on TTL expiry only | on data change | manual purge}
  Reason:     {why caching is or isn't applicable here}

RETRY + TIMEOUT
  Decision:   DECIDED | DEFER | N/A
  Max retries:  {e.g. 3}
  Backoff:      {fixed 1s | exponential 1s/2s/4s | exponential+jitter}
  Timeout:      {e.g. 60s for LLM, 5s for DB}
  After exhaustion: {raise CanopyError("LLM unavailable") | log and continue | circuit break}
  Idempotent:   {yes | no | conditional — explain if no/conditional}
  Reason:       {why this retry policy}

OBSERVABILITY
  Decision:   DECIDED | DEFER | N/A
  Log on:       {start | completion | error | all three}
  Timed:        {yes — log duration_ms | no}
  Sensitive fields excluded: {list fields NOT logged}
  Alert threshold: {e.g. error rate > 5% | p99 > 10s | none}
  Reason:       {what you need to know in production}

AUTH / AUTHZ
  Decision:   DECIDED | DEFER | N/A
  Caller:     {any | authenticated user | service account | internal only}
  Mechanism:  {session token | API key | none — internal}
  Per-resource authz: {yes — explain | no}
  Audit log:  {yes — what's recorded | no}
  Reason:     {why this auth model}

RATE LIMITING
  Decision:   DECIDED | DEFER | N/A
  Limit:      {e.g. 60 req/min per user}
  Scope:      {per user | per IP | global}
  On breach:  {429 Too Many Requests | queue | drop}
  Reason:     {why this limit}

IDEMPOTENCY
  Decision:   DECIDED | DEFER | N/A
  Safe to retry: {yes | no | conditional}
  Key:        {request ID | content hash | natural key | none needed}
  On duplicate: {no-op | error | produce same result}
  Reason:     {why}

CONSISTENCY
  Decision:   DECIDED | DEFER | N/A
  Model:      {strong | eventual — state staleness window}
  Transactions: {yes — scope | no}
  Reason:     {why this consistency level}

DATA VOLUME
  Decision:   DECIDED | DEFER | N/A
  Expected rows: {e.g. ≤ 1000 per query}
  Hard limit:    {e.g. MAX_ROWS = 5000}
  Pagination:    {offset | cursor | none — below limit}
  Reason:        {expected growth and memory constraints}

ERROR PROPAGATION
  Decision:   DECIDED | DEFER | N/A
  Raises:     {exception types — e.g. CanopyError, DatabaseError}
  Catches:    {what exceptions are caught at this layer}
  User message: {how errors are presented to the end user}
  Reason:     {what callers need to handle}

SECURITY SURFACE
  Decision:   DECIDED | DEFER | N/A
  New input vectors: {none | list any user-controlled inputs to SQL/file/shell}
  New data exposed: {none | describe}
  Mitigation:   {parameterized queries | validation | none needed}
  Reason:       {why safe or what's been done}

ADR TRIGGERS
  {List any decisions that deserve a DECISIONS.md entry — or "none"}

DEV-LOOP READINESS
  {READY — NFR block complete, proceed to /dev-loop}
  {BLOCKED — reason}
```

---

## Quick NFR Block (for small features / hotfixes)

Used when `/nfr-check quick` is invoked. Covers only the top 3 mandatory NFRs.

```
[NFR QUICK BLOCK — {FEATURE NAME}]
Generated: {YYYY-MM-DD}

CACHING:        {DECIDED/DEFER/N/A — one-line reason}
RETRY:          {DECIDED/DEFER/N/A — one-line reason}
OBSERVABILITY:  {DECIDED/DEFER/N/A — one-line reason}

SKIPPED: {list any mandatory NFRs skipped with reason — e.g. "AUTH: N/A — internal-only call"}
ADR TRIGGERS: {none | list}
DEV-LOOP READINESS: {READY | BLOCKED: reason}
```

---

## NFR Gap Report (for `review existing` invocation)

Used when auditing an already-built feature for missing NFR decisions.

```
[NFR GAP REPORT — {FEATURE / MODULE NAME}]
Reviewed: {YYYY-MM-DD}

COVERED NFRs:
  {list NFRs with existing decisions — DECIDED/DEFER/N/A}

GAPS FOUND:
  [GAP: SEVERITY] {NFR category}
    Current state: {what exists or doesn't exist}
    Risk:          {what can go wrong without this}
    Recommended:   {the decision that should be made}

SEVERITY LEVELS:
  CRITICAL — gap is actively causing or likely to cause a production incident
  HIGH     — gap creates technical debt with real risk; fix this sprint
  MEDIUM   — gap is a known trade-off; acceptable with documentation
  LOW      — gap is stylistic or optimization; fix in next cleanup pass

REMEDIATION ORDER: {list HIGH/CRITICAL gaps in priority order}
```

---

## Deferral Template

Used when a decision cannot be made yet. A DEFER without a trigger is not valid.

```
DEFER: {NFR category}
  Reason: {why this cannot be decided now}
  Trigger: {the specific condition under which this must be revisited}
  Owner: {who is responsible for revisiting}
  Risk until revisited: {what happens if this remains undecided}
```

**Examples of valid deferral triggers:**
- "Defer caching until we have usage data showing ≥ 10 queries/day repeating"
- "Defer rate limiting until the product is public-facing"
- "Defer pagination until result sets exceed 500 rows in production"
- "Defer circuit breaking until the external API has had two downtime incidents"

**Examples of INVALID deferral reasons (reject these):**
- "We'll figure it out later"
- "Not needed for v1"
- "Low priority right now"
- "TBD"
