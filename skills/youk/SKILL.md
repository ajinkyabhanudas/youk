---
name: youk
description: "Entry point for youk: routes to the right skill and explains what youk can do."
---

# youk — Session Activation (collision-proof alias for /start)

Use this in projects where /start is overridden by a project skill.
In projects with no collision, /start and /youk are identical.

---

## Execution

Call `youk-code.route_to_skill("start", "session activation")`.
Follow the returned skill_content exactly — do not abbreviate.

---

## Rules

- This skill exists solely to provide a collision-safe entry point
- If /start works fine in this project, prefer /start — it is more discoverable
- Do not add logic here; keep this as a thin delegate to the start skill
