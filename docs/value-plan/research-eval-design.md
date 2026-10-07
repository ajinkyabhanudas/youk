# Research: how to test youk (2026-10-06)

Written after the first battery (G1) answered nothing. Sources were read, not skimmed; where a number comes from a search summary and not the paper itself it is marked (reported).

## What youk wants from a test

Four claims, each needs its own test. One battery cannot answer all four.

| Claim | Question | Right test |
|---|---|---|
| B. Correctness | Does the harness raise the pass rate on tasks the model can sometimes fail? | Paired replay, tasks screened for headroom, k >= 3 |
| V3. Overhead | Does it cost fewer tokens for the same result? | Same runs, cost and time reported with the pass rate |
| V1/V2. Corrections, review | Fewer repeated mistakes, easier review? | Live ledger plus a small randomized live trial. Replay cannot measure this |
| Compounding | Does a project get easier over sessions? | Chronological task sequences, memory on and off. Never a one-shot task |

G1 tested B on tasks that could not discriminate and called it a verdict.

## Findings and what each changes

1. **Report paired differences with clustered error bars.** Questions drawn in groups need clustered standard errors, which can be over 3x the naive ones; a paired test removes task difficulty from the noise. [Miller, Adding Error Bars to Evals, arXiv 2411.00640](https://arxiv.org/abs/2411.00640). Change: cluster by repo, report the interval, and state the smallest effect the design can detect before running.

2. **One run is not a measurement.** Across 10 runs of 6 agent configurations, single-run pass@1 moved 2.2 to 6.0 points, and even at temperature 0 the standard deviation was above 1.5 points (reported). Runs needed per arm are about 16 sd^2 / gap^2 for 80% power. [Identical Runs, Different Results, arXiv 2609.33812](https://arxiv.org/html/2609.33812v1), [On Randomness in Agentic Evals, arXiv 2602.07150](https://arxiv.org/pdf/2602.07150). Change: k >= 3, and a pre-run power calculation.

3. **Many benchmark tasks are invalid.** OpenAI's audit of SWE-bench Verified found at least 59.4% of the audited hard problems had tests that reject correct fixes, and many statements were underspecified. [OpenAI](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/). SWE-Bench Pro V2 dropped 89 of 731 tasks as invalid. [Scale](https://labs.scale.com/blog/swe-bench-pro-v2). Change: our G1 had four youk tasks failing in both arms, probably this. Validate each task before it is scored.

4. **Tasks must have headroom.** Memory evaluation on real repositories kept a task only if injected experience helped in a reference setting; at the memory-off ceiling, even verified experience lowered the pass rate on 25.7% of pairings. [VibeMemBench, arXiv 2609.23570](https://arxiv.org/html/2609.23570). Anthropic notes the same saturation effect. [Demystifying evals for AI agents](https://github.com/chyornyy/anthropic_engineering_md/blob/main/anthropic_engineering_blog/Demystifying%20Evals%20for%20AI%20Agents.md). Change: screen on the bare arm only (no selection on the arm under test), keep tasks the bare arm solves sometimes but not always.

5. **Context files add cost and rarely add accuracy.** Context files did not generally improve task success and raised inference cost by over 20% on average; instructions were followed, repository overviews were not helpful, and they help mainly for non-standard practices. [Evaluating AGENTS.md, arXiv 2602.11988](https://arxiv.org/abs/2602.11988). Our G1 measured +20% cost with no visible gain. Anthropic's own guidance is the smallest set of high-signal tokens, started minimal and added to from observed failures. [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents). Change for S11: the lean context holds only non-inferable, checkable rules; no overviews.

6. **Memory systems mostly fail to beat memory-off.** Eleven of twelve solver and system pairings did not exceed the baseline; 69.3% of failures were form degradation, and volume, not meaning, did the harm. Curated, compressed experience raised resolution 1.1 to 4.5 points and cut steps. The sign of the effect depends on solver headroom. [VibeMemBench](https://arxiv.org/html/2609.23570); also limited context learning in [SWE Context Bench, arXiv 2602.08316](https://arxiv.org/pdf/2602.08316). Change: youk's brief is a memory system and has the same risk. Inject compressed, relevant items, gated on task size and headroom; test memory with matched memory-on, memory-off and irrelevant-text pairs.

7. **Compounding needs sequences.** SWE-Bench-CL orders issues chronologically and scores forward transfer, forgetting and tool-use efficiency. [arXiv 2507.00014](https://arxiv.org/pdf/2507.00014). Change: a compounding test is a chain of related tasks per repo, not independent tasks.

8. **Ablate components, read transcripts, classify failures.** Evaluate the system around the model by removing context files, skills, memory and gates one at a time, with trace-level kill-point analysis and a split between "could have succeeded" and impossible. [Engineering Reliable Coding Agents, arXiv 2608.13867](https://arxiv.org/pdf/2608.13867). Anthropic: start with 20 to 50 tasks from real failures, test both when a behaviour should fire and when it should not, isolate each trial's state, and read the transcripts. Change: add "should not fire" tasks (youk's overhead on trivial work) and a failure-reason tag per run.

9. **Report cost with accuracy, and beat simple baselines.** Cost-controlled comparison on a Pareto frontier; simple baselines such as retry often match complex agents at lower cost. [AI Agents That Matter, arXiv 2407.01502](https://arxiv.org/pdf/2407.01502). Change: report pass rate against cost per arm, and include a cost-matched retry baseline.

10. **Stop early when the answer is clear.** Sequential testing cuts evaluation cost 40 to 80% (reported), with a minimum meaningful effect fixed first. [DeltaSelect, arXiv 2609.19607](https://arxiv.org/pdf/2609.19607). Change: run in rounds with interim looks, and a futility stop.

11. **Self-report misleads.** In METR's randomized trial, experienced developers were 19% slower with AI tools while believing they were 20% faster. [METR](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/). Change: judge youk on logged outcomes, never on how it feels. Task length in METR's method is calibrated to human time. [Measuring AI Ability to Complete Long Tasks, arXiv 2503.14499](https://arxiv.org/html/2503.14499v1). Change: tag each task with a size tier and report tiers separately.

## What goes into youk

Code that cannot be skipped:
- `scripts/sim/design.py`: pre-run design check (informative-task share, minimum detectable effect, power, cost estimate) and the interim stopping rule.
- `run_battery.py` refuses to start a paid run whose design cannot detect the target effect, unless `--allow-underpowered` is given, which is written into the results.
- A contract saved: no evaluation spend without the design check.

Plan changes (cards): triage pilot on the bare arm; an M+ task tier; a compounding sequence test; S11 lean content rules from findings 5 and 6; lean and full compared on both tiers.

## What this does not settle

- Search summaries supplied some figures (marked reported); the primary papers should be read before any number is quoted outside youk.
- No published study measures a harness like youk end to end. These are transferable methods, not proof that youk helps.
