# Fingerprint protocol

How to turn a pile of someone's writing into a profile that can actually be imposed on new text.

## Corpus requirements

Adjective lists do not work. "Direct, thoughtful, conversational" describes most competent writers and constrains nothing. The profile must come from measured samples.

**Minimum viable:** 1,500 words across 3 pieces.
**Good:** 5,000 words across 6 or more pieces spanning at least two registers.
**Ideal:** the above plus 2 pieces the writer dislikes and can say why. Negative examples localise the boundary faster than positive ones.

Bias the corpus toward unedited writing: Slack, sent mail, first drafts, comments on pull requests. Published work has been through an editor and shows the editor's habits as much as the writer's. If only published work is available, note that the profile is of the edited voice.

## What to measure

Run `scripts/stylecheck.py --profile` over the corpus for the quantitative half, then read for the qualitative half. Both halves are required. Numbers alone produce a plausible impostor.

### Quantitative (computed)

- **Sentence length distribution.** Not just the mean. The coefficient of variation, and the shape: does the writer alternate long and short, or cluster short runs then a long one?
- **Paragraph length distribution**, same treatment.
- **Contraction rate** per 100 words. A person at 8 is a different person from one at 1.
- **First-person rate** and which forms. "I think" versus "I'd argue" versus none.
- **Sentence-opener distribution.** What fraction start with a subject, a conjunction, a subordinate clause, an adverb? Writers are remarkably stable here and it is almost never imitated.
- **Connective inventory.** Which joining words actually appear, and in what proportion. Most writers use a handful heavily and never touch the rest. This is one of the strongest fingerprints available.
- **Punctuation ratios.** Colons, semicolons, parentheses, dashes, per 1,000 words.
- **Clause depth.** Average commas per sentence as a rough proxy for how much the writer nests.

### Qualitative (read for)

- **Signature moves.** Specific constructions the writer reaches for repeatedly. Not "uses examples" but "opens with the objection before stating the position", or "ends paragraphs on the shortest sentence in them".
- **Metaphor domain.** Where do the comparisons come from? Engineering, sport, cooking, music, finance? Writers rarely range widely and the domain is a strong tell.
- **Attention pattern.** What do they linger on and what do they skip? Some writers spend three sentences on setup and one on the conclusion. Some invert it.
- **Refusals.** What is conspicuously absent. No exclamation marks. Never asks rhetorical questions. Never uses the word "leverage". Absences are cheap to enforce and highly identifying.
- **Failure modes.** How does their writing go wrong when they are tired or rushed? Reproducing this occasionally is what separates a voice from a polished imitation of one.
- **Vocabulary tics.** Words they use in a slightly unusual sense, or far more than average.

## Writing the profile

Store as `voice/<name>.md`. Structure:

```markdown
# <name>

**Corpus:** N words, M pieces, registers covered, date range.
**Confidence:** high / medium / low, and where it is thin.

## Measured targets
sentence CV: 0.xx (band 0.xx–0.xx)
mean sentence: xx words
contractions/100w: x.x
first person/100w: x.x
opener mix: subject xx% / conjunction xx% / subordinate xx% / adverb xx%
top connectives: ...
punctuation per 1000w: colon x, semicolon x, paren x

## Signature moves
(3–6 specific, reproducible constructions with a real example of each)

## Refusals
(things absent from the corpus, stated as hard rules)

## Metaphor domain
## Register notes
## Known gaps
(what the corpus does not cover, so the profile is not over-applied)
```

## Rules for the profile itself

- **Every claim needs a corpus example.** If it cannot be evidenced, it is a guess, and guesses accumulate into a stranger.
- **At least half the profile must be positive constraints.** A profile that is mostly prohibitions cannot generate anything. It can only sand. If the prohibition count exceeds the signature-move count, the profile is not finished.
- **Record confidence per section.** Thin evidence should be marked thin so it can be overridden rather than trusted.
- **Never let general good-prose advice into the profile.** "Varies sentence length" belongs to everyone. It is not a fingerprint. Only include what would be *wrong* to apply to a different writer.

## Validation

Before trusting a new profile, run the swap test.

1. Take a real passage by the writer, hold it out of the corpus.
2. Generate a passage on the same topic using only the profile.
3. Show both to the writer unlabelled.

If they cannot pick their own, the profile is either very good or the passage is too short to discriminate. Use at least 200 words. If they pick correctly and can say *why*, that reason is a missing entry in the profile. Add it and repeat.
