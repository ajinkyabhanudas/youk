# Voice Application by Content Type

Used in the CLASSIFY phase. Each content type has specific rules about structure,
length, and what to include.

---

## Commit Messages

**Audience:** Public (GitHub history, future maintainers)
**Length:** 1-3 sentences. No bullet lists. No headers.
**Structure:** [WHY this was needed] — [WHAT changed] — [KEY trade-off if significant]

**Rules:**
- First sentence: the reason or problem, not just the action
- Use conventional commit prefix where it helps (feat, fix, refactor, test, docs, chore)
- Do not start with "This commit", "Added", "Updated" as the first word
- Do not end with a summary sentence
- If the change is complex (new module), 2-3 sentences max — not a full explanation
- Breaking changes: clearly stated in first sentence

**Template:**
```
{why the change was needed or what problem it solves}. {what was done}. {key trade-off or what was NOT done — if significant}.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

**Examples:**

Before: "Add cache module with LRU eviction and TTL"
After: "LLM calls for repeated questions pay full API cost every time. Exact-match cache with SHA-256 key, 24h TTL, 500-entry LRU eliminates redundant calls. Semantic caching (embedding-based) deferred until usage patterns justify the cost."

Before: "Fix bug in query loop where empty results weren't handled"
After: "Query loop raised AttributeError on empty DB results — no guard on zero-row response. Added explicit empty-result path that returns a plain-English 'no results' message instead."

Before: "Update README with new features"
After: "README didn't reflect cache module, streaming UI, or current test count. Updated architecture section, feature list, and test count (168). Docker setup instructions unchanged."

---

## README Sections

**Audience:** Mixed — technical reviewers (Pedro), potential contributors, public
**Length:** As long as needed, not longer. Aim for one paragraph per section.
**Structure:** Headers follow existing README structure. Prose, not bullet lists for explanations.

**Rules:**
- Lead with what the section is about in one sentence
- Technical users can handle SQL and architecture terms
- Non-technical users can't — separate sections for each where needed
- No "this project aims to..." — say what it does, not what it aims to do
- Features: state what users can do, not what the system supports
- Architecture: describe what modules do, not how they're implemented

**Template for feature description:**
```
{Feature name}: {what the user can do}. {key technical note if relevant}. {limitation or scope if important}.
```

**Template for architecture section:**
```
{Module}: {what it does in one sentence — from the user's perspective}.
```

---

## DECISIONS.md Rationale

**Audience:** Future Ajinkya, future maintainers, technical
**Length:** 2-4 sentences per section (Context, Decision, Why Not, Consequences)
**Structure:** Follow ADR format from /adr references

**Rules:**
- Context: why was this decision forced? what made it necessary now?
- Decision: one sentence starting with "We chose/use/decided"
- Why Not: one sentence per alternative, starting with "Not X: because Y"
- Consequences: both what's enabled AND what's foreclosed
- No hedging — decisions are made, not considered

**Example Context section:**
Before: "There were considerations around the caching approach that needed to be addressed."
After: "Repeated identical queries (common in Jajean's grant workflow) paid full LLM API cost on every run. We needed to decide: in-process dict, Redis, or SQLite."

**Example Why Not section:**
Before: "Redis was not chosen because it would add complexity."
After: "Not Redis: adds a second service to manage in Docker; single-process deployment doesn't need distributed cache."

---

## Code Comments (Inline, explaining WHY)

**Audience:** Future developer (technically proficient)
**Length:** 1 line preferred. 2-5 lines for non-obvious invariants.
**Structure:** Comment explains WHY, not WHAT. What is visible from the code itself.

**Rules:**
- If removing the comment would confuse a reader: keep it
- If removing the comment leaves the code self-explanatory: remove it
- Never explain what the code does — only why it does it
- Reference external constraints ("Anthropic API requires...", "psycopg2 is synchronous so...")
- Reference bugs or incidents when relevant ("This silently fails without the guard — see D3")

**One-line template:**
```python
# {why this behavior is necessary — the constraint or invariant it satisfies}
```

**Block comment template (for non-obvious behavior):**
```python
# {the hidden constraint or non-obvious invariant}
# {what would happen if this weren't here}
# {reference if applicable — API doc, DECISIONS.md entry}
```

**Examples:**

Good one-liner:
```python
# Anthropic requires all tool results from one turn in a single user message.
tool_results_message = format_tool_results(pending_results)
```

Good block:
```python
# Strips lat/lon before model sees results — coordinates are sensitive for Jocotoco's
# anti-poaching work. User-facing Results tab still shows full data.
results = _format_result(rows, exclude=_SENSITIVE_COLUMNS)
```

Bad (explains WHAT, not WHY):
```python
# Loops through the results and removes sensitive columns
results = _format_result(rows, exclude=_SENSITIVE_COLUMNS)
```

---

## Stakeholder Brief (from /pm-review BRIEF output)

**Audience:** Jajean (non-technical) or organizational stakeholders
**Length:** 1 paragraph, maximum 5 sentences
**Structure:** Problem → Decision → What this means for you → What was NOT done (if relevant)

**Rules:**
- No technical jargon (no SQL, no API, no module names)
- Name the specific benefit the stakeholder experiences
- Name the limitation honestly — stakeholders respect honesty
- No passive voice
- First sentence: what changed and why it matters

**Template:**
```
{What changed, in plain English, and why it matters to the reader}. {What the reader can now do that they couldn't before}. {Any limitation they should know}. {What comes next, if relevant}.
```

**Example:**
"We added a memory feature to the tool so that questions you've asked before are answered immediately — no wait. When you ask Jajean a question you've asked in the last 24 hours, the system retrieves the stored answer rather than re-running the database query. New questions still take the usual 10-15 seconds. We'll revisit the time window once we see which questions you repeat most often."
