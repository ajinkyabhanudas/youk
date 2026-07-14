# youk — session stats

*Exported: 2026-07-14 · 39 sessions recorded*

> **What this measures:** youk tracks process discipline — whether engineering gates fired (NFR check, code review, skill invocation) before code was written. A high org\_score means the gates ran. It does not measure whether the code shipped was correct, performant, or secure. Those are separate quality signals.

## org score trajectory

**6.3/10  (+0.2 over 6 health checks)**

`▅▅▅▅▅▅`

*Left = oldest health check, right = most recent. Scale: 0–10.*

*Target: 7.0+ sustained over 20+ sessions.*

## skill invocation rate

**70%** — capability skill fired in 14 of 20 sessions with real work (commits or skill activity).

Capability skills: `nfr-check`, `dev-loop`, `code-review`, `stress-test`, `adr`, `write-spec`, `pm-review`, `security-review`, `verify`, `learn`.

*Target: >60%. Below 50% means gates are being skipped on real work.*

## session close rate

**41%** — 16 of 39 sessions closed with `/done` (code-review + verify + learn in sequence).

*Target: >50%. `/done` is what closes the learning loop.*

## developer autonomy

*Did the developer pre-empt gates before youk asked? This is the primary signal that compounding is working — the developer internalised the gate, not just the tool.*

**0%** — developer pre-empted a gate in 0 of 38 sessions where a gate could have fired.

*Target: rising trend over time. 0% is normal in early sessions.*

## skill gap trend

*SkillGap lines written per month — how many times youk detected a missed gate. A decreasing trend means gaps are being fixed. An increasing trend means new patterns are being encountered (expected in early sessions).*

| month | gaps logged |
|-------|-------------|
| 2026-06 | 2 |
| 2026-07 | 23 |

*Target: stable or decreasing after session 20.*

## trajectory table

| date | org score |
|------|-----------|
| 2026-07-02 | 6.1/10 |
| 2026-07-03 | 6.1/10 |
| 2026-07-05 | 6.2/10 |
| 2026-07-09 | 6.1/10 |
| 2026-07-10 | 6.1/10 |
| 2026-07-13 | 6.3/10 |

---

*These stats are from the author's own sessions. Run `make export-stats` in your own youk install to generate yours.*
