---
name: learn
description: >
  Knowledge coach and learning layer. After any session where a non-trivial pattern,
  decision, or concept was used, maps it to the developer's existing domain knowledge,
  builds analogies that make it stick, explicitly calls out where analogies break down
  (the highest-value part), and identifies genuine knowledge gaps. Persists learnings to
  domain knowledge files that accumulate across projects and stacks. Works for any
  developer — discovers their background from knowledge/user-profile.md rather than
  assuming it. Triggers on: session end (always), "what did I just learn", "explain
  this concept to me", "how does X relate to Y I already know", or any time a new
  pattern is applied that connects to prior domains.
---

# learn — Knowledge Coach Skill

A structured learning skill that builds a persistent, connected knowledge graph from
every session, for any stack and any developer background. The core insight: the fastest
path from "I know approximately how this works" to "I understand it well enough to teach
it and catch edge cases" is a precisely mapped analogy — AND an explicit statement of
where that analogy breaks down.

The output is not a summary. It is a knowledge update: concrete additions to a mental
model, grounded in what the developer already knows deeply.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Post-session learning digest — full loop |
| `concept: [name]` | Deep dive on a specific concept used in this session |
| `map: [concept] to [domain]` | Explicitly map a concept to a known domain |
| `gap: [area]` | Surface known gaps in a specific area |
| `recall: [domain]` | Retrieve what's been learned in a domain from knowledge files |
| `bridge: [concept A] [concept B]` | Explain how two concepts relate (are they the same? different? analogous?) |
| `quick` | 5-bullet micro-brief only — no deep analysis |

---

## Context Capture (Always First)

Before any phase, read and extract:

1. **Read `knowledge/user-profile.md`** (at `~/.claude/youk/knowledge/user-profile.md`).
   If it doesn't exist → run the PROFILE BOOTSTRAP phase before anything else.

2. Extract or infer from session context:

```
SESSION CONTEXT:     [what was built/decided/debugged this session]
STACK:               [project language/framework detected or inferred from session]
CONCEPTS USED:       [list of patterns, technologies, or decisions from the session]
USER PROFILE:        [DEEP domains from user-profile.md — these are the analogy targets]
PRIOR KNOWLEDGE:     [what's already in the relevant knowledge files — reference don't inline]
NEW vs. REINFORCING: [initial assessment — were these concepts new or reinforcing]
```

If this is a `concept:` or `map:` invocation, focus on that specific concept rather
than the full session.

---

## PROFILE BOOTSTRAP (fires only when user-profile.md does not exist)

When user-profile.md is missing, this is the user's first /learn run. Before MAP phase,
ask or infer the user's background:

1. Check the session context for signals: what did they fix? What did they explain
   fluently? What concepts did they apply without looking up? These reveal depth.

2. If signals are insufficient, ask (one question only):
   > "To build analogies that land, what's your strongest technical background?
   > (e.g. AWS/cloud, Java backend, mobile, data science, embedded systems)"

3. Create `knowledge/user-profile.md` with the schema:

```markdown
# User Profile — Observed Domain Depth

*Auto-created by /learn. Updated as depth is observed. Never committed — local only.*

## Domains

### {domain name}
**Depth:** DEEP | WORKING | SURFACE
**Evidence:** {what revealed this depth}
**Reliable analogy targets:** {specific concepts in this domain that translate well}

## Unmapped Domains (first seen in sessions but no analogy base)

| Domain | First seen | Priority |
|---|---|---|
```

4. Continue to EXTRACT with the newly bootstrapped profile.

---

---

## The Seven Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — EXTRACT

Identify what concepts, patterns, and decisions were meaningfully applied this session.

**What qualifies for extraction:**
- A design pattern that was implemented (LRU cache, retry with backoff, thread+queue)
- An architectural decision that was made (in-process vs. external cache, sync vs. async)
- A debugging technique that revealed something about how the system works
- A framework or tool behavior that was non-obvious
- A trade-off that was evaluated and decided

**What does NOT qualify:**
- Mechanical implementation details ("we called function X with parameters Y")
- Already-documented decisions (in DECISIONS.md or canopy-context.md)
- Obvious code patterns (list comprehensions, basic function calls)

Emit:
```
[EXTRACTED CONCEPTS]
{N} concepts identified this session:
1. {Concept name} — {what was learned about it}
2. ...
```

---

### Phase 2 — MAP

For each extracted concept, find the closest analogy in the developer's existing domains.

**Source of truth for analogies:** `knowledge/user-profile.md` (not domain-map.md, which
is a legacy static file). Read the DEEP and WORKING domains. Find the domain where the
concept has the closest structural match — same invariants, same failure modes, same mental
model — then pick a specific artifact within that domain, not the domain itself.

Wrong: "this is like distributed systems"
Right: "this is like Redis maxmemory-policy LRU in ElastiCache — eviction when capacity is full"

**When the concept is on the current stack** (`knowledge/stacks/{stack}.md` exists):
Read the "Common cross-stack analogies" table for starting points. These are generic;
replace with user-specific analogies from user-profile.md where possible.

**When no DEEP domain analogy exists:**
- Use a WORKING domain and flag as PARTIAL
- If no analogy is stronger than WEAK, explicitly say so — a weak analogy is more dangerous
  than no analogy (it produces false confidence)
- Add the domain to user-profile.md under "Unmapped Domains"

Emit for each concept:
```
[MAP: {concept}]
Closest analogy: {specific artifact in the developer's background — not the domain, the thing}
Domain: {which background domain — must match an entry in user-profile.md}
Source: {user-profile.md entry that grounded this — confirms it's observed depth, not assumed}
Analogy quality: STRONG | PARTIAL | WEAK
Note (if PARTIAL/WEAK): {what the analogy gets wrong that the developer should watch for}
```

---

### Phase 3 — BRIDGE

Build the explicit bridge between the new concept and the analogy.

This is the most important phase for knowledge retention. The bridge must:
1. State exactly how the concepts are similar (the model that transfers)
2. State what the analogy gets right
3. **State explicitly where the analogy breaks down** — this is where edge cases live

Format:
```
[BRIDGE: {concept} ↔ {analogy}]

How they're similar:
  {the transferable model — specific, not abstract}

What the analogy gets right:
  {the behaviors or properties that transfer directly}

WHERE THE ANALOGY BREAKS DOWN:
  {the specific way the new concept behaves differently — the gap where bugs live}
  {this is non-optional — every analogy has limits; name them}

Example that illustrates the difference:
  {a concrete scenario that works in the analogy but fails in the new concept, or vice versa}
```

---

### Phase 4 — GAP

Identify what is genuinely new territory — concepts that have no strong analogy in
Ajinkya's existing background, or where the analogy is so weak it would mislead.

Emit:
```
[GAP IDENTIFIED]
Concept: {what was encountered}
Why no strong analogy: {which prior domain would seem to apply but doesn't, and why}
Gap type:
  [ ] Genuinely new domain — no prior exposure
  [ ] Known domain, new depth — knew it existed, hadn't worked with it
  [ ] Known concept, different context — familiar in one domain, new behavior in another
Recommended resource: {the one thing to read/try to fill this gap}
Priority: HIGH | MEDIUM | LOW
```

---

### Phase 5 — PERSIST

Write learnings to the appropriate knowledge files. Read `references/knowledge-structure.md`
for the file organization.

**Rule:** Only write what is genuinely worth accumulating. Obvious patterns, already-known
facts, and one-off debugging details do not belong in the knowledge base.

**Write to the domain knowledge file:**

Target path: `knowledge/domain/{topic}.md` under the youk root (`~/.claude/youk/`).
Create the file if it doesn't exist. Create `knowledge/domain/` if the directory doesn't exist.

```
## {concept name}
*Added: {date}*
*Source: {project / session / context}*

**What it is:** {one sentence}
**Analogy:** {the bridge — specific, not abstract}
**Where the analogy breaks:** {the gap}
**Project example:** {where this was applied, with a concrete reference}
**When to reach for this:** {the condition that suggests this pattern is relevant}
```

**Update the gap log** if a gap was identified:

Target path: `knowledge/domain/gaps.md`

```
## Gaps (Active)
| Concept | Domain | Priority | Added | Addressed |
|---|---|---|---|---|
| {concept} | {domain} | HIGH/MED/LOW | {date} | — |
```

**Update `knowledge/user-profile.md`** when new depth is observed this session:

- A new domain was encountered → add to "Unmapped Domains" table with date and priority
- A first-principles resolution happened in a domain → raise confidence or add evidence line
- A PARTIAL analogy was confirmed as STRONG after a second encounter → update analogy quality
- A new "reliable analogy target" was validated → add to the domain's target list

Rule: depth only goes up. Never lower a domain from DEEP → WORKING. Depth is cumulative.

**Note on cross-project promotion:** `session_end()` auto-promotes contracts with methodology
phrases, but the LAYER DECISION below makes the two-layer split explicit and visible.

**[LAYER DECISION] — required at end of every PERSIST phase**

For each concept persisted to `knowledge/domain/`, classify it explicitly into one of three layers:

| Layer | What belongs here | Action |
|-------|-------------------|--------|
| **Project-only** | Implementation details, file paths, tool names, project-specific behaviour | None — stays in `knowledge/domain/` |
| **Global candidate** | Methodology, principles, how-to-work patterns, transferable analogies | Call `promote_to_global_contracts([principle])` now |
| **SHIPPED** | Capability or well-architected principle that improves youk for *all users* — skill design decisions, quality bars, exit conditions, architectural invariants | Call `add_proposal()` targeting the committed file it belongs in |

**SHIPPED** is the third layer and the most important for youk development sessions. A concept is SHIPPED when:
- It changes how a skill should behave (→ target: `skills/{name}/SKILL.md`)
- It is a well-architected invariant that should be documented for all users (→ target: `docs/well-architected.md`)
- It is a new skill that should be generated (→ target: `generate_skill()` then `add_proposal()`)

For each **SHIPPED** concept:
1. Identify the committed file it belongs in
2. Call `add_proposal(title=..., rationale=..., action="SKILL_EDIT", target="{skill-name}", content=..., target_section=...)` — or `FILE_CREATE` for new skills
3. The proposal sits in `PENDING.md` for review — nothing commits automatically
4. State what was proposed and why: "SHIPPED → added as proposal to `skills/challenge/SKILL.md` Phase 2 quality bars"

For each **global candidate**, call `promote_to_global_contracts([principle])` now — do not
defer to `session_end()`. State which were promoted and why.

Example:
- "always run `ruff check servers/` before committing" → **Project-only** (names a tool + path)
- "read the project's CI config to find the lint command before committing" → **Global** (promotes the principle)
- "challenge skill must extract FIXED_CONSTRAINTS before running lenses — never attack walls" → **SHIPPED** (quality bar for `skills/challenge/SKILL.md`)
- "a skill without hiring validation tests will drift silently — drift sentinels are non-negotiable" → **SHIPPED** (add to `docs/well-architected.md` under Operational Excellence)

---

### Phase 6 — MICRO-BRIEF

Generate a 5-bullet "mental model update" for the session. This is the quick-recall
version — readable in 60 seconds, no prior context needed.

Format:
```
[MENTAL MODEL UPDATE — {date}]
Session: {one-line description of what was built}

1. {Most important new concept — one sentence including the key bridge or gap}
2. {Second concept}
3. {Third concept}
4. {Key gap identified — what's genuinely new territory}
5. {One meta-observation about the session — a pattern that applies beyond this project}
```

---

### Phase 7 — CONNECT (for `bridge:` invocations)

When asked to bridge two specific concepts, produce a structured comparison:

```
[BRIDGE: {A} vs. {B}]

Surface similarity: {why someone might think these are the same thing}

How they're the same:
  {the properties and behaviors that are identical}

How they're different:
  {the specific properties where they diverge — not "they're implemented differently"
   but "A does X in scenario Z; B does Y in scenario Z"}

When to use A instead of B:
  {specific conditions that favor A}

When to use B instead of A:
  {specific conditions that favor B}

Common mistake: {the most frequent confusion caused by treating these as equivalent}
```

---

## Quality Bars (Non-Negotiable)

- **The bridge breakdown is mandatory.** Every analogy has limits. A bridge without a breakdown is not a bridge — it's a false equivalence waiting to become a bug.
- **Persistence must be additive.** Don't overwrite existing knowledge — append, unless the prior entry is factually wrong.
- **Gaps are opportunities, not embarrassments.** Identifying a gap is the whole point. Flag it without hedging.
- **Micro-brief must stand alone.** Someone who didn't read the full session should understand all 5 bullets with no prior context.
- **Cross-project pattern recognition.** If a pattern from this session was also seen in a prior project, note the connection. This is how a knowledge graph forms.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Bridge specificity test**: For any concept encountered, produces a specific analogy grounded in the developer's user-profile.md — not the domain, the artifact. "LRU → Redis maxmemory-policy LRU in ElastiCache" not "LRU → caching systems."
2. **Gap discipline**: When no STRONG analogy exists in the developer's observed depth, says so explicitly rather than forcing a WEAK analogy that will mislead.
3. **Profile bootstrap**: When user-profile.md is missing, correctly infers or asks for the developer's background before attempting MAP — never assumes.
4. **Accumulation test**: Running this skill across 5 sessions on 2+ different stacks produces a knowledge base that grows and cross-references, not 5 independent summaries.
5. **CTO-track framing**: At least one bullet per session connects the pattern to a principal/CTO-relevant skill (architectural decision-making, trade-off reasoning, system design).
6. **Recall test**: Given `recall: {domain}`, produces a structured summary of that domain's concepts learned across all sessions, with project cross-references.

---

## Reference Files

| File | When to read |
|------|-------------|
| `knowledge/user-profile.md` | MAP phase — developer's observed domain depth and analogy targets |
| `knowledge/stacks/{stack}.md` | BOOTSTRAP / MAP phase — concept seeds for the current stack |
| `references/knowledge-structure.md` | PERSIST phase — how knowledge files are organized |
| `knowledge/*.md` | MAP + CONNECT phases — existing accumulated knowledge |

Note: `references/domain-map.md` is a legacy file seeded for one specific developer. For new
users, user-profile.md is the live source. The domain-map.md file can be deleted once
user-profile.md is fully populated.

---

## Example Flows

**Post-session after building cache module (developer with AWS background):**
> "Learn from this session."

Read user-profile.md → DEEP: AWS, WORKING: Data Science
→ EXTRACT (LRU eviction, SHA-256 key design, TTL expiry, semantic vs. exact-match)
→ MAP (LRU → Redis maxmemory-policy ElastiCache; SHA-256 key → S3 content-addressed key)
→ BRIDGE (LRU: analogy STRONG; break: in-process is ephemeral + single-process, not distributed)
→ GAP (semantic caching: PARTIAL in Data Science domain — embedding math is the same, context is new)
→ PERSIST (knowledge/caching.md + update user-profile.md: "Redis eviction analogy confirmed STRONG")
→ MICRO-BRIEF (5 bullets)

**First session — no user-profile.md exists:**
> "/learn"

PROFILE BOOTSTRAP → infer from session (developer fixed a Docker networking issue from first
principles → Docker depth: WORKING) → create user-profile.md skeleton
→ EXTRACT → MAP (with newly created profile) → PERSIST

**Deep dive on a specific concept:**
> "concept: exponential backoff with jitter"

Read user-profile.md → find strongest domain with retry/queue analogy → MAP
→ BRIDGE (what transfers / where it breaks) → GAP if no STRONG analogy
→ PERSIST → MICRO-BRIEF

**New stack encountered (TypeScript + React, developer with Python background):**
> "/learn" after first React session

Read user-profile.md (DEEP: Python, WORKING: Data Science)
Read knowledge/stacks/typescript_react.md → component re-render, hooks dep array, etc.
→ EXTRACT → MAP each concept to Python/data-science analogies
→ BRIDGE (component re-render ↔ reactive formula in spreadsheet, but: React batches state, formulas don't)
→ Add "typescript_react" to user-profile.md → PERSIST → MICRO-BRIEF
