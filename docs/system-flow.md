# youk System Flow

For developers using youk across multiple projects who want to understand how the system chooses and runs workflows.

---

## What youk is

youk is an always-on engineering system running as two persistent HTTP servers managed by launchd: **youk-core** (port 8001) and **youk-code** (port 8002). It does not wait to be invited — it routes every task, enforces gates, and records learning automatically. The developer's job is to work; youk's job is to make that work compound.

Every session produces: a resume point (what was in progress), a session plan (what to do next), and — if `/done` fires — updated domain knowledge and improvement proposals. These accumulate across sessions on all projects.

---

## How a task flows through the system

```
Developer input
      │
      ▼
  session_start()
  ┌─────────────────────────────────────────────────────┐
  │ Loads: contracts, project context, resume point,    │
  │ pending proposals, doc-freshness alerts             │
  │ Writes: state/sessions/{slug}/open.json             │
  └─────────────────────────────────────────────────────┘
      │
      ▼
  Task size detection
  ┌─────────┬──────────┬──────────┐
  XS/S      M          L          XL
  │         │          │          │
  dev-loop  ▼          ▼          ▼
  only   gate chain  gate chain  gate chain
         (6 steps)   + adversary-loop
      │
      ▼ (M+ gate chain)
  optimize_intent() → [intake if ambiguous]
      │
  route_task() → plan_hook + overengineering_flag
      │
  challenge() or adversary-loop()
      │
  nfr_check()
      │
  check_nfr_gate() → [re-run nfr_check if blocked]
      │
  check_challenge_gate() → [re-run challenge if blocked]
      │
  dev-loop()
      │
  [implementation]
      │
  coverage-tree() + task_checkpoint()
      │
  code-review()
      │
  session_end() → audit log + pre-close snapshot
```

**Size guide:** XS = typo/rename/one-liner. S = single-file fix. M = multi-file feature. L = cross-system change. XL = architecture/new subsystem.

Hard rule: for M+ tasks, the gate chain must complete before implementation starts. Gates are not ceremony — they are the mechanism that prevents solving the wrong problem.

---

## How the system decides which skill to run

`route_to_skill(skill_name, task)` returns `{mode: "in_session", skill_content}`. The skill content is a SKILL.md file — a text prompt executed in-session. No separate agent is spawned; no API call is made. Skills are files, not services.

| Skill | Triggered by | What it does |
|---|---|---|
| `session` | Every session start | Loads brief, surfaces resume point, detects force_learn |
| `challenge` | M/S tasks; /challenge | Tests "are we solving the right problem?" across 3 lenses |
| `adversary-loop` | L/XL tasks | Multi-angle attack on the plan: frames, devil's advocate, hard constraints |
| `nfr_check` | M+ tasks | 4-question reliability/maintainability audit |
| `dev-loop` | Every implementation task | Breaks work into deliverables, registers in task graph |
| `coverage-tree` | After implementation | MECE coverage map of what was built vs. what should be tested |
| `code-review` | /done, /check | Reviews diff for correctness, security, complexity |
| `learn` | /done, force_learn=True at next session_start | Extracts domain knowledge, updates concept graph |
| `verify` | /done | Confirms tests pass, lint clean, no regressions |

---

## State isolation — how multi-project sessions work

```
~/.claude/youk/state/
  sessions/
    youk/                 ← all youk session state
      open.json           ← active session marker (written_at: epoch)
      challenge-ran.json
      nfr-check-ran.json
      route-task-ran.json
      routing-breadcrumb.json
      session-plan.json
      active_task.json
      pre-close.json      ← written by session_end, consumed by next session_start
    canopy/               ← all canopy session state (completely separate)
      open.json
      ...
  task-graph.db           ← shared SQLite, WAL mode (concurrent-read safe)
  knowledge/
    projects/
      youk/               ← youk contracts, decisions, context
      canopy/             ← canopy contracts, decisions, context
```

Each project's session lives in its own slug-scoped directory. Opening a canopy window does not touch youk's state. Slug resolution reads `state/sessions/*/open.json` by mtime, with a 4-hour staleness gate — entries older than 4 hours are skipped so stale test artifacts cannot confuse production slug detection.

The only shared resource is `task-graph.db` which runs in WAL (write-ahead log) mode, allowing concurrent reads alongside writes without blocking.

Writes to shared gate flag files use `fcntl.flock()` advisory locks, preventing corruption from concurrent async handler calls within the same server process.

---

## The learning loop — how knowledge compounds

1. **At `/done`:** `learn` skill fires → knowledge domain files updated → concept graph populated → improvement proposals added to `PENDING.md`
2. **If session dropped without `/done`:** `session_end()` writes `pre-close.json` with skills invoked, task labels, commits made. Next `session_start()` detects it → runs `/learn quick` automatically → 5-bullet micro-brief extracted before new session plan loads
3. **Every session via `/improve`:** `self_heal()` reads 30 days of audit logs → generates improvement proposals → developer reviews and applies approved ones

---

## What youk does not do

- Does not auto-commit, auto-push, or modify external systems without explicit developer action
- Does not read `.env` files or secrets — API keys are always supplied by the developer's terminal session
- Does not spawn background agents or make API calls outside of the current session
- Does not decide task size for XL based on LOC — only on cross-system blast radius (ADR-007 heuristic)
- Does not bleed state between projects — each project's gate flags are isolated in `state/sessions/{slug}/`
