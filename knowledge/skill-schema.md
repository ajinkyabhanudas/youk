# SKILL.md Schema

A SKILL.md is a phase-gated execution protocol. It is not documentation — it is the system
prompt that Claude uses when a skill is invoked. Every line either directs behavior or wastes
tokens. Write it as if it is code, not prose.

---

## Required structure (in order)

```
--- frontmatter ---
# Title — Skill Name
(one-line tagline — what this skill does and why it matters)
---
## Invocation Grammar
## Context Capture
## The [N] Phases
  ### Phase 1 — NAME
  ### Phase 2 — NAME
  ...
## Quality Bars (Non-Negotiable)
## Reference Files
## Example Flows
```

---

## Frontmatter

```yaml
---
name: kebab-case-skill-name
description: >
  One paragraph. What the skill does. When it triggers. What output it produces.
  Be specific — this is used by route_task to decide whether to invoke this skill.
  Include: trigger conditions ("Fires when..."), output type ("Produces..."),
  what NOT to use it for.
---
```

Optional frontmatter fields:

```yaml
fast-path: |
  Conditions where this skill can return instantly without API call.
  Example: if task mentions only one file and is a rename → XS, return directly.

auto-skip: |
  Conditions where invoking this skill is unnecessary.
  Example: if already ran this session and scope has not changed → skip.
```

---

## Invocation Grammar

A table of directive variations. Every skill must have at minimum:

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full execution: all phases |
| `quick` | Abbreviated: 2-3 most important phases, skip ceremony |
| `enter: PHASE_NAME` | Skip to a specific phase (assumes prior phases already done) |

Add skill-specific directives as needed. Each row must be unambiguous — no "it depends."

---

## Context Capture

A fixed block extracted ONCE at the start, before any phase. Format:

```
KEY:          [value or infer and state assumption]
KEY:          [value or ask if blocking]
...
```

Rules:
- If context is derivable from the conversation, infer it and state the assumption. Do not ask.
- Ask only if a missing value is BLOCKING (without it, the wrong phase output is guaranteed).
- Never ask for context that can be read from files, git history, or the current task.

The context block becomes the source of truth for all subsequent phases.

---

## Phases

Each phase begins with the token `[PHASE: NAME]`.

### What every phase must contain

1. **A numbered action list** — specific steps to take, in order. Not "do analysis" — "identify X, check Y, flag Z."
2. **A compact output summary** — one sentence at the end of the phase: what was decided and what the next phase needs from this one.
3. **A clear stopping condition** — when is this phase done? What signals completion?

### Phase anti-patterns (avoid these)

- "Analyze the code and identify issues" — too vague. List what to check.
- No output summary — the next phase has no input.
- Phases that do the same thing — merge them or remove one.
- Phase that asks many questions — pick one question per phase if blocking, infer the rest.

### Compact output format (at end of each phase)

```
> Compact phase summary: "What was determined. What is known for the next phase."
```

---

## Quality Bars (Non-Negotiable)

This section is the skill's testing protocol. Every item must be:
- **Verifiable** — someone reading the output can determine pass/fail
- **Non-obvious** — if any competent Claude would do this without being told, don't list it
- **Binding** — "non-negotiable" means it cannot be skipped even in `quick` mode

Format:
```
- **Name of check:** What specifically to verify. What failure looks like.
```

Bad quality bar: "Code must be high quality."
Good quality bar: "Every rejected alternative must have a stated reason — 'we didn't choose X' without a reason is not documentation."

Include a **Hiring Validation** sub-section: 3-5 questions that distinguish a skill running correctly from going through the motions. Each question is a specific scenario with a specific expected behavior.

---

## Reference Files

A table of external files the skill reads during execution:

| File | When to read |
|------|--------------|
| `references/filename.md` | PHASE_NAME — before doing X |

Rules:
- List ONLY files that actually exist or are explicitly being proposed
- State WHICH phase reads each file — not "when relevant"
- References should contain: pre-built examples, checklists, lookup tables, or definitions
  that would otherwise bloat the SKILL.md itself

If a reference file is needed but doesn't exist yet: note it as "(proposed)" — it is a
signal that this skill is incomplete and the reference must be generated alongside it.

---

## Example Flows

3-4 concrete examples showing different invocation paths. Format:

```
**Scenario description:**
> "exact user input or trigger"

Phase chain → what each phase does → what the output looks like → what happens next
```

Examples must be specific. "User asks for review" is not an example. "User pastes a
FastAPI endpoint and says 'audit only'" — that is an example.

Include at least one example per major invocation mode (full, quick, enter: PHASE).

---

## Skill sizing guidelines

| Phases | Token budget | When appropriate |
|--------|-------------|-----------------|
| 2-3 | XS-S | Focused single-output skills (commit quality, quick review) |
| 4-5 | M | Standard workflow skills (dev-loop, pm-review, write-spec) |
| 6-7 | L | Research or multi-stakeholder skills (adr, stress-test) |
| 8+ | Rare | Only if phases are truly independent and cannot be merged |

---

## Signal-aware generation

When generating a new SKILL.md from signals (not a blank-slate request), the generation
must encode the triggering signal directly:

- **Demand gap** (route_task returned this skill but no SKILL.md exists): generate from
  the task that triggered the gap — use that task as the primary example flow
- **Audit gap** (sessions showed a skill missing X): include X as a quality bar and add
  a specific phase step to catch it
- **Best-practices gap** (cross-project.md has a pattern no skill covers): add a quality
  bar that enforces the pattern, cite the cross-project source in the bar's description
- **Project-type gap** (python_ml project, no python_ml skill exists): add project-type
  specific context capture fields and stack-specific quality bars

---

## Anti-patterns (what a bad SKILL.md looks like)

- **Generic phases**: "ANALYZE → SYNTHESIZE → REPORT" — not a skill, a to-do list
- **No context capture**: the skill assumes context from the conversation — breaks after compaction
- **Aspirational quality bars**: "output should be excellent" — untestable
- **No invocation grammar**: every call runs the same 6 phases — no fast-path for simple cases
- **No example flows**: the skill's behavior is theoretical, never demonstrated
- **References that don't exist**: listed as if they do — the skill will silently degrade
- **Phases without output summaries**: context doesn't carry forward — next phase starts blind
