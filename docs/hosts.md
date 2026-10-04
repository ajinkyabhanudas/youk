# Agent hosts

youk's core is host-neutral: policy reads a versioned capability declaration, never a
vendor name ([ADR-012](adr/adr-012-agent-host-capability-contract.md)). A host connects to
youk in two ways, and they are independent:

1. **MCP tools** (`youk-core` :8001 and `youk-code` :8002, streamable HTTP). Any MCP client
   can call them. Everything youk reasons about (sizing, claim verification, learnings,
   Domain Brief, health) is reached this way and behaves the same on every host.
2. **Host hooks** (session start, compaction, prompt submit, pre-tool guard). These let youk
   act without the model choosing to call a tool. Each host needs an adapter that translates
   its hook events.

## Capability matrix

Generated from `servers/shared/agent_host.py`; `tests/test_hosts_doc.py` fails if this table
drifts from it. "yes" means the adapter declares the capability. `scripts/host_inventory.py`
separately confirms each declared capability is wired to a real hook in the repo.

| Capability | Class | claude-code | codex |
|---|---|---|---|
| session_context | safety | yes | yes |
| compaction_context | advisory | yes | yes |
| prompt_context | advisory | yes | yes |
| pre_tool_guard | safety | yes | yes |

A safety capability a host does not declare is **blocked** (fails closed); a missing
advisory capability is **degraded**. An unregistered host declares nothing, so it gets the
MCP tools but not the hook-driven safeguards.

## Verification status

- **Claude Code:** exercised in daily use.
- **Codex:** hooks are registered and `host_inventory.py` finds them wired, but they have not
  been exercised against a live Codex session. Treat Codex hook behaviour as designed, not
  proven.
- **Any other MCP host:** tools work. Hook-driven safeguards do not exist for it. Use the
  working agreements in `AGENTS.md` and [youk-lite](youk-lite.md), which need no tooling.

## What is still Claude-rooted

The policy layer is neutral; the installation layer is not yet. Measured by matches of
`.claude`, `CLAUDE_ROOT`, `CLAUDE_DIR`, `claude mcp` or `CLAUDE.md` in code:

| Where | What it assumes |
|---|---|
| `scripts/install.sh`, `install.ps1`, `uninstall.*`, `doctor.sh`, `lib/snapshot.sh` | install into `~/.claude/youk`, register servers with `claude mcp add`, patch `CLAUDE.md` |
| `servers/core/src/health.py`, `session.py`, `skill_signals.py` | audit logs and skills under `~/.claude/` |
| `Makefile` | `CLAUDE_DIR` default |
| `servers/shared/skill_loader.py` | skills mounted into the containers at `/claude` (`CLAUDE_ROOT`) |

Registering the two servers with another host is one MCP configuration entry (the URLs
above); the installers just do not do it for you yet. Migrating these paths behind one
configurable home directory is the open follow-up to ADR-012.
