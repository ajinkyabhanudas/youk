# youk System Wiring

> The vein-and-artery map. Every component, every connection, every data flow.
> This is the source of truth for how the system talks to itself.
> Keep this current when wiring changes — stale maps cause wrong debugging paths.

---

## Architecture: Two Containers, One State Volume

```
┌──────────────────────────────────────────────────────────────────────┐
│  Claude (in-session)                                                 │
│    ↕ streamable-HTTP / MCP JSON-RPC                                  │
│                                                                      │
│  ┌─────────────────────┐      ┌─────────────────────┐               │
│  │  youk-core:8001     │      │  youk-code:8002     │               │
│  │  (Docker container) │      │  (Docker container) │               │
│  │                     │      │                     │               │
│  │  server.py          │      │  server.py          │               │
│  │  ├─ session.py      │      │  ├─ skills.py       │               │
│  │  ├─ routing.py      │      │  ├─ skill_gen.py    │               │
│  │  ├─ health.py       │      │  ├─ nfr.py          │               │
│  │  ├─ state_paths.py  │      │  ├─ review.py       │               │
│  │  ├─ session_slug.py │      │  ├─ skill_loader.py │               │
│  │  ├─ graph.py        │      │  └─ contract_verifier.py            │
│  │  ├─ compaction.py   │      │                     │               │
│  │  ├─ challenge_gate.py│     └─────────────────────┘               │
│  │  ├─ nfr_gate.py     │                ↕                           │
│  │  ├─ intake_gate.py  │      shared: /youk/state/ (volume mount)   │
│  │  ├─ intent.py       │                                            │
│  │  ├─ knowledge_index.py│                                          │
│  │  ├─ file_index.py   │                                            │
│  │  ├─ concept_graph.py│                                            │
│  │  ├─ revisable_sets.py│                                           │
│  │  ├─ skill_signals.py│                                            │
│  │  └─ tokens.py       │                                            │
│  └─────────────────────┘                                            │
│                                                                      │
│  launchd manages both servers — they restart automatically on crash  │
└──────────────────────────────────────────────────────────────────────┘
```

Both containers mount the same host directory at `/youk/state/`. This shared volume is the only channel between them — no inter-container network calls.

---

## youk-core: Module Wiring

```
server.py (MCP tool surface — Claude calls these)
│
├── session.py
│   ├── state_paths.py          ← slug-scoped path resolution (SINGLE AUTHORITY)
│   ├── compaction.py           ← build_brief, write_contracts
│   ├── models.py               ← SessionState schema
│   └── tokens.py               ← read_and_clear
│
├── routing.py                  ← route_task logic, size + ceremony detection
│
├── health.py                   ← self_heal, org_score, wiring_pulse, doc_regen,
│   ├─ wiring_pulse.py          │  docker_bloat_pulse, personal_data_pulse
│   ├─ doc_regen.py             │
│   ├─ docker_bloat_pulse.py    │
│   └─ personal_data_pulse.py   │
│
├── state_paths.py              ← slug_state_dir, current_session_slug, atomic_write
├── session_slug.py             ← delegates to state_paths.current_session_slug()
│
├── challenge_gate.py           ← check_challenge_gate (pure function)
├── nfr_gate.py                 ← check_nfr_gate (pure function)
├── intake_gate.py              ← check_intake_gate (pure function)
│
├── intent.py                   ← optimize_intent
├── compaction.py               ← build_brief, write_contracts
│
├── graph.py                    ← task-graph.db (SQLite WAL), task nodes/edges
│
├── file_index.py               ← project file indexing, find_relevant, find_related_docs
├── knowledge_index.py          ← knowledge/ file search, rebuild_knowledge_index
├── concept_graph.py            ← cross-session concept graph (SQLite)
│
├── revisable_sets.py           ← enroll/propose/apply judgment set revisions
├── revision_detectors.py       ← auto-detect revisable pattern candidates
├── skill_signals.py            ← get_skill_signals, get_steering_vocab, detect patterns
├── steering_vocab.py           ← steering vocabulary management
│
├── guardrails.py (shared)      ← hard rule enforcement (knowledge writes, destructive cmds)
├── models.py (shared)          ← SessionState, RouteResult, shared schemas
├── skill_loader.py (shared)    ← SKILL.md file loading (used by youk-code)
└── state_schema.py (shared)    ← state file schemas
```

---

## youk-code: Module Wiring

```
server.py (MCP tool surface)
│
├── skills.py                   ← route_to_skill, write_skill_handoff, mark_rationale_preempted
│   └── skill_loader.py (shared)← loads SKILL.md files from skills/ directory
│
├── skill_gen.py                ← generate_skill, assess_skill, detect_skill_gaps,
│                                  generate_stack_overlay, analyze_stack_for_skills
│
├── nfr.py                      ← run_nfr_check (4-question NFR audit)
│
├── review.py                   ← check_commit_quality (diff analysis)
│
└── contract_verifier.py        ← verify_contracts (pre-commit hook support)
```

---

## State: What Lives Where

```
/youk/state/
  sessions/
    {slug}/                     ← one dir per project slug
      open.json                 ← active session marker {slug, written_at}
      challenge-ran.json        ← gate flag: challenge fired this session
      nfr-check-ran.json        ← gate flag: nfr_check fired this session
      route-task-ran.json       ← gate flag: route_task fired + what it returned
      challenge-gate-passed.json← gate flag: check_challenge_gate returned unblocked
      intake-ran.json           ← gate flag: intake skill fired this session
      routing-breadcrumb.json   ← last route_task result for this session
      loop-correction.json      ← loop correction state
      active_task.json          ← current task, routing_context, files touched
      session-plan.json         ← session plan items
      pre-close.json            ← written by session_end, consumed by next session_start
      convergence-state.json    ← iterative convergence tracking
      pending-action.json       ← deferred pending action
      session-goal.json         ← stated goal for drift detection
  session-open.json             ← REDIRECT POINTER ONLY {active_slug, open_at}
                                   never used for slug resolution
  session.json                  ← persistent session counter, org_score history
  task-graph.db                 ← SQLite WAL: task nodes, edges, dependency graph
  knowledge/
    projects/{slug}/            ← per-project contracts, decisions, context
    domain/                     ← accumulated domain knowledge from /learn
    user-profile.md             ← observed developer depth across domains
  active_task.json              ← fallback only: used when no slug is active
  loop-correction.json          ← root fallback (slug-scoped preferred)
```

**Slug resolution rule:** `state_paths.current_session_slug()` reads `sessions/*/open.json` sorted by mtime descending, skips entries older than 4 hours, returns the slug from the first valid entry. Returns `"unknown"` if none found. Called by both `session.py` and `server.py` via `state_paths`.

---

## MCP Tool Surface: What Claude Calls

### youk-core tools
| Tool | Module | What it does |
|---|---|---|
| `session_start` | server.py → session.py | Loads context, writes sessions/{slug}/open.json, returns brief |
| `session_end` | server.py → session.py | Writes audit, deletes session open.json, returns delta |
| `route_task` | server.py → routing.py | Size + ceremony detection, writes gate flags |
| `optimize_intent` | server.py → intent.py | Clarifies vague goals before routing |
| `check_nfr_gate` | server.py → nfr_gate.py | Blocks M+ until NFR decisions are made |
| `check_challenge_gate` | server.py → challenge_gate.py | Blocks M+ until challenge ran for current slug |
| `check_intake_gate` | server.py → intake_gate.py | Blocks when intake_required=True |
| `mark_challenge_ran` | server.py (inline) | Writes challenge-ran.json under sessions/{slug}/ |
| `task_checkpoint` | server.py → session.py | Mid-task progress + pattern detection |
| `compact_context` | server.py → compaction.py | Writes tiered context brief |
| `self_heal` | server.py → health.py | org_score, proposals, wiring check |
| `save_contract` | server.py → compaction.py | Persists behavioral contracts |
| `add_proposal` | server.py (inline) | Queues improvement to PENDING.md |
| `apply_proposal` | server.py (inline) | Applies approved proposal from PENDING.md |
| `create_task_graph` | server.py → graph.py | Creates task DAG in SQLite |
| `mark_task_done` | server.py → graph.py | Marks node done, unblocks children |
| `find_relevant` | server.py → file_index.py | Semantic file search |
| `query_concept_graph` | server.py → concept_graph.py | Cross-session pattern lookup |
| `track_tokens` | server.py → tokens.py | Token budget tracking |

### youk-code tools
| Tool | Module | What it does |
|---|---|---|
| `route_to_skill` | server.py → skills.py | Returns skill_content from SKILL.md |
| `nfr_check` | server.py → nfr.py | 4-question NFR audit output |
| `generate_skill` | server.py → skill_gen.py | Creates new SKILL.md from patterns |
| `assess_skill` | server.py → skill_gen.py | Quality assessment of existing skill |
| `detect_skill_gaps` | server.py → skill_gen.py | Finds patterns with no matching skill |
| `check_commit_quality` | server.py → review.py | Pre-commit diff quality check |
| `list_skills` | server.py → skill_loader.py | Lists available skills |
| `write_skill_handoff` | server.py → skills.py | Passes structured output between skills |

---

## Data Flow: session_start → route_task → session_end

```
Claude calls session_start(project_dir)
  → server.py: resolves slug from project_dir path basename
  → session.py: start_session()
      reads: state/session.json (counter), state/knowledge/projects/{slug}/
      writes: state/sessions/{slug}/open.json  (via state_paths.atomic_write)
              state/session-open.json  (redirect pointer only)
  → returns: brief (verbatim paste), session_plan, resume_point

Claude calls route_task(task, project_dir)
  → server.py: _get_session_slug() → state_paths.current_session_slug()
  → routing.py: _route_task() → size, ceremony, plan_hook, blocked
  → server.py: _enrich_route_result_impl() → adds skill routing, graph_state
  → server.py: writes state/sessions/{slug}/route-task-ran.json  (via atomic_write)
  → session.py: write_routing_context() → state/sessions/{slug}/active_task.json
  → returns: RouteResult with size, ceremony, plan_hook, blocked, skill_routing

[M+ gate chain fires — challenge, nfr_check, check_nfr_gate, check_challenge_gate]
  Each gate check reads slug via state_paths.current_session_slug()
  Each gate flag writes to state/sessions/{slug}/ (not state/ root)

Claude calls session_end(summary, commits_made, close_cluster)
  → server.py → session.py: end_session()
      deletes: state/sessions/{slug}/open.json
               state/sessions/{slug}/challenge-ran.json (and other session flags)
      writes:  state/sessions/{slug}/pre-close.json (if commits or skills fired)
               state/session.json (updated counter, org_score)
               state/knowledge/projects/{slug}/ (contracts, decisions)
  → returns: session_delta block
```

---

## How skill content reaches Claude

```
Claude calls route_to_skill("challenge", task)   [youk-code:8002]
  → skills.py: loads skills/challenge/SKILL.md from filesystem
  → returns: {mode: "in_session", skill_content: "<full SKILL.md text>"}

Claude executes the skill_content as a prompt to itself.
No agent is spawned. No separate API call. The skill is a text prompt.
```

Skills are discovered from `~/.claude/skills/{name}/SKILL.md`. The skill loader scans this directory. When Claude Code runs route_to_skill, the skill file content is returned and Claude runs it in the current session context.

---

## Isolation Invariant (multi-project sessions)

The isolation invariant is maintained by `state_paths.py`. Any code that reads or writes per-session state **must** go through:
- `state_paths.slug_state_dir(slug)` to get the path
- `state_paths.atomic_write(path, data)` to write it

Bypassing these (e.g., writing directly to `YOUK_ROOT / "state" / "challenge-ran.json"`) breaks the invariant and causes cross-project bleed. The root-level `state/session-open.json` is a redirect pointer (for the `_live_session_running()` guard only) — never read for slug resolution.

---

## What youk does NOT do

- Does not auto-commit, auto-push, or modify external systems without explicit developer action
- Does not read `.env` files or secrets — API keys stay in the developer's terminal session
- Does not make inter-container network calls — shared state is file-based via the mounted volume
- Does not spawn background agents or make API calls outside of the current session
- Does not decide task size for XL based on LOC — only on cross-system blast radius (ADR-007)
- Does not bleed state between projects — each project's gate flags are isolated in `state/sessions/{slug}/`
