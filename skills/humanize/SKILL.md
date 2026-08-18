---
name: humanize
description: >
  Writing style enforcer. Applies the developer's voice to commit messages, documentation
  sections, DECISIONS.md rationale, code comments, and any other written output that
  represents the developer publicly or persistently. Ensures a consistent voice across the
  project's written artifacts. Not applied to code itself, test names, or structured
  data — only to prose that a human reads. Triggers on: draft commit message, any
  README section being written, DECISIONS.md rationale text, inline code comments
  explaining WHY, and any stakeholder communication drafted from the project.
---

# humanize — Voice and Writing Style Skill

A style application skill that ensures all written output from the project reflects
the developer's voice: consistent, first-principles, technically precise but accessible,
and free of the filler language that makes AI-generated text feel impersonal.

The goal is not stylistic decoration. It is reputation consistency: every commit,
every doc section, and every decision rationale should feel like it came from the
same thoughtful engineer, because it did.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Classify → Draft → Voice → Check → Output (+ Quantify, recursive, for long-form content) |
| `commit: [draft]` | Apply voice to a commit message specifically, checked against recent commit history (Phase 4b, corpus-level) before finalizing |
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
AUDIENCE:      [technical peer | non-technical stakeholder | self (project record) | public (GitHub)]
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

**Before applying voice, consult the learned steering vocabulary.** Call
`youk-core.get_steering_vocab("voice")` (or the relevant quality label). If it returns
`learned=True`, apply those confidence-weighted behaviors — they were learned from what
actually landed with this developer. If `learned=False`, proceed with the profile below,
then record what you applied.

Apply the developer's voice characteristics. Load the profile in this order:
1. `knowledge/global/voice-profile.md` — the developer's OWN learned voice (gitignored,
   local, populated by the voice-fingerprint system). Use it if it exists.
2. `references/voice-profile.md` — the committed generic template. Fall back to this when
   no local profile exists yet.
Never ship or commit a personal profile; it is per-developer data.

**After voicing, record the decomposition** so the vocabulary compounds: call
`youk-core.record_steering_decomposition("voice", "<the concrete move you applied>",
"<content type>", confidence="approved")`. If the developer later accepts the output
unedited, that's a `verified` signal; if they correct it, record `corrected` (a veto).
This is how youk's voice steering learns from real outcomes instead of a static profile.

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
For a non-technical stakeholder: plain English, no acronyms, no SQL, outcomes over mechanics
For a technical peer: technical precision, SQL can appear, mechanisms matter
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

### Phase 4b — QUANTIFY (recursive, single-document or corpus-level)

Run this for doc sections, briefs, reports, and any content where Phase 4's qualitative CHECK isn't
enough on its own, because a draft can pass every qualitative rule individually and still read as
AI-generated in aggregate (this is not hypothetical — it happened three times in a row on a real report
before this phase existed). For content under ~300 words (commits, code comments), the single-document
version below doesn't apply — a 2-3 sentence commit has no meaningful sentence-length variance to
measure — but the underlying tell still shows up, just at corpus scale instead of document scale: the
same opening verb, connector, or structural template reused commit after commit. **Don't skip
short-form content, check it differently.** See "Commit-specific check (corpus-level)" below.

This is a **recursive improvement loop**, not a one-shot check: measure, compare against a benchmark,
fix what's flagged, re-measure, repeat. **Exit condition is convergence, not a round count**: stop when
a full measurement pass finds nothing new to fix, or after 4 rounds if it hasn't converged (flag that
explicitly rather than looping forever — a document that won't converge after 4 rounds usually needs a
structural rewrite of the flagged section, not another patch). This mirrors the project's general
reasoning-loop discipline (exit on zero new findings, not on a fixed number of passes) applied to
prose quality specifically.

**Persona for this phase: the careful technical editor who trusts the reader and never pays for
rhythm with information.** Confirmed by a blind A/B score on a real document (round 4 of this skill's
development) — a second editing pass that chased word-frequency numbers down further scored *lower*
(73/100) than the version it started from (86/100), because the fixes traded prose quality for
statistics. Before finalizing any FIX in this phase, apply this checklist:

1. **Prefer in-place word/phrase swaps over sentence restructuring.** A synonym swap that preserves the
   sentence's existing shape is lower-risk than rewriting the sentence, because restructuring is what
   introduces new, unchecked patterns.
2. **Never split a sentence unless every resulting piece states a new fact.** A short sentence that
   only restates the previous one for punch ("A blank spinner says nothing.") is the aphoristic
   over-correction tell, not a fix — merge it back or cut it.
3. **A word only gets cut if removing it is provably lossless** (a grammatical or logical reason it was
   redundant — e.g. "already run" after "had," where the past perfect already carries the meaning), not
   because its frequency count alone is elevated. High frequency is a prompt to *look*, not a mandate
   to cut.
4. **Re-check every replacement against the full taxonomy before finalizing it, not just the one metric
   it was written to fix.** The round-4 regression happened because a fix for word-frequency was never
   re-checked against the antithesis rule, and introduced a fresh antithesis in the same sentence.
   Fixing one axis and not checking the others is the single most repeated failure across every round
   of this skill's development — check the whole list every time, not just the flagged item.
5. **Precision beats idiom.** Don't trade semantic accuracy for a punchier or more natural-sounding
   phrase — "know how to make without thinking" reads more human than "already know how to make," but
   it also subtly implies carelessness that wasn't intended. If a more natural phrase changes the
   meaning, it's not a fix.

Run `scripts/quantify.py <file>` (all eleven checks, fixed order). Fix every FLAG, re-run until clean
or each remaining flag is judged legitimate. If a flag is missed, fix the script and
`ai-tell-taxonomy.md` in the same sitting, not just the instance.

**Round structure:**

1. **MEASURE.** Compute, over the full draft:
   - Sentence-length mean and standard deviation (burstiness). Method and genre-adjusted targets in
     `references/distributional-realism.md` §1 — formal/graded writing runs lower burstiness than
     creative writing; don't target novel-level variance.
   - Word-frequency rate per 1,000 words for any word appearing suspiciously often, compared against
     the general-English baseline table in `references/distributional-realism.md` §3. A multiplier of
     5-10x+ baseline is worth a look; judge it against what the genre plausibly explains before cutting.
   - Punctuation frequency: colons (revised target, corrected 2026-08-17 after a developer rejected
     the original "~1 per 250-300 words" estimate three times as still too many — that number was my
     own guess, never verified against real usage. Real target: a colon is justified only for a genuine
     three-or-more-item parallel list where commas alone would be clumsy, or a very short, unavoidable
     "label: single word" tag. Every other use — attaching an explanation, a single-item elaboration, a
     definition, a two-item pair — gets a period or a comma instead. On a 4,000-word document this
     converged at 2 colons, not 10-15. Don't trust a self-set numeric threshold for this; when a
     developer says a count still feels high, believe the ear over the arithmetic and keep cutting.),
     em dash count (target zero in long-form output from this skill, regardless of any personal sample
     that seems to permit it — see the contamination note below).
2. **COMPARE.** For each metric outside its target band, is this a real tell or genre-explained
   variation? Not every elevated number is a problem — forcing a rate down to a generic baseline when
   the genre genuinely warrants elevation (e.g., comparative connectives in a document about comparing
   decisions) produces awkward, over-corrected prose, which is its own failure mode. Judge the
   multiplier against plausible genre explanation before touching anything.
3. **FIX.** For metrics that are genuinely outliers: rewrite with genuinely varied replacements, not
   a single substitute phrase (swapping one crutch word for one replacement word just relocates the
   tell — this is the single most common failure in this phase, confirmed repeatedly). Prefer full
   restructuring or dropping the clause over finding a synonym.
4. **RE-MEASURE.** Run MEASURE again on the fixed draft. If new outliers appear (this happens — a fix
   for one word routinely becomes the next round's crutch), that's not a failed round, it's the loop
   working as designed. Continue to another FIX round.
5. **Exit** when a MEASURE pass finds nothing new, and report the final metrics alongside the
   qualitative `[VOICE CHECK]` block from Phase 4.

**Source contamination warning**: don't treat any writing sample as ground truth for a person's voice
without confirming it's actually human-authored. A commit message, doc section, or anything this
skill (or any AI) has touched is contaminated unless independently verified otherwise. This project
learned this the hard way — an apparent conflict between a "no em dash" rule and em-dash use in commit
samples turned out to be because the commits were mostly AI-authored, not a real voice signal. Prefer
sources that can't have been AI-touched: live chat messages typed in the moment, dictated corrections,
handwritten notes.

Emit:
```
[QUANTIFY: round N]
Sentence length: mean {X}, stdev {Y} (target: stdev roughly 5-9 for formal long-form)
Colons/1000 words: {X} (target: ~3-4)
Em dashes: {X} (target: 0)
Outlier words: {word (Nx baseline), ...} or "none"
Converged: {yes | no, round N of 4}
```

**Commit-specific check (corpus-level).** Before finalizing any commit message:

1. **Glance at recent history first.** Pull the last ~15-20 commits (`git log --oneline -20` or similar)
   before finalizing wording. Note the opening verb/structure each one used (Fix, Add, Wire, Cut, Move,
   Refactor...) and any connector phrase already leaning on repetition. If the draft repeats an opening
   verb or connector used in 3+ of the last 20, that's the corpus-scale version of the "rather than 30
   times in one document" problem — vary it, don't default to the same safe template every time.
2. **Batch-audit periodically, not just live.** Every ~30-50 commits (or on request), concatenate the
   last N commit messages into one corpus and run the same word-frequency-vs-baseline method from §3 of
   `references/distributional-realism.md` against that corpus, not a single message. A phrase or
   sentence-opening pattern that's fine once is a tell at high frequency across 30 commits, exactly like
   within one long document, just measured over time instead of over word count. Report findings the
   same way as the `[QUANTIFY]` block above, with "corpus of N commits" in place of a single document's
   word count.
3. This is what makes the discipline apply to the actual commits this project writes going forward, not
   just to long-form deliverables — a commit message is drafted by this skill, so it's in scope for the
   same recursive-improvement standard, adapted to its shorter, higher-frequency form.

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
4. **Audience test**: The same technical decision expressed for a non-technical stakeholder (plain English) and for GitHub (technical) should read noticeably differently, and both should feel natural for their audience.
5. **Brevity test**: A commit message never exceeds 3 sentences unless it's documenting a breaking change. If it's getting long, the change should be split.
6. **Corpus-repetition test**: given the last 20 commit messages, no single opening verb or connector phrase accounts for more than a small handful of them, and a batch frequency audit every ~30-50 commits finds no word or phrase running 5-10x+ above baseline across the corpus (Phase 4b, commit-specific check).

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/voice-profile.md` | VOICE + CHECK phases — canonical voice characteristics |
| `references/by-content-type.md` | CLASSIFY phase — rules per content type |
| `references/before-after.md` | VOICE phase — concrete transformation examples |
| `references/signal-noise-framework.md` | CHECK phase (`check:`/`chat:`) — SUBTRACT + REVEAL passes |
| `references/distributional-realism.md` | QUANTIFY phase — burstiness/perplexity method, genre-adjusted targets, lexical-frequency method |
| `references/ai-tell-taxonomy.md` | QUANTIFY + CHECK phases — cumulative living catalogue of AI-writing patterns, extend on every new find |
| `scripts/quantify.py` | QUANTIFY phase — run this, don't recreate its checks from memory. Extend it whenever a new pattern is caught. |

---

## Example Flows

**Commit message:**
> "commit: Added caching to the query loop with LRU eviction and TTL."

CLASSIFY (commit, public) → DRAFT (analyze what changed) → VOICE:
"Wire exact-match cache into the query loop: SHA-256 key, 24h TTL, 500-entry LRU.
Repeated questions (common in the user's recurring workflows) skip the LLM call entirely.
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
