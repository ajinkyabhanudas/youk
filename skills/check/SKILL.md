---
name: check
description: >
  Run code-review, and add security-review if auth, credentials, or data access
  paths are in scope. Use mid-session before a commit when you want a quality
  gate without closing the session. Triggers on: "/check", "review this",
  "check the code", "audit this", "quick review before commit".
---

# check — Mid-Session Code + Security Review

Quality gate without closing the session. Runs code-review always; adds
security-review when auth or data paths are touched.

---

## Execution

**Step 1 — Code review**

Call `youk-code.route_to_skill("code-review", "mid-session check")`.
Follow returned skill_content.

**Step 2 — Security review (conditional)**

If any of the following are true in the files being reviewed:
- Auth, login, token, credential, or permission logic
- Direct database queries or ORM access
- External API calls with credentials
- File I/O on paths provided by user input

Call `youk-code.route_to_skill("security-review", "mid-session check")`.
Follow returned skill_content.

**Step 3 — Report**

Summarize findings. Do not call session_end — /check is mid-session.

If code-review returns NEEDS REVISION: surface issues before the developer commits.
If code-review returns APPROVED or APPROVED WITH COMMENTS: say so explicitly.
