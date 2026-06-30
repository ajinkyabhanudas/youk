---
name: context-sync
description: >
  Hierarchical context manager. Maintains a 4-level context hierarchy across sessions:
  global user memory → project context → session state → feature scope. Enforces
  reference-over-inline loading to minimize token usage. Prunes stale context. Flushes
  session learnings back to the appropriate level at session end. Triggers on: session
  start, session end, before spawning any sub-agent, when context feels bloated or
  stale, "sync context", "clean up context", "what's in context", or any time the
  same information is being re-derived that should already be loaded.
---

# context-sync — Hierarchical Context Manager

A session-management skill that keeps context clean, hierarchical, token-efficient,
and current. Context is the shared memory of a development session — when it is
bloated with stale information or missing the right information, every decision
that follows is worse.

Built on the principle that context at the wrong level of abstraction is worse than
no context: loading a 500-line architecture doc when you need one env var wastes
tokens and buries the relevant detail.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| `start` | Session start: load L1 + L2, health-check context, report status |
| `end` | Session end: flush learnings to appropriate level, prune session state |
| `audit` | Standalone audit of current context state — what's loaded, what's stale |
| `load: L{N}` | Load a specific context level on demand |
| `prune` | Remove stale or redundant context, replace with references |
| `flush` | Write session learnings back to project context (L2 / L3) |
| `scope: [feature]` | Create L4 scope for a specific feature being worked on |
| `clear: L{N}` | Clear a specific context level (with confirmation for L1/L2) |

---

## The 4-Level Hierarchy

Read `references/context-hierarchy.md` for full detail on what belongs at each level.

```
L1 — Global User Memory
     Location: ~/.claude/projects/[project]/memory/*.md
     Content:  User profile, feedback, preferences, cross-project knowledge
     Load:     Session start; read-only during session
     Update:   Only by /learn at session end; never inline

L2 — Project Context
     Location: .claude/[project]-context.md
     Content:  Architecture, design decisions, env vars, test patterns, security rules
     Load:     Session start; reference (don't inline) during session
     Update:   After any architecture change, new module, env var change

L3 — Sprint / Task State
     Location: .claude/prd-status.md
     Content:  Current sprint goals, what's done, what's next, resume prompt
     Load:     Start of each working session; reference during session
     Update:   After each build step completes

L4 — Feature Scope
     Location: In-session only (not persisted)
     Content:  The specific task being worked on, active NFR decisions, active ADR
     Load:     Created when feature work begins
     Update:   Throughout the feature session
     Flush:    Key decisions pushed to L2 at session end
```

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — AUDIT

Inventory what is currently loaded in context:

1. List all files that have been read or referenced this session
2. Identify which context level each belongs to
3. Flag any content that has been inlined that could be referenced instead
4. Estimate token cost of current context (see `references/token-patterns.md`)
5. Identify stale items: content that was relevant earlier but is no longer active

Emit:
```
[CONTEXT AUDIT]
Loaded:
  L1: {list of memory files loaded or referenced}
  L2: {project context file — path}
  L3: {prd-status — path}
  L4: {active feature scope — description or "none"}

Token estimate: ~{N} tokens in active context
Stale items: {list any content no longer needed for current task}
Inline content that should be references: {list any files whose full content was inlined}
Health: CLEAN | BLOATED | STALE | MISSING CRITICAL
```

---

### Phase 2 — LOAD

Load the appropriate context level for the current task:

**At session start (load L1 + L2 + L3):**
1. Read memory index (`MEMORY.md`) — note which memory files are relevant
2. Read L2 project context — do not re-derive what's already documented
3. Read L3 sprint state — pick up exactly where the last session left off
4. Report: "Loaded. Resuming from: [resume prompt from prd-status.md]"

**At feature start (load L4):**
1. State the feature in one sentence
2. Load the NFR Decision Block for this feature (if it exists)
3. Load relevant ADRs (by ID reference, not full content)
4. State what information from L2 is most relevant to this feature

**On demand (load specific section):**
- If a specific piece of L2 information is needed, reference its section by heading
- Never re-read the full L2 file to find one fact — reference the section

---

### Phase 3 — PRUNE

Remove context that is no longer needed or that is duplicated.

**Prune triggers:**
- A file was read in full but only one section was needed → note the section reference, not the full file
- A decision was debated and resolved → remove the debate, keep the decision
- A code example was shared for context → remove after it's been used
- An error message was shared for debugging → remove after the bug is fixed
- Information is duplicated across L1 and L2 → keep at the more specific level

**Prune rule:** If removing this context would require re-deriving a fact rather than
re-reading a reference, don't prune it. If removing it just means loading the right
file when needed, prune it.

Emit a prune report:
```
[PRUNED]
Removed: {what was removed}
Replaced with reference to: {file:section}
Token savings: ~{N} tokens
```

---

### Phase 4 — HEALTH

After AUDIT + LOAD + PRUNE, report the context health state:

```
[CONTEXT HEALTH]
Status: CLEAN | BLOATED | STALE | MISSING CRITICAL

CLEAN: Context is appropriately loaded for the current task.
  Loaded levels: {list}
  Token estimate: ~{N} tokens
  Recommended action: none

BLOATED: Too much context is loaded for the current task.
  Over-loaded items: {list}
  Recommended action: prune {list}

STALE: Context has information that has been superseded.
  Stale items: {list with what superseded them}
  Recommended action: update {file:section} with {new information}

MISSING CRITICAL: Key context for the current task is not loaded.
  Missing: {list — what's needed and where to find it}
  Recommended action: load {file:section}
```

---

### Phase 5 — FLUSH

At session end, persist valuable session learnings back to the appropriate level.
Then write one audit log entry. The audit entry is compact — it must not add meaningful
token cost. Write it last, after all context updates are done.

**What to flush:**
- New architectural decisions → L2 project context (canopy-context.md)
- New NFR decisions → L2 (and reference in prd-status.md if P0)
- Completed build steps → L3 (prd-status.md)

**Audit log entry (always, at session end):**

Location: `.claude/audit/YYYY-MM.md` (one file per month, append-only)

Format — keep it under 10 lines:
```
### {YYYY-MM-DD}
Project: {name}
Built:   {one-line description of what was done}
Skills:  {list of skills invoked, in order}
Quality: {N}/{M} outputs accepted first-pass (no revision needed)
Score:   {session health score}/10 — {one-word reason: CLEAN/SLOW/BLOCKED/REWORK}
Insight: {one sentence — what should change or what worked well}
Gap:     {any skill miss observed — or "none"}
```

Token note: the audit entry is ~120 tokens. Always write it. Do not skip for token reasons —
the audit accumulates the org's institutional memory. Skipping breaks the performance review.

If `.claude/audit/` does not exist, create it silently before writing.
- New patterns that apply across sessions → L2 (patterns section)
- Genuine knowledge learnings → flag for /learn to process

**What NOT to flush:**
- Debugging dead-ends (not useful to future sessions)
- Intermediate reasoning (only the conclusion matters)
- Content that is derivable from the code (don't duplicate code in context)
- Resolved errors (unless the error pattern is likely to recur)

Emit a flush report:
```
[FLUSHED]
To L2 ({file}):
  - {what was added / updated}

To L3 ({file}):
  - {what was added / updated}

Flagged for /learn:
  - {any genuine knowledge learnings to process}

Session state cleared.
```

---

## Quality Bars (Non-Negotiable)

- **Never inline a file that can be referenced.** "Read references/best-practices.md section 3" is better than pasting its contents into context.
- **L1 is read-only during a session.** Only /learn updates L1 at session end.
- **L4 must not bleed into L2 until the feature is complete.** Don't pollute the project context with in-progress feature decisions.
- **FLUSH is mandatory at the end of any session where an architectural decision was made.** Decisions that aren't flushed are lost.
- **Re-deriving a fact that's already in L2 is a failure mode.** If you catch yourself re-analyzing something that's documented in canopy-context.md, stop and read L2 instead.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Reference test**: Given a task that requires knowing the DB schema, it references `.claude/canopy-context.md` → Architecture section, rather than re-reading schema.py and deriving the schema again.
2. **Stale detection**: Given a context that contains an old NFR decision that was revised this session, it flags the old decision as stale and updates the reference.
3. **Flush completeness**: After a session where a new module was added, it ensures canopy-context.md is updated with the new module before marking the session complete.
4. **Token awareness**: On a simple bug fix, it loads only L4 (the relevant module) rather than L1+L2+L3+L4.
5. **Resume test**: On session start, given a prd-status.md with a "Resume from here" prompt, it reports exactly the next step without requiring the user to re-explain the task.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/context-hierarchy.md` | LOAD phase — what belongs at each level |
| `references/token-patterns.md` | AUDIT phase — token cost patterns |
| `references/flush-templates.md` | FLUSH phase — what to write at session end |

---

## Example Flows

**Session start:**
> "Start a new session on canopy."

AUDIT (what's in context?) → LOAD L1 (memory files) → LOAD L2 (canopy-context.md) →
LOAD L3 (prd-status.md — resume prompt) → HEALTH (CLEAN) → Report: "Loaded. 168 tests
passing. Resume from: [exact prompt from prd-status.md]"

**Context bloated mid-session:**
> "Sync context — I feel like we have a lot of stuff loaded."

AUDIT → flag 3 files that were inlined full-content → PRUNE → HEALTH (CLEAN, -~800 tokens)

**Session end with new module:**
> "End session. We added cache.py today."

FLUSH → add cache.py to L2 architecture table → add decision D3 reference to L2 →
update test count in L2 → update prd-status.md with completed step → flag cache patterns for /learn
