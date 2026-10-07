# Voice style

Anything youk writes for a developer, commit messages and PR text included, should read like that developer wrote it. youk learns the voice from the developer's own prompts. It does not ship anyone's voice, name or measurements, so none of that is in this repo.

## How it learns, on the developer's machine

- The UserPromptSubmit hook saves each prompt (30 characters or more, not slash commands) to `knowledge/voice-corpus.jsonl`. That file and `knowledge/global/` are gitignored.
- At session end youk measures sentence length, contractions, first person, commas, openers, connectives and punctuation, and writes `knowledge/global/voice-{slug}-{register}.md` once there are 1500 words.
- The humanize skill reads the hand-kept `knowledge/global/voice-profile.md` and falls back to the generic template.

## What is enforced for everyone

The commit hook blocks any AI-tell, hard or soft. Write plain and short and avoid these:
- em dashes
- two clipped sentences used for emphasis
- lists of three
- "not X, but Y" pairs
- colon-led change lists
- tidy because-so chains
- the word "key" and other graded vocabulary

## Rule for contributors

Do not commit a person's name, email, writing samples or measured style numbers. They belong in the local, gitignored files above.
