# AI-tell taxonomy — living reference

Cumulative catalogue of AI-writing patterns to check any long-form draft against. Companion to
`voice-profile.md` (positive voice fingerprint) and `distributional-realism.md` (statistical checks).
Run `scripts/quantify.py <file>` to check mechanically. Extend both on every new catch — don't rebuild
from memory.

## 1. Vocabulary tells

- Consultant/AI metaphors: load-bearing, lands/landed, compounding, unpack, crux, grapple with,
  navigate (metaphorical), seamless, holistic, nuanced, multifaceted, underscore, resonate, elevate,
  foster, harness, unlock, paradigm, landscape, ecosystem (metaphorical), journey (metaphorical),
  testament to, shed light on, dive into, keystone, tapestry, delve, underneath (spatial filler).
- Decorative intensifiers (cut, check meaning survives): quietly, directly, entirely, actually, really,
  exactly.
- Self-certifying adjectives: honest/honestly, genuine, authentic, real — when certifying trust rather
  than distinguishing ("a real risk" is fine; "the honest framing" is not).
- Repetition crutches (frequency, not the word, is the tell): shape/shapes, narrow/narrower, specific,
  real (as in "the real X"), against, same (when used as a connective echo across sections rather than
  natural reference to genuinely different nouns). Any noun/connector reused 3+ times needs a
  substitution pass — but see the "not every repetition is a tell" note below before cutting.
- Public-research list, not yet independently caught here: optimize, leverage, streamline, ensure,
  furthermore, moreover, additionally, "it's important to remember that," "the work," "hold," "pull,"
  "signal," "built different," "earn," "matters" (as a verb), "shift," ministrations, boundless.

## 2. Sentence-structure tells

- Negation-reveal/antithesis: "X isn't A, it's B," "not because X, but Y," "not just X, it's Y."
  Exception: naming a real rejected alternative is fine ("validation status, not the raw score"). Test:
  if the negative half could be deleted without losing information, cut it. Recurs at three levels:
  single sentence, repeated template across sections, paragraph-level reveal architecture.
- Wh-clefts / epiphany staging: "What I underestimated was...", "What shipped is...". States that an
  insight is coming instead of just stating the insight. Rewrite with the real subject leading.
- Hindsight-admission clause: "a rule I hadn't thought to ask about." Confesses a blind spot instead of
  stating the fact. Fix: "Pedro also had a rule of his own."
- Rule of three: triadic lists used for rhythm, not because three was the right count.
- Uniform causal template: "[claim], because [reason]" repeated as the closing sentence shape. Vary:
  lead with cause, split sentences, use "since," or drop the connector.

## 3. Punctuation tells

- Em dash: the most-cited single AI signal. Banned in long-form prose — restructure or use a
  period/comma.
- Colon-as-scaffolding: "[clause]: [elaboration]" as the default explain/list device. Budget: only
  genuine 3+ item lists or an unavoidable published title. Everything else — period or comma.
- Rigid Intro-Point-Point-Point-Conclusion, including identical sub-headers reused regardless of
  whether the content actually parallels.

## 4. Tone/register tells

- Overly polite, neutral tone — reads safe, not specific.
- False-intimacy openers: "here's the part most people miss," "but here's the truth."
- Self-aware meta-commentary about the document's own construction: "I haven't forced every section
  into identical sub-headings..."
- Textbook-label insertion (MBA/assessed-writing specific): naming a framework explicitly ("in the
  product-management sense of the term") instead of letting the reasoning demonstrate it.
- Over-correction into aphoristic one-liners: fixing choppy prose by making every sentence short
  produces a different wrong register (blog-punchy), not a correct one. The fix is genuine
  sentence-length variation, not uniform brevity.

## 5. Narrative-architecture tells

- Reveal/twist paragraph shape: setup → dramatic reversal → resolution, even with no single flagged
  sentence. Check paragraphs, not just sentences.
- Essay narrating its own logic: "This is what connected X back to Y" — show the connection, don't
  announce it.
- Proof-beat fragments: a clipped sentence + colon-delivered stat as a dramatic beat ("It worked.
  Verified: 1.6 seconds.").
- Narrative accuracy drift: real events reframed for dramatic effect until misleading (e.g. casting a
  collaborator as "correcting" the author when the real dynamic was shared reasoning). Fact-check
  dramatized narrative, don't just style-check it.
- Bullet-fusion: a run of short, atomic, syntactically-parallel declarative sentences, each stating one
  isolated fact, strung together with periods instead of real connective tissue. Reads like a bulleted
  list converted to prose — no subordination, no clause showing how the facts relate (causally,
  temporally, or otherwise). Distinct from the aphoristic-one-liner tell above: that one is about
  rhetorical punch, this one is about atomized facts with no syntactic relationship between them. Fix:
  fold two or three of the fused sentences into one, using a subordinate clause or connector that states
  the actual relationship ("because," "which," "and I only saw that because…") — vary sentence length
  and structure the way real spoken reasoning does, don't just keep declarative sentences short.

## Methodology notes

- **Checking after writing doesn't fix the habit.** Draft the way the specific person would actually
  say it — short, direct, no setup — then check against this list. Don't draft in default "polished
  essay" register and sand off whatever gets caught; the next new sentence reverts to default.
- **A fixed checklist has a ceiling.** It only catches what's already on it. Run a full
  word-frequency count (strip stopwords, sort by count) on every draft — any non-subject-matter word
  appearing unusually often is worth a look, listed or not.
- **Not every repetition is a tell.** "The same X" reused across genuinely different nouns is normal
  English cohesion. Forcing artificial variation onto it (e.g. "one email" for "that email")
  manufactures a worse, new tic. Fix the repeated *rhetorical move*, not every repeated common word.

## How to use this file

1. Skim this file (and the relevant voice-profile) before drafting, so both are live constraints from
   the start, not a rule referenced once and dropped.
2. Run `scripts/quantify.py` after drafting — word/punctuation frequency across the whole document.
3. Run an independent fresh-context critique whose primary bar is overall prose quality and register
   fit, not pattern-matching this list. A draft can pass every item here and still read robotic in
   aggregate.
4. Any new pattern a human or agent catches that isn't listed: add it here and to `quantify.py` before
   moving on. The list compounds; it doesn't reset.

## Sources

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- [Forbes: The 15 New Giveaway Signs Of AI-Generated Content (February 2026)](https://www.forbes.com/sites/jodiecook/2026/02/03/the-15-new-giveaway-signs-of-ai-generated-content-in-february-2026/)
- [Forbes: 15 New Giveaway Signs Of AI Writing (May 2026 update)](https://www.forbes.com/sites/jodiecook/2026/05/21/15-new-giveaway-signs-of-ai-writing-may-2026-update/)
- [Grammarly: Decoding AI Language](https://www.grammarly.com/blog/ai/common-ai-words/)
- [contentbeta: 300+ AI Words and Phrases to Avoid](https://www.contentbeta.com/blog/list-of-words-overused-by-ai/)
- Project-specific findings (colon-scaffolding, aphoristic over-correction, narrative-accuracy drift,
  hindsight-admission clause) are original to this project, not yet cross-checked externally.
