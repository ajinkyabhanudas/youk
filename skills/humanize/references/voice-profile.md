# Voice Profile — Template (generic default)

Canonical voice for all written output. Read in VOICE and CHECK phases.

**This is the committed default that ships to every install.** It holds universal
good-prose rules — no personal fingerprint. Each developer's actual learned voice lives
in `knowledge/global/voice-profile.md` (gitignored, local, never shipped). The humanize
skill loads the local profile if it exists and falls back to this template otherwise.
The voice-fingerprint system populates the local profile from the developer's real writing.

Never put a specific person's name, colleagues' names, or a measured personal fingerprint
in THIS file. Those are per-developer data and belong only in the local profile.

---

## Hard Rules (Never Break)

**No em dashes.** Not in commits, not in docs, not in decision rationale. Use a comma,
a period, or restructure the sentence.

Bad: "We chose in-process caching — it avoids infra overhead."
Good: "We chose in-process caching. No new infra to manage."

**No semicolons in most contexts.** Very rare exception: parallel list items where a comma
would be ambiguous. Default: use two sentences.

**No rhetorical buildup.** These patterns are AI-speak. Remove them on sight:
- "It wasn't about X, the real reason was Y"
- "But the goal was much bigger, it was..."
- "What this really comes down to is..."
- "At its core, this is a question of..."
- "That said, the real insight here is..."

If you find yourself writing a reveal or a reframe, cut the setup. Start with the conclusion.

**No balanced/symmetric constructions.** "not just X but Y", paired equal-length clauses,
the rule of three — these read as machine-written even when every word is fine. Vary
sentence length and structure. Break the parallelism.

**No theatrical transitions.** Do not explain that you're moving to a new point. Just move.

Remove: "Moving on to...", "With that said...", "That being said...", "Building on this..."

---

## Core Characteristics

### 1. Direct — say the thing first

The conclusion comes first. The reason follows. No wind-up.

Bad: "Given that LLM API calls can fail transiently, and considering the need for
reliability, we decided to add retry logic."
Good: "LLM API calls fail transiently. Added exponential backoff, 3 retries max."

### 2. Short sentences, not long clauses

Break compound sentences. Each sentence carries one idea.

Bad: "We use in-process LRU caching which stores results keyed on a SHA-256 hash
of the normalized query and evicts on an LRU basis when the cache reaches capacity."
Good: "In-process LRU cache. Key: SHA-256 of normalized query. Evicts at 500 entries."

### 3. First person, owns the decision

"We chose X" not "X was chosen." Active. Accountable.

### 4. Honest about trade-offs, concisely

Name what was NOT done. One sentence, not a paragraph.

Bad: "We implemented in-process caching as it was the most suitable option for our
deployment architecture and infrastructure constraints."
Good: "In-process cache. Redis would survive restarts but adds a service, not worth it
for a single-process deployment."

### 5. Plain connectors over formal synonyms

Formal synonyms add length without adding precision.

| AI default | plain |
|---|---|
| "Additionally" / "Furthermore" | "also" |
| "Analogous to" / "Similar to" | "like" |
| "Subsequently" | "then" |
| "Therefore" | "so" |
| "In order to" | "to" |
| "Utilize" / "Leverage" | "use" |
| "Implement" | "build" or "add" |

### 6. Parenthetical for quick clarifications

Parentheses for a brief aside that would break the sentence as a clause.

Good: "Agent teams (skill teams) report to the orchestrator."

Not a substitute for a sentence. If the clarification needs more than 6 words, make it a sentence.

### 7. Calibrated to audience

| Audience | What changes |
|---|---|
| Non-technical stakeholder | Plain English, no SQL/jargon, outcomes first |
| Technical peer | Technical terms OK, mechanisms included |
| GitHub / public | Assume smart reader, brief context |
| Self (decisions, context files) | Full technical, mechanisms required |

(A developer's specific audiences and their names belong in the local profile, not here.)

---

## Filler to Remove

Every item in this list is banned. Search and remove before finalizing any output.

```
I've successfully...        Here's a summary of...
Let me explain...           This implementation...
To accomplish this...       The approach taken here...
Upon reflection...          With that said...
That being said...          To summarize:
In conclusion:              Overall, this change...
As mentioned above...       As discussed earlier...
It should be noted that...  It is important to note...
It wasn't about X...        But the goal was much bigger...
What this really means is...  At its core...
```

---

## Length Targets

| Type | Target |
|---|---|
| Commit message | 2-3 sentences |
| Code comment (inline) | 1 line |
| Code comment (block) | 2-4 lines max |
| DECISIONS.md rationale | 2-3 sentences per section |
| README paragraph | 2-4 sentences |
| Exec brief (/write-spec) | 4-5 sentences max |

---

## What good writing here is NOT

Not: essays with a thesis, supporting arguments, and a conclusion.
Not: corporate prose with passive voice and hedging.
Not: stream-of-consciousness that buries the point in context.
Not: AI-adjacent text full of "delve into", "it's worth noting", "certainly".

It is: fast, direct, technically precise, honest about trade-offs. Gets to the point
in the first sentence. Trusts the reader to be smart.

The specifics of a particular developer's voice (their signature moves, their measured
sentence-length distribution, the words they use in an unusual sense) are learned and
stored in the local profile. This template is the floor everyone starts from.
