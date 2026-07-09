# Stack: Python + PostgreSQL
detection_key: python_postgresql

Detected when: Python project + psycopg2/asyncpg/SQLAlchemy + postgres connection evidence.

---

## Core concepts a developer will encounter

| Concept | What it is (one sentence) | When it appears |
|---|---|---|
| Connection pooling | Reusing DB connections across requests instead of opening a new one per query | Performance at scale; psycopg2 ThreadedConnectionPool, SQLAlchemy pool |
| Transaction isolation levels | Controls what a transaction can see from concurrent writes (READ COMMITTED, REPEATABLE READ, SERIALIZABLE) | Data consistency bugs; deadlocks; concurrent writes |
| Advisory locks | Postgres-native application-level locks, not tied to rows | Preventing double-processing; distributed mutex patterns |
| EXPLAIN / query plan | Postgres's report of how it executes a query — index use, scan type, cost estimate | Slow query diagnosis; index effectiveness |
| Index types (B-tree, GIN, GiST) | Different index structures optimized for different query patterns | Full-text search (GIN), range queries (GiST), equality (B-tree) |
| Prepared statements / parameterized queries | Query templates with placeholders — prevents SQL injection, enables plan caching | Any user-supplied input; repeated queries |
| COPY vs INSERT | COPY is a bulk-load command 10–100× faster than row-by-row INSERT | Data import; seeding; large batch writes |
| statement_timeout | PostgreSQL config that kills queries running longer than N ms | Runaway queries; API timeout alignment |
| Row-level locking (SELECT FOR UPDATE) | Locks specific rows during a transaction to prevent concurrent modification | Inventory/balance patterns; optimistic vs pessimistic locking |
| Schema migrations (Alembic) | Versioned, reversible database schema changes | Any DDL change; adding columns, indexes |
| JSONB column | Semi-structured storage inside PostgreSQL — queryable, indexable | Flexible attributes; config storage; EAV patterns |
| Read replica routing | Sending read-only queries to a replica to reduce primary load | Scale-out; analytics queries |

---

## Patterns that commonly surprise developers

- **Connection pool exhaustion**: Each Gunicorn/uWSGI worker holds N connections. At 4 workers × 5 threads × poolsize 5 = 100 connections. PostgreSQL max_connections is often 100. Overflow = "too many clients" error that looks random.
- **Long transaction anti-pattern**: A Python loop that opens a transaction, does work, and commits at the end holds locks the entire time. Postgres vacuum can't clean dead rows while any transaction is open.
- **`autocommit=False` default**: psycopg2 opens a transaction on first query. Reads inside that transaction are consistent (REPEATABLE READ semantics) — but also hold a transaction slot. Close cursors and connections promptly.
- **Migration vs. application startup race**: Running `alembic upgrade head` in the same container as the app start can cause the app to start before the migration completes. Separate init container or health-check gate.
- **JSONB vs. TEXT JSON**: Storing JSON as TEXT is queryable only with casts; JSONB is binary, indexed, and has operators. Use JSONB unless you need to preserve JSON key order.

---

## Common cross-stack analogies (starting points for MAP phase)

Replace with user-specific analogies from user-profile.md where possible.

| Concept | Generic analogy | Analogy quality |
|---|---|---|
| Connection pooling | Thread pool / worker pool for network connections | STRONG |
| Transaction isolation | Git branch merge conflicts — what you can see depends on what's been committed | PARTIAL |
| Advisory locks | Named mutex / semaphore in concurrent programming | STRONG |
| EXPLAIN output | Compiler optimization report / profiler flame graph | PARTIAL |
| Schema migration | Database schema versioning ≈ software versioning | STRONG |
| SELECT FOR UPDATE | Pessimistic lock (vs. CAS optimistic lock) | STRONG |
| COPY bulk load | Batch insert vs. row-by-row insert — orders of magnitude difference | STRONG |
| statement_timeout | Request timeout / circuit breaker at infrastructure level | STRONG |
