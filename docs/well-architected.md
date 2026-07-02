# youk — Well-Architected Design

## Framework choice

This document uses the **AWS Well-Architected Framework (WAF)** as the organizing structure — six pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability. It's widely understood, covers all dimensions of an operational system, and maps cleanly to youk's concerns.

Other frameworks exist and are valid:
- **Anthropic Responsible Scaling Policy (RSP)** — AI safety commitments, model capability thresholds, and deployment criteria. Relevant if youk were deployed at scale or used to train models. Not applicable here: youk is a local engineering system with no model training or public API exposure.
- **Google MERL / AI-ready infrastructure** — Focuses on ML pipelines, experiment tracking, and model serving. Not applicable here: youk routes to skills, it doesn't run ML workloads.
- **NIST AI RMF** — Risk management framework for AI systems. Partially applicable: the guardrails.yaml hard rules and `confirmed=True` gates address the governance requirements. Not formally mapped here but traceable.

**Why WAF and not the others:** youk is an operational platform, not an AI safety system or ML infrastructure project. WAF covers the six dimensions that actually matter for youk's reliability and cost. The WAF document is a **reference** — it is never loaded into session context at startup (that would be overhead for every session). It's loaded lazily: nfr_check injects 2 targeted WAF questions for M+ tasks on the youk repo itself, nothing more.

---

youk's design maps directly to the six AWS Well-Architected Framework pillars. This document makes that mapping explicit so contributors can trace why each mechanism exists and what invariant it protects.

---

## Operational Excellence

**Goal:** Run and monitor systems, continuously improve.

| Mechanism | What it does |
|---|---|
| `session_start` → `session_plan` | Every session begins with a forward-looking proposal built from structured files — not a question |
| `session_end` → audit log | Structured log entry per session (skills used, close cluster, token usage) — machine-readable, not narrative |
| `self_heal()` | Reads 30 days of audit logs, generates improvement proposals — never auto-applies |
| `compact_context` | Proactive context management; fires on events (new analysis, commit, plan shift) not exchange count |
| `doc-map.yaml` + session_plan doc-freshness | Surfaces documentation drift at session start before it accumulates |
| `task_checkpoint(session_learnings)` | Per-task learning accumulator — pattern_trigger fires when same gap appears 2+ times in session, enabling immediate mid-session adaptation rather than deferring to session end |
| `end_session` M+ skill gate | Returns skill_gate_warning when close_cluster=True but no capability skill was invoked — surfaces the gap at the moment it can still be corrected |
| Org_score discipline gate | Caps org_score at 6.5 when 3+ consecutive sessions invoke zero capability skills — forces skill engagement before 7.0+ is reachable |

**Key invariant:** `session_end` is the only path through which improvement proposals are generated. No implicit side-effects.

### Knowledge Coherence

Every concept defined in PRD.md or well-architected.md has exactly one authority file. Derived files (README, PHILOSOPHY, CLAUDE.md) reference and align to the authority — they do not redefine it. When the authority file changes, the drift surfaces within one session via `_check_doc_freshness()`.

**Key invariant:** No concept diverges silently across more than one session. Planned: `check_doc_graph()` MCP tool (see ADR-007) will make this queryable and enforce it automatically.

---

## Security

**Goal:** Protect data, systems, and assets. Detect security events.

| Mechanism | What it protects |
|---|---|
| `knowledge-extraction-not-logging` hard rule | No raw conversation transcripts ever stored — enforced at `session_end` tool level |
| `no-credential-commits` hard rule | `.env`, `*secret*`, `*api_key*` files blocked from commits at `check_commit_quality` |
| `no-auto-apply-proposals` hard rule | `apply_proposal(confirmed=True)` required — founder must explicitly approve every self-heal change |
| `check_command` | Destructive shell commands (`rm -rf`, `reset --hard`, force push) blocked until confirmed |
| `knowledge/projects/` gitignored | Per-project session state never committed to public repos — zero accidental secret exposure |

**Key invariant:** No MCP tool writes outside `/youk/` or `/claude/skills/`. Write access is scoped at the Docker volume level, not just in code.

---

## Reliability

**Goal:** Workloads perform correctly and consistently.

| Mechanism | What it protects |
|---|---|
| Docker isolation | youk-core and youk-code are independent containers — one failure doesn't cascade |
| stdio transport | No network socket, no port binding — no connection-level failures |
| `doctor.sh` | Health check with specific `Fix:` lines for every known failure mode |
| `_check_doc_freshness()` at session_start | Catches documentation drift before it causes confusion in later sessions |
| Compounding context loop | `session_end` writes `resume-from:` externally; `session_start` reads it — sessions compound without relying on Claude's context window surviving |

**Key invariant:** No session data is stored in project repos. Zero footprint. A clean `git clone` of any project repo is unaffected by youk.

---

## Performance Efficiency

**Goal:** Use resources efficiently; scale to meet demand.

| Mechanism | What it does |
|---|---|
| `route_task` ceremony sizing | XS tasks get no ceremony; XL tasks get full architecture review. Proportional cost |
| Event-based `compact_context` triggers | Compact when new context is created (after route_to_skill, after commit), not on exchange count |
| `optimize_intent` fast path | Pattern-matched intents return instantly (no API call); only truly ambiguous inputs hit the API |
| `nfr_check` size-gated questions | XS/S: 2-question instant; M: 4-question API; L/XL: full. Cost scales with risk |
| `track_tokens` | Accumulates token usage per session; `self_heal` detects over-ceremony (>2× budget) or under-ceremony (<0.5×) |

**Key invariant:** Task size is the primary gate on ceremony. A one-line bug fix (`route_task` → XS) never triggers architecture review.

---

## Cost Optimization

**Goal:** Avoid unnecessary costs. Measure and track usage.

| Mechanism | What it does |
|---|---|
| `track_tokens` + audit log `Tokens:` line | Per-session token accounting written to audit log for trend analysis |
| `self_heal` token scoring | If avg token usage > 2× budget for 2+ sessions, org_score penalty + `headroom` recommendation |
| XS bypass | XS tasks skip `route_task`, `optimize_intent`, all ceremony — zero token overhead |
| `compact_context` event triggers | Proactive compaction means shorter context windows per exchange (vs waiting for 50% fill) |
| Proposals, never auto-apply | No token spend on rejected changes — founder reviews before any self-heal action runs |

**Key invariant:** `track_tokens` is the observability floor. If it's not being called, `self_heal` flags it after 3 sessions with no token data.

---

## Sustainability

**Goal:** Minimize environmental impact of running systems.

| Mechanism | What it does |
|---|---|
| Zero footprint in project repos | `knowledge/projects/` is gitignored. No files written to downstream project repos ever |
| No global state mutation without approval | `apply_proposal(confirmed=True)` is the only path to persistent change in youk's knowledge base |
| Knowledge extracted, not stored | Session insights are extracted to structured files; raw conversation is discarded |
| Single binary per variant | Each youk variant is one Docker image. No multi-process sprawl |
| `compact_context` from files | Briefs are rebuilt from structured files, not stored as conversation snapshots — no dead state accumulates |

**Key invariant:** Every write to `~/.claude/youk/` is either ephemeral state (`state/`) or explicit knowledge extraction. Nothing grows unbounded without a purge mechanism.

---

## Design decisions that satisfy multiple pillars

| Decision | Pillars |
|---|---|
| Docker + MCP stdio transport | Security (no network exposure), Reliability (isolation), Sustainability (single process per variant) |
| Proposals require `confirmed=True` | Security (no auto-apply), Operational Excellence (founder in loop), Cost (no wasted token spend) |
| `session_end` extracts, not logs | Security (no transcripts), Reliability (structured audit), Operational Excellence (machine-readable) |
| `knowledge/projects/` gitignored | Security (no accidental exposure), Reliability (no cross-install contamination), Sustainability (zero footprint) |

---

## MCP access hierarchy

youk enforces access control at the Docker volume layer, not just in code. This is the only trustworthy boundary — code-level checks can be bypassed, but a container without a write mount cannot write.

```
┌─────────────────────────────────────────────────────────────┐
│  Access level    │  Container     │  Mounts                 │
│──────────────────┼────────────────┼─────────────────────────│
│  Read-write      │  youk-core     │  ~/.claude (rw)         │
│                  │                │  project dir (ro)       │
│──────────────────┼────────────────┼─────────────────────────│
│  Read-only       │  youk-code     │  ~/.claude (ro)         │
│                  │                │  project dir (ro)       │
│──────────────────┼────────────────┼─────────────────────────│
│  No access       │  either        │  ~/   (not mounted)     │
│                  │                │  /etc, /tmp, /usr       │
└─────────────────────────────────────────────────────────────┘
```

**Hard constraints (tool-level enforcement):**
- `apply_proposal(confirmed=True)` required — no auto-apply, ever
- `check_knowledge_write(content)` blocks transcript storage at `session_end`
- `check_command(command)` blocks destructive shell ops without confirmation
- `check_commit_quality(...)` blocks credential files at commit time

**Soft constraints (surfaced once, deferred to founder):**
- NFR check before M+ tasks
- Spec before L/XL tasks
- Session-close cluster (context-sync + learn + humanize) at session end
- ADR for decisions with real alternatives

Soft constraints appear in `route_task().warnings` and `session_plan`. They are never enforced — the founder has final say. Hard constraints return `blocked: True` from the tool and stop execution.

**Within-session write scope for youk-core:**

| Path | What writes there | Cleared when |
|---|---|---|
| `~/.claude/youk/state/` | session.json, session-plan.json, current-session-tokens.json | session_start (reset), session_end (clear tokens) |
| `~/.claude/youk/knowledge/projects/{slug}/` | context.md, contracts.md, decisions.md | Accumulates; pruned manually |
| `~/.claude/audit/` | YYYY-MM.md audit log | Accumulates; feeds self_heal for 30-day window |
| `~/.claude/youk/knowledge/proposals/` | PENDING.md | Cleared by apply_proposal |
