# Common Trade-offs — Pre-Built Option Comparisons

Used in the EXPLORE phase. When one of these recurring decisions is being made,
use this as a starting point — but always verify the specific constraints of the
current project before adopting conclusions wholesale.

---

## Caching Backend

### Options: In-Process LRU vs. Redis vs. SQLite vs. No Cache

**In-Process LRU (e.g., Python `functools.lru_cache` or custom dict)**
- Zero infrastructure: no new service to deploy
- Sub-millisecond access: no network round-trip
- Lost on restart: cache is ephemeral
- Single-process only: doesn't scale horizontally
- Best when: single-process app, Docker-deployed, restarts acceptable as cache miss
- Worst when: high-availability requirement, multiple instances, cache must survive deploys

**Redis**
- Persistent across restarts (with AOF/RDB)
- Shared across multiple instances: true horizontal scaling
- Adds operational complexity: new service, new infra, new failure mode
- Requires network round-trip: adds ~1ms per lookup
- Best when: multi-instance deployment, cache persistence required, rate limiting needed
- Worst when: single-process app, adding infra cost isn't justified yet

**SQLite (file-based)**
- Persistent across restarts
- No network: file I/O only
- Concurrent write limits: write locking under load
- Good fit for structured cache with TTL columns and metadata
- Best when: persistence needed, SQLite already in use, low write concurrency
- Worst when: high write concurrency, sub-millisecond access needed

**No Cache**
- Zero complexity, zero bugs
- Every call hits the underlying data source
- Best when: operation is cheap, data is never repeated, or staleness is never acceptable
- Worst when: any external API / LLM call that may be repeated

**Standard decision matrix:**
| Constraint | Choose |
|---|---|
| Single-process Docker deployment | In-process LRU |
| Multi-instance or high-availability | Redis |
| Persistence without Redis infra | SQLite |
| Real-time, never-stale data | No cache |

---

## SQL vs. NoSQL

**Relational (PostgreSQL, SQLite)**
- ACID transactions: strong consistency guarantees
- Joins: efficient cross-table queries
- Schema-enforced: prevents garbage data
- Best when: data has relationships, consistency matters, ad-hoc queries needed
- Worst when: unstructured/variable documents, extreme write throughput, schema changes are frequent

**Document DB (MongoDB, DynamoDB)**
- Schema flexibility: no migrations for document structure changes
- Horizontal write scaling: designed for high-throughput writes
- No joins: application-level relationship resolution
- Best when: variable document structure, write-heavy workload, no need for complex joins
- Worst when: relational data, ACID transactions required, analytical queries

**Standard rule:** Default to relational (PostgreSQL) unless you have a specific
unstructured-document or massive-write-throughput requirement. "We might need flexibility
later" is not a reason to choose NoSQL.

---

## Synchronous vs. Asynchronous Execution

**Synchronous (threading or blocking I/O)**
- Simple mental model: one thing at a time
- Psycopg2, most stdlib I/O: synchronous by default
- Better for: CPU-bound work, database-heavy code with synchronous drivers
- Threading works: Python GIL doesn't hurt I/O-bound threads

**Asynchronous (asyncio, aiohttp)**
- High concurrency with low thread overhead
- Requires async-all-the-way: mixing sync and async is painful
- Better for: high-concurrency web servers, many simultaneous I/O operations
- Worst when: most dependencies are synchronous (psycopg2, anthropic SDK v1)

**Standard rule:** Use threading for I/O-bound work with synchronous drivers.
Reserve asyncio for greenfield async-native stacks. Never mix without a clear plan.

---

## Monolith vs. Microservices

**Monolith**
- One deployable: simple CI/CD, simple debugging, no network hops
- Shared process: modules can call each other directly
- Scales vertically: add CPU/RAM to the one instance
- Best when: small team, early stage, unclear boundaries, latency-sensitive
- Worst when: teams need independent deploy cycles, services have radically different scaling needs

**Microservices**
- Independent deployment: teams ship without coordinating
- Technology freedom: each service can use different stack
- Network hops: every service call is now a distributed call (latency + failure modes)
- Best when: large team with clear ownership boundaries, proven monolith bottlenecks
- Worst when: unclear boundaries (leads to distributed monolith), small team

**Standard rule:** Start with a modular monolith. Extract services only when you
have a proven bottleneck or genuine team autonomy requirement. "We might need to
scale X independently" is not sufficient — wait until you actually do.

---

## Direct API Call vs. Abstraction Layer

**Direct API Call (e.g., call `anthropic.Anthropic().messages.create()` directly)**
- Simple: no indirection
- Tight coupling: changing provider means changing all call sites
- Best when: single provider, prototype, not expecting to swap

**Abstraction Layer (e.g., `ModelClient` ABC with `AnthropicClient` implementation)**
- Vendor-neutral: swap provider by changing the registry entry
- Testable: mock the interface, not the real API
- Extra code: one more layer to maintain
- Best when: multiple providers possible, strong testing requirement, API may evolve

**Standard rule:** For LLM clients, use an abstraction layer — providers change faster
than you expect and testability is critical. For specialized APIs (Stripe, Twilio) with
one clear provider, direct calls are acceptable if well-isolated.

---

## File-based State vs. Database

**File-based (JSON, JSONL, SQLite file)**
- Zero infrastructure: just a file
- Easy backup: copy the file
- No concurrent writes: file locking required for multi-process
- Best when: single-process, low volume, simple structure, Docker-mounted volume works

**Database (PostgreSQL, hosted DB)**
- Concurrent access: built-in locking and transactions
- Query power: filter, aggregate, join
- Infrastructure overhead: connection management, migrations, backups
- Best when: multiple processes, high volume, complex queries, multi-user

**Standard rule:** Start with file-based (JSONL for append-heavy, SQLite for structured).
Migrate to PostgreSQL when: concurrent writes needed, volume exceeds 100K records,
or query complexity exceeds what SQLite handles well.

---

## Testing Strategy: Unit vs. Integration vs. E2E

**Unit tests (mock dependencies)**
- Fast: milliseconds per test
- Isolated: failures pinpoint exactly what broke
- Risk: mocks can diverge from real behavior (the "integration gap")
- Best when: pure logic, algorithms, data transformations

**Integration tests (real dependencies)**
- Slower: seconds per test (DB, file I/O)
- Realistic: catches real driver behavior, SQL dialect differences
- Risk: harder to parallelize, requires test infrastructure
- Best when: module boundaries, DB queries, external API contracts

**E2E tests (full stack)**
- Slowest: seconds to minutes per test
- Most realistic: catches integration failures between all layers
- Fragile: many failure modes, hard to debug
- Best when: critical user flows, regression prevention for shipped features

**Standard rule for canopy-style projects:** Unit tests for logic, integration tests
for DB layer (with real DB), E2E tests for the one or two critical user flows.
Avoid mocking the DB — the gap between mock behavior and real PostgreSQL behavior
is where real bugs hide.
