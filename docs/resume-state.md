# Where a project stopped

Ask youk where a project stopped and the answer is computed from facts at that moment. No note is
stored, so none can go stale, be overwritten by a later writer, or silently fail to save.

## The two sources

| Source | Records | Written by | Closed by |
|---|---|---|---|
| Task graph (`state/task-graph.db`) | what was started and what is next, per project | `route_task` (M and larger) starts a task: tagged to the project, in flight, claimed by the session | `task_checkpoint` marks the routed task done |
| Git (the project directory) | the work as it is: branch, last commit, uncommitted files | git | not applicable |

A task that is in flight and not done was started and never finished. That is what "stopped mid-task"
means, and it needs no one to remember to write it down.

`src: servers/core/src/resume.py`. `where_stopped(slug, project_dir)` returns the structured answer;
`render` makes the one line shown at session start:

    Resume: STOPPED MID-TASK: wire the report | NEXT: write the docs | git: feat/x, 3 uncommitted file(s), last commit abc1234 add the parser (2 hours ago)

A project's own authored "Resume from" line (its `.claude/prd-status.md`) is shown after the facts and
never replaces them. Each source is read independently, so a failure in one costs only its part.

## What was removed, and why

Before, where a project stopped was a prose line (`resume-from:` in `context.md`) written by six code
paths with six wordings. The last writer won. It beat every fresher source when read, did nothing when
`context.md` was missing, and needed a schema, a recursion guard and a container-path workaround to stop
corrupting itself. Removed:

- the `resume-from:` line and `_update_resume_point` with its six call sites
- `_strip_resume_wrapping`, `_resolve_youk_root`, and the `ResumePointer` schema (they existed only to patch that line)
- `pre-close.json` (it was read but always lost to the prose line, so it never worked)
- `resume_candidate` in `session-checkpoint.json`, and the plan-derived "Last working on" write
- the scrape of a summary line into a resume note at `session_end`

Older `context.md` files may still hold a `resume-from:` line. It is ignored and dropped the next time
that file is rewritten.

## Two bugs fixed that made the old answer wrong

- `route_task` seeded graph nodes with no project (113 of 147 rows), and `next_task(project)` also matched
  project-less rows, so another project's stub could come back as this project's next task. `next_task` is
  now strictly scoped, and routing tags the project.
- Nothing ever marked a routed task in flight or done. It does now (`start_task` at routing, `mark_done` at
  `task_checkpoint`).

## One identity per project

The slug used to be the directory's basename in seven places, so a git worktree was its own project.
`servers/shared/project_identity.py` is the single rule: a worktree belongs to the repository it was
made from; every other directory keeps its basename. Hooks, the server and the ledger all use it.

## Stores that remain, and what each is for

| Store | Role | Not a resume store because |
|---|---|---|
| `state/task-graph.db` | intent and lifecycle per project | it is a source |
| git | work state | it is a source |
| `state/events/` | what happened, for the value report | it records activity, not position |
| `state/active_task.json` | what the model touched, for PreCompact | a snapshot for compaction, not read for resume |
| `state/session-plan.json` | the plan shown at session start | output of start, not input to it |
| `knowledge/projects/{slug}/context.md` | project type, first seen, recent commits | static context |
| `state/session-checkpoint.json` | lets a dropped session's audit entry be written | audit recovery only |
| audit logs | session history for the health score | history |

## How a new session picks up

1. The SessionStart hook calls `session_start`, which runs `where_stopped` for the project and puts the
   line in the brief and the digest.
2. For the value plan, the next card comes from the same task graph (`next_task`), which is loaded from
   `docs/value-plan/tasks.json`.
3. Nothing depends on a session having ended cleanly.

What this does not cover: a task of size XS or S is never routed, so it leaves no graph record. Its only
trace is git (uncommitted files, last commit). A task finished without calling `task_checkpoint` stays in
flight until it is.
