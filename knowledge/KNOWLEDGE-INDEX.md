# youk Knowledge Index

*Managed by youk-core. Last updated: 2026-06-28.*
*This is not a log. Every entry is a structured insight — extracted, not transcribed.*

---

## Health Status

| Type | Count | Last Updated | Health |
|---|---|---|---|
| Interpretation patterns | 1 | 2026-06-28 | GOOD |
| Clarification cases | 1 | 2026-06-28 | GOOD |
| Domain knowledge | (symlink → ~/.claude/skills/learn/knowledge/) | — | — |
| Pending proposals | 0 | — | CLEAN |

---

## Interpretation Patterns
Location: `knowledge/interpretation/user-intent.md`

How Ajinkya's phrases map to actual intent. Updated when a new pattern is confirmed or an existing one gains evidence.

Current patterns: **1** (make-it-a-repo)

---

## Clarification Cases
Location: `knowledge/clarifications/YYYY-MM/`

Structured cases where initial interpretation required correction. Each case extracts a latent pattern. Organized by month, not appended chronologically.

Current cases: **1** (2026-06-28 — "build a repo out of this")

---

## Domain Knowledge
Location: `knowledge/domain/` → symlink to `~/.claude/skills/learn/knowledge/`

Concept-graph knowledge: analogy, break points, when to use / not use. Format defined in `~/.claude/skills/learn/references/knowledge-structure.md`.

---

## Proposals
Location: `knowledge/proposals/PENDING.md`

Self-heal proposals pending founder review. Hard rule: never auto-applied.

---

## Health Rules (enforced by youk-core)

- Entries older than 90 days with no reinforcement → `knowledge/archive/`
- Interpretation patterns appearing 3+ times with HIGH confidence → eligible for promotion to `config/routes.yaml`
- Conflicting patterns (same phrase → different intents) → flagged here for review
- Session end: all new entries validated for required fields before write
