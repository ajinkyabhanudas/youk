# Domain Angles — Database & Data Layer

Load when direction involves: migrations, schema changes, queries, ORM usage,
indexing, transactions, data pipelines, caching layers backed by a DB, or any
task that reads/writes persistent storage.

These angles supplement the 11 standard angles — they do not replace them.
Run standard angles first, then inject these as additional attack surfaces.

---

## DA-1 — Migration Safety

**Angle:** Does this direction involve a schema change that could lock a live table,
cause data loss, or break a currently-running query?

Attack questions:
- Does the migration add a NOT NULL column without a default on a table with existing rows?
- Does the migration drop a column that application code still reads?
- Is the migration reversible? What does rollback look like?
- Does the migration run inside a transaction, or does a partial failure leave the schema in an inconsistent state?
- Is this migration safe to run while traffic is live, or does it require a maintenance window?

Weight signal: BLOCKING if data loss is possible. HIGH if table lock > 1s on a live table.

---

## DA-2 — Query Performance at Scale

**Angle:** Does this direction produce queries that work at current data volume
but degrade non-linearly as data grows?

Attack questions:
- Does any query lack an index on its WHERE or JOIN condition?
- Does any ORM call produce N+1 queries (one query per row in a result set)?
- Does any query use `SELECT *` where only 2-3 columns are needed?
- Is there a query that returns unbounded rows with no LIMIT?
- Does any aggregation (COUNT, SUM, GROUP BY) run on a full table scan?

Weight signal: HIGH if N+1 exists. HIGH if unbounded result set. LOW if missing index on low-traffic path.

---

## DA-3 — Transaction Boundaries

**Angle:** Are the operations in this direction correctly grouped into transactions,
and what happens if a transaction is interrupted mid-way?

Attack questions:
- Are multiple writes that must succeed together wrapped in a single transaction?
- If the process crashes between write A and write B, is the data in a consistent state?
- Are there nested transactions, and does the database actually support them?
- Is the transaction scope too wide — holding a lock longer than necessary?
- Does any retry logic replay writes that already committed, causing duplicates?

Weight signal: BLOCKING if inconsistent state on interruption. HIGH if retry causes duplicates.

---

## DA-4 — Connection Management

**Angle:** Does this direction manage database connections correctly under load?

Attack questions:
- Is a connection pool used, or is a new connection opened per request?
- Are connections explicitly closed after use, or do they leak on error paths?
- What happens when the pool is exhausted — does the system queue, fail fast, or hang?
- Does the ORM session scope match the request scope, or can a session bleed across requests?

Weight signal: HIGH if connections leak. HIGH if no pool under concurrent load.

---

## DA-5 — Consistency Model

**Angle:** Does this direction assume a consistency level that the data layer
doesn't actually guarantee?

Attack questions:
- Does the code assume read-your-writes consistency? Is that guaranteed by the DB configuration?
- Does any caching layer serve stale data that the code assumes is current?
- Are there race conditions where two writers update the same row without a lock?
- Does the code assume the order of rows in a query result without an ORDER BY?

Weight signal: BLOCKING if race condition can produce corrupt data. HIGH if stale cache causes wrong behavior.

---

## Promotion history
Generated: 2026-07-19 | Source: seed domain file
