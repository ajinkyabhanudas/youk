# youk-research — Fixed Source List

Scanned in priority order. Higher priority sources are fetched first; if token ceiling
is approaching, lower-priority sources are skipped.

## Priority 1 — Anthropic

- **Search query prefix:** `site:anthropic.com/engineering OR site:anthropic.com/research`
- **Focus:** MCP patterns, multi-agent coordination, context management, prompt caching
- **Key pages to check:**
  - anthropic.com/engineering (blog index — check for posts in last 30 days)
  - anthropic.com/research/tool-use
  - Model specification (anthropic.com/claude/model-spec) — for behavioral alignment patterns

## Priority 2 — Karpathy

- **Search query prefix:** `site:github.com/karpathy OR karpathy.github.io`
- **Focus:** agentic workflow structure, how he organises AI coding sessions, spec-first patterns
- **Key pages to check:**
  - github.com/karpathy (recent repo activity and starred repos)
  - Any posts or talks referenced in his GitHub README
- **Note:** Karpathy rarely posts frequently — a scan finding 0 new items is normal

## Priority 3 — OpenAI Cookbook

- **Search query prefix:** `site:cookbook.openai.com OR site:github.com/openai/openai-cookbook`
- **Focus:** agent coordination patterns, tool use best practices, context window management
- **Key pages to check:**
  - cookbook.openai.com (index — look for agent/multi-agent sections)
  - github.com/openai/openai-cookbook/tree/main/examples (recent additions)

## Priority 4 — Hacker News (developer tools signal)

- **Search query prefix:** `site:news.ycombinator.com "Show HN"`
- **Focus:** new developer productivity tools, MCP servers gaining traction, agentic IDE tools
- **Key signal:** "Show HN" posts with >100 points in the last 30 days related to AI coding
- **Note:** HN is signal, not authoritative. Patterns from HN require corroboration from P1-P3 before proposing.

---

## Topics (default scan topics when none specified)

1. `agentic coding patterns` — how engineers structure AI-assisted development workflows
2. `MCP server token efficiency` — patterns for reducing overhead in MCP-based systems
3. `LLM context management` — techniques for preserving context across sessions
4. `Claude Code developer workflows` — how developers are using Claude Code effectively

---

## Exclusions (skip if encountered)

- Content about GPT, Gemini, Llama, Mistral, Cohere, or other non-Anthropic models
- Content behind paywalls (403, 401, or subscription wall detected in first 200 chars)
- Reddit, Twitter/X, LinkedIn — too noisy, signal/noise ratio too low
- Content older than 90 days (for Anthropic/OpenAI); older than 180 days (for Karpathy — he posts rarely)
