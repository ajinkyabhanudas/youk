---
name: learn
description: >
  Knowledge coach and learning layer. After any session where a non-trivial pattern,
  decision, or concept was used, maps it to Ajinkya's existing domain knowledge, builds
  analogies that make it stick, explicitly calls out where analogies break down (the
  highest-value part), and identifies genuine knowledge gaps. Persists learnings to
  domain knowledge files that accumulate across projects. Designed to accelerate the
  journey from "I know approximately how this works" to "I understand the underlying
  model well enough to teach it and catch edge cases." Triggers on: session end (always),
  "what did I just learn", "explain this concept to me", "how does X relate to Y I
  already know", or any time a new pattern is applied that connects to prior domains.
---

# learn — Knowledge Coach Skill

A structured learning skill that builds a persistent, connected knowledge graph from
the work Ajinkya does every session. The core insight: engineers with broad backgrounds
(cloud, IoT, data science, MBA) often know the components but not how they connect.
This skill makes those connections explicit — and more importantly, calls out where
the analogy breaks down before the gap causes a production bug.

The output is not a summary. It is a knowledge update: concrete additions to a mental
model, with explicit identification of what's genuinely new vs. what reinforces
something already known.

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

Before any phase, extract or infer:

```
SESSION CONTEXT:     [what was built/decided/debugged this session]
CONCEPTS USED:       [list of patterns, technologies, or decisions from the session]
DOMAINS TO MAP TO:   [Ajinkya's relevant background domains — read references/domain-map.md]
PRIOR KNOWLEDGE:     [what's already in the relevant knowledge files — reference don't inline]
NEW vs. REINFORCING: [initial assessment — were these concepts new or reinforcing]
```

If this is a `concept:` or `map:` invocation, focus on that specific concept rather
than the full session.

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

For each extracted concept, find the closest analogy in Ajinkya's existing domains.
Read `references/domain-map.md` for the full domain-to-concept mapping.

The mapping should be specific: not "this is like distributed systems" but "this is
like Redis maxmemory-policy in ElastiCache — the eviction strategy when capacity is full."

Emit for each concept:
```
[MAP: {concept}]
Closest analogy: {specific thing in Ajinkya's background}
Domain: {which background domain — AWS / Azure IoT / data science / etc.}
Analogy quality: STRONG | PARTIAL | WEAK
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

**Note on cross-project promotion:** Generalizable behavioral contracts (those expressing
methodology rather than project-specific paths) are automatically promoted to
`knowledge/global/contracts.md` by `session_end()`. You do not need to write to any
cross-project file directly — the promotion happens at session close.

---

### Phase 6 — MICRO-BRIEF

Generate a 5-bullet "mental model update" for the session. This is the quick-recall
version — the thing Ajinkya can read in 60 seconds to remember what he learned.

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

1. **Bridge specificity test**: For the canopy LRU cache implementation, it produces "LRU eviction → analogous to Redis maxmemory-policy LRU in ElastiCache" AND explicitly notes "where it breaks: Redis persists across restarts and is distributed; this cache is ephemeral and single-process."
2. **Gap discipline**: When a pattern has no strong analogy in Ajinkya's background, it says so clearly rather than forcing a weak analogy that would mislead.
3. **Accumulation test**: Running this skill across 5 sessions produces a knowledge base that grows and cross-references, not 5 independent summaries.
4. **CTO-track framing**: At least one bullet per session connects the pattern to a CTO-relevant skill (architectural decision-making, trade-off reasoning, system design, team/product thinking).
5. **Recall test**: Given `recall: AWS`, it produces a structured summary of AWS-domain concepts learned across all sessions, with specific cross-references to the projects where they appeared.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/domain-map.md` | MAP phase — Ajinkya's domain-to-concept mapping |
| `references/knowledge-structure.md` | PERSIST phase — how knowledge files are organized |
| `knowledge/*.md` | MAP + CONNECT phases — existing accumulated knowledge |

---

## Example Flows

**Post-session after building cache module:**
> "Learn from this session."

EXTRACT (LRU eviction policy, SHA-256 key design, TTL expiry, exact-match vs. semantic)
→ MAP (LRU → Redis maxmemory-policy; SHA-256 key → S3 deterministic object keys)
→ BRIDGE (LRU eviction: analogy strong; break: in-process not distributed)
→ GAP (semantic caching: no strong AWS/IoT analogy — genuinely new)
→ PERSIST (write to knowledge/caching.md)
→ MICRO-BRIEF (5 bullets)

**Deep dive on a specific concept:**
> "concept: exponential backoff with jitter"

EXTRACT → MAP (→ TCP congestion control, → IoT telemetry retry patterns)
→ BRIDGE (exponential backoff: same concept; jitter: new — TCP doesn't randomize same way)
→ GAP (none — strong prior analogy)
→ PERSIST → MICRO-BRIEF
