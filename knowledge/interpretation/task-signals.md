# Task Size Detection Signals

*Machine-readable heuristics for youk-core routing. Complements config/routes.yaml.*
*These are the signals that distinguish a sentence-level task description from a day-level one.*

---

## Size: XS

Strong signals (any one → XS):
- "fix the typo", "rename", "add a comment"
- Question asking for explanation: "what does X do", "how does Y work"
- One-liner: total description < 8 words

No signals → XS if description is a single sentence with no action verb beyond "look at" or "check".

---

## Size: S

Strong signals (any one → S):
- "bug fix", "hotfix", "fix the X bug"
- "add a test for", "write a test"
- "update the config", "change the value of"
- "one function", "single file change"

Disqualifiers (bump to M):
- "also" or "and" suggesting multiple changes
- Mentions a new abstraction or new module

---

## Size: M

Strong signals (any one → M):
- "add a feature", "implement", "build", "create a new"
- "refactor the X module", "clean up the X system"
- "new endpoint", "new component", "new page"
- Time language: "a few hours", "this afternoon"

Disqualifiers (bump to L):
- "entire", "all of", "the whole"
- Mentions architecture, design, or database schema change

---

## Size: L

Strong signals (any one → L):
- "redesign", "new system", "new service"
- "architecture decision", "technical design"
- "multi-day", "this week"
- Database schema migration mentioned

Disqualifiers (bump to XL):
- "new project", "from scratch", "green field"
- Multiple L-sized tasks in one description

---

## Size: XL

Strong signals (any one → XL):
- "new project", "from scratch", "start fresh"
- "multi-week", "over the next month"
- "entire platform", "major migration"
- "make this a proper project" (see user-intent.md: make-it-a-repo pattern)

---

## Ambiguity Resolution

When signals conflict (both S and M signals present):
- Default to the larger size (more ceremony, not less)
- Ask for clarification if the task would change skill routing significantly

When no signals match:
- Use description word count: < 8 words → XS, 8-20 → S, 20-50 → M, > 50 → L
