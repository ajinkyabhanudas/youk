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

## Installing for a host

`scripts/install.sh` chooses the host after cloning: `YOUK_HOST=claude-code|codex|none`, or
detected from `PATH` (Claude Code wins when both CLIs exist). It then does only what that host
owns:

| Step | claude-code | codex | none |
|---|---|---|---|
| Register `youk-core` / `youk-code` | `claude mcp add --scope user ... --transport http` | `codex mcp add <name> --url ...` | prints the two URLs |
| Instructions file | `~/.claude/CLAUDE.md` | `$CODEX_HOME/AGENTS.md` (or `AGENTS.override.md` when that exists and is non-empty, since Codex reads only one) | none |
| Skill links, hooks plugin, pre-install snapshot | yes | no (skills are served over MCP) | no |
| Container mount `/host` | `~/.claude` | `~/.codex` | an empty `<youk dir>/.host` |
| Audit logs | `~/.claude/audit` | `<youk dir>/audit` | `<youk dir>/audit` |

The install directory is `YOUK_HOME`, else an existing `~/.claude/youk`, else `~/.claude/youk` for
Claude Code, else `~/.youk`. With Claude Code it must stay inside `~/.claude`, because skill links
are relative to it. The installer records its choices in `state/path-map.env`
(`YOUK_AGENT_HOST`, `HOST_CONFIG_DIR`, `HOST_SKILLS_LINKED`); the runtime, `doctor.sh`,
`uninstall.sh`, the Makefile and the host-side scripts all read that file instead of assuming a
location. Installs made before it existed have no file and are treated as Claude Code installs, so
nothing about an existing install moves.

Codex hooks (session start, prompt submit, pre-tool guard) are not written by the installer. They
live in `~/.codex/hooks.json` or `config.toml`; see [getting-started](getting-started.md), "Agent-host
selection".

## Verification status

- **Claude Code:** exercised in daily use.
- **Codex MCP registration, instructions file, uninstall:** tested with stub `claude` and `codex`
  binaries that record their arguments (`tests/test_host_adapters.py`), including a real run of
  `uninstall.sh` against a Codex install. The commands and file locations come from OpenAI's docs
  ([MCP](https://developers.openai.com/codex/mcp), [AGENTS.md](https://developers.openai.com/codex/guides/agents-md)).
  They have not been run against a real Codex CLI.
- **Codex hooks:** registered and found wired by `host_inventory.py`, but not exercised against a live
  Codex session. Treat their behaviour as designed, not proven.
- **`install.sh` end to end:** not run in the environment this was built in (it needs Docker and
  launchd). Its host logic is in `scripts/lib/hosts.sh`, which is tested; the glue around it is not.
  Run `bash scripts/doctor.sh` after installing; it checks the recorded host.
- **Any other MCP host:** tools work. Hook-driven safeguards do not exist for it. Use the working
  agreements in `AGENTS.md` and [youk-lite](youk-lite.md), which need no tooling.

## What is still specific to one vendor

- **`install.ps1` and `uninstall.ps1`** (PowerShell) still install for Claude Code only. On Windows,
  `install.sh` under Git Bash or WSL2 supports every host above.
- **The pre-install snapshot and restore** cover Claude Code files only.
- **The hooks plugin** (`plugin/`) is Claude Code's registration. The hook scripts it calls are shared
  with Codex.
- **Project-local skills** are looked up under `<project>/.claude/skills`. Another host's project skill
  folder is not.
- **The one LLM call youk makes itself** (`optimize_intent`) has a provider seam but only an Anthropic
  adapter, authenticated by `ANTHROPIC_API_KEY` or a Claude Code sign-in key file. Without a key it
  falls back to the heuristic path, so every other host works but that call is not model-assisted
  unless the key is set.
- **File names.** `docs/claude-md-template.md` and the `claude_md` field in session state keep their
  names; the content is host-neutral.
