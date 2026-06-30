# Assumption Taxonomy — Categories of Hidden Assumptions

Used by Agent C in the ATTACK phase. Every design rests on assumptions. The ones
that cause production incidents are the ones that were obvious at design time —
so obvious they were never written down.

---

## The 7 Assumption Categories

### Category 1: User Behavior Assumptions

What the design assumes users will do, know, or not do.

**High-risk assumptions:**
- User provides valid, well-formed input (SQL injection surface if wrong)
- User asks questions in a specific language or format
- User is in a specific timezone (date/time queries)
- User is a single person (multi-user race conditions)
- User reads error messages before retrying (load amplification if wrong)
- User won't try to access other users' data (authz surface)

**How to detect:** Look for any code path where user-provided data is used without validation.

**How to probe:** "What does this system do if a user sends [specific unexpected thing]?"

---

### Category 2: Data Quality Assumptions

What the design assumes about the data it processes.

**High-risk assumptions:**
- All required fields are present (null dereference)
- Values are within expected ranges (integer overflow, display truncation)
- Enumeration values are stable (unknown enum crashes match statements)
- Foreign key relationships are consistent (join returns expected rows)
- Data is in expected encoding (UTF-8 assumed, Latin-1 stored)
- Row counts stay within dev-time range (performance cliff at scale)
- Data doesn't contain adversarial inputs (prompt injection for LLM systems)

**How to detect:** Look for any place data is read from a DB, file, or external API
and used without validation.

**How to probe:** "What does this system do if the DB has [specific malformed data]?"

---

### Category 3: Infrastructure Assumptions

What the design assumes about the environment it runs in.

**High-risk assumptions:**
- Filesystem is writable and has sufficient space (file-based cache/history)
- Network is reliable and low-latency (external API calls)
- DNS resolves correctly (external hostnames)
- Clock is accurate and monotonic (TTL expiry, timestamps)
- Environment variables are set (crashes on startup if not)
- Process is single-instance (in-process state not shared)
- Memory is sufficient (in-process cache grows unbounded)
- Ports are available (Docker networking)

**How to detect:** Look for any code that depends on the host environment without
validating that dependency.

**How to probe:** "What happens if we deploy this to a new environment with [missing thing]?"

---

### Category 4: External Dependency Assumptions

What the design assumes about third-party APIs, services, and libraries.

**High-risk assumptions:**
- External API contract is stable (breaking changes happen)
- External API is available (downtime happens)
- External API rate limits are as documented (may change without notice)
- External API response time is acceptable (slow days happen)
- Library behavior matches the installed version's documentation (bugs exist)
- Authentication credentials don't expire (tokens have lifetimes)
- External API won't change pricing or access model (LLM costs change)

**How to detect:** Look for any call to an external service without a circuit breaker,
timeout, or retry policy.

**How to probe:** "What happens if [external service] is unavailable / returns 429 / changes its schema?"

---

### Category 5: Scale Assumptions

What the design assumes about the volume of data, users, and requests.

**High-risk assumptions:**
- Data volume stays near current levels (linear growth assumptions)
- Concurrent user count matches dev-time expectations (single user vs. team)
- Query complexity stays at current level (ad-hoc complex queries happen)
- Response time expectations are the same for all users (p99 tail latency)
- Memory usage per request is bounded (LLM response sizes vary widely)

**How to detect:** Look for any hard-coded limit, in-process collection, or algorithm
with non-obvious complexity.

**How to probe:** "What is the p99 latency when 50 users query simultaneously?"

---

### Category 6: Team & Process Assumptions

What the design assumes about the people who will maintain and operate it.

**High-risk assumptions:**
- Silent failures will be noticed by someone (no alerting)
- Non-obvious code behavior is understood without documentation (tribal knowledge)
- Future maintainers know the context behind design decisions (no ADRs)
- The deployment process won't change (hardcoded assumptions about infra)
- Only the original author will run this code (paths only the author knows)
- The team will remember to update X when Y changes (not automated)

**How to detect:** Look for any place where correct operation depends on a human
doing something correctly at the right time, without automation or alerting.

**How to probe:** "If a new developer takes over this project with no handoff, what would break first?"

---

### Category 7: Time Horizon Assumptions

What the design assumes about how long the system will be used as-is.

**High-risk assumptions:**
- This is temporary (temporary things become permanent)
- This doesn't need to scale (it will scale)
- These hard-coded values are correct forever (MAX_ROWS = 5000 today)
- TTL values are appropriate for future data change rates
- This technology will still be supported/maintained (dependencies become abandoned)
- The data model is stable (requirements change)

**How to detect:** Look for any hard-coded constant, any "we'll refactor this later"
comment, and any dependency on a specific technology version.

**How to probe:** "What happens to this system in 12 months if nothing is changed?"

---

## Assumption Risk Scoring

For each assumption identified, score:

| Dimension | Options |
|---|---|
| **Probability of being wrong** | HIGH (likely to change) / MEDIUM / LOW (stable) |
| **Impact if wrong** | CRITICAL (data loss/security) / HIGH (failure) / MEDIUM (degradation) / LOW (nuisance) |
| **Detection time** | IMMEDIATE (fails fast) / DELAYED (silent for hours/days) / NEVER (silent permanently) |

Highest-priority assumptions: HIGH probability + HIGH impact + DELAYED/NEVER detection.

---

## Probing Techniques

**"What if" questioning:**
- "What if the DB returns zero rows?"
- "What if the LLM API is down for 10 minutes?"
- "What if a second user runs a query while the first is running?"

**"Who changes this" questioning:**
- "Who changes the MAX_ROWS constant when data grows?"
- "Who notices if the cache file gets corrupted?"
- "Who updates the schema.py when the DB schema changes?"

**"Day 1 vs. Day 365" questioning:**
- "What works on Day 1 of deployment that might not work on Day 365?"
- "What is different about the production environment vs. the dev environment?"
- "What will a new developer change first when they join, and will that break anything?"
