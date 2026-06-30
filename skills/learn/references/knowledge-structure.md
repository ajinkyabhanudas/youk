# Knowledge Structure — How Knowledge Files Are Organized

Used in the PERSIST phase. Defines where to write each type of learning and how
to structure the knowledge files for efficient recall and accumulation.

---

## File Organization

Knowledge files live in `~/.claude/skills/learn/knowledge/`.
One file per domain or technology area. Files grow over time.

```
knowledge/
├── caching.md          — caching patterns: LRU, TTL, eviction, invalidation, semantic
├── retry-reliability.md — retry, backoff, circuit breaking, idempotency
├── database.md         — PostgreSQL patterns, transactions, connections, indexing
├── llm-api.md          — LLM API usage: tool use, streaming, token management, cost
├── python-patterns.md  — Python-specific patterns: ABCs, dataclasses, threading, generators
├── security.md         — security patterns: auth, parameterized queries, secret management
├── testing.md          — test patterns: monkeypatching, fixtures, integration vs. unit
├── system-design.md    — distributed systems concepts mapped to Ajinkya's background
├── architecture.md     — architectural patterns: layering, separation of concerns, interfaces
├── product-thinking.md — PM patterns: prioritization, scope, trade-off reasoning
├── cto-track.md        — CTO-specific skills: decision-making, team design, strategy
└── gaps.md             — active knowledge gaps with priority and recommended resources
```

---

## Entry Format (within each file)

Every entry in a knowledge file follows this format:

```markdown
## {Concept Name}
*Added: {YYYY-MM-DD} | Source: {project/session} | Updated: {YYYY-MM-DD}*

**What it is:** {one sentence — the definition}

**Core model:** {the mental model that makes it work — 2-3 sentences}

**Analogy from background:** {the closest thing from Ajinkya's existing domains}
- Domain: {AWS / Azure IoT / data science / etc.}
- What transfers: {the model or behavior that's the same}
- What doesn't transfer: {where the analogy breaks — non-optional}

**When to reach for this:**
{the conditions or symptoms that indicate this pattern is relevant — 2-4 bullet points}

**When NOT to use this:**
{the conditions that look like they need this but don't — 1-3 bullet points}

**Canopy example:** {where this appeared in the canopy project, with file reference}

**Cross-references:** {other entries that connect to this one}

**Open question / gap:** {anything still unclear or to explore further}
```

---

## The Gaps File

`knowledge/gaps.md` is the active gap tracker. It lists concepts where knowledge
is incomplete, analogies are weak, or the concept is entirely new territory.

```markdown
# Knowledge Gaps

## Active Gaps

| Concept | Why It's a Gap | Priority | Added | Source |
|---|---|---|---|---|
| Semantic caching | No strong analogy; embedding similarity search in this context is new | HIGH | {date} | canopy/cache session |
| DB transaction isolation levels | Used RDS but not at this depth | MEDIUM | {date} | canopy/db session |

## Addressed Gaps

| Concept | How Addressed | Date |
|---|---|---|
| LRU eviction | Built cache.py; analogy to Redis ElastiCache documented | {date} |
```

---

## Accumulation Rules

### Rule 1: Add, don't overwrite
Each new session adds to an existing entry rather than replacing it. Use sub-bullets
and dated notes within entries to show how understanding evolved.

### Rule 2: Cross-reference liberally
When a new concept connects to an existing entry, add a cross-reference to both.
This is how the knowledge graph forms.

### Rule 3: Gaps are first-class entries
A gap entry is as valuable as a full entry. It captures what is known to be unknown.

### Rule 4: Source tracking matters
Every entry records which project/session it came from. This lets you trace the
origin of a pattern when it appears in a new context.

### Rule 5: "When NOT to use" is mandatory for patterns
The most common knowledge failure is applying a pattern in a context where it
doesn't fit. Explicitly documenting when NOT to use something prevents this.

---

## Recall Patterns

When using `recall: [domain]`, the skill reads the relevant file and produces
a structured recall summary:

```
[RECALL: {domain}]
{N} entries in {domain}

CORE CONCEPTS LEARNED:
  - {Concept 1}: {one-line summary + key insight}
  - {Concept 2}: {one-line summary + key insight}

ACTIVE GAPS IN THIS DOMAIN:
  - {Gap}: {one-line description}

MOST RECENT UPDATE: {date} — {what was added}

CONNECTIONS TO OTHER DOMAINS:
  - {cross-reference}
```

---

## Starter Entries (pre-seeded from canopy sessions)

These entries should be created on first run of /learn for the canopy project:

### caching.md seed
```
## Exact-Match Query Cache (LRU + TTL)
*Added: 2026-06-26 | Source: canopy/cache module*

What it is: Cache that stores query results keyed on a normalized hash of the input.
Core model: SHA-256(casefold + collapsed whitespace) → stable key for equivalent queries.
LRU eviction at max capacity; TTL for staleness control. File-backed (JSON) for persistence.
Analogy: Redis maxmemory-policy LRU (ElastiCache), S3 content-addressed keys.
Break: in-process cache is ephemeral (lost on restart), single-process, not distributed.
When to use: any code path where same input → same output within a known time window AND
  the output is expensive to compute (LLM call, external API, slow DB query).
When NOT: writes/mutations, real-time-required data, user-specific session state.
Canopy example: src/canopy/cache.py — lookup_cache, write_cache, clear_cache.
Gap: semantic caching (embedding-based) — deferred but genuinely new territory.
```
