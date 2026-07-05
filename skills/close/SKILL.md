---
name: close
description: >
  Lightweight session close without code-review or learn. Use when work was
  exploratory, no code was written, or /done already ran. Does NOT set
  close_cluster — org_score won't move. Prefer /done for any session where
  code was written. Triggers on: "/close", "quick close", "lightweight close",
  "just close the session", "close without review".
---

# close — Lightweight Session Close

For exploratory sessions or when /done already ran. Compacts context and ends
the session without triggering the full review chain.

---

## Execution

1. Call `youk-core.compact_context(cwd)` — paste the returned `brief` verbatim
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
