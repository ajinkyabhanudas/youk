# Tool Contract Template

Every MCP tool and AI step must define these 6 fields before it is used in any routing path.
Missing fields are a contract violation — the tool's behavior is undefined under failure.

---

## Template

```
Name: <tool_name>
Description: <one sentence — what the tool does, not how>
Input schema:
  - <param>: <type> [required|optional] — <constraint: nullability, enums, ranges, sequencing>
  - ...
Output schema:
  - <field>: <type> — <always-present or conditional on: ...>
  - ...
Failure modes:
  - <condition> → <what the tool returns or raises>
  - ...
Side effects:
  - reads: <state files or external resources read>
  - writes: <state files or external resources written>
  - sequencing constraints: <must run before/after X; idempotent? destructive?>
```

---

## Applied contracts — 8 critical-path tools

### session_start

```
Name: session_start
Description: Opens a session for a project directory, returns a SessionState with resume
             context, session plan, contracts, and all machine signals for the session.
Input schema:
  - project_dir: str [required] — absolute path to the project; must be resolvable by
                                  _resolve_project_path(); empty string raises ValueError
Output schema:
  - project: str — always present; slug derived from project_dir
  - resume_point: str — always present; may be empty string if no prior context
  - session_counter: int — always present; monotonic, starts at 1
  - session_plan: list[str] — always present; may be empty list
  - contracts: list[str] — always present; loaded from contracts.md; may be empty
  - force_learn: bool — always present; True = run /learn immediately (Option C)
  - health_check_due: bool — always present; True = run /improve this session
  - pending_build_task: str | None — None = no unrouted commits detected;
                                     non-None = commits landed without routing, description
                                     to pass to /build before next code task
  - falsifier_alerts: list[dict] — always present; may be empty
  - audit_patterns: list[dict] — always present; may be empty
  - brief: str — always present; YOUK CONTEXT BRIEF block for compaction
Failure modes:
  - project_dir unresolvable → ValueError("project_dir required")
  - state files corrupted/missing → silent defaults; session_counter resets to 1
  - git log unavailable → resume_point from context.md only; no commit history
Side effects:
  - reads: {slug}/context.md, {slug}/active_task.json, {slug}/routing-breadcrumb.json,
           contracts.md, session-open.json (legacy redirect), audit/*.md, voice-audit.json
  - writes: session-open.json (root-level redirect), {slug}/session-open.json,
            project-context.json (first-seen only)
  - sequencing constraints: must be called once per session before any other tool;
                            calling twice in one session increments session_counter
```

### session_end

```
Name: session_end
Description: Closes the session, writes audit entry, updates compounding scores, and
             returns a session_delta block for display.
Input schema:
  - reason: str [required] — "done" | "retroactive-close"; controls audit outcome field
  - commits_made: bool [required] — True if any git commit ran this session
  - close_cluster: bool [required] — True only when /done was explicitly typed;
                                     False for /close, retroactive-close, or Option C
  - explicit_contracts: list[str] [optional, default=[]] — new contracts saved this session
  - decision_retrospectives: list[dict] [optional, default=[]] — {decision, outcome, evidence}
  - autonomy_depth: dict [optional, default={}] — {skill_name: SURFACE|WORKING|DEEP|ELITE}
  - contract_violations: list[str] [optional, default=[]] — free-text descriptions
  - findings: dict [optional, default={}] — {severity: count} from code-review
  - finding_categories: list[str] [optional, default=[]] — domain labels per finding
  - outcome: str [optional, default="NONE"] — SHIPPED|STAGED|ABANDONED|NONE
  - outcome_result: str [optional, default="UNKNOWN"] — WORKED|FAILED|PENDING|UNKNOWN
Output schema:
  - session_delta: dict | None — None if session had no compounding signal;
                                 present when close_cluster=True and skills > 0
    - contracts: int — contracts added this session
    - contracts_total: int — cumulative total
    - domain_knowledge: int — concepts added
    - skills_invoked: int — capability skills fired
    - verdict: str — COMPOUNDING|STATIC
Failure modes:
  - no active session (session-open.json missing) → writes audit entry with unknown slug
  - audit dir write failure → silent; session_delta still returned
Side effects:
  - reads: session-open.json, {slug}/context.md, audit signals
  - writes: audit/{YYYY-MM}.md (appends session entry), session-open.json (deleted),
            {slug}/context.md (updated), audit-signals.jsonl, voice-audit.json
  - sequencing constraints: must be called last; calling before compact_context loses
                            the compacted brief from the audit entry
```

### task_checkpoint

```
Name: task_checkpoint
Description: Records mid-task progress, checks goal state, and fires pattern_trigger
             if a recurring session learning has been observed 2+ times.
Input schema:
  - project_dir: str [required] — same value passed to session_start
  - task_label: str [required] — human-readable description of the completed sub-task
  - size: str [required] — XS|S|M|L|XL; gates whether ceremony check runs
  - session_learnings: list[str] [optional, default=[]] — observations to persist;
                                                          triggers pattern_trigger on repeat
Output schema:
  - goal_check: dict — always present
    - goal_met: bool — True if success_criteria in session-goal.json satisfied
    - stated_goal: str | None — None if session-goal.json absent
  - pattern_trigger: list[str] — empty if no recurring patterns; non-empty = act immediately
  - dev_loop_not_registered: str | None — None if dev-loop was recorded for this task;
                                          non-None = ceremony gap message
  - medium_risk_unsurfaced: bool — True if medium-risk-question.json exists and surfaced=False
Failure modes:
  - project_dir unresolvable → returns {goal_check: {goal_met: false}, pattern_trigger: []}
  - session-goal.json absent → goal_check.goal_met=false, stated_goal=None
Side effects:
  - reads: session-goal.json, {slug}/ceremony-sequence.json, {slug}/medium-risk-question.json
  - writes: audit stub (first checkpoint only), session_learnings to knowledge store
  - sequencing constraints: M+ tasks must call after each significant sub-task; firing
                            pattern_trigger requires immediate action, not deferred to /done
```

### route_task

```
Name: route_task
Description: Classifies task size and returns routing plan with skills, plan hook, and
             token budget. Core gate before any code work.
Input schema:
  - task: str [required] — task description; vague input should be pre-processed by
                           optimize_intent first
  - intent_brief: str [optional] — output from optimize_intent; improves size accuracy
  - file_context: list[str] [optional] — file paths relevant to the task; passed as
                                         leading context to the first route_to_skill call
Output schema:
  - size: str — XS|S|M|L|XL; always present
  - plan_hook: str — always present; empty string if no plan output needed
  - skills: list[str] — always present; may be empty for XS
  - blocked: bool — always present; True = intake_required or translation_risk=high
  - collapsing_question: str | None — None when blocked=False; present when blocked=True
  - token_budget: int — always present; remaining session budget estimate
  - warnings: list[dict] — always present; may be empty; each has rule_id and message
  - graph_state: dict | None — None if no pending tasks; present when task graph active
  - has_skill_md: bool — always present; False = skill generation candidate
  - file_context: list[str] — echoed back; always present
Failure modes:
  - task empty → blocked=True, collapsing_question="what is the task?"
  - translation_risk=high → blocked=True, collapsing_question=<sharpening question>
  - MCP offline → caller must surface "route_task unavailable" and halt M+ work
Side effects:
  - reads: contracts.md, {slug}/ceremony-sequence.json, skill-graph.yaml
  - writes: {slug}/routing-breadcrumb.json (records route_task fired + task description)
  - sequencing constraints: must run before any M+ implementation; blocked=True means
                            halt — never proceed past a blocked route_task
```

### mark_challenge_ran

```
Name: mark_challenge_ran
Description: Persists a flag that the challenge skill completed for this session slug,
             unblocking check_challenge_gate.
Input schema:
  - task: str [required] — task description matching what was challenged; stored in flag
  - angles_checked: list[str] [optional, default=[]] — challenge angles covered; stored
                                                        for retrospective audit
Output schema:
  - ok: bool — always True on success
  - flag_path: str — absolute path of the written flag file
Failure modes:
  - no active session slug → raises ValueError; gate remains blocked
  - write failure → raises IOError; gate remains blocked
Side effects:
  - reads: session-open.json (to resolve slug)
  - writes: {slug}/challenge-ran.json — {task, angles_checked, ran_at}
  - sequencing constraints: must run AFTER challenge skill returns PASSED verdict;
                            idempotent (overwrite safe); consumed by check_challenge_gate
```

### check_loop_dry

```
Name: check_loop_dry
Description: Verifies the challenge reasoning loop has reached convergence (zero new
             objections from all angles). Returns dry=True only when all angles pass
             with no new findings in the last round.
Input schema:
  - angles: list[str] [required] — angles covered in the challenge loop
  - new_objections_this_round: int [required] — count of objections from the last round;
                                                must be 0 for convergence
  - task: str [optional] — task context; stored in loop-dry record
Output schema:
  - dry: bool — True = loop converged; False = must run another round
  - reason: str — always present; explains why dry=True or what angle is still open
  - rounds_run: int — always present; total rounds detected from challenge-ran.json history
Failure modes:
  - angles empty → dry=False, reason="no angles provided"
  - new_objections_this_round > 0 → dry=False always, regardless of round count
  - challenge-ran.json absent → dry=False, reason="challenge not yet marked as run"
Side effects:
  - reads: {slug}/challenge-ran.json
  - writes: none
  - sequencing constraints: call at the end of each challenge round; do NOT exit the loop
                            on round count alone — only on dry=True
```

### check_nfr_gate

```
Name: check_nfr_gate
Description: Validates that NFR check output meets the bar required to proceed with
             M+ implementation. Blocks if key decisions are missing or unresolved.
Input schema:
  - task: str [required] — task being gated
  - size: str [required] — XS|S|M|L|XL; gate only fires for M+
  - nfr_decision_block: str [required for M+] — full NFR Decision Block output from
                                                 nfr_check; empty string fails the gate
Output schema:
  - blocked: bool — always present; True = must re-run nfr_check before proceeding
  - reason: str — always present; empty string when blocked=False
  - ceremony_warning: str | None — None if challenge ran before nfr; non-None if
                                   ceremony order was violated (warning, not block)
Failure modes:
  - size XS/S → blocked=False always; gate is a no-op
  - nfr_decision_block empty on M+ → blocked=True, reason="NFR block missing"
  - MCP offline → caller must treat as blocked and halt
Side effects:
  - reads: {slug}/challenge-ran.json, {slug}/ceremony-sequence.json
  - writes: {slug}/ceremony-sequence.json (records "nfr" gate fired)
  - sequencing constraints: must run after nfr_check completes and before dev-loop;
                            re-run nfr_check if blocked=True
```

### check_challenge_gate

```
Name: check_challenge_gate
Description: Verifies that mark_challenge_ran was called this session, unblocking
             M+ implementation. Hard gate — implementation cannot proceed while blocked.
Input schema:
  - task: str [required] — task being gated; must match what was passed to route_task
  - size: str [required] — XS|S|M|L|XL; gate only fires for M+
Output schema:
  - blocked: bool — always present; False = safe to proceed
  - reason: str — always present; empty string when blocked=False
  - ceremony_warning: str | None — None if nfr ran before challenge_gate check;
                                   non-None if ceremony order was violated
Failure modes:
  - size XS/S → blocked=False always; gate is a no-op
  - challenge-ran.json absent for current slug → blocked=True
  - no active session → blocked=True, reason="no active session slug"
Side effects:
  - reads: {slug}/challenge-ran.json, session-open.json
  - writes: {slug}/ceremony-sequence.json (records "challenge_gate" fired on pass)
  - sequencing constraints: must run after mark_challenge_ran and after check_nfr_gate;
                            L/XL blocked → route adversary-loop; M blocked → re-run challenge
```
