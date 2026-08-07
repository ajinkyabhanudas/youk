# youk — session stats

*Exported: 2026-08-07 · 88 sessions recorded*

> **What this measures:** youk tracks process discipline — whether engineering gates fired (NFR check, code review, skill invocation) before code was written. A high org\_score means the gates ran. It does not measure whether the code shipped was correct, performant, or secure. Those are separate quality signals.

## org score trajectory

**9.7/10  (+1.6 over 10 health checks)**

`▆▆▇███████`

*Left = oldest health check, right = most recent. Scale: 0–10.*

*Target: 7.0+ sustained over 20+ sessions.*

## skill invocation rate

**75% (40/53 real-work sessions)** — capability skill fired in at least one session with real work (commits or skill activity).

Capability skills: `nfr-check`, `dev-loop`, `code-review`, `stress-test`, `adr`, `write-spec`, `pm-review`, `security-review`, `verify`, `learn`.

*Target: >60%. Below 50% means gates are being skipped on real work.*

## session close rate

**53% (47/88 all sessions)** — sessions closed with `/done` (code-review + verify + learn in sequence).

*Target: >50%. `/done` is what closes the learning loop.*

## developer autonomy

*Did the developer pre-empt gates before youk asked? This is the primary signal that compounding is working — the developer internalised the gate, not just the tool.*

**0% (0/87 gate-eligible sessions)** — developer pre-empted a gate before youk asked.

*Target: rising trend over time. 0% is normal in early sessions.*

## skill gap trend

*SkillGap lines written per month — how many times youk detected a missed gate. A decreasing trend means gaps are being fixed. An increasing trend means new patterns are being encountered (expected in early sessions).*

| month | gaps logged |
|-------|-------------|
| 2026-06 | 2 |
| 2026-07 | 25 |
| 2026-08 | 1 |

*Target: stable or decreasing after session 20.*

## trajectory table

| date | org score |
|------|-----------|
| 2026-07-20 | 8.1/10 |
| 2026-07-21 | 8.1/10 |
| 2026-07-23 | 8.7/10 |
| 2026-07-24 | 9.4/10 |
| 2026-07-28 | 9.4/10 |
| 2026-07-30 | 9.5/10 |
| 2026-07-31 | 9.6/10 |
| 2026-08-03 | 9.7/10 |
| 2026-08-04 | 9.7/10 |
| 2026-08-05 | 9.7/10 |

## denominator reconciliation

> Two metrics use different session pools. Skill rate counts only sessions with real work; close rate counts all sessions. A session without commits or skills is counted by close rate but not skill rate.

| metric | value | numerator | denominator | denominator definition |
|--------|-------|-----------|-------------|------------------------|
| skill invocation rate | 75% | 40 | 53 | sessions with commits or skill activity |
| session close rate | 53% | 47 | 88 | all recorded sessions |
| developer autonomy | 0% | 0 | 87 | sessions with a gate-eligible Skills: line |

---

*These stats are from the author's own sessions. Run `make export-stats` in your own youk install to generate yours.*
