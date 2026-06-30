# Token Patterns — What Costs Tokens and How to Avoid It

Used in the AUDIT phase. Identifies the highest-cost context patterns and their
reference-based alternatives.

---

## Token Cost Reference (Approximate)

| Content | Tokens | Alternative |
|---|---|---|
| Full canopy-context.md | ~3,000 | Reference by section: ~50 + section content |
| Full DECISIONS.md (10 entries) | ~4,000 | Reference by ID: "D3 — coordinate stripping" ~20 |
| Full README.md | ~2,000 | Reference by section or summarize in 3 bullets |
| Full test file (100 tests) | ~5,000 | Reference pattern: "see monkeypatch pattern in canopy-context.md" |
| Full source file (200 lines) | ~2,500 | Reference function name and file path |
| Code snippet (20 lines) | ~250 | Often necessary — retain if actively working with it |
| NFR Decision Block | ~200-300 | Keep active — small, high-value |
| ADR entry (full) | ~400-600 | Keep decision summary only: ~50 |
| Memory file (user-ajinkya.md) | ~200 | Load once at session start; keep loaded |
| Error traceback | ~100-200 | Use for debugging; prune once resolved |
| LLM response (long) | ~500-2000 | Summarize conclusion; prune reasoning |

---

## High-Cost Anti-Patterns

### Anti-pattern 1: Full File Inline

**What it looks like:** Pasting the full contents of canopy-context.md, README.md,
or a source file into context "for reference."

**Cost:** 1,500-5,000 tokens per file

**What to do instead:**
1. Reference the file by path
2. When you need a specific fact, reference the specific section
3. Only read the full file when you need to understand the whole structure (session start)

---

### Anti-pattern 2: Re-Reading Previously Read Files

**What it looks like:** Reading canopy-context.md at session start AND again mid-session
when a specific fact is needed.

**Cost:** 3,000 tokens for the second read

**What to do instead:**
- At session start, read the file fully and note the key facts
- Mid-session, state: "From session-start read of canopy-context.md: [fact]"
- Only re-read if the file may have changed since the initial read

---

### Anti-pattern 3: Retaining Resolved Debugging Context

**What it looks like:** Keeping a 200-line error traceback in context after the bug
is fixed.

**Cost:** ~200-400 tokens per retained error

**What to do instead:**
- Use the traceback for debugging
- Once fixed, prune it
- Keep only: "Bug was: {one-line description}. Fix: {one-line description}."

---

### Anti-pattern 4: Full ADR in Active Context

**What it looks like:** Keeping the full 400-word ADR entry in context while working
on the implementation it documents.

**Cost:** ~500 tokens per ADR

**What to do instead:**
- Keep only the DECISION line and WHY NOT summary
- "D4: In-process LRU cache. Not Redis: zero-infra requirement. Revisit if multi-instance."
- Reference the full entry in DECISIONS.md when needed

---

### Anti-pattern 5: Debate Reasoning in Context

**What it looks like:** Keeping the full reasoning exchange about whether to use
approach A or B, even after the decision is made.

**Cost:** 500-2,000 tokens for a multi-round debate

**What to do instead:**
- Once a decision is made, prune the debate
- Keep only: "Decided: {choice}. Why: {one sentence}. Why not {alternative}: {one sentence}."

---

### Anti-pattern 6: Duplicate Context Across Levels

**What it looks like:** The same module description appears in canopy-context.md AND
as an inline paste in the current session.

**Cost:** Double the token cost

**What to do instead:**
- If the information is in L2, reference it
- Don't re-state in L4 what's already in L2

---

## Token Budget Targets

| Session type | Target token budget for context |
|---|---|
| Simple bug fix | < 1,000 tokens |
| Feature implementation (M) | < 3,000 tokens |
| Feature implementation (L) | < 5,000 tokens |
| Architecture review | < 4,000 tokens |
| Session start (full load) | < 4,000 tokens (L1 + L2 summary + L3 status) |

---

## Reference Syntax

Use these patterns to reference content without inlining it:

```
"Read .claude/canopy-context.md → Architecture section"
"See DECISIONS.md D4 for the cache backend decision"
"Pattern: references/nfr-categories.md → Section 1 (Caching)"
"See test_query_loop.py → monkeypatch section for fixture patterns"
"L2 environment variables table for CANOPY_CACHE_TTL_HOURS default"
```

These references cost ~20-50 tokens each and load only what's needed.
