# references/evidence.md — Tagging Ladder, Verification-First Doctrine, R10

---

## Evidence Tagging Ladder

Apply to every piece of evidence cited. Verdicts require ≥ TRACED for load-bearing claims.

| Tag | Meaning | Sufficient for HOLDS? |
|-----|---------|----------------------|
| `[EXECUTED]` | Command run, output observed directly this session | Yes |
| `[TRACED]` | Read the source file/code; confirmed claim holds at the line level | Yes |
| `[READ]` | Read the document; claim appears there; code not traced | No — UNVERIFIED-AS-STATED |
| `[ASSUMED]` | Training knowledge or inference; no source file confirmed | No — UNVERIFIED-AS-STATED |

**Upgrade path:** Any claim currently tagged [ASSUMED] or [READ] can be upgraded by tracing
the relevant source file. Once upgraded, the verdict can change from UNVERIFIED-AS-STATED to
HOLDS or PARTIAL based on what the trace reveals.

**Downgrade trigger:** If tracing reveals the source contradicts the claim, downgrade to PARTIAL
or note the contradiction in the verdict.

---

## Verification-First Doctrine

Before assigning any verdict to a claim:

1. Identify the evidence tag the claim currently carries.
2. If [ASSUMED] or [READ]: attempt to trace the relevant source before assigning HOLDS.
3. If tracing is impossible (file access unavailable, system not running): assign UNVERIFIED-AS-STATED
   and document why tracing was not possible.
4. If tracing reveals the claim is correct: upgrade to [TRACED] and assign HOLDS.
5. If tracing reveals the claim is partially correct or implementation differs from description:
   assign PARTIAL with a specific one-line description of the discrepancy.

**The "check the code" reflex:** Whenever a doc or README makes a specific claim about behavior
(a formula, a threshold, a sequence, an enforcement mechanism), the first action is to read the
relevant source file. Not to accept the README at face value and tag [READ].

---

## R10 — Numeric Reconciliation (mandatory)

**Rule:** Any quantity appearing in ≥2 sources (committed file, live tool return, doc, metric,
CI output) must be explicitly reconciled with both values cited and their denominators/scopes
stated before the quantity is used in a finding.

**Why it exists:** Near-equal metrics from different denominators are exactly the hiding place
where analytical errors occur. A metric of 41% (all-sessions close rate) and 42% (all-sessions
skill invocation rate) are close enough to be confused under casual inspection, but measure
different things. Using either as the other produces a material error that survives into the
verdict.

**Application:**

For every quantity in a finding:
1. List all sources where the quantity appears.
2. For each source: state the value and the denominator/scope.
3. If values differ: state why (different filters, different time windows, different denominators).
4. State which value is used in the current finding and why.

**Format:**
```
[R10 — RECONCILED]
Quantity: {what is being measured}
Source 1: {value} — {file/tool}, {denominator/scope} [TAG]
Source 2: {value} — {file/tool}, {denominator/scope} [TAG]
Reconciliation: {why the values differ — different denominator, different time window, different filter}
Used here: {which value, which denominator, why}
```

**R10 triggers on:**
- Any percentage or rate that appears in ≥2 sources
- Any formula weight that appears in both code and docs
- Any threshold that appears in both config and README
- Any metric that a live tool return and a committed file both report (even if "the same")

**R10 does NOT require reconciliation for:**
- Quantities that appear in only one source
- Non-numeric claims (behavioral descriptions, design principles)
- Quantities where both sources agree exactly AND use the same denominator

---

## Null-Baseline as a Reusable Move

The null-baseline test is not specific to youk or to repos. It applies to any planning target:

**The move:** Before evaluating how well the target delivers its promise, ask what the user
gets WITHOUT the target. This establishes the baseline against which the target's marginal
value is measured.

**Reusable application:**

| Target type | Null-baseline question |
|------------|----------------------|
| Repo/product | What does the minimum-viable tier deliver? What requires the full stack? |
| Architecture | What does the system deliver without the proposed change? |
| Plan | What happens if we do nothing? What does the minimum intervention deliver? |
| Migration | What does running the current system unchanged cost vs. the migration? |
| Feature | What does the user do today without this feature? How much better is the feature? |

**Key finding pattern:** "X claims to deliver N benefits. The minimum tier delivers M of N.
The remaining N-M require [additional dependencies/infrastructure/behavioral change]."

This pattern is repeatable across targets. It systematically reveals overstatement in
"without/with" comparisons and tier distinctions.

---

## Live vs. Committed State (carries from DEV-1 + P4)

When analyzing a live system (not a clean clone):

1. **Record git SHA at start:** `git rev-parse HEAD` → log in STATE/progress.md
2. **Flag divergences:** Any place where live state (session files, audit log, runtime metrics,
   uncommitted changes) differs from committed state must be logged in STATE/deviation-log.md
3. **Live tool returns vs. committed files:** A live tool return (e.g. session_start metric)
   may use a different denominator, filter, or time window than a committed export (e.g. STATS.md).
   Apply R10: both values and their scopes must be reconciled.
4. **Uncommitted changes:** If the repo has uncommitted changes at analysis time, note which
   files are modified and whether those modifications affect any claims being evaluated.

**The lesson from this pack's material error:** The 41%/70% conflation occurred because
the live session_start return (42% all-sessions) and the committed STATS.md export (70%
real-work sessions, at an earlier session count) were both real values but used different
denominators. Neither was wrong — but using one as the other produced a material error
that survived into the gap register, verdict, and CAP acceptance criterion.

R10 exists because of this. Apply it whenever a metric appears in ≥2 places.
