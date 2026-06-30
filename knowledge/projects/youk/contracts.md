# Working contracts: youk

Behavioral agreements from development sessions. These are VERBATIM — never paraphrase.
compact_context() pins these at the top of every brief.

---

- commit format: small, logical commits with plain-English explanation before proceeding; one concept per commit, not one large commit
- test commits: implementation commits are co-authored by Claude (Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>); commits by Ajinkya have no co-author
- explain before acting: explain what you are about to do and why before every non-trivial action (M+ tasks)
- gate discipline: complete all items in a gate before moving to the next gate; verify ruff passes after every code change
- no silent fallbacks: if a tool or API call fails, surface the error explicitly rather than silently continuing with degraded behavior
