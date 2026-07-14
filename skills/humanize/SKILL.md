---
name: humanize
description: >
  Writing style enforcer. Applies Ajinkya's voice to commit messages, documentation
  sections, DECISIONS.md rationale, code comments, and any other written output that
  represents him publicly or persistently. Ensures consistency of voice across the
  project's written artifacts. Not applied to code itself, test names, or structured
  data — only to prose that a human reads. Triggers on: draft commit message, any
  README section being written, DECISIONS.md rationale text, inline code comments
  explaining WHY, and any stakeholder communication drafted from the project.
---

# humanize — Voice and Writing Style Skill

A style application skill that ensures all written output from the project reflects
Ajinkya's voice — consistent, first-principles, technically precise but accessible,
and free of the filler language that makes AI-generated text feel impersonal.

The goal is not stylistic decoration. It is reputation consistency: every commit,
every doc section, and every decision rationale should feel like it came from the
same thoughtful engineer, because it did.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Classify → Draft → Voice → Check → Output |
| `commit: [draft]` | Apply voice to a commit message specifically |
| `doc: [draft]` | Apply voice to a documentation section |
| `decision: [draft]` | Apply voice to a DECISIONS.md rationale |
| `comment: [draft]` | Apply voice to an inline code comment |
| `brief: [draft]` | Apply voice to a stakeholder brief (from /pm-review) |
| `check: [text]` | Audit text: voice compliance + signal/noise framework (SUBTRACT + REVEAL), no rewrite |
| `chat: [reply]` | Apply signal/noise framework to a conversational reply — cut filler, surface the unstated |

---

## Context Capture (Always First)

Before applying voice, identify:

```
CONTENT TYPE:  [commit | doc section | decision rationale | code comment | stakeholder brief | conversational reply]
AUDIENCE:      [technical (Pedro) | non-technical (Jajean) | self (project record) | public (GitHub)]
TONE:          [factual | explanatory | persuasive]
DRAFT:         [the text to be transformed]
```

Audience determines vocabulary level. Tone is almost always factual or explanatory.
Persuasive is rare and should be flagged explicitly.

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — CLASSIFY

Determine the content type and apply the appropriate rules from
`references/by-content-type.md`.

Each content type has different:
- Length constraints
- Structural requirements
- Vocabulary level
- What to include vs. exclude

Emit:
```
[CLASSIFIED AS: {type}]
Audience: {technical | non-technical | public}
Rules applied: {see by-content-type.md section {N}}
```

---

### Phase 2 — DRAFT

If no draft is provided, generate one in standard technical voice. This is the
"before" state — useful for showing the transformation.

If a draft is provided, analyze it:
1. What is it trying to say?
2. What is the core message, stripped of filler?
3. What is stated implicitly that should be stated explicitly?
4. What is stated that doesn't need to be there?

---

### Phase 3 — VOICE

Apply Ajinkya's voice characteristics. Read `references/voice-profile.md` for the
full profile with examples.

**Core transformations to apply:**

**1. First-principles framing (why before what)**
Before: "Added retry logic to the LLM client."
After: "LLM API calls fail transiently. This adds exponential backoff so a 429 or
503 doesn't surface to the user."

**2. Own the decision (active voice, first person)**
Before: "It was decided to use in-process caching due to infrastructure constraints."
After: "We chose in-process LRU caching over Redis — no new infrastructure to manage
for a single-process Docker deployment."

**3. Be honest about trade-offs**
Before: "Implemented caching for better performance."
After: "Added SHA-256 keyed LRU cache with 24h TTL. Cache miss still hits the LLM —
first query for a new question always pays full cost."

**4. Name what was NOT done**
Before: "Added export functionality."
After: "Added CSV export. PDF export was considered but deferred — the use case (donor
communications) is well served by CSV in the short term."

**5. Cut filler language**
Remove: "In order to", "It should be noted that", "As part of this change",
"This commit", "We are pleased to announce", "Leveraging", "Utilizing"
Replace with: the actual content

**5b. Conversational filler (chat replies specifically)**
Remove openers: "Good question", "Great", "Sure", "Certainly", "Let me…", "I'll go ahead and…"
Remove closers: any re-ask of a resolved question, unrequested "let me know if…" / next-step offers
Remove meta-framing: "worth being precise", "easily-confused", "Put simply", "to be clear",
"the important thing to note" — commentary about the answer's structure instead of the answer
Lead with the answer. Match length to information content, not to perceived thoroughness.

**6. Calibrate to audience**
For Jajean: plain English, no acronyms, no SQL, outcomes over mechanics
For Pedro: technical precision, SQL can appear, mechanisms matter
For public (GitHub): assume smart reader, brief context, decision-forward

---

### Phase 4 — CHECK

Audit the voiced text against the quality bars from `references/voice-profile.md`:

- [ ] The first sentence states the reason, not just the action
- [ ] Active voice throughout (no "was decided", "has been implemented")
- [ ] No filler language (incl. conversational openers/closers/meta-framing — see step 5b)
- [ ] Trade-off is acknowledged (what was NOT done or chosen)
- [ ] Length is appropriate for content type
- [ ] Audience vocabulary level is correct

For `check:` / `chat:` modes, also run the **signal/noise framework**
(`references/signal-noise-framework.md`): PASS 1 SUBTRACT (cut lines failing the removal test),
PASS 2 REVEAL (surface the missing line / misleading frame / wrong connotation, load-bearing only).

Flag any violations:
```
[VOICE CHECK]
Violations: {list — or "none"}
```

---

### Phase 5 — OUTPUT

The final text, ready to use. No "here's the rewrite" preamble — just the text.

For commit messages: format matches conventional commits where appropriate.
For doc sections: formatted in the document's existing style.
For decision rationale: written to paste directly into DECISIONS.md.
For code comments: one line or block comment format appropriate to the language.

---

## Quality Bars (Non-Negotiable)

- **The first sentence must carry weight.** If the first sentence could be removed without losing information, it will be.
- **No trailing summaries.** Never end with "In summary, X" or "Overall, this change..."
- **Filler words are actively removed.** See the filler word list in `references/voice-profile.md`.
- **Every trade-off acknowledged.** No change is purely additive — what was NOT done is always worth a clause.
- **Length matches content type.** Commit messages: 1-3 sentences. Doc sections: as long as needed, not longer. Code comments: one line unless the WHY requires more.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **First-principles test**: Given "fixed the cache bug", it produces "Cache lookup was using case-sensitive comparison — normalized to lowercase before hashing so 'What is X?' and 'what is X?' share a cache entry."
2. **Trade-off test**: Given any "added X" commit, it adds at least one clause about what was NOT done or what the trade-off is.
3. **Filler test**: Given a paragraph with "In order to leverage the existing infrastructure...", it produces a paragraph starting with the actual decision or action.
4. **Audience test**: The same technical decision expressed for Jajean (plain English) and for GitHub (technical) should read noticeably differently, and both should feel natural for their audience.
5. **Brevity test**: A commit message never exceeds 3 sentences unless it's documenting a breaking change. If it's getting long, the change should be split.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/voice-profile.md` | VOICE + CHECK phases — canonical voice characteristics |
| `references/by-content-type.md` | CLASSIFY phase — rules per content type |
| `references/before-after.md` | VOICE phase — concrete transformation examples |
| `references/signal-noise-framework.md` | CHECK phase (`check:`/`chat:`) — SUBTRACT + REVEAL passes |

---

## Example Flows

**Commit message:**
> "commit: Added caching to the query loop with LRU eviction and TTL."

CLASSIFY (commit, public) → DRAFT (analyze what changed) → VOICE:
"Wire exact-match cache into the query loop: SHA-256 key, 24h TTL, 500-entry LRU.
Repeated questions (common in Jajean's grant workflows) skip the LLM call entirely.
First query for any new question still pays full API cost."

**README section:**
> "doc: Write a section explaining what canopy does."

CLASSIFY (doc, public/non-technical blend) → VOICE:
"Canopy translates plain-English questions into SQL, runs them against a PostgreSQL
database, and returns answers in plain English — no SQL knowledge required. SQL is
shown alongside every answer for review."

**Decision rationale:**
> "decision: We used in-process caching because Redis would be too complex."

CLASSIFY (decision, technical self-record) → VOICE:
"Single-process Gradio app deployed via Docker. In-process LRU avoids introducing
a Redis service — zero additional infrastructure, zero additional failure modes.
Redis becomes the right choice if the deployment moves to multiple instances."
