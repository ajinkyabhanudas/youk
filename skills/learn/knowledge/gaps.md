# Knowledge Gaps

*This file tracks concepts where understanding is incomplete, analogies are weak,
or the area is genuinely new territory. A gap is as valuable as a full entry —
it captures what is known to be unknown.*

---

## Active Gaps

| Concept | Why It's a Gap | Priority | Added | Source Project |
|---|---|---|---|---|
| LLM semantic faithfulness eval (LLM-as-judge) | Verbatim check works for exact numbers; semantic faithfulness ("approximately 35,000") needs an LLM judge. RAGAS / DeepEval are the tools. | MEDIUM | 2026-06-27 | canopy |
| Agentic org design at scale (>10 skills) | No established framework for AI agent org management; audit-log + skill-health is the closest pattern, but playbook is being invented | MEDIUM | 2026-06-27 | canopy/skills |
| Semantic caching (embedding-based) | Embedding similarity search in cache context; knew embeddings from data science but not this application pattern | HIGH | 2026-06-26 | canopy |
| PostgreSQL MVCC (multi-version concurrency control) | Used PostgreSQL via AWS RDS but not at this depth; transaction isolation levels not well-understood | MEDIUM | 2026-06-26 | canopy |
| Thundering herd mitigation patterns | Identified as a risk in stress-test; singleflight pattern is new | MEDIUM | 2026-06-26 | canopy |
| LLM token budget optimization | Know token counts exist; cost optimization patterns not yet internalized | MEDIUM | 2026-06-26 | canopy |
| Circuit breaker pattern | Familiar conceptually from cloud (API Gateway); implementation pattern not yet applied | LOW | 2026-06-26 | canopy |
| Gradio internals (component lifecycle) | Using Gradio but treating it as a black box | LOW | 2026-06-26 | canopy |

---

## Addressed Gaps

| Concept | How Addressed | Date |
|---|---|---|
| LRU eviction policy | Built cache.py with LRU; analogy to Redis documented; break points documented | 2026-06-26 |
| Thread + queue for streaming | Built UI streaming with thread+queue; psycopg2 sync constraint understood | 2026-06-26 |
| Anthropic tool use protocol | Built query loop with tool use; parallel tool result requirement documented as D4 | 2026-06-26 |
| Read-only DB sessions (psycopg2) | Implemented readonly=True with understanding of why dual-layer guard | 2026-06-26 |

---

## Gap Priority Guide

**HIGH:** Likely to affect a decision being made in the next 1-3 sessions.
**MEDIUM:** Will matter when the project scope expands or a new project starts.
**LOW:** Background knowledge that would be useful but isn't blocking.

---

## Recommended Resources for Active Gaps

| Gap | Recommended Resource |
|---|---|
| Semantic caching | OpenAI semantic cache tutorial; pgvector documentation |
| PostgreSQL MVCC | "Designing Data-Intensive Applications" Ch 7; PostgreSQL docs on isolation levels |
| Thundering herd | Go singleflight package documentation (canonical example); "SRE Book" Ch 22 |
| Circuit breaker | Martin Fowler's circuit breaker article; Netflix Hystrix design doc |
