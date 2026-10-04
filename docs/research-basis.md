# Research basis

Each design choice below cites outside research. This file records what the
source says, what it does not say, and whether it was checked. Verified means
the paper's own page or abstract was read on 2026-10-04; "not verified" means
no source was found, and the choice stands on its own engineering reasons.

| Design choice | Source | What it shows | What it does not show | Status |
|---|---|---|---|---|
| Put retrieved evidence after the task text, not buried mid-prompt (`intent._sizing_grounding`) | Liu et al., [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/), TACL 12 (2024) | Accuracy is highest when relevant information is at the start or end of a long context and drops in the middle (a U shape), on multi-document QA and key-value retrieval | That the end beats the start, or that it applies to a short evidence block in a short prompt. This placement is a reasonable choice, not a tested one in this setting | Verified |
| A claim is not trusted on the author session's say-so (verification pipeline) | Huang et al., [LLMs Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798), ICLR 2024 | Without external feedback, self-correction often fails to help and sometimes degrades answers | That every self-check is useless; correction works when external feedback (tools, tests, a knowledge base) is available, which is what the pipeline's grep/test/live-call checks provide | Verified |
| L/XL claims need confirmation from a separate session | [Cross-Context Review](https://arxiv.org/abs/2603.12123) (2026) | Reviewing in a fresh session beat a second review in the producing session (F1 28.6% vs 21.7%, 360 reviews) | A large effect. The gain is modest, so the separate-session rule is a cost/benefit call, which is why it is limited to L/XL | Verified |
| Third-person reframing of candidates before review (`domain_edge_case_review.py`) | [The Self-Correction Illusion](https://arxiv.org/abs/2606.05976) (2026) | Re-presenting an identical claim under an external role raised the explicit-correction rate by 23 to 93 points across 13 model-domain cells (10 significant) | That correction accuracy improves, only that flagging does. It attributes the effect to chat-template role labeling, not to shared training data. A self-distrust prompt that leaves the claim in place did not help | Verified |
| Local embedding model for "same lesson" and precedent retrieval (`semantic_similarity.py`) | [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | 384-dim embeddings, 22.7M parameters, about 91 MB on disk | Anything about sizing-task similarity. The 0.30 task floor and 0.55 lesson threshold come from this repo's own pair measurements and were not re-measured | Model facts verified. Task floor: separates 8 related from 8 unrelated task pairs with the real model in CI (run 500). Lesson floor: admits none of 6 unrelated lessons. Small samples; lesson recall untested |
| Domain Brief from bounded contexts and invariants | `docs/problem-space-modeling-design.md` cites a 2026 DDD source ("LLMs lack persistent understanding of domain constraints") | Not checked | Not checked | Not verified: the quoted sentence was not found. The Domain Brief stands on its own engineering reasons (stable per-project facts, matched fresh per task) |
| LLM requirements elicitation floods engineers with false positives unless filtered | `docs/problem-space-modeling-design.md` item 2 | Not checked | Not checked | Not verified |

## Reusable learnings: what the research says

youk keeps three kinds of reusable knowledge: contracts and lessons promoted across
projects, a per-project Domain Brief, and sizing precedent. The research that bears on
how to reuse them:

| Finding | Source | What it shows | What it does not show | Status |
|---|---|---|---|---|
| Distil experience into short natural-language insights, edit them with ADD / UPVOTE / DOWNVOTE / EDIT, and retrieve similar past successes at task time | Zhao et al., [ExpeL](https://arxiv.org/abs/2308.10144) | Beat a ReAct baseline on HotpotQA, ALFWorld and WebShop; insights learned on HotpotQA transferred to FEVER | Anything about coding agents or per-project settings. Read at abstract and project-page level, not the full paper | Verified (summary level) |
| Keep context as an evolving playbook updated by small incremental edits, not rewrites | [Agentic Context Engineering](https://github.com/ace-agent/ace) (ICLR 2026) | Whole-context rewrites lose detail on each pass (brevity bias, context collapse); incremental edits avoided it and gained 10.6% on agent tasks | That youk's store has this problem. Read from secondary summaries; the paper itself was not opened | Verified (secondary summaries) |
| Keep a library of reusable skills that later tasks build on | Wang et al., [Voyager](https://arxiv.org/abs/2305.16291) | Without the library progress plateaued; the library carried to a new world and also helped AutoGPT | That text lessons behave like executable skills. Voyager's skills are code in Minecraft | Verified (summary level) |
| Retrieve the relevant slice instead of loading everything | Li et al., [RAG or Long-Context LLMs?](https://arxiv.org/abs/2407.16833) | Long context is slightly more accurate when cost is no object; retrieval is far cheaper, and a retrieve-then-fall-back router matched it with 38.6–61% of the tokens | That a cached domain model cuts reasoning cost. No study found tests that claim, so the cost saving is argued, not measured | Verified (summary level) |

## Advancements still needed, in priority order

Each item says what the evidence supports, what youk does today, and what would count as done.

1. **Retrieve global learnings per task instead of loading the last 50.**
   `session._load_global_contracts` returns `combined[-cap:]`, so once the store passes 50
   entries the oldest are dropped by age, not relevance, and every session pays for all 50.
   `pattern_promotion.query_global_patterns` filters by domain but has no live caller.
   ExpeL (retrieve similar) and the RAG-vs-long-context result (retrieve a slice) both point
   the other way. Partly done: the sizing evidence block in `optimize_intent` now ranks
   `state/global-patterns.jsonl` against the task with `rank_by_similarity`, shows up to three
   above `LESSON_RELEVANCE_FLOOR` (0.40), and logs `lesson_count`. The floor's precision is
   checked in CI; its recall is unmeasured and may be too strict. The session-start
   load now picks the best-supported 50 (real `confirmed_count`, then newest) and always keeps
   the committed defaults; before, it took the newest 50 and dropped the defaults first once
   personal learnings filled the cap. It is not per-task, since no task is known at session start.
   Still open: `route_task` output does not carry lessons, and the floor needs tuning from
   logged `lesson_count` against real tasks.
2. **Record where a promoted learning came from.** Done: `promote_to_global_contracts` now
   finds which projects' `contracts.md` hold the lesson (same meaning threshold as cross-project
   detection) and writes them as provenance with `confirmed_count` set to the real number. When
   no source project can be determined it records `unknown` with a count of 0 instead of the
   old constant `confirmed_count=2` / `cross-project`. Entries promoted before this change keep
   the old values. ExpeL's up/down-voting and ACE's incremental curation both need this
   per-learning evidence.
3. **A way to retire a learning.** Done: `retire_global_pattern` appends a `retired` tombstone
   with a required reason; `contracts.md`, `query_global_patterns` and per-task retrieval all
   drop retired rows, and the retired wording still blocks re-promotion. Nothing is deleted.
   Not yet automatic: a session has to call it. `promote_to_global_contracts` already reports
   opposite-claim conflicts, and the self-heal step tells the session to retire the wrong one.
4. **Measure whether grounded sizing is better.** The sizing log now records
   `grounding_status`, and `/health` reports cold-estimate and override rates, but nothing
   compares sizing outcomes with and without evidence. `resolved_size` is the system's own
   output, not a checked outcome. Done when: a task's actual effort or rework is joined to its
   sizing row and grounded and cold rows are compared.
5. **Phase C/D chain: wired, now judge it on data.** Reversal detection and promotion of
   confirmed patterns were unwired earlier because they duplicated the contracts path and had no
   entries. They are now reachable as tools and self-heal steps, `promote_pattern_group` refuses a
   meaning-duplicate of anything already in the store, and a bad learning can be retired. Keep it
   only if `state/confirmed-patterns.jsonl` and `state/global-patterns.jsonl` show entries it
   produced; otherwise delete it.
6. **Domain Brief for projects other than youk.** Done: session start builds
   `state/domain-briefs/{slug}.json` from the project's own `DECISIONS.md` (when missing or
   older than it); both the sizing prompt (youk-core) and the nfr_check edge-case pass
   (youk-code, which reads the current slug from `state/sessions/*/open.json`) use the current
   project's brief, and neither serves another project's legacy `state/domain-brief.json`. Limit:
   only the `DECISIONS.md` dialects `domain_brief.py` recognises produce content; a project that
   records decisions elsewhere gets an empty brief that says so.
7. **Widen the floor calibration.** Done at small scale: both floors held on the real model in
   CI (task floor on 8 related and 8 unrelated pairs, lesson floor on 6 unrelated lessons). Still
   open: lesson recall (whether a relevant lesson clears 0.40) is untested, and the samples are
   small. Grow the pair lists from real rows in `state/sizing-decisions.jsonl`.
