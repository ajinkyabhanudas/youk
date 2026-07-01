# User Intent Interpretation Patterns

*How Ajinkya's phrases map to actual intent. Prevents the "initial interpretation was wrong" failure mode.*
*Maintained by youk-core. Entries promoted to config/routes.yaml when confidence reaches HIGH + 3 observations.*

---

## Pattern: "activate youk / where were we / what's the plan"

**Surface forms:** "activate youk", "youk", "/start", "where were we", "what are we working on", "what's the plan", "let's start", "what's next"

**Initial interpretation (wrong):** Answer the question conversationally, or summarise recent conversation context.

**Actual intent:** Run the start skill — call session_start, get pending proposals, format the activation card. The card is the answer. Do not narrate, do not start tasks.

**Key signals:**
- First message of a session (before any task has been described)
- Explicit invocation: "activate youk", "/start"
- Orientation questions at session open: "where were we", "what's pending"

**Confidence:** HIGH
**Observations:** 1 (2026-07-01 — start skill created)

**Routing implication:** First message + orientation phrase → route_to_skill("start", cwd). Do not call optimize_intent first — this is not a vague task, it is a known activation pattern.

**Added:** 2026-07-01 | Source: start skill design session

---

## Pattern: "make it a repo / build a repo"

**Surface forms:** "can we build a repo out of this", "let's make this a repo", "turn this into a project", "build a repo for this"

**Initial interpretation (wrong):** Create a GitHub repository — git init, push the current files, maybe a README.

**Actual intent:** Build a proper, reproducible, open-source-quality project with architecture documentation, versioning, CI/CD, and a self-improving structure. The "repo" is the vehicle; the destination is a production-grade system.

**Key signals that reveal actual intent:**
- Quality adjectives: "state of the art", "proper", "real", "professional"
- Compound requests: "and build out a structure", "and make this itself a project"
- Future-oriented language: "over time", "build out", "grow into"
- Self-referential language: "make the best version of itself"

**Confidence:** HIGH
**Observations:** 1 (2026-06-28 — youk design session)

**Routing implication:** When "repo" + quality signals → escalate to /orchestrate new-project flow (XL), not just /adr + /humanize.

**Added:** 2026-06-28 | Source: youk design session

---

## Pattern: "cleaner" / "make it cleaner"

**Surface forms:** "clean this up", "make it cleaner", "simplify this", "cleaner code"

**Initial interpretation (wrong — common):** Reduce line count, code golf, make it shorter.

**Actual intent:** Reduce cognitive load for the next reader. Simplify the mental model. Remove indirection. The measure is "how long does it take to understand" not "how few lines."

**Key signals that reveal actual intent:** (none needed — established pattern from code review history)

**Confidence:** HIGH
**Observations:** 3+ (established pattern)

**Routing implication:** When asked to "clean up" → /simplify, not arbitrary line reduction.

**Added:** 2026-06-28 | Source: historical pattern

---

## Template for New Entries

```markdown
## Pattern: "{phrase}"

**Surface forms:** "{variation 1}", "{variation 2}"

**Initial interpretation (wrong):** {what was first assumed}

**Actual intent:** {what was actually meant}

**Key signals that reveal actual intent:**
- {signal 1}
- {signal 2}

**Confidence:** LOW | MEDIUM | HIGH
**Observations:** N (dates)

**Routing implication:** {how this affects task routing or skill selection}

**Added:** YYYY-MM-DD | Source: {session description}
```
