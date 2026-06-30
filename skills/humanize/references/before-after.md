# Before / After — Voice Transformation Examples

Used in the VOICE phase. Reference these examples to understand the transformation.
Each example shows AI-default voice → Ajinkya's voice.

---

## Commit Messages

### Example 1: New feature

Before (AI default):
```
feat: add query result caching with TTL and LRU eviction

This commit adds a caching module to store query results and avoid redundant LLM API
calls. The cache uses SHA-256 hashing for keys, supports configurable TTL via env var,
and implements LRU eviction with a configurable maximum size. Cache hits are surfaced
in the UI with a status indicator.
```

After (Ajinkya's voice):
```
Repeated questions hit the LLM every time — expensive and slow. Exact-match cache
with SHA-256 key, 24h TTL, 500-entry LRU now short-circuits the model call for
known questions. Semantic similarity caching deferred until we have usage data on
query patterns.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Example 2: Bug fix

Before:
```
fix: resolve issue where cache lookup was failing for queries with different casing
```

After:
```
Cache treated "What species..." and "what species..." as different queries. Key now
normalizes to lowercase + collapsed whitespace before hashing — covers copy-paste
and history re-use.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Example 3: Refactor

Before:
```
refactor: extract database connection logic into separate module

Moved database connection code from query/executor.py to db/connection.py to
improve separation of concerns and make it easier to test.
```

After:
```
DB connection was tangled with query execution — hard to test either independently.
Extracted to db/connection.py: connection creation and readonly session setup live
there; executor.py handles only SQL validation and execution.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Example 4: Documentation

Before:
```
docs: update README to reflect new caching feature and test count
```

After:
```
README was behind: missing cache module, streaming UI, and 168-test suite. Updated
architecture section, feature list, and test count. Docker setup unchanged.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## Decision Rationale

### Example 1: Cache backend

Before:
```
Context:
We needed to decide on a caching solution for the application. Several options
were evaluated including Redis, in-process caching, and SQLite.
```

After:
```
Context:
Repeated identical queries paid full LLM API cost (~$0.01-0.05/query) every run.
With Jajean asking the same donor-report questions regularly, this adds up and
adds 8-10s latency for questions with known answers. The decision: in-process dict,
Redis, or SQLite file.
```

---

### Example 2: Why Not section

Before:
```
Why not Redis:
Redis was not selected because it would require additional infrastructure setup and
add complexity to the deployment. For a single-user application, this overhead was
not deemed necessary.
```

After:
```
Not Redis: adds a second service and network hop to a single-process Docker deployment.
The persistence benefit (cache survives restarts) isn't needed when a restart is a
planned event and a cold cache is acceptable.
```

---

## Code Comments

### Example 1: API constraint

Before:
```python
# This function formats the tool results into the right format
def format_tool_results(results):
```

After:
```python
# Anthropic API: all tool results from one turn MUST arrive in a single user message.
# Sending separately raises a 400 — this isn't prominently documented.
def format_tool_results(results):
```

---

### Example 2: Design invariant

Before:
```python
# Sets the connection to read-only mode
conn.set_session(readonly=True)
```

After:
```python
# Second layer of the SELECT guard: even if executor.py's regex check has a gap,
# psycopg2 refuses any write at the session level. Belt-and-suspenders per D2.
conn.set_session(readonly=True)
```

---

### Example 3: No comment needed

Before:
```python
# Function to get the model client
def get_model_client() -> ModelClient:
    return _registry[config.backend]
```

After (no comment — the function name explains it):
```python
def get_model_client() -> ModelClient:
    return _registry[config.backend]
```

---

## README Sections

### Example 1: What canopy does

Before:
```
Canopy is a natural language to SQL tool that allows non-technical users to query
a PostgreSQL database using plain English questions. The system utilizes an LLM to
generate SQL queries which are then executed against the database.
```

After:
```
Canopy translates plain-English questions into SQL, runs them read-only against a
PostgreSQL database, and returns answers in plain English — no SQL knowledge needed.
SQL is shown alongside every answer for technical review.
```

---

### Example 2: Architecture description

Before:
```
The caching module provides functionality to cache query results to improve performance
and reduce API costs. It uses SHA-256 hashing for cache keys and supports LRU eviction.
```

After:
```
`cache.py`: exact-match query cache. SHA-256 key on normalized question text, 24h TTL,
LRU eviction at 500 entries. Repeated questions skip the LLM call entirely.
```
