<!-- Managed by youk; install.sh wraps this block in BEGIN/END youk fence markers. Remove with make uninstall.
     Codex and other hosts read AGENTS.md, so paste the same block there (docs/hosts.md).
     The pre-slimming version is frozen at bench/arms/full/CLAUDE.md for comparison runs. -->
youk is active. Hooks enforce the rules below; a block is the rule working, so do not route around it.
- Work on a branch, never the default branch. One concept per commit. Never push to main or force-push.
- Run the project's lint and the full test suite before every commit.
- Never read .env or print a secret. Never commit screenshots or keys.
- A task that touches several files or needs a design choice: call youk-core.route_task first, then follow the skills it returns.
- Smaller tasks: do the work directly, no routing and no ceremony.
- If a tool call fails, say so. No silent fallbacks.
- At the end of a session call youk-core.session_end.
