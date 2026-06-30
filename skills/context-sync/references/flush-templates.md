# Flush Templates — What to Persist at Session End

Used in the FLUSH phase. For each type of session output, these templates define
what to write and where.

---

## Template 1: New Module Added → Flush to L2

**Target:** `.claude/canopy-context.md` → Architecture section

**What to add:**
```
[in the module map table]
├── {module_name}.py   {one-line description of what this module does}
```

**What to add to Critical Design Decisions (short-form):**
```
{N}. **{Decision title}** — {one sentence summary}. Full reasoning: DECISIONS.md D{N}.
```

**Test count update:**
```
## Test suite
**{N} passed** (as of {YYYY-MM-DD}).
```

---

## Template 2: New Environment Variable → Flush to L2

**Target:** `.claude/canopy-context.md` → Environment variables table

**What to add:**
```
| `{VAR_NAME}` | `{default}` | {purpose — one sentence} |
```

**Also update:** `.env.example` with the new variable.

---

## Template 3: Build Step Completed → Flush to L3

**Target:** `.claude/prd-status.md`

**Pattern:**
```
[update the completed step with ✓]
[update the "Resume from here" section to the next step]
```

**Resume from here template:**
```
## Resume from here

{Exact task}: {implement/add/fix} {specific thing} in {file path}.
{Status}: {what's done and what's next}.
{NFR}: {reference to NFR block if relevant}.
{ADR}: {D{N} — one-line decision if relevant}.
{Tests}: Run `pytest tests/ -q` before and after.
```

---

## Template 4: New Architectural Pattern → Flush to L2

**Target:** `.claude/canopy-context.md` → Patterns section (or create if doesn't exist)

**Example:**
```
## Patterns

### {Pattern name}
{One sentence: when to use this pattern}
{Code reference: see module/function.py:line}
{Key rule: the invariant that must be maintained}
```

---

## Template 5: New Security Rule → Flush to L2

**Target:** `.claude/canopy-context.md` → Security rules section

**What to add:**
```
- {Security rule} — {brief reason why}
```

---

## Template 6: Deferred Decision → Flush to L3

**Target:** `.claude/prd-status.md` → Deferred items section

**Template:**
```
## Deferred

### {Feature / Decision name}
Deferred: {YYYY-MM-DD}
Reason: {why deferred}
Trigger: {specific condition to revisit — not "later"}
Owner: {who watches for the trigger}
```

---

## Template 7: Knowledge Learning → Flag for /learn

At session end, identify any patterns worth adding to the knowledge graph.
Do not write to L1 directly — flag for /learn to process.

**Flag format:**
```
[LEARN FLAG]
Concept: {what was learned}
Domain connection: {how this connects to Ajinkya's existing domains}
New territory: {yes/no — was this genuinely new or reinforcing existing knowledge}
Where demonstrated: {which feature/decision in this session}
```

---

## End-of-Session Checklist

Before marking a session complete, verify:

- [ ] All completed build steps are marked in prd-status.md
- [ ] "Resume from here" prompt is updated to the next unfinished step
- [ ] Any new modules are listed in canopy-context.md architecture table
- [ ] Any new env vars are in canopy-context.md and .env.example
- [ ] Test count is updated in canopy-context.md
- [ ] Any new architectural decisions are referenced in canopy-context.md (full entry in DECISIONS.md)
- [ ] Any deferred items are logged in prd-status.md with triggers
- [ ] Any knowledge learnings are flagged for /learn

This is the same checklist as the Living Documents table in canopy-context.md.
If in doubt, run through that table: README, DECISIONS.md, .env.example, canopy-context.md, prd-status.md, schema.py.
