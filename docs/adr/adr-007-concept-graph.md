# ADR-007: Concept Graph as First-Class MCP Capability

**Date:** 2026-07-28
**Status:** Implemented (v0.3.0)
**Projects affected:** youk, canopy, genie-fertility

---

## Context

youk accumulates domain knowledge across sessions via /learn (writing to `knowledge/domain/*.md`) and contracts (writing to `contracts.md`). Both stores are flat text files — rich for human reading, opaque to semantic retrieval. When starting a new session, there is no way to ask "what have I learned about auth across all three projects?" without manually scanning files.

The BM25 file index (ADR-006) addresses cross-project *file* retrieval but not *concept* retrieval. A concept graph stores the semantic units themselves — patterns, decisions, domain knowledge — and their relationships, making them queryable across projects and sessions.

---

## Decision

Extend `shared-index.db` with two new regular SQLite tables:

```sql
concepts      (id, label, type, project_slug, session_n, created_at, summary)
concept_edges (from_id, to_id, edge_type, weight, source_session)
```

**Population:** `end_session()` calls `extract_concepts()` from `concept_graph.py` when `/learn` ran. Extraction is rule-based (reads domain/*.md files) — no LLM call in the hot path.

**Query:** `query_concept_graph(query, project_slug=None)` returns seed matches (label substring) + one-hop neighbors via `concept_edges`. Exposed as MCP tool in `server.py`.

**Edge semantics:** Co-occurrence within the same /learn session, same concept type. Weight=1.0. Future upgrade: cross-type edges from explicit /learn structure.

---

## Rationale

**Why SQLite tables (not FTS5)?** Graph traversal requires JOIN semantics and recursive CTEs. FTS5 is optimized for text search, not hop traversal. The concept graph is small (<10K rows at 1-year horizon) — standard B-tree indexes on `label` and `project_slug` keep queries under 10ms.

**Why rule-based extraction?** LLM-based concept extraction would be higher signal but adds latency and cost to every `/done` close. Rule-based extraction from `/learn`'s structured output (domain/*.md headings and list items) is sufficient for the first-generation graph. The upgrade path to LLM extraction is additive — `extract_concepts()` interface is stable.

**Why co-occurrence edges?** The cheapest edge signal with real value: two patterns written in the same session by `/learn` are semantically related (they emerged from the same work). Cross-type and cross-session edges are a v2 addition once the graph has enough nodes to validate traversal quality.

---

## Consequences

**Positive:**
- `query_concept_graph("auth")` surfaces auth-related patterns across youk, canopy, and genie-fertility in one call.
- Fully additive — no existing tables modified. `CREATE TABLE IF NOT EXISTS` makes it safe to run against existing `shared-index.db`.
- Idempotent writes: `INSERT OR IGNORE` on uniqueness constraints means `/learn` can run twice without duplicate concepts.
- Silent-fail on DB errors — never blocks `/done` or session close.

**Negative / constraints:**
- Concept quality depends on `/learn` discipline — sessions without `/learn` contribute nothing to the graph.
- Rule-based extraction misses implicit relationships (e.g. "ZPD" and "cognitive scaffolding" won't be edge-connected unless they appear in the same domain file). LLM upgrade deferred.
- No concept deletion — stale concepts accumulate over time. Mitigation: `session_n` field allows filtering to recent concepts.

---

## Registered projects

| Slug | Project dir |
|---|---|
| `youk` | `~/.claude/youk` |
| `canopy` | `~/Desktop/Jocotoco/canopy` |
| `genie-fertility` | (registered at first `/learn` run in that project) |

---

## Files

| File | Role |
|---|---|
| `servers/core/src/concept_graph.py` | Schema DDL, extract_concepts(), write_concepts(), query_concept_graph(), get_concept_stats() |
| `servers/core/src/server.py` | MCP tools: query_concept_graph, get_concept_graph_stats |
| `servers/core/src/session.py` | Hook in end_session() — calls extract+write when learn ran |
| `tests/test_concept_graph.py` | 33 tests: schema, extract, write, query, cross-project |
| `~/.claude/CLAUDE.md` | One-line instruction: call query_concept_graph when task references prior patterns |

---

## Upgrade path (v2)

1. LLM-based concept extraction: call a lightweight model to extract concepts from /learn's full output, not just structured list items. Interface (`extract_concepts()` signature) is stable.
2. Cross-type edges: when a `pattern` concept and a `domain` concept co-occur in the same session, emit a cross-type edge with weight=0.5.
3. Concept weight decay: concepts from sessions older than 90 days get a `weight` multiplier applied at query time so recent signal ranks higher.
