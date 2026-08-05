# youk skill trust artifact — how capability skills show their thinking

Design locked 2026-08-05 (session #69) via ux-designer skill. This is youk's
signature trust surface: how a developer sees that a capability skill's reasoning
(stress-test, code-review, challenge, nfr-check) actually ran and what it yielded.

## Ideology (creator's hard constraints)

- **Minimum ink, maximum witnessed value.** User sees as little as possible; what
  they DO see must prove youk earned its keep.
- Never show phase-by-phase prose, round counts, or intermediate findings inline —
  wasted screen real estate.
- The user must SEE thinking was deployed — not silence, not a faint line — as a
  compressed VISUAL artifact, not a paragraph.
- Three jobs (cognitive psych): REASSURE (it ran), INFORM (angles covered), SATISFY
  (verdict + what it caught). Reduce uncertainty without spending attention.
- Receipt voice = value in the user's terms ("caught 2 data-loss bugs before they
  shipped"), never tool telemetry.

## The single idea (craft-gate D9)

Evidence, not assertion — the verdict is on top, its proof is one glance below.
Attention-weighted ink: cheap summary on top (all a veteran needs), expensive proof
below (for the wary new user to verify). Verdict-first because developers read top-down.

## Four fields the dev must read at a glance (low ink, max value)

1. **verdict + value** — what youk caught, in the dev's terms (SATISFY).
2. **why THIS verdict** — the load-bearing reason the reasoning landed here (not why
   the task was done — why the judgment went this way).
3. **proof strip** — angles attacked, each ✓ or ⚠ⁿ→fixed (REASSURE + INFORM).
4. **open surface** — what is genuinely still open, read from youk's OWN convergence
   state, never guessed. See the convergence-honesty rule below.

## Convergence-honesty rule (resolves the "run-to-dry vs show-open-angle" paradox)

youk's loops exit on convergence (zero new objections from all 7 angles: structural,
operational, experiential, adversarial, temporal, outcome, semantic), NOT round count.
So "unchallenged angle" cannot mean "an angle youk skipped" — post-convergence there
are none. The honest open surface is what convergence itself REVEALS, already tracked
in `convergence_state`:
- `distance_from_optimum` (e.g. "0/7") — did it truly run to dry.
- `unknown_unknowns: [...]` — the open edges convergence surfaced. THIS is the "open"
  line. It exists because convergence found it, not because youk was lazy.
- Things unfalsifiable IN THIS ENVIRONMENT (e.g. "Windows .ps1 path — no Windows host
  to run it here"). Honest claim: unprovable here, not unchecked.

The `open:` line reads these fields. If `distance_from_optimum` is 0/7 AND
`unknown_unknowns` is empty AND nothing is unfalsifiable-here → the artifact says
`fully closed` explicitly (a rare, earned signal, not filler). The open line is
ALWAYS present so its absence can never be misread as completeness.

## Templates skills emit

Caught-something (the case that matters):
```
✓ youk caught {N} issue(s) before they shipped — {value list}. fixed + verified.
  why: {load-bearing reason THIS verdict, ≤10 words}
  {skill}  {angle ✓|⚠ⁿ} … → {verdict}
  {skill}  {angle ✓|⚠ⁿ} … → {verdict}
  open: {unknown_unknowns / unfalsifiable-here, ≤12 words | "fully closed"}
```

Clean pass (nothing caught — thinking still shown):
```
✓ youk pressure-tested this — no issues across {angles_converged}/7 angles.
  why: {load-bearing reason, ≤10 words}
  {skill}  {all angles ✓} → {verdict}
  open: {… | "fully closed"}
```

Worked example (real run, session #69 uninstall feature):
```
✓ youk caught 3 issues before they shipped — 2 data-loss bugs, 1 wrong-delete. fixed + verified.
  why: file-mutation + symlink-removal are the irreversible paths — deepest attack there
  stress-test  scale ✓  edge ⚠²  assume ⚠¹  → SURVIVES
  code-review  precedence ⚠¹                → fixed
  open: Windows .ps1 uninstall path unfalsifiable here (no Windows host)
```

## Rules baked in

- `⚠ⁿ` always pairs with `→ fixed` on the same visual row — a problem is never shown
  without its resolution (no anxiety residue).
- Line 1 never uses tool words (no SURVIVES/APPROVED); those live only in the proof-strip.
- Max 4 proof rows; more skills collapse to `+k more ✓`.
- No box-drawing borders — alignment alone carries it (renders anywhere, less ink).
- Degrade to plain ASCII (`v`, `!2`) if unicode unavailable.

## Two paired fixes (next task, M+ — build after uninstall is committed)

1. **Plan-approval → gates handoff** (kills double-work where the dev has to ask
   "did you run stress-test?"). Scope: **M+ plans only.** Mechanism: extend the
   existing plugin PostToolUse hook ([plugin/scripts/post_tool_use.py]) — on
   `tool_name == "ExitPlanMode"`, flag `active_task.json`. Then `user_prompt_submit.py`
   injects a one-line directive ("approved M+ plan → run route→nfr→dev-loop→code-review
   →stress-test→verify now, don't ask") and clears the flag. No settings.json change,
   no new hook event — the PostToolUse surface already exists and matches on tool_name.

2. **Skill impact receipt** — CLAUDE.md Output Contract gains: capability skills
   surface only this artifact, verdict-first, value-voiced; never phase prose. Audit
   writer (session_end) records skill YIELD (`stress-test(2 fixed)`) not bare names,
   so the durable trail shows impact, not just invocation. See [[tool-enforced-gates]].
