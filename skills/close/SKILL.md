---
name: close
description: "Lightweight session close without review or learning. Use for exploratory sessions or after /done; does not move org_score."
---

# close — Lightweight Session Close

For exploratory sessions or when /done already ran. Compacts context and ends
the session without triggering the full review chain.

---

## Execution

1. Call `youk-core.compact_context(cwd)` — show the returned `digest` (do not paste `brief`)
2. Call `youk-core.session_end("done", commits_made=<bool>)`
   — do NOT set close_cluster=True

Report one line: "Session closed. (Note: /done sets close_cluster and moves org_score — use it when code was written.)"

---

## When to use /close vs /done

| Situation | Command |
|---|---|
| Code was written this session | `/done` |
| Exploratory / research only | `/close` |
| /done already ran, just compacting | `/close` |
| Quick context save before break | `/close` |
