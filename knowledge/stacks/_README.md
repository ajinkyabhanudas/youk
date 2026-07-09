# Stack Knowledge Bootstrap Templates

Each file in this directory seeds the concept graph for a detected project stack.
Read by the `learn` skill BOOTSTRAP phase when a stack is encountered for the first time.

**What's here:** The CS concepts a developer WILL encounter on this stack, named precisely,
with the analogy scaffold left blank for the user's /learn session to fill.

**What's NOT here:** User-specific analogies. Those live in `knowledge/user-profile.md`
(local, gitignored). The stack file says "you will encounter X". The user profile says
"X is like Y in your background". The learn skill bridges them.

**When a new stack is encountered:**
1. `session_start` detects first-seen project type
2. Session plan includes: "New stack ({stack}) — type /learn after this session to seed your knowledge graph"
3. /learn BOOTSTRAP phase reads this file, prompts the MAP phase to build analogies from user-profile.md
4. PERSIST phase writes to knowledge/domain/{concept}.md

## Adding a new stack

Copy the template below, fill in the concepts. Name the file `{stack}.md` where stack
matches the value returned by `_detect_stack()` in session.py.

```markdown
# Stack: {name}
detection_key: {value from project-type detection}

## Core concepts a new developer will encounter

| Concept | What it is (one sentence) | When it appears |
|---|---|---|
| ... | ... | ... |

## Patterns that commonly surprise developers from other stacks

- {pattern}: {what surprises people and why}

## Common cross-stack analogies (starting points for MAP phase)

These are generic analogies that hold for most backgrounds. The MAP phase should
replace these with user-specific analogies from user-profile.md where possible.

| Concept | Generic analogy | Analogy quality |
|---|---|---|
| ... | ... | STRONG/PARTIAL/WEAK |
```
