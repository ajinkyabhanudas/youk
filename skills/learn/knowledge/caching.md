# Caching — Knowledge File

*Domain: Performance / Cost Optimization*
*CTO relevance: architectural decision-making, cost management, reliability trade-offs*

---

## Exact-Match Query Cache (LRU + TTL)

*Added: 2026-06-26 | Source: canopy/cache module*

**What it is:** A cache that stores expensive operation results keyed on a normalized
hash of the input. Returns stored result on cache hit; executes operation on miss.

**Core model:**
Key design is everything. SHA-256(casefold(query) + collapse-whitespace) creates a
stable key for equivalent inputs regardless of capitalization or spacing. LRU eviction
removes least-recently-used entries when capacity is full. TTL expiry prevents stale
results from persisting longer than their useful window.

**Analogy from background:**
- Domain: AWS (ElastiCache Redis), plus content-addressed storage (S3)
- What transfers: LRU eviction strategy is identical to Redis `maxmemory-policy allkeys-lru`; SHA-256 key is the same as S3 content-addressed object keys where sha256(content) = key
- **What doesn't transfer:** Redis is distributed, persistent, and shared across processes. In-process LRU is ephemeral (lost on restart), single-process only. A Redis cache survives a deployment; this one doesn't. Redis can be shared across horizontally scaled instances; this can't.

**When to reach for this:**
- Any external API call (LLM, REST) where the same input produces the same output
- Any DB query on stable reference data (species names, site metadata)
- Any computation where p99 cost is > 1s or > $0.01 per operation
- When cache hit rate can reasonably be expected > 20% (low hit rate = cache overhead for no benefit)

**When NOT to use this:**
- Operations where the output must always reflect current state (real-time data)
- User-specific data that must not be shared across users (wrong key design would expose cross-user data)
- Write operations (caching a write is meaningless; invalidation on write is the right approach)
- When the input space is effectively infinite with near-zero repetition (hit rate ≈ 0%)

**Canopy example:** `src/canopy/cache.py` — `lookup_cache()`, `write_cache()`, `clear_cache()`
Key: `sha256(casefold + collapse-whitespace)`. TTL: env var `CANOPY_CACHE_TTL_HOURS` (default 24h). LRU: 500 entries.

**Cross-references:**
- gaps.md → semantic caching (the next level up from exact-match)
- retry-reliability.md → thundering herd (what happens when cache expires under load)

**Open question / gap:** Semantic caching: embedding similarity search to handle "what birds did we see in Q1?" and "which species were detected in the first quarter?" as the same query. Gap documented in gaps.md.

---

## Cache Key Design

*Added: 2026-06-26 | Source: canopy/cache module*

**What it is:** The function that maps an input to a cache key. The quality of key
design determines both correctness (same input → same key) and hit rate (equivalent
inputs → same key).

**Core model:**
Three properties of a good cache key:
1. **Deterministic:** same input always produces the same key
2. **Collision-free:** different semantically distinct inputs produce different keys
3. **Normalized:** equivalent-but-different-looking inputs (case, whitespace) produce the same key

**Normalization levels:**
- Level 1: exact match only (fastest, lowest hit rate)
- Level 2: case + whitespace normalization (covers copy-paste, history re-use) ← canopy uses this
- Level 3: semantic normalization via embeddings (highest hit rate, requires embedding model)

**Analogy from background:**
- Domain: AWS (S3 content-addressing, DynamoDB partition keys)
- What transfers: DynamoDB partition key design — key determines distribution and access pattern; same trade-offs apply (too specific = cache miss on equivalent queries, too general = cache collision)
- What doesn't transfer: DynamoDB key design is permanent and has hot-partition implications; cache key design can be changed without migration

**Canopy example:** `cache.py` line: `hashlib.sha256(question.casefold().split().join(" ").encode()).hexdigest()`

---

## TTL (Time to Live) Design

*Added: 2026-06-26 | Source: canopy/cache module*

**What it is:** The duration after which a cache entry is considered stale and ignored.

**Core model:**
TTL is the acceptable staleness window. Setting TTL requires answering: "How long can
I serve the old answer before it's wrong enough to matter?" For canopy's LLM responses
to biological monitoring data: 24 hours is the window. Data doesn't change intra-day.

**Trade-off:**
- Long TTL: higher hit rate, more staleness risk
- Short TTL: lower hit rate, more freshness
- No TTL: cache grows unbounded and never invalidates → stale data forever

**Analogy from background:**
- Domain: AWS CloudFront cache TTL, CDN cache-control headers
- What transfers: same concept — how long can the cached version serve requests before invalidation?
- What doesn't transfer: CloudFront TTL has downstream effects (browser caches); our cache TTL is private to one process

**Configurable TTL (env var):** Correct pattern — TTL should be tunable without code change. `CANOPY_CACHE_TTL_HOURS=0` disables caching entirely.

**Canopy example:** `CANOPY_CACHE_TTL_HOURS` env var, default 24h.
