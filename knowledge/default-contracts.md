# youk default contracts — committed to repo, inherited by all installs
# These load before personal global contracts at every session start.
# Add rules here when the behavior must apply to every youk user, not just the current install.
# Personal cross-project rules belong in knowledge/global/contracts.md (gitignored).

- whenever youk writes a runtime artifact (*.db, *.jsonl, *.json state files, generated overlays) into a project directory that isn't ~/.claude/youk/, immediately add a matching gitignore entry in that project's .gitignore — never leave a generated file unguarded in a project repo
