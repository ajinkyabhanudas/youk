<div align="center">

<img src="assets/install-demo.svg" alt="youk — install, first session, compounding loop" width="100%"/>

[![CI](https://github.com/ajinkyabhanudas/youk/actions/workflows/ci.yml/badge.svg)](https://github.com/ajinkyabhanudas/youk/actions/workflows/ci.yml)
[![health.py coverage](https://img.shields.io/badge/health.py%20coverage-86%25-4CAF50)](tests/test_health.py)
[![Python](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/protocol-MCP-8B5CF6)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/license-MIT-22C55E)](LICENSE)

**Most AI coding tools give you a smart assistant. youk gives you one that gets measurably better at *your* work every week — and audits itself to prove it actually is.**

</div>

---

## The one-minute version

A fresh AI agent is as good on session 50 as session 1 — no better. youk changes the slope: the agent compounds.

- **It improves at your work.** When it's missing a capability for what you're doing, it builds one from your actual task. When a skill fails or gets skipped, it's patched *in that same session* — not queued. Recurring mistakes turn into fixes you approve once and never see again.
- **It routes by stakes.** A typo and a new subsystem get different treatment. Non-trivial work passes real gates — scope, non-functional requirements, review — *before* code is written.
- **It keeps itself honest.** youk runs its own health pulse every session, including checking that the capabilities it built are actually wired into the live loop — not just passing tests. It's designed to *not* become the tech-debt factory it exists to save you from.

The foundation under all of it is memory — working agreements, decisions, and your resume point written to files that outlive any chat and survive `git clone`. That part is table stakes; plenty of tools remember now. **What's rare is the layer on top: a system that improves at your specific work and can tell you whether it's succeeding.**

Nothing changes in how you work except the install.

| A typical AI assistant | youk |
|---|---|
| Equally capable on session 50 as session 1 | Compounds — fewer corrections over time |
| Same treatment for a typo and a rewrite | Routes by stakes; gates guard non-trivial work |
| Repeats mistakes you've corrected before | Patches the failing skill in the session it failed |
| No idea if it's actually helping | Reports its own `org_score` and health trend |
| (Also remembers context across sessions) | (Also remembers — but that's the floor, not the point) |

> **Status:** Active development (v0.1.0). Compounding starts on day one; the gains get obvious around session 10–20 as youk tunes to your patterns and the audit log fills.

---

## Start here (60 seconds)

You don't need Docker or an install to try it. Pick your level:

| Level | What you get | Setup |
|---|---|---|
| **1 — youk-lite** | Memory across sessions | Paste ~8 lines into your `CLAUDE.md` → **[docs/youk-lite.md](docs/youk-lite.md)** |
| **2 — full youk** | Memory + skill routing + the self-improving loop | One install command (Docker) ↓ |

**Most people should start at Level 1.** It needs zero dependencies and the value shows immediately. Upgrade when memory alone isn't enough.

### Full install (Level 2)

**macOS / Linux / WSL2 / Git Bash:**
```bash
curl -sL https://raw.githubusercontent.com/ajinkyabhanudas/youk/main/scripts/install.sh | bash
```

**Windows PowerShell** (`curl | bash` won't work here):
```powershell
git clone https://github.com/ajinkyabhanudas/youk "$HOME\.claude\youk"
cd "$HOME\.claude\youk"; Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass; .\scripts\install.ps1
```

One command — builds the Docker image, registers the MCP servers, patches your `CLAUDE.md`. First run ~2 min; re-runs are idempotent. Then open any Claude Code session and just work — youk activates itself.

**Prerequisites:** Docker Desktop (running) · Claude Code · Python 3.11+
**Verify anytime:** `bash ~/.claude/youk/scripts/doctor.sh` — checks every dependency and prints a `Fix:` line for anything broken.

Full platform-by-platform walkthrough: **[docs/getting-started.md](docs/getting-started.md)**.

---

## What youk does, in four ideas

1. **Improves at your work.** When a skill is missing, youk generates one from your actual task — not a generic template. When a skill fails or gets skipped, it's patched in the same session it failed. Recurring gaps become proposals you approve once.

2. **Routes by stakes.** A one-line fix and a new subsystem get different treatment. Non-trivial work passes gates (scope → non-functional requirements → review) *before* code is written.

3. **Audits itself.** youk runs its own pulse every session — including checking that the capabilities it built are actually wired into the live loop, not just passing tests. Run `/health` anytime for an `org_score` (0–10) and a trend. This is the guard against youk quietly becoming tech debt.

4. **Remembers (the foundation).** Working agreements, decisions, and your resume point are written to files, reloaded every session, and survive `git clone`. Necessary groundwork — but the three above are what make youk different from a tool that only remembers.

Deeper on any of these: **[docs/well-architected.md](docs/well-architected.md)** · **[PHILOSOPHY.md](PHILOSOPHY.md)** · [Wiki](https://github.com/ajinkyabhanudas/youk/wiki).

---

## Everyday use

Once installed, you mostly just work. A few commands are worth knowing:

| Command | When |
|---|---|
| `/build` | Starting a feature or non-trivial change — runs the gate chain |
| `/done` | End of a session — reviews, captures what was learned, closes the loop |
| `/health` | Anytime — how is youk doing? |
| `/learn` | Extract and save what today taught you (included in `/done`) |

The single most important habit: **type `/done` at the end of a session.** That's what closes the compounding loop — without it, the work happened but youk didn't learn from it.

Full command list and routing detail: **[docs/getting-started.md](docs/getting-started.md)**.

---

## Reference

| Topic | Doc |
|---|---|
| Full setup, every platform | [docs/getting-started.md](docs/getting-started.md) |
| youk-lite (no install) | [docs/youk-lite.md](docs/youk-lite.md) |
| Design principles | [docs/well-architected.md](docs/well-architected.md) · [PHILOSOPHY.md](PHILOSOPHY.md) |
| Guard rails & safety | [docs/guardrails.md](docs/guardrails.md) |
| Variants & configuration | [docs/variants.md](docs/variants.md) |
| Author's live stats | [STATS.md](STATS.md) |
| Everything else | [Wiki](https://github.com/ajinkyabhanudas/youk/wiki) |

**Uninstall** (preserves your knowledge; `--purge` to remove it too):
```bash
bash ~/.claude/youk/scripts/uninstall.sh
```

---

## Contributing & License

Issues and PRs welcome. Run `make checkup-fast` before pushing. MIT — see [LICENSE](LICENSE).
