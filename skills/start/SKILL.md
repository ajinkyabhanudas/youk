---
name: start
description: >
  Session activation and welcome card. Fires on /start, "activate youk",
  or any equivalent phrase at the beginning of a session. Calls session_start,
  reads pending state, and produces a single structured card that orients
  both the human and the agent. Works for fresh clones (no prior context) and
  returning sessions (prior work to resume). No code written. No tasks started.
  Output is the card, then silence — wait for the user to direct.

fast-path: |
  If session_start was already called this session AND resume_point is set,
  skip LOAD and go straight to RENDER using the data already in context.
---

# start — Session Activation

One command. One card. Everything needed to begin.

---

## Invocation

Triggered by any of:
- `/start`
- `activate youk`
- `youk`
- "what's the plan", "where were we", "what are we working on" (first message only)

Do NOT trigger this mid-session for status checks — that's `/plan` or `/health`.

---

## Phase 1 — LOAD

Call these tools in order:

```
youk-core.session_start(cwd)          → state, resume_point, session_plan, context_health,
                                         pending_proposals_count, contracts, project_context_files
youk-core.get_proposals()             → pending proposals (if pending_proposals_count > 0)
```

If `health_check_due` is True in session_start response, also call:
```
youk-core.self_heal()                 → org_score, findings (surface as one-liner in card)
```

Store all responses. Do not output anything yet.

---

## Phase 2 — READ CONTEXT

From session_start, determine the session mode:

**Fresh install / first session:**
- `context_health == "NONE"` AND no prior audit entries
- No resume_point, no contracts, git log may be sparse
- Mode: ONBOARD

**Fresh clone / new machine:**
- `context_health == "L1"` or `"L4"` (README found, no .claude/ files)
- readme_snippet present, no contracts or decisions yet
- Mode: ORIENT

**Returning session:**
- `context_health == "L2"` or higher, OR resume_point is set
- Contracts loaded, resume_point meaningful
- Mode: RESUME

---

## Phase 3 — RENDER

Output one card. Format exactly as shown below — no preamble, no narration.

### ONBOARD mode (fresh install, no prior context)

```
youk — session #1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{IF readme_snippet}Project: {readme_snippet}{END IF}
{IF stack}Stack: {stack}{IF framework} / {framework}{END IF}{END IF}

I remember what you agree to. Say "always use X" or "never do Y" this
session and it loads automatically every future session. By session 5,
I know your patterns. By session 20, you stop re-explaining things.

One thing matters: type /done before you close this tab.
That saves today's session. Contracts are safe as you go — the session
record and /learn output need /done.

{IF no survey exists}
I don't have a map of this codebase yet.
  /survey — 12-question map: stack, modules, entry points, integrations
{END IF}

Ready. What are we building?
```

### ORIENT mode (fresh clone, project detected)

```
youk — session #1 on {project}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Project: {readme_snippet}
Stack: {stack}{IF framework} / {framework}{END IF}

No prior context on this machine. Working agreements you make today
load automatically every future session.

I don't have a codebase map yet. Run /survey first — it produces a
one-page map (stack, modules, entry points, integrations) that loads
in every future session brief and is ready for any joining developer.

One thing matters: type /done before you close this tab.
That's how today's session saves. Contracts are safe as you go.

Ready. Start with /survey, or tell me what to build.
```

### RESUME mode (returning session)

```
youk — session #{n} on {project}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Picked up from
  {resume_point}

Today's plan
  1. {session_plan[0]}
  2. {session_plan[1]}
  3. {session_plan[2]}
  ... (up to 5 items)

{IF days_since_last >= 7}
  Note: plan items above are from your last session. Run /plan to rebuild from current git state if the project moved.
{END IF}

{IF pending_proposals > 0}
  ⚑ {pending_proposals_count} proposal(s) pending review — /health to see them
{END IF}

{IF contracts exist}
  {contracts_count} rules active{IF domain_concepts_count > 0} · {domain_concepts_count} domain concepts{END IF} · session #{n}
  "{most_recent_contract}"{IF session_counter <= 5}  <- loaded automatically{END IF}
{END IF}
{IF contracts is empty}
  Session #{n} · no rules saved yet — working agreements you set today load next time
{END IF}

{IF session_counter >= 30}
  30 sessions in — your rules load faster than you'd re-explain them.
{ELSE IF session_counter >= 10}
  10 sessions in — the system knows your patterns.
{END IF}

{IF health_check_due AND self_heal was called}
  Health: {org_score}/10 — {first finding, one line}
{END IF}

{IF dashboard_summary is non-empty}
  Trend: {dashboard_summary}
{END IF}

{IF pending_proposals > 0}
  {pending_proposals_count} proposal(s) pending — /health to see them
{END IF}

Commands: /build · /done · /check · /health · /plan · /decide

Note: if this project has .claude/skills/done, it overrides youk's /done. Use 'ship it' phrase instead.

Ready. What's first?
```

---

## Rules

- Output the card once. Then stop. Do not start tasks, ask questions, or suggest next steps beyond "what's first?" or "what are we building?".
- Fill in actual values from the tool responses — never placeholder text.
- If session_plan has fewer than 3 items, only list what exists. Do not pad.
- If pending_proposals_count is 0, omit that line entirely.
- If contracts list is empty, omit the rules/contracts lines.
- `━` divider width: match the header line length (adjust to fit project name).
- No em dashes in the card output.

## Data bindings for RESUME card

- `{contracts_count}` — `len(contracts)` from session_start response
- `{domain_concepts_count}` — count of `*.md` files in `knowledge/domain/` excluding `gaps.md` (read from brief or domain_knowledge field if present)
- `{most_recent_contract}` — last item in `contracts` list, truncated to 60 chars
- `{session_counter}` / `{n}` — `session_counter` from session_start
- `{no survey exists}` — true when `survey_stale_note` in session_start contains "No codebase survey yet"
