# youk default contracts — committed to repo, inherited by all installs
# These load before personal global contracts at every session start.
# Add rules here when the behavior must apply to every youk user, not just the current install.
# Personal cross-project rules belong in knowledge/global/contracts.md (gitignored).

- whenever youk writes a runtime artifact (*.db, *.jsonl, *.json state files, generated overlays) into a project directory that isn't ~/.claude/youk/, immediately add a matching gitignore entry in that project's .gitignore — never leave a generated file unguarded in a project repo
- decide everything the evidence can settle and state the call with its reasoning; only ask the developer when the answer turns on a preference, value, or fact they hold that cannot be derived from the code, constraints, standards, or stated goal — never present an option already ranked lower as if it were live. Guard the mirror: a developer preference overrides a derivable standard (surface it), name the source before claiming derivable, and surface high-cost or irreversible decisions even when derivable. A seniority label ("L9", "elite", "principal") names a behavior, not a persona — resolve it to the specific behavior the task needs.
- youk must natively know its project-scoped next task and keep it current automatically — at session end it computes the next task from that project's own validated task state and writes the resume pointer itself. Never a manual pointer edit, never a generic cross-project list. "What's next" is always derived from the project youk is in.
