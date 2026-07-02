---
name: compaction
description: >
  Internal knowledge file for the youk compaction server component (servers/core/src/compaction.py).
  Documents recurring gap patterns, known gotchas, and invariants that have caused bugs
  across multiple sessions. Not a user-facing skill — this is the institutional memory for
  compaction.py development and maintenance.
---

# compaction — Internal Component Patterns

Recurring gap patterns extracted from audit logs (3+ occurrences). This file exists so
the same misunderstandings and bugs aren't reinvented session after session.

---

## Recurring Gap: Mid-Session Contracts Not Written to File

**Pattern:** Contracts verbalized mid-session (e.g. "always use TypeScript") existed only
in conversation context until `session_end`. Auto-compaction erased them silently, causing
`session_end` fire rate to appear as 0% — the contracts were never persisted.

**Root cause:** `save_contract` was not called immediately on contract detection. The
assumption was that `session_end` would sweep up all contracts at close, but session_end
was never called (tab-close is the default end-of-session behavior).

**Fix:** `save_contract()` must fire immediately on contract detection — mid-session, not
at close. CLAUDE.md now states this explicitly with trigger phrases.

**Invariant:** A contract in conversation context has a survival rate of ~0% across
tab-closes. A contract in `contracts.md` has a survival rate of 100%. Write to file, always.

---

## Recurring Gap: `mkdir` Outside try/except in `build_brief`

**Pattern:** `build_brief()` called `os.makedirs()` before opening the checkpoint file.
If the mkdir failed (permissions, disk full), the exception propagated as an unhandled
error instead of degrading silently.

**Fix:** Wrap the entire checkpoint-write block in try/except. If it fails, log to stderr
and continue — the brief can still be returned in-memory; a write failure is non-fatal.

```python
try:
    os.makedirs(checkpoint_dir, exist_ok=True)
    with open(checkpoint_path, "w") as f:
        f.write(brief_text)
except Exception as e:
    print(f"[compaction] checkpoint write failed: {e}", file=sys.stderr)
```

**Invariant:** `compact_context` must never raise — it should degrade gracefully if the
filesystem is unavailable. The brief is the primary output; file persistence is secondary.

---

## Recurring Gap: Verbatim-Paste Framing Is Probabilistic, Not Deterministic

**Pattern:** CLAUDE.md framing implied that pasting the `brief` verbatim "protects
contracts from auto-compaction." This is misleading — verbatim-paste only improves the
odds by making the brief recent context; actual durability requires writing to file.

**Correct mental model:**
- Verbatim-paste → brief survives the *next* compaction cycle (because it's recent)
- File write → brief survives every compaction cycle, forever
- Tab-close without `/done` → conversation context is gone; only file-written contracts survive

**Implication for CLAUDE.md:** The instruction to paste verbatim is still correct and
valuable — it keeps the brief in the recent context window. But it must not be framed as
a durability guarantee. Durability = write to file.

---

## Known Gotchas

- `compact_context` is called proactively (not on a timer) — triggers are event-based:
  after commits, after M+ tasks, after 8+ tool calls without compacting.
- The `brief` field returned by `compact_context` must be pasted verbatim in the
  response — not summarized, not reformatted. Paraphrasing causes precision loss on
  the next compaction cycle.
- `contracts.md` is the durable store; `session_state/*.json` is ephemeral session state.
  When in doubt about which file to read, read `contracts.md`.
