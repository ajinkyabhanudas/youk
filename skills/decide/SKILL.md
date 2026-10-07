---
name: decide
description: "Log an architecture decision record. Use for /decide, we-decided-to, or any choice that must survive across sessions."
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
