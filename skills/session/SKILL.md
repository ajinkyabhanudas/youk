---
name: session
description: >
  Internal knowledge file for the youk session server component (servers/core/src/session.py).
  Documents recurring gap patterns, known gotchas, and invariants that have caused bugs
  across multiple sessions. Not a user-facing skill — this is the institutional memory for
  session.py development and maintenance.
---

# session — Internal Component Patterns

Recurring gap patterns extracted from audit logs (3+ occurrences). This file exists so
the same bugs aren't reinvented session after session.

---

## Recurring Gap: Project Type Detection

**Pattern:** `_detect_project_type()` returns `"unknown"` for the youk repo itself.

**Root cause:** Detection logic looked for `requirements.txt` at `project_dir` root. The
youk repo uses `pyproject.toml` at root and has Python sources under `servers/`. It also
runs in Docker — no `requirements.txt` at the expected path.

**Fix:** Scan for Python markers in priority order:
1. `pyproject.toml` (modern Python)
2. `requirements.txt` at root or one level up
3. `*.py` files under `src/` subdirectories
4. `Dockerfile` with `FROM python` as a fallback signal

Also check `project_dir/..` for Makefiles — callers may pass a subdirectory.

**Test guard:** Add a unit test that passes the youk repo directory and asserts
`project_type == "python"`.

---

## Recurring Gap: Pending Count Includes APPLIED Entries

**Pattern:** `_count_pending_proposals()` returns a count that includes proposals with
`status: APPLIED` — making the pending count wrong on every session that has prior applied proposals.

**Root cause:** Count logic read all `## PENDING-` blocks without filtering by status.

**Fix:** After splitting on `## PENDING-`, check each block for `**Status:** APPLIED` and
exclude it from the count. Only count blocks where status is `PENDING` or absent.

**Invariant:** The "pending" count shown in `session_start` must match the actual number
of proposals a human needs to act on. APPLIED entries are historical, not actionable.

**Test guard:** Unit test with a PENDING.md containing 2 PENDING + 3 APPLIED entries.
Assert `_count_pending_proposals()` returns 2.

---

## Recurring Gap: No Unit Tests = Silent Bugs

**Pattern:** Bugs in `_count_pending_proposals` and `_detect_project_type` were invisible
for multiple sessions because no unit tests existed.

**Invariant:** Any function in `session.py` that parses file content or makes a routing
decision must have at least one unit test covering the happy path and one covering the
edge case that historically failed.

**Test locations:** `tests/unit/test_session.py`

---

## Known Gotchas

- `_generate_session_plan()` builds a list of strings — ordering matters; items prepended
  with `insert(0, ...)` appear first in the plan card.
- `days_since_last` can be `None` if no prior session exists — always guard with
  `if days_since_last is not None and days_since_last >= N`.
- `session_counter` starts at 1 for the first session — `<= 3` correctly targets
  sessions 1, 2, 3 for junior onboarding messages.
- `close_cluster_missed` is True when the last session's `close_cluster` was False or
  absent — not when `session_end` was never called.
