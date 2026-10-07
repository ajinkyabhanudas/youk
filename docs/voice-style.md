# Voice style

Anything youk writes for a developer, commit messages and PR text included, should read like that developer wrote it. youk learns the voice from the developer's own prompts. It does not ship anyone's voice, name or measurements, so none of that is in this repo.

## How it learns, on the developer's machine

- The UserPromptSubmit hook saves each prompt (30 characters or more, not slash commands) to `knowledge/voice-corpus.jsonl`. That file and `knowledge/global/` are gitignored.
- At session end youk measures sentence length, contractions, first person, commas, openers, connectives and punctuation, and writes `knowledge/global/voice-{slug}-{register}.md` once there are 1500 words.
- The humanize skill loads the hand-kept `knowledge/global/voice-profile.md` first, then the measured profile as writing targets, then the generic template. The numbers are targets for writing, never a pass or fail test.
- `scripts/voice_report.py` prints the learned profile. A local `knowledge/global/voice-baseline.json` can hold earlier numbers to compare against.

## What is enforced for everyone

The commit hook and the PR check block any AI-tell, hard or soft. Write plain and short and avoid these:
- em dashes
- two clipped sentences used for emphasis
- lists of three
- "not X, but Y" pairs
- colon-led change lists
- tidy because-so chains
- the word "key" and other graded vocabulary

## Voice and layout are separate

The voice is the same in a commit, a PR and a chat reply. The layout changes with the situation: a commit is plain paragraphs for what changed, why and the impact, and a PR is a formal document with headed sections. See `docs/writing-templates.md`.

## Rule for contributors

Do not commit a person's name, email, writing samples or measured style numbers. They belong in the local, gitignored files above. `tests/test_voice_learning.py` fails if the git user's name appears in the voice and benchmark files.
