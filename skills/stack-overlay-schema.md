# Stack Overlay Schema

Authority file for all generated stack overlay files.
Every overlay in `skills/{name}/references/stacks/{framework}.md` must follow this structure.

Generated overlays are saved per-project on first encounter. They are directive, not educational.
Each section must stay under 400 tokens. Total overlay: under 600 tokens.

---

## Required Sections (in order)

### 1. Correctness Pitfalls
Language/framework bugs that are easy to miss because they don't cause immediate failures —
they fail silently, produce wrong data, or create races. Each row: pattern + consequence + severity.

Format:
```
| Pattern | Consequence | Severity |
|---|---|---|
| {specific code pattern to watch for} | {what breaks when this happens} | CRITICAL/HIGH/MEDIUM |
```

Rule: Minimum 5 rows, maximum 10. Only include things that ACTUALLY appear in this stack regularly.

---

### 2. Security Additions
Attack surfaces specific to this framework or language. Layers on top of the base security
checklist — do not repeat checks that already exist there.

Format: Same table as Correctness Pitfalls but scoped to security surfaces.

Rule: Minimum 3 rows, maximum 8. Skip generic OWASP items already in the base checklist.

---

### 3. Reliability Patterns
How errors propagate in this stack. What fails silently. What must be explicitly handled that
other stacks handle automatically. Retry and timeout defaults for this stack's common libraries.

Format: Prose + specific defaults:
```
Library: {library name}
Default timeout: {value or "none — must set explicitly"}
Retry behavior: {default behavior}
What fails silently: {list}
```

---

### 4. Performance Gotchas
The N+1s, blocking calls, and memory patterns that are common in this specific framework.
Not "general performance" — patterns specific to this stack that will hit in production.

Format: Numbered list, each item: what + when it happens + how to detect.

---

### 5. Critical Questions (Before You Ship)
The questions a senior engineer asks when reviewing code in this stack. Not checklists —
questions that force thinking. These are the ones that catch the class of bugs that
pass code review and break in production.

Format:
```
Before shipping {stack/framework} code, ask:
1. {question} — {why it matters}
2. {question} — {why it matters}
...
```

Rule: Minimum 5 questions, maximum 8. Each must be answerable from the code or require
an explicit decision. "Will this scale?" is too vague. "What does this query look like with 50k rows and no index on {field}?" is correct.

---

### 6. Test Strategy
What the base test-strategies.md doesn't cover for this stack. Framework-specific patterns,
fixture anti-patterns, and what must be integration-tested vs. unit-tested for this stack.

Format: Brief bullet list — specific library names and patterns.

---

## Generation Instructions (for Claude Code)

When generating an overlay:
1. Read the base skill's SKILL.md first — understand what it already checks
2. Read cross_project_knowledge — look for stack-specific patterns already observed
3. Fill all 6 sections following the schema above
4. Keep it directive: every line must change behavior, not describe a concept
5. The Critical Questions section is the most valuable — don't truncate it
6. Total token budget: ~500 tokens for the overlay. If you're going over, cut Correctness or
   Performance before cutting Critical Questions
7. After generating: call add_proposal(change_type="FILE_CREATE", target="{write_path}")
   then apply_proposal(confirmed=True)

---

## What Good Looks Like

A good overlay:
- Is specific to the framework version commonly in use (Django 4.x, not "Django")
- Contains at least 2 items the developer would NOT catch in a standard code review
- Has Critical Questions that reference actual code patterns (N+1 on a specific ORM method, not "performance")
- Has no content that duplicates the base skill's existing checks

A bad overlay:
- Lists generic best practices available in any tutorial
- Has Critical Questions like "Is this secure?" (no specificity)
- Duplicates the base audit checklist without framework-specific additions
- Exceeds 600 tokens (forces the dev to read rather than scan)
