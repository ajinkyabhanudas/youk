---
name: schema-migration-audit
rationale_why: "SQLite ALTER TABLE has no DDL rollback — a wrong migration corrupts the database permanently and silently. This gate catches unsupported DDL, irreversible operations, and silent data loss before they run."
description: >
  Pre-migration safety gate for SQLite schema changes. Fires before any ALTER TABLE,
  CREATE TABLE, DROP TABLE, or migration script runs against a SQLite database. Audits
  for: unsupported DDL operations (SQLite 3.35+ required for DROP COLUMN), irreversible
  changes with no rollback path, silent data loss (column type changes, NOT NULL additions
  to existing data), and missing backup gates. Produces a migration verdict (SAFE / RISKY /
  BLOCKED) with a concrete remediation for each finding. Triggers on: "migrate the schema",
  "add column", "drop column", "alter table", "run migrations", any migration file creation
  or modification, or any task that writes to shared-index.db / task-graph.db schema.
  Do NOT trigger for: read-only queries, index creation on existing columns (no schema change),
  or migration rollbacks that have already been reviewed.
---

# schema-migration-audit — SQLite Migration Safety Gate

SQLite is not Postgres. DDL that works cleanly in Postgres can silently corrupt or fail
in SQLite. The specific risks: ALTER TABLE supports only ADD COLUMN and RENAME in SQLite
< 3.35 (DROP COLUMN was added in 3.35.0, released 2021-03-12); there is no ROLLBACK for
DDL; and column type changes happen silently without data validation. This skill audits
migration files before they run.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full audit: CLASSIFY → PROBE → VERDICT |
| `quick` | CLASSIFY → VERDICT only — identify blocking issues, skip deep probe |
| `review: {file}` | Audit a specific migration file by path |
| `enter: PROBE` | Skip CLASSIFY (target already identified), go straight to risk probe |
| `pre-commit` | Triggered from check_commit_quality — abbreviated, returns SAFE/RISKY/BLOCKED only |

---

## Context Capture (Always First)

```
MIGRATION_FILE:   [path to migration file, or "(inline SQL)" if embedded in code]
SQLITE_VERSION:   [target SQLite version — infer from Dockerfile or requirements; assume 3.31 if unknown]
DB_FILE:          [path to database file — default: servers/core/shared-index.db or task-graph.db]
EXISTING_SCHEMA:  [read from db file via .schema or migration history; "(unavailable)" if no access]
BACKUP_EXISTS:    [yes: path | no | unknown — check for backup step in migration script]
TABLES_AFFECTED:  [list of tables the migration touches]
DATA_AT_RISK:     [yes: which columns/tables have live data | no | unknown]
```

Rules: infer SQLITE_VERSION from Dockerfile python:3.x base or requirements.txt; assume 3.31 if no signal exists (conservative — 3.31 predates DROP COLUMN support). Ask only if MIGRATION_FILE is blocking (no file, no path, no inline SQL provided).

---

## The Three Phases

### Phase 1 — CLASSIFY

1. Read the migration file (or inline SQL if embedded in Python/shell).
2. Identify every DDL statement present: `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`, `CREATE INDEX`, `DROP INDEX`, `RENAME`, `DROP COLUMN`, `ADD COLUMN`, `INSERT INTO ... SELECT` (data migration pattern).
3. For each statement, classify against this table:

| DDL operation | SQLite support | Risk level |
|---|---|---|
| ADD COLUMN (nullable, no DEFAULT) | All versions | SAFE |
| ADD COLUMN (NOT NULL, no DEFAULT) | All versions | RISKY — existing rows get NULL, violates constraint if data exists |
| ADD COLUMN (NOT NULL, with DEFAULT) | All versions | SAFE |
| RENAME TABLE | 3.25+ | SAFE |
| RENAME COLUMN | 3.25+ | SAFE |
| DROP COLUMN | 3.35+ only | BLOCKED if SQLite version < 3.35 |
| DROP TABLE | All versions | RISKY — irreversible without backup |
| CREATE TABLE | All versions | SAFE |
| Column type change (no native support) | N/A — must rebuild | RISKY — requires table rebuild pattern |
| Constraint change (ADD/DROP constraint) | Not supported | BLOCKED — must rebuild |

4. Flag any `BEGIN TRANSACTION` / `COMMIT` wrappers — their absence means no atomic execution.
5. Check for backup step: does the migration script back up the database file before altering it?

> Compact phase summary: DDL operations identified and classified by risk level. Next phase needs the list of RISKY and BLOCKED items and whether a transaction wrapper exists.

---

### Phase 2 — PROBE

For each RISKY or BLOCKED item from Phase 1:

1. **NOT NULL without DEFAULT:** Check if the table has existing rows. If `DATA_AT_RISK: yes` — this BLOCKS migration unless a default value is added or existing rows are backfilled first. State the exact fix: `ALTER TABLE {table} ADD COLUMN {col} {type} NOT NULL DEFAULT {safe_value}`.

2. **DROP COLUMN on SQLite < 3.35:** State the table-rebuild pattern as the only path:
   ```sql
   BEGIN TRANSACTION;
   CREATE TABLE {table}_new AS SELECT {kept_columns} FROM {table};
   DROP TABLE {table};
   ALTER TABLE {table}_new RENAME TO {table};
   COMMIT;
   ```
   Flag: this pattern is data-destructive for columns being dropped — verify no application code still reads the dropped column.

3. **DROP TABLE:** Check git history or grep the codebase for references to the table name. If any reference found outside the migration — BLOCKED until callers are updated.

4. **Column type change:** Confirm whether the application code reads the column as the old or new type. A type change in SQLite does not validate existing data — integers become text silently. State the required backfill: `UPDATE {table} SET {col} = CAST({col} AS {new_type}) WHERE {col} IS NOT NULL`.

5. **Missing transaction wrapper:** Every DDL migration must be wrapped in `BEGIN TRANSACTION; ... COMMIT;`. Without it, a partial migration leaves the schema in an inconsistent state with no recovery path.

6. **Missing backup gate:** A backup step (`sqlite3 db.file ".backup backup.file"` or `cp db.file db.file.bak`) must precede any RISKY or BLOCKED operation. Its absence does not block SAFE migrations but is flagged for RISKY.

> Compact phase summary: Each RISKY/BLOCKED item has a concrete remediation. VERDICT phase needs: blocked_count, risky_count, and remediation list.

---

### Phase 3 — VERDICT

Emit a migration verdict block:

```
[SCHEMA MIGRATION VERDICT — {migration file or "(inline)"}]
SQLite version assumed: {version}
Tables affected: {list}

SAFE operations ({n}):
  - {operation}: {why it's safe}

RISKY operations ({n}):
  - {operation}: {risk} — Fix: {one-line remediation}

BLOCKED operations ({n}):
  - {operation}: {reason blocked} — Fix: {one-line remediation or alternative pattern}

Transaction wrapper: {present | MISSING — add BEGIN TRANSACTION / COMMIT}
Backup gate: {present | MISSING — add before first RISKY operation}

Verdict: SAFE | RISKY | BLOCKED
  SAFE: all operations are version-compatible and reversible
  RISKY: proceed only after applying remediations above; back up first
  BLOCKED: do not run until BLOCKED items are resolved — migration will fail or corrupt data
```

If verdict is SAFE and no RISKY items exist: stop here, no further action needed.
If verdict is RISKY or BLOCKED: do not allow migration to proceed — surface remediations.

---

## Quality Bars (Non-Negotiable)

- **Version-specific gate is non-negotiable:** Every DROP COLUMN finding must state the SQLite version threshold (3.35.0). "SQLite doesn't support this" without a version is not actionable. Failure: verdict says "not supported" without specifying that 3.35+ supports it.

- **Table-rebuild pattern completeness:** When the table-rebuild pattern is the only path, all three steps must be present (CREATE new, DROP old, RENAME). Missing any step leaves the database in a broken intermediate state. Failure: verdict says "rebuild the table" without the exact SQL.

- **No silent NOT NULL:** Any `ADD COLUMN ... NOT NULL` without a DEFAULT on a table with existing rows must be flagged RISKY regardless of whether DATA_AT_RISK is confirmed. Absence of confirmation ≠ absence of data. Failure: skill passes a NOT NULL addition without asking about existing rows.

- **Transaction wrapper is binary:** Either it's present (SAFE) or it's flagged (MISSING). A "best practice" note is not sufficient — absent transaction wrapper is a RISKY finding, not a suggestion. Failure: verdict mentions transaction wrapper only in passing.

- **Backup before RISKY:** A backup step is required before any RISKY operation on a production database file. "Recommended" is not the word — it is required. The verdict must say MISSING if no backup step exists in the migration script.

### Hiring Validation

1. **Version trap:** Migration adds `ALTER TABLE tasks DROP COLUMN legacy_field`. SQLite version is unspecified. Expected: skill flags this as BLOCKED until version is confirmed ≥ 3.35; provides table-rebuild pattern as the safe fallback.

2. **Silent NOT NULL:** Migration adds `ALTER TABLE sessions ADD COLUMN project_slug TEXT NOT NULL`. No DEFAULT, database has 200 existing rows. Expected: skill flags RISKY, states that existing rows will violate the constraint, and provides the exact fix with a default value.

3. **No transaction:** Migration has three ALTER TABLE statements with no `BEGIN TRANSACTION`. Expected: skill flags MISSING transaction wrapper as a RISKY finding, not a style comment.

4. **Type change bypass:** Migration script does `CREATE TABLE sessions_new (..., duration INTEGER)` and copies from `sessions` where `duration` was stored as TEXT. Expected: skill flags the type conversion and asks about the cast behavior for non-numeric text values already in the column.

5. **Backup absent on DROP TABLE:** Migration drops a table that `git grep` shows referenced in 3 source files. Expected: skill flags BLOCKED (active references) AND MISSING backup, not just one or the other.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/sqlite-ddl-limits.md` (proposed) | CLASSIFY phase — version-specific DDL support matrix |
| `references/table-rebuild-pattern.md` (proposed) | PROBE phase — canonical table rebuild SQL template |

---

## Example Flows

**Safe column addition:**
> "Add a nullable `resume_point` column to the sessions table."

CLASSIFY → ADD COLUMN nullable, no DEFAULT → SAFE → PROBE (skipped — no RISKY items) → VERDICT: SAFE, proceed.

**Blocked DROP COLUMN on old SQLite:**
> "Remove the `legacy_field` column from the tasks table. SQLite 3.31 in Docker."

CLASSIFY → DROP COLUMN detected, version 3.31 < 3.35 → BLOCKED → PROBE → table-rebuild pattern generated with exact SQL → VERDICT: BLOCKED, apply table-rebuild pattern before proceeding.

**Quick pre-commit check:**
> Schema migration audit, pre-commit mode.

CLASSIFY only → if any BLOCKED items: return BLOCKED immediately; if RISKY: return RISKY with list; if SAFE: return SAFE. No PROBE or deep remediation in pre-commit mode.

**NOT NULL trap:**
> "Add `project_slug TEXT NOT NULL` to the sessions table. We have 500 live sessions."

CLASSIFY → ADD COLUMN NOT NULL, no DEFAULT, DATA_AT_RISK: yes (500 rows stated) → RISKY → PROBE → fix: `ADD COLUMN project_slug TEXT NOT NULL DEFAULT 'unknown'` plus backfill → VERDICT: RISKY, apply fix before running.
