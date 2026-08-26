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
| `doc-map.yaml` + session_plan doc-freshness | Surfaces documentation drift at session start before it accumulates. Four checks: timestamp drift, broken links, orphaned concepts, invariant match. |
| `task_checkpoint(session_learnings)` | Per-task learning accumulator — pattern_trigger fires when same gap appears 2+ times in session, enabling immediate mid-session adaptation rather than deferring to session end |
| `end_session` M+ skill gate | Returns skill_gate_warning when close_cluster=True but no capability skill was invoked — surfaces the gap at the moment it can still be corrected |
| Org_score discipline gate | Caps org_score at 6.5 when 3+ consecutive sessions invoke zero capability skills — forces skill engagement before 7.0+ is reachable |
| Org_score formula (derived from `servers/core/src/health.py`) | 5.0 base + capability_skill_rate×2.0 + close_rate×0.5 + gap_resolution×0.5 + prevented_cost×0.5 + framing_accuracy×0.5 + autonomy_depth×1.0 + loop_dry_rate×1.0 + human_precision×0.5 + convergence_bonus(0.5 max) + durability_bonus(±0.25) + outcome_signal×0.5 + outcome_quality×0.5 − compliance_penalty(0.5 max); multiplied by depth_multiplier; ceiling 10.0 |
| `ceremony_sequencer.py` | Tracks gate order per session slug (`ceremony_sequencer`). Warns if `check_nfr_gate` fires before `mark_challenge_ran`, or `task_checkpoint` fires without dev-loop registration. Python-enforced, not prompt-only. |
| `scan_failure_patterns()` | Scans `~/.claude/audit/` for recurring `FindingCategories` entries across sessions. When a domain hits threshold (default 3), surfaces `⚠ PATTERN:` alert in `session_plan` before the developer starts a 4th attempt in a failing domain. |
| `reentry_suggestion` in `write_skill_handoff` | `check_reentry()` reads `skill-graph.yaml` reentry edges. If handoff severity meets edge threshold (e.g. code-review finds HIGH → suggest re-entering nfr-check), returns `reentry_suggestion` in the handoff result. |
| `translation_risk=medium` soft block | `route_task` produces `SoftRuleWarning(rule_id="medium-translation-risk")` and writes `medium-risk-question.json`. `mark_medium_risk_surfaced()` confirms the question reached the user. `task_checkpoint` flags `medium_risk_unsurfaced=True` if it didn't. |

**Key invariant:** `session_end` is the only path through which improvement proposals are generated. No implicit side-effects.

### Knowledge Coherence

Every concept defined in PRD.md or well-architected.md has exactly one authority file. Derived files (README, PHILOSOPHY, CLAUDE.md) reference and align to the authority — they do not redefine it. When the authority file changes, drift surfaces within one session via `_check_doc_freshness()`.

`check_doc_graph()` runs four checks: timestamp drift (authority newer than derived), broken links (derived file deleted), orphaned concepts (authority deleted), and invariant match (per-concept string must appear in all derived files). New docs in `docs/` that are not referenced anywhere in `doc-map.yaml` surface as untracked. Verdict: `COHERENT` / `DRIFT` / `BROKEN`.

**Key invariant:** No concept diverges silently across more than one session. `check_doc_graph()` is queryable as an MCP tool and runs automatically in `/done`.

---

## Security

**Goal:** Protect data, systems, and assets. Detect security events.

| Mechanism | What it protects |
|---|---|
| `knowledge-extraction-not-logging` hard rule | No raw conversation transcripts ever stored — enforced at `session_end` tool level |
| `no-credential-commits` hard rule | `.env`, `*secret*`, `*api_key*` files blocked from commits at `check_commit_quality` |
| `no-auto-apply-proposals` hard rule | `apply_proposal(confirmed=True)` required — founder must explicitly approve every self-heal change |
| `no-destructive-without-confirm` hard rule | `rm -rf`, `DROP TABLE`, `reset --hard`, `--no-verify` require explicit per-operation confirmation — enforced by `check_command` |
| `lint-before-commit` hard rule | `ruff check servers/` + `pytest tests/` must pass before any commit — enforced by `.git/hooks/pre-commit`; `--no-verify` is itself blocked by `check_command` |
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
| `make checkup` (L0–L6) | Hierarchical integration test suite — each layer gates the next; L3 exercises all 53 capability skills via real MCP, L5 tests gate contracts and proposal lifecycle, L6 runs a full session round-trip |
| `make checkup-fast` | L0+L1 only — environment + Docker + MCP handshake; replaces `make doctor` for quick infra checks |
| `_check_doc_freshness()` at session_start | Catches documentation drift before it causes confusion in later sessions |
| Compounding context loop | `session_end` writes `resume-from:` externally; `session_start` reads it — sessions compound without relying on Claude's context window surviving |
| Validated state store | Mutable-claim state (plan, active task, queue, gate flags) is schema-validated on read and write in a single store — a malformed write raises rather than silently corrupting. Append-only logs and monotonic counters stay out; they cannot lie, only grow |
| Read-time verification | A stored claim about system state ("X is broken", "gap open") is re-checked against current code before session_start surfaces it as live — a fixed issue never resurfaces as a to-do, and a claim that cannot be verified surfaces tagged, never as a clean item |
| Project-scoped next task | "What's next" is computed at session_end from the project's own validated task graph and written automatically — scoped to the project youk is in, never a generic cross-project list, never a manual pointer edit |
| Wiring pulse | Every session_start checks whether each capability youk built is actually invoked in the live loop (CLAUDE.md routing, session code, another tool, or a skill) — not merely defined and tested. A tool referenced nowhere is orphaned and surfaced loudly. Unit tests verify a part works; the pulse verifies it is reached. Autoruns unconditionally, so built-but-not-wired fails fast instead of becoming late tech debt |

**Key invariant:** No session data is stored in project repos. Zero footprint. A clean `git clone` of any project repo is unaffected by youk.

**Reliability requirement (not yet fully built — see `knowledge/domain/self-evolution-build-plan.md`):** persisted state must be validated, single-sourced, self-verifying at read, and project-scoped. State stored as unschematized loose files with no read-time verification is how a compounding system quietly stops compounding — fixed issues resurface and queued work evaporates. The compounding-context loop above is only as trustworthy as the store underneath it.

---

## Performance Efficiency

**Goal:** Use resources efficiently; scale to meet demand.

| Mechanism | What it does |
|---|---|
| `route_task` ceremony sizing | XS tasks get no ceremony; XL tasks get full architecture review. Proportional cost |
| Hook-based context management | `UserPromptSubmit` hook injects intent-gated brief (~100-200 tokens) before each turn; `PreCompact` hook injects preservation brief before auto-compact; `PostToolUse` hook captures active task state continuously |
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
| `UserPromptSubmit` hook context pressure signal | Triggers `/compact` at 40% context fill vs waiting for auto-compact at 70% — reduces per-inference token cost 3-4× in heavy sessions |
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
| Hook-driven write-first discipline | `PostToolUse` hook externalizes active task state after every tool call; context can be cleared at any time without losing work state |

**Key invariant:** Every write to `~/.claude/youk/` is either ephemeral state (`state/`) or explicit knowledge extraction. Nothing grows unbounded without a purge mechanism.

---

## Design decisions that satisfy multiple pillars

| Decision | Pillars |
|---|---|
| Docker + MCP stdio transport | Security (no network exposure), Reliability (isolation), Sustainability (single process per variant) |
| Proposals require `confirmed=True` | Security (no auto-apply), Operational Excellence (founder in loop), Cost (no wasted token spend) |
| `session_end` extracts, not logs | Security (no transcripts), Reliability (structured audit), Operational Excellence (machine-readable) |
| `knowledge/projects/` gitignored | Security (no accidental exposure), Reliability (no cross-install contamination), Sustainability (zero footprint) |

### Steer the model in its own terms, not with personas

A quality label — "senior engineer", "rigorous", "thorough", "L9" — is a compressed human pointer to a region of the model's behavior. Prompting the model *with* the label asks it to reconstruct that region from a stereotype, which is lossy. The model has direct access to what the label resolves to, and that resolution is task-relative: "rigorous" means one set of behaviors for a code review and a different set for an estimate. So youk's design goal is to resolve a steering label to the specific behaviors the task needs at the point of use, rather than freezing one label — or one fixed decomposition of it — into a prompt. A frozen decomposition is just a richer stereotype; it is still lossy in the next context.

The stronger form, which youk builds toward: do not trust the model's description of its own good behavior, and do not treat natural language as the only steering channel. Steer by what verifiably worked — concrete past outputs that passed an objective check or a developer's judgment — conditioned back as examples. This only holds if those examples are outcome-filtered (verified-good only) and sourced from the ceiling (the model's best output under pressure, plus developer corrections), never from the system's own averaged history. A system that conditions on its own mediocre past teaches itself to stay mediocre. (Design detail: `knowledge/domain/self-evolution-build-plan.md`; runs on the self-revision meta-loop, not as a parallel mechanism.)

**How this is wired (built, not aspirational):** the steering vocabulary is live via two tools. Before steering on a quality label, call `get_steering_vocab(label)` — if it returns `learned=True`, steer with those concrete, confidence-weighted behaviors; if `learned=False`, elicit a fresh decomposition from the model for *this* task and record it, never fall back to the bare-label stereotype. After work completes, call `record_steering_decomposition(label, behavior, task_context, confidence)` with an honest confidence (`verified` if the work passed an objective check, `approved` if the developer accepted it, `corrected` if they rejected it). New skills should reach for this instead of inventing a persona label. Confidence is a read-time weight, so the strict/lenient balance is tunable without discarding recorded data.

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
