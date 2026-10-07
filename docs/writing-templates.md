# Writing templates

The voice is how the words sound. It is learned from the developer and is the same everywhere. The template is how the text is laid out, and it changes with the situation. A commit message is a short note for the next maintainer, a PR description is a formal document a reviewer works from, and a chat reply is just a reply.

`servers/shared/writing_templates.py` holds the layouts and the structural checks. `template_for(situation)` returns the skeleton for the situation that applies.

## Commit message

A subject line under 72 characters, then plain paragraphs for what changed, why it was needed, and the impact it had. How many paragraphs depends on the size of the staged change.

| staged change | body needed |
|---|---|
| one file, 10 lines or fewer | none, a subject is enough |
| small | one paragraph |
| 30 lines or more | what changed and why |
| 3 files or more, or 80 lines or more | what changed, why and the impact |

The commit-msg hook (`scripts/voice_gate_precommit.py`) checks the count after the voice gate. Trailers and merge, revert and fixup commits do not count. No labels, because colon-led lists are an AI-tell.

## Pull request

A formal document with headed sections.

```
## What changed
## Why
## Impact
## How it was checked
## Not done        (optional)
```

The PreToolUse hook checks `gh pr create` and `gh pr edit` bodies for the first four, rule `pr-structure`, and then runs the voice gate on the wording, rule `voice-pr-text`. A title-only edit is not checked for layout.

## Decision record

`Chose`, `Over`, `Because`, `Cost`, the format `DECISIONS.md` already uses.

## Chat

No template. Answer first, short plain sentences, and only what changes what the reader does next.

## Limits

The checks are structural. They can see that a paragraph is there, not that it really is the impact. `YOUK_GUARD_OFF=pr-structure` switches the PR layout check off on purpose, and `YOUK_GUARD_OFF=commit-layout` does the same for the commit check.
