---
name: youk-research
description: >
  External best-practices scanner for the youk system. Fires when invoked via
  /research [topic], when self_heal() returns research_topics, or on the weekly
  scheduled cron. Scans Anthropic engineering blog, Karpathy GitHub activity,
  OpenAI cookbook, and HN developer tools posts. Extracts patterns relevant to
  youk (context persistence, token efficiency, skill routing, agent coordination).
  Deduplicates against existing cross-project.md and PENDING.md. Calls
  add_proposal() for each novel pattern. Produces a summary of proposals queued.
  NOT a general web research tool — scope is strictly youk improvement patterns.
  Never called from session_start, route_task, or any hot path.

auto-skip: |
  Skip if this skill already ran within the last 7 days (check last scan timestamp
  in knowledge/projects/youk/last-research-scan.txt). Skip if all topics in the
  current call were covered in the last scan.
---

# youk-research — External Best-Practices Scanner

Scan external sources for developer-productivity and agent-coordination patterns. Extract what's relevant to youk. Propose it. Never auto-apply.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| `/research` | Full scan: all 4 sources, all default topics |
| `/research [topic]` | Focused scan: all sources filtered to the given topic |
| `/research enter: PROPOSE` | Skip collect + extract; propose from patterns already extracted this session |
| `quick` | Scan 2 sources (Anthropic blog + HN), 1 topic only |
| `stack` | Per-project stack briefing — reads project type from context.md, generates 3-5 actionable findings about what's new in that stack, writes to research-inbox/ (replaces the cron-based project-research.py, no API key required) |

---

## Context Capture

```
TOPICS:        [from invocation; default: "agentic coding, MCP token efficiency, context persistence, skill routing"]
LAST_SCAN:     [read knowledge/projects/youk/last-research-scan.txt; "never" if missing]
EXISTING_PATTERNS: [first 500 chars of knowledge/cross-project.md — used for dedup]
PENDING_IDS:   [count of items in knowledge/proposals/PENDING.md — surface if > 5 before starting]
```

If PENDING_IDS > 5: surface once — "5+ proposals already pending — continue scan or review existing first?" One redirect accepted. Silence = continue.

---

## The 4 Phases

### Phase 1 — COLLECT

Search each source in `references/sources.md` for the given TOPICS. Use WebSearch, not WebFetch, at this phase — search results only.

1. For each source in the fixed source list:
   - Run: `WebSearch "{source_keyword} {topic} site:{domain} OR {domain}"` (or equivalent)
   - Collect top 3 results per source × topic combination
   - Record: title, URL, 1-sentence relevance hint from the search snippet
2. Deduplicate URLs — a URL seen in multiple searches counts once
3. Cap total URLs at 12 — prioritise Anthropic + Karpathy over generic sources
4. If a search returns 0 results for a topic+source pair: skip silently, don't mention

> Compact phase summary: "Collected N URLs across M sources. Proceeding to extract patterns from top hits."

---

### Phase 2 — EXTRACT

Fetch and extract patterns from the collected URLs. Use Haiku for this phase — not Sonnet.

1. For each URL (in priority order: Anthropic > Karpathy > OpenAI > HN):
   - WebFetch the URL; read the first 3,000 chars
   - Extract patterns as structured entries:
     ```
     pattern: [one concrete technique in ≤15 words]
     relevance: [why this matters to youk — cite which youk component it improves]
     source_url: [the URL]
     change_type: SKILL_EDIT | FILE_CREATE
     target: [skill name for SKILL_EDIT, or "knowledge/cross-project.md" for FILE_CREATE]
     ```
   - Extract at most 2 patterns per URL — quality over quantity
2. Discard patterns that are:
   - Already a verbatim phrase in EXISTING_PATTERNS (string match)
   - Generic ("use good prompts", "test your code") — no specific mechanism
   - About models youk doesn't use (GPT, Gemini, Llama)
3. If a URL is paywalled or 403: skip, note in summary

> Compact phase summary: "Extracted N patterns from M pages. [X discarded as generic/duplicate.] Proceeding to propose."

---

### Phase 3 — DEDUPLICATE

Before proposing, do a final pass to avoid creating duplicate proposals.

1. Read current `knowledge/proposals/PENDING.md` — extract proposal titles
2. For each extracted pattern: check if a pending proposal with the same target + similar title exists
   - "Similar" = Jaccard similarity > 0.4 on title words (approximate mentally)
   - If duplicate: skip, note as "already pending"
3. Check `knowledge/cross-project.md` headings — if pattern matches an existing heading exactly: skip
4. Result: a final list of novel patterns to propose

> Compact phase summary: "After dedup: N novel patterns to propose. [M duplicates skipped.]"

---

### Phase 4 — PROPOSE

Call `youk-core.add_proposal()` for each novel pattern. Use Sonnet only here if the pattern requires synthesis beyond what was extracted verbatim.

1. For each novel pattern:
   - Formulate the proposal:
     - `title`: "Research: [pattern name]" (prefix makes origin clear)
     - `rationale`: "Sourced from [source_url]. [relevance]. Signal type: best_practices_gap."
     - `change_type`: from extracted entry
     - `target`: from extracted entry
     - `content`: for SKILL_EDIT — the specific text addition. For FILE_CREATE (cross-project.md addition) — a new `## Pattern Name` section
   - Call `youk-core.add_proposal(title, rationale, change_type, target, content)`
2. Write scan timestamp: `echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) topics: TOPICS" > knowledge/projects/youk/last-research-scan.txt`
3. Return summary:
   ```
   youk-research complete.
   Scanned: N URLs across M sources
   Extracted: P patterns
   Proposed: Q proposals queued in PENDING.md
   Skipped: R (duplicates or generic)
   Run get_proposals() to review.
   ```

> Compact phase summary: "Queued Q proposals. Scan timestamp written. Research complete."

---

---

## Stack Mode — Per-Project Briefing (no API key, no cron)

`/research stack` replaces the `project-research.py` cron job. Runs in-session,
zero additional API credits — Claude Code itself generates the briefing.

### When to invoke

- At the start of a session on a project you haven't touched in a while
- When `session_start` surfaces "N research finding(s)" in the session plan
- Weekly discipline: run once per project per week to stay current on the stack
- Automatically suggested by session_plan when no research-inbox entry exists within 14 days

### Stack Briefing Phases

#### Phase S1 — IDENTIFY

Read the current project's stack from context files:

```
slug      = _slug(project_dir)   ← from session context
stack     = project-type field in knowledge/projects/{slug}/context.md
inbox_dir = ~/.claude/youk/knowledge/projects/{slug}/research-inbox/
last_file = most recent *.md in inbox_dir (by filename date), or "none"
```

Check staleness: if last_file exists and its date is within 7 days → surface once:
"Stack briefing for {slug} was generated {N} days ago. Regenerate? (yes/skip)"
One redirect accepted. Silence = regenerate.

Emit:
```
[STACK BRIEFING — {slug}]
Stack: {stack}
Last briefing: {last_file date or "none"}
Generating...
```

#### Phase S2 — GENERATE

Use the stack-specific focus areas below to generate 3-5 briefing entries.
Each entry must be:
- **Specific** — names a concrete library version, pattern, or API change
- **Actionable** — includes something the developer could do in their next session
- **New or commonly misused** — skip stable, well-known fundamentals

Stack focus areas (same as project-research.py `_SOURCE_MAP`):

| Stack | Focus |
|---|---|
| `python` | Python 3.12-3.13 features (f-string improvements, JIT in 3.13), uv as pip/poetry replacement, Ruff linting, FastAPI + Pydantic v2, async patterns, pytest 8+ |
| `python_postgresql` | SQLAlchemy 2.x async, Alembic migration patterns, PostgreSQL 16-17 (pg_vector, logical replication), PgBouncer vs asyncpg pools, psycopg3, pytest-postgresql |
| `python/docker` | Same as python + Docker multi-stage build patterns, volume mount performance, health check best practices, compose watch mode |
| `js_react` | React 19 / Server Components / App Router, TypeScript strict mode, Tailwind v4, Vite 6, Vitest + Playwright, WCAG 2.2, Core Web Vitals, Zustand/Jotai patterns |
| `js_node` | Node.js 22+ (native fetch, native test runner), ESM migration, Bun runtime, Hono vs Express vs Fastify, OpenAPI + Zod, JWT security, rate limiting |
| `go` | Go 1.22-1.23 (range-over-int, toolchain), slog structured logging, pgx v5, wire DI, Go fuzzing, goroutine leak detection, generics patterns |
| `rust` | Rust 2024 edition, async Tokio 1.x, axum patterns, serde improvements, cargo workspace, thiserror/anyhow, clippy evolution, WASM targets |
| `unknown` | 12-factor app, OpenTelemetry, GitHub Actions CI/CD, trunk-based development, API design (REST vs GraphQL vs gRPC), technical debt management |

Format each entry as:

```markdown
## [Pattern or Concept Name]

[3-5 sentences: what changed or is commonly misused, why it matters for this
stack, and one concrete action the developer should consider this week.]
```

#### Phase S3 — WRITE

Write the briefing to the research inbox:

```
path: ~/.claude/youk/knowledge/projects/{slug}/research-inbox/YYYY-MM-DD-research.md
```

File structure (identical to project-research.py output so session_start reads it):

```markdown
# Project Research — {slug} — {YYYY-MM-DD}

Stack: {stack}

---

## [Pattern Name 1]
...

## [Pattern Name 2]
...
```

Create the `research-inbox/` directory if it doesn't exist.

Emit on completion:
```
Stack briefing written: knowledge/projects/{slug}/research-inbox/{date}-research.md
{N} findings generated for {stack} stack.
session_start will surface these at your next session open.
```

#### Phase S4 — SURFACE (optional, if session_plan shows stale inbox)

If invoked because session_plan showed "N research finding(s) — call add_proposal() to queue each one":
- Read the inbox files surfaced
- For each `##` heading, offer: "Queue as proposal? (yes/skip/all)"
- For accepted items: call `youk-core.add_proposal(title, rationale, change_type, target, content)`
- `change_type` = FILE_CREATE, `target` = `knowledge/cross-project.md` for general patterns;
  SKILL_EDIT + skill name for skill-specific improvements

This phase is separate from S1-S3 — invoke with `/research stack propose` if you want to
queue inbox items without regenerating.

---

## Quality Bars (Non-Negotiable)

- **Source attribution:** Every proposal must include `source_url` in its rationale. A proposal without a URL is rejected.
- **youk-specific relevance:** Every pattern must name which youk component it improves (session_start, route_task, a specific skill, health.py, etc.). "Improves AI assistants" is not specific enough.
- **Haiku-first enforcement:** COLLECT and EXTRACT phases must not escalate to Sonnet. If a page is too complex for Haiku to parse, skip it and note in summary.
- **Dedup before propose:** Phase 3 must run before Phase 4. Never propose a pattern that already exists in PENDING.md or cross-project.md.
- **No auto-apply:** add_proposal() is called, never apply_proposal(). The founder reviews and applies.
- **Token ceiling:** total tokens for a full scan must stay ≤ 15,000. If approaching the ceiling mid-EXTRACT, stop and propose from what was collected.

### Hiring Validation

1. **Dedup test:** Cross-project.md has "Planning before execution is first-class." You find an Anthropic post saying "always plan before coding." Does this get proposed? No — it's a duplicate. The skill must detect this.
2. **Generic pattern test:** You extract "write clear prompts" from an OpenAI blog. Does it get proposed? No — no specific mechanism, not youk-specific. The skill must discard it.
3. **Token ceiling test:** After 8 URLs, token count is at 13k. Should you fetch the next 4 URLs? No — stop extract, proceed to propose from what's collected.
4. **Source escalation test:** A Karpathy GitHub README is 8,000 chars. EXTRACT reads the first 3,000. Is this correct? Yes — cap at 3,000 chars per page, don't escalate to read more.
5. **Pending overflow test:** PENDING_IDS is 7 when the skill starts. Does it silently continue? No — surfaces the count once and waits one redirect.

---

## Reference Files

| File | When to read |
|------|--------------|
| `references/sources.md` | Phase 1 — before running any searches |
| `knowledge/cross-project.md` | Context Capture + Phase 3 — for dedup |
| `knowledge/proposals/PENDING.md` | Phase 3 — for dedup |

---

## Example Flows

**Full weekly scan (no topic specified):**
> `/research`

COLLECT → searches Anthropic blog, Karpathy GitHub, OpenAI cookbook, HN for 4 default topics → 10 URLs collected.
EXTRACT → Haiku reads each, extracts 8 patterns, discards 3 as generic.
DEDUPLICATE → 1 already in cross-project.md, 1 already pending → 3 novel patterns remain.
PROPOSE → 3 add_proposal() calls, scan timestamp written.
Output: "youk-research complete. Scanned: 10 URLs. Proposed: 3. Skipped: 4."

---

**Focused scan on a specific gap:**
> `/research MCP server token efficiency`

COLLECT → searches all 4 sources for "MCP server token efficiency" → 6 focused URLs.
EXTRACT → 4 patterns, 2 discarded (generic / duplicate of Anthropic deferred tool loading pattern already in cross-project.md).
DEDUPLICATE → 2 novel.
PROPOSE → 2 proposals queued with change_type FILE_CREATE targeting cross-project.md.

---

**Skip to propose (patterns already extracted this session):**
> `/research enter: PROPOSE`

Skips COLLECT and EXTRACT. Uses patterns already identified earlier in the conversation.
DEDUPLICATE → checks PENDING.md.
PROPOSE → calls add_proposal() for each novel pattern.

---

**quick mode (weekly cron, low-cost run):**
> `/research quick`

COLLECT → Anthropic blog + HN only, 1 default topic, top 3 URLs.
EXTRACT → Haiku, 3 pages max, 1 pattern each.
PROPOSE → up to 3 proposals.
Token budget: ≤ 5,000 tokens.
