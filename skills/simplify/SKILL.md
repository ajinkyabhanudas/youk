---
name: simplify
description: >
  Code quality skill. After implementation, identify and reduce complexity — long
  functions, deep nesting, unclear naming, redundant abstractions. Produces a
  concrete diff-ready list of simplification targets, not general advice.
---

# simplify — Complexity Reduction Gate

Fires after implementation to reduce accidental complexity before it compounds.
Not a style pass — a structural pass. The question at every step: "what would a reader
need to know that they shouldn't have to know?"

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full scan — all four lenses |
| `quick` | Naming + nesting only — fastest path |
| `functions only` | Long function scan only |
| `naming only` | Identifier clarity pass |

---

## The Four Lenses

**Lens 1 — Function length**
Functions over 30 lines should be questioned. Over 60: extract unless proven indivisible.
Signal: multiple `if`/`for`/`while` blocks at the same indent level = multiple concerns.

**Lens 2 — Nesting depth**
More than 3 levels of indent = cognitive stack overflow. Early return > nested else.
Guard clauses over nested conditions.

**Lens 3 — Naming clarity**
Names should eliminate comments, not invite them. If you need a comment to explain what
a variable holds: rename the variable.
Targets: `data`, `result`, `info`, `tmp`, `obj`, single-letter names outside list comps.

**Lens 4 — Abstraction fitness**
Is this abstraction paying for itself? A helper called once with a name that obscures
what it does is a net negative. Delete it and inline.

---

## Output Format

For each finding:

```
[LENS N: NAME]
File: {path}:{line}
What: {exactly what is complex}
Fix: {one-sentence concrete action — rename X to Y, extract lines M-N, remove wrapper Z}
Weight: HIGH | LOW
```

HIGH = confuses a reader in < 10 seconds.
LOW = worth doing on the next pass, does not block merge.

At the end: "Simplification complete. {n} HIGH items, {m} LOW items."

---

## Quality Bar

- Every finding is actionable in under 5 minutes.
- No style opinions (tabs vs spaces, brace position). Structural only.
- HIGH items are blocking — surface them before any commit.
- If zero findings: emit "No simplification targets found." Do not manufacture work.

---

## Hiring Validation

1. Given a 80-line function with three concerns: identifies the extract boundary, names
   the extracted functions, does not recommend extracting further (Lens 4 fires: over-abstraction).
2. Given well-named code with no nesting over 2 levels: returns "No simplification targets found"
   rather than manufacturing LOW findings to appear thorough.
3. Never recommends adding comments — recommends renaming instead.
