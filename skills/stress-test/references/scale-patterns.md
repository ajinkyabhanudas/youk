# Scale Patterns — How Scale Changes System Behavior

Used by Agent A in the ATTACK phase. These are the recurring ways that systems
behave correctly at low scale and fail at high scale. For each pattern, ask whether
the subject is vulnerable.

---

## Pattern 1: The Thundering Herd

**What it is:** When a shared resource (cache, downstream API, DB) is unavailable or
cold-starts, many concurrent callers simultaneously try to recreate it. The surge of
simultaneous requests overwhelms the resource at exactly the moment it is most vulnerable.

**Classic trigger:** Cache expires or is cleared. 100 concurrent users all get a miss,
all fire LLM requests simultaneously. LLM API gets 100 requests at once instead of the
usual trickle.

**Detection:** Look for: shared cache that can expire; retry loops without jitter; no
request coalescing (singleflight).

**Common fixes:**
- Staggered TTL (randomize expiry within a window)
- Singleflight pattern (coalesce duplicate in-flight requests for the same key)
- Cache warming (proactively populate cache before it expires)
- Jitter on retries (prevent synchronized retry storms)

---

## Pattern 2: The N+1 Query

**What it is:** For a list of N items, the code issues N+1 database queries — one to
get the list, then one per item for associated data.

**Classic trigger:** Code that looks like:
```python
results = db.query("SELECT id FROM detections WHERE species = 'X'")
for r in results:
    details = db.query("SELECT * FROM sites WHERE id = %s", r.site_id)  # N queries
```

**At small N**: barely noticeable. At large N: catastrophic.

**Detection:** Look for DB queries inside loops. Look for ORM usage that triggers
lazy-loading per item.

**Common fixes:**
- JOIN the tables in the original query
- Batch fetch: `SELECT * FROM sites WHERE id IN (...)`
- Eager loading with ORM (if using one)

---

## Pattern 3: Resource Pool Exhaustion

**What it is:** A fixed pool of resources (DB connections, threads, file handles) is
exhausted when all consumers are waiting for something slow.

**Classic trigger:** Thread pool of 10. LLM call takes 30s. 11th user's request cannot
get a thread and hangs indefinitely (or fails immediately with no thread available).

**Detection:** Look for: fixed thread/connection pool sizes; slow external calls in
request path; no request queue or queue without size limits.

**Common fixes:**
- Set a maximum queue size (reject early rather than queue indefinitely)
- Timeout on pool acquisition (fail fast with clear error)
- Increase pool size (short-term; addresses symptom not cause)
- Move slow operations out of the hot path (async worker queue)

---

## Pattern 4: Algorithmic Complexity Cliffs

**What it is:** An algorithm that is O(n²) or worse — looks fine at n=100, falls off
a cliff at n=10,000.

**Classic examples:**
- Nested loops over a result set
- String concatenation in a loop (O(n²) due to reallocation)
- Naive deduplication with O(n²) comparison
- Recursive algorithms without memoization

**Detection:** Look for nested loops over data structures, any loop inside a loop over
the same data set.

**Common fixes:**
- Use sets/dicts for O(1) lookup instead of O(n) list scan
- Use string builders / join() instead of concatenation
- Memoize recursive functions
- Filter/sort at the DB level, not in Python

---

## Pattern 5: Write Serialization

**What it is:** All writes to a shared resource (file, in-process dict, DB table with
exclusive lock) are serialized, creating a bottleneck that limits overall throughput.

**Classic trigger:** In-process cache uses a global dict. At 50 concurrent writes, all
writes serialize through Python's GIL. File-based cache uses file locking — writes
queue up.

**Detection:** Look for: shared mutable state (global dict, module-level variable);
file writes with locking; DB operations in transactions that hold locks longer than needed.

**Common fixes:**
- Separate read path from write path
- Write asynchronously (queue writes, batch them)
- Use lock-free data structures where possible
- Use DB row-level locking instead of table-level

---

## Pattern 6: Memory Accumulation

**What it is:** Memory usage grows monotonically with time or load, eventually
causing OOM or severe slowdown.

**Classic triggers:**
- In-process cache with LRU eviction but no size limit
- Accumulating log records in memory instead of flushing
- Growing sets/lists in a long-running process that are never cleared
- Per-request allocations that aren't garbage collected promptly

**Detection:** Look for: collections that grow without explicit size limits; in-process
state in long-running processes; any place data is appended-to without pruning.

**Common fixes:**
- Set explicit max size on all in-process collections
- Flush to disk/DB periodically rather than accumulate in memory
- Profile memory under sustained load before assuming it's fine

---

## Pattern 7: Cold Start Penalty

**What it is:** The first request after startup (or after a cache miss) takes much
longer than subsequent requests. If this cold-start period is long enough, it causes
user-visible failures or timeouts.

**Classic triggers:**
- Lazy initialization of expensive resources (DB connection pool, schema loading)
- Empty cache on restart causing all first requests to hit the backend
- Module-level code that runs once on import and is slow

**Detection:** Look for: lazy initialization patterns; resources that are created
on first use rather than at startup; any code that builds state from scratch.

**Common fixes:**
- Eager initialization at startup (fail fast if resources unavailable)
- Cache warming at startup (pre-populate common queries)
- Health check endpoint that validates all resources are ready before accepting traffic

---

## Scale Rules of Thumb

| Current scale | What to watch at 10x |
|---|---|
| 1 user | Concurrency issues, resource contention |
| 10 users | Thread/connection pool exhaustion, thundering herd |
| 100 users | N+1 queries, algorithmic complexity cliffs |
| 1000 users | Write serialization, memory accumulation, infra limits |
| 10000 users | Architecture-level changes needed; single-box assumptions break |

For canopy (current: single user, target: small team):
- 10x = 10 simultaneous users → watch thread pool, thundering herd, write serialization
- 100x = 100 users → would require architectural changes (not current scope)
