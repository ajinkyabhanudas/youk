# Distributional realism — measuring "sounds human" statistically

Companion to `ai-tell-taxonomy.md` (which catalogues specific banned words/phrases/structures) and
`voice-profile.md` (which is a specific developer's voice fingerprint). This file is about a different
axis: whether a document's *statistical shape* — sentence-length variance, word-frequency distribution
— matches how humans actually write, independent of whether any individual word or phrase is a known
tell. A document can pass every item in the taxonomy file and still read as AI-generated if its
distributional shape is too uniform.

Built 2026-08-17 from actual research (sources below), not intuition, after ad hoc word-frequency
baselines used earlier in the same project turned out to be closer to genuine signal than expected.

---

## 1. Burstiness (sentence-length and complexity variance)

**The core finding**: human writing has high variance in sentence length and syntactic complexity.
AI-generated text is comparatively uniform. This is called "burstiness," and it's one of the two
classic statistical AI-detection signals (the other is perplexity — see §2).

**Concrete, testable numbers from research**: human text sentence-length standard deviation runs
roughly ±7 words around the mean; AI text runs roughly ±2.7. AI writing left unguided tends toward
uniform 12-18 word sentences and a repeating paragraph template (intro sentence, two or three
similar-length supporting sentences, a concluding sentence) — structural symmetry that reads as
statistically uniform even when no individual sentence is objectionable.

**Critical genre caveat, easy to get wrong**: humans write with *lower* burstiness and perplexity in
formal, graded contexts (academic writing, professional reports) than in creative writing. Don't
target novelist-level variance for a formal report — target the burstiness profile of *formal
reflective writing specifically*. A report that reads like a short-story writer produced it is its own
tell, just a different one.

**How to measure**: split the document into sentences, compute word count per sentence, take the mean
and standard deviation. Compare against the rough human/AI reference numbers above, adjusted down for
formal register.

**Baseline reading, this project's internship report (round 3 draft, 2026-08-17)**: 153 sentences,
mean length 22.9 words, standard deviation 12.2, range 2-70 words. This is well above even the
unadjusted human reference (±7) and far above the AI reference (±2.7) — genuinely strong burstiness,
not a problem area. The document's real weakness (see §3) was lexical, not structural: word-choice
repetition, not sentence-rhythm uniformity. These are different axes and need checking separately —
good burstiness does not imply good lexical diversity, and vice versa.

---

## 2. Perplexity (word-choice predictability)

Perplexity measures how "surprised" a language model is by a given word choice — roughly, how
predictable the next word is given what came before. Higher perplexity correlates with more
human-like writing, because humans pick words for reasons a model doesn't optimize for: rhythm,
specificity, a private association, mild imprecision. AI text tends toward the statistically likeliest
next word, which reads as smoother but more predictable.

This isn't something to hand-measure the way burstiness can be (it requires a language model to score
against), but the practical implication is: don't always reach for the smoothest, most expected word.
An unexpected but accurate word choice is a human signal, not a flaw to correct.

**Known limitation, worth knowing**: newer LLM output is close to indistinguishable from human text on
these metrics alone — perplexity/burstiness detectors are unreliable in isolation and increasingly
gameable. Non-native English speakers are disproportionately flagged by perplexity-based detectors
because their natural word choices are already less "expected" to a model trained mostly on native
text. Treat these metrics as a diagnostic for *this project's own drafting process*, not as a claim
about what a detector would say.

---

## 3. Lexical distribution (word-frequency-vs-baseline)

The method already used earlier in this project, now formalized: count word frequency across the whole
document, compute rate per 1,000 words, compare against a general-English baseline rate. A word running
5-10x+ above its normal rate of occurrence is a real signal worth checking, regardless of whether it's
ever been manually flagged before — this is what caught "same" (20x baseline), "already" (11x), and
"instead" (12x) in this project when no checklist-based pass had found them.

**Important calibration, learned the hard way in this project**: not every elevated word is a problem.
A word that's genuinely topic-relevant (comparative connectives in a document about comparing
decisions) will run above generic baseline for legitimate genre reasons. The fix is not to force the
rate down to 1x — that's a different kind of unnatural. Judge the *multiplier* relative to what the
genre plausibly explains, and stop tightening once further cuts start requiring awkward substitutes
rather than natural rephrasing (a substitute phrase that reads worse than the "problem" it replaced is
a sign you've gone past the real fix).

**No solid genre-specific baseline exists** for "reflective MBA report" specifically — only general
English corpus rates were available for this project. This is a real gap; if a genre-matched reference
corpus becomes available, baselines here should be updated against it rather than generic English.

---

## 4. Deliberate human noise — the inverse move

Everything above is about removing statistical uniformity. The complementary move is deliberately
preserving or reintroducing the specific inconsistencies a real author's writing has, rather than
smoothing everything toward "clean." Drawn from Ajinkya's own writing samples (commit message bodies,
messages in this project's conversation) already gathered for `voice-profile.md`:

- **Register isn't perfectly uniform.** His commit bodies are mostly technical and formal but drop in
  occasional contractions ("doesn't," "wasn't," "can't") rather than maintaining textbook-formal
  throughout. A report that's uniformly formal in register end to end is itself a mild uniformity tell.
- **Willingness to let a sentence run long when a mechanism needs explaining**, rather than breaking
  every complex idea into short sentences for readability. His real commit prose does this — dense,
  evidence-first sentences that carry a full causal chain rather than being chopped into three shorter
  ones.
- **Resolved, not a live tension**: an earlier pass of this research flagged an apparent conflict —
  `voice-profile.md`'s hard no-em-dash rule versus em-dash use in the commit-message samples it was
  built from. Ajinkya confirmed those commit messages are mostly AI-authored, not his own writing, so
  the em-dash usage in them was contamination in the source sample, not a real signal about his voice.
  The no-em-dash rule and the external research (em dash as the single most commonly cited AI-detection
  signal) agree. **Lesson for future voice-fingerprinting work**: verify a writing sample is actually
  human-authored before treating its patterns as ground truth — a commit message, doc section, or any
  artifact this project (or any AI) touched is a contaminated source unless independently confirmed
  otherwise. Prefer sources that can't have been AI-touched: live chat messages typed in the moment,
  handwritten notes, dictated corrections.

---

## Sources

- [GPTZero: What is perplexity & burstiness for AI detection?](https://gptzero.me/news/perplexity-and-burstiness-what-is-it/)
- [Medium: Analysing Perplexity and Burstiness in AI vs. Human Text](https://medium.com/@jhanwarsid/human-contentanalysing-perplexity-and-burstiness-in-ai-vs-human-text-df70fdcc5525)
- [Pangram: Why Perplexity and Burstiness Fail to Detect AI](https://www.pangram.com/blog/why-perplexity-and-burstiness-fail-to-detect-ai) (limitations, gameability, non-native-speaker bias)
- [TextSight: Sentence Length Variance — The One Pattern That Separates Human Writing From AI](https://www.textsight.ai/blog/sentence-length-variance/) (source of the ±7 vs ±2.7 stdev figures)
- [Nature: Stylometric comparisons of human versus AI-generated creative writing](https://www.nature.com/articles/s41599-025-05986-3.pdf)
- [Oxford Digital Scholarship in the Humanities: Stylometric detection of AI-generated texts](https://academic.oup.com/dsh/advance-article/doi/10.1093/llc/fqag064/8714041)
