# Clarification Case: "build a repo out of this"

**Date:** 2026-06-28
**Session:** youk initial design session

---

**Context:** End of MCP server architecture planning session. The plan was finalized for youk as two Docker MCP servers (youk-core + youk-code).

**Initial interpretation:** Create a GitHub repository for the plan files — git init, organize the plan, push to remote.

**User's actual intent:** Build youk as a proper, reproducible open-source-quality project. Not just a place to store files — a project with architecture, versioning, self-improvement capability, and a structure that can grow into a full variant platform.

**What revealed the actual intent:** The follow-up expansion message: "state of the art project", "reproducible structure", "youk making the best version of itself into a repo", "build out an architecture", "guard rails, soft and hard rules", "live document structure that heals and learns."

**Time to resolution:** 0 back-and-forth exchanges — caught from the user's immediate elaboration. The correction came as an expansion, not as a "no, that's wrong."

---

**Latent knowledge extracted:**
→ Added Pattern: "make it a repo" to `knowledge/interpretation/user-intent.md`

**Root cause of misinterpretation:** "Repo" is an ambiguous word. In minimal context, the most common meaning is "git repository." The actual intent requires quality signals and future-oriented language that elevates "repo" to "proper project."

**Prevention path:** When "repo/repository" appears alongside quality adjectives or future-oriented language, surface a clarifying question before executing: "Are we building a minimal git repo, or a full project structure with architecture and docs?"

**Proposed routes.yaml trigger:** See `knowledge/proposals/PENDING.md` — PENDING-001 (if created by health check).
