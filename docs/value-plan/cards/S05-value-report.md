# S05 Value report

Size M. Depends: S03, S04. Metric: makes V1 to V3 visible.

**Goal.** One report that answers: is youk helping, per arm, per week. It replaces org_score as the headline.

**Why.** STATS.md says org_score measures gates fired. Skill-rate is a proxy that rewards ceremony.
The patterns youk already saved say to replace proxies with outcome metrics.

**Load.** `servers/shared/events.py`, `scripts/export_stats.py`, `scripts/dashboard.py`, `EVAL.md`.

**Build.**
- `scripts/value_report.py` and `make value-report`: V1 (corrections per M+ task, repeat-gap rate), V2 (first-pass
  acceptance, evidence-packet rate once S13 exists), V3 (tokens, wall time, hook ms, session_start ms), grouped by arm and week.
- Interval estimates (bootstrap) when n is at least 10; otherwise print "n too small" and the raw counts.
- A "diagnostic" section keeps org_score, skill rate and close rate, labelled as process measures.
- `export_stats.py` headline switched to the value report.

**Tests.** Synthetic ledger with known answers; empty ledger; single arm.

**Out of scope.** Charts, Langfuse export.

**DoD.** Standard DoD.

**Kill criterion.** If nobody opens the report in 4 weeks, fold it into the session digest.

**Handoff.** Paste the first real report into the anchor's log entry.
