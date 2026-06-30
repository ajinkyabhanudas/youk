# Context Hierarchy — What Belongs at Each Level

The 4-level hierarchy ensures that every piece of information lives at the right
level of abstraction. Information at the wrong level is either invisible (too specific
to be found) or noisy (too general to be useful).

---

## Level 1 — Global User Memory

**Scope:** Persists across all projects and sessions.
**Owner:** /learn (writes), /context-sync (reads)
**Location:** `~/.claude/projects/[project]/memory/`
**Load pattern:** Read at session start; reference by filename, not inline
**Update pattern:** Only /learn updates this at session end

### What belongs here:
- User's background, expertise, learning goals (user-ajinkya.md)
- Collaboration preferences and workflow rules (user-ajinkya.md)
- Feedback the user has given about how to work together (feedback-*.md)
- Cross-project knowledge patterns (see /learn)
- Domain knowledge that transfers across projects (see /learn)

### What does NOT belong here:
- Project-specific architecture or design decisions
- Feature-specific state
- Temporary debugging context
- Information that's derivable from the current project's code

### Example contents:
```
user-ajinkya.md:
  - Background: AWS, Azure IoT, data science, Python, React, MCP, MBA
  - Workflow: dev-loop every implementation, ruff+pytest after each change
  - Voice: concise, first-principles, owns decisions

feedback-nfr.md:
  - Caching was missed before /nfr-check existed — always probe for it in LLM codepaths
```

---

## Level 2 — Project Context

**Scope:** Persists within one project across all sessions.
**Owner:** Developer (writes), /context-sync (reads and updates at flush)
**Location:** `.claude/[project]-context.md`
**Load pattern:** Read at session start; reference by section during session
**Update pattern:** After any architecture change, new module, env var change

### What belongs here:
- Architecture diagram / module map
- Critical design decisions (short-form, referencing DECISIONS.md for full rationale)
- Environment variables with defaults and purposes
- Test suite state (count, how to run, patterns used)
- Security rules and invariants
- Patterns that must be followed (monkeypatching, error propagation, etc.)
- Session housekeeping checklist

### What does NOT belong here:
- Implementation details (read the code)
- Test contents (read the test files)
- Full ADR entries (read DECISIONS.md)
- User-facing content (read README)
- Temporary session state

### Section structure (for efficient reference loading):
```
# canopy — developer context
## Living documents — update checklist
## Session housekeeping
## Project summary
## Stack
## Architecture (module map)
## Critical design decisions (short-form)
## Patterns
## Environment variables
## Test suite
## Security rules
```

### How to reference a section:
"Read .claude/canopy-context.md → Environment variables section"
NOT: "Read .claude/canopy-context.md" (loads everything)

---

## Level 3 — Sprint / Task State

**Scope:** Persists within one project; updated frequently (per build step).
**Owner:** Developer (writes), /context-sync (reads and updates at flush)
**Location:** `.claude/prd-status.md`
**Load pattern:** Read at session start; update after each build step
**Update pattern:** After each feature completion, new scope item, or status change

### What belongs here:
- Current sprint or milestone goals
- What's been completed (with dates and brief notes)
- What's in progress
- What's next — the exact "Resume from here" prompt
- Known blockers
- Deferred items with their trigger conditions

### What does NOT belong here:
- Architecture (belongs in L2)
- How things work (belongs in L2 or code)
- Full decisions (belongs in DECISIONS.md)
- Permanent project facts (belongs in L2)

### The Resume Prompt — most important field:
The "Resume from here" section in prd-status.md must be specific enough that a new
session can start immediately without requiring the user to re-explain context.

Bad: "Continue with the caching work"
Good: "Implement write_cache() in src/canopy/cache.py. The lookup_cache() function is
complete and tested. NFR block for caching is in [location]. ADR D4 covers the
in-process LRU decision."

---

## Level 4 — Feature Scope

**Scope:** In-session only. Not persisted until session end flush.
**Owner:** /context-sync creates it; dev-loop uses it
**Location:** In-session working memory
**Load pattern:** Created when feature work begins
**Update pattern:** Throughout the feature session
**Flush pattern:** Key decisions pushed to L2 at session end

### What belongs here:
- The feature being built (one sentence)
- Active NFR Decision Block (from /nfr-check)
- Active ADR (from /adr — just the decision and why-not, not full entry)
- Open questions being resolved
- Current implementation state (what's been written, what's next)
- Test plan for this feature

### What does NOT belong here:
- Information that's already in L1/L2/L3 (reference it, don't copy it)
- Debugging output (use, then discard)
- Intermediate reasoning (keep conclusions, discard debate)

### L4 creation template:
```
[L4 SCOPE: {feature name}]
Feature: {one sentence}
NFR block: {reference or "run /nfr-check first"}
Relevant ADRs: {D{N}, D{M} — one-line summary of each}
Starting point: {which file, which function}
Test plan: {reference test-strategies.md or state approach}
Open questions: {list}
```

---

## Cross-Level Rules

### The Single Source of Truth Rule
Each piece of information lives at exactly one level. If it appears in two places,
one of them must be a reference to the other.

- Architecture is in L2. DECISIONS.md is a full record. L2 references DECISIONS.md entries by ID.
- Code is the truth. L2 documents patterns and rules, not the code itself.
- L1 is global. L2 is project-specific. Information that applies to all projects goes in L1.

### The Reference Rule
Before loading content into context, ask: is this information already documented at
a level that can be referenced? If yes, reference the section — don't inline it.

Cost comparison (approximate):
- Inlining canopy-context.md: ~3,000 tokens
- Referencing "section: Architecture": ~50 tokens (the reference) + what you actually need

### The Flush Rule
Information that was created at L4 (feature scope) must be evaluated at session end:
- Architecture decision → flush to L2
- Task completion → flush to L3
- Reusable pattern → flush to L2 (patterns section)
- Knowledge learning → flag for /learn to process into L1
- Debugging artifact → discard
