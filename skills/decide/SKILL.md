---
name: decide
description: >
  Log an architectural decision record (ADR). Wraps the adr skill with a prompt
  for the decision statement if not already given. Use when making a meaningful
  technical choice that should survive across sessions. Triggers on: "/decide",
  "log this decision", "record this choice", "write an ADR", "document this
  architecture decision", "we decided to".
---

# decide — Log an Architectural Decision

A thin wrapper around the adr skill. Ensures the decision statement is captured
before delegating.

---

## Execution

If the user has not provided a clear decision statement, ask:
"What's the decision? (One sentence: 'We will use X for Y because Z.')"

Once the decision statement is clear:
Call `youk-code.route_to_skill("adr", decision_statement)`.
Follow returned skill_content.
