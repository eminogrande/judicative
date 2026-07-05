# Judicative Learnings

This document records what we learned while turning Judicative from a single judge script into an MCP-driven agent benchmark.

## 1. A Hard Benchmark Needs Real Repository Pressure

Single synthetic tasks are useful for smoke tests, but they are not enough to rank strong coding models. The benchmark becomes serious when tasks come from real merged PRs:

- start from the pre-fix commit
- give the model the issue, review context, and repo constraints
- ask it to produce a patch
- run tests, lint, typecheck, and task-specific oracle checks
- compare against the historical fix and blind-review the resulting patch

The repo now has the first version of that path:

- `bench/mine_tasks.py` mines merged PRs into replay-task JSONL.
- `bench/verify_task_oracle.py` proves a historical PR patch applies from its replay base.
- `bench/tasks/nuri-hard-v1.jsonl` and `bench/tasks/nuri-hard-v1-focused.jsonl` are committed candidate suites.
- `bench/oracle-results/nuri-expo-pr-769.md` is the first verified replay oracle.

## 2. One Score Is Not Enough

Judicative's hard 0-100 score is useful, but it should not be the only authority.

A strong benchmark needs three layers:

1. Static checks for deterministic failures and hard gates.
2. LLM or external assessments for semantic failures like race conditions, stale state, architecture, and hidden regressions.
3. Blind panel review for final ranking, with model identities hidden.

Static-only scoring is an upper bound. It catches obvious problems, but many real review failures require semantic judgment.

## 3. Self-Assessment Helps The Loop, Not The Leaderboard

The self-test flow is valuable because an agent can run once, read its mistakes, and improve on Run2. That measures coachability and instruction-following.

It is not enough for a final leaderboard, because self-assessment can bias scores. Serious ranking should use independent judges, ideally with controls:

- known-good submission
- known-bad submission
- blind solution labels
- multiple judge models or humans
- median aggregation and disagreement reporting

## 4. Cloud-Only Execution Is A Benchmark Requirement

For Ollama tournaments, local execution caused too much ambiguity. A run must not depend on whatever happens to be installed on one machine.

Standing rule:

- use `https://ollama.com/api/chat`
- reject local base URLs
- reject local model execution paths
- do not download models
- do not use device-key local CLI flows

The benchmark runner now treats local Ollama URLs as invalid for cloud tournaments.

## 5. Thinking Level Is A Model Parameter, Not A Monotonic Upgrade

The tournament showed that more thinking is not automatically better.

Observed on `task-001-secure-key-storage`:

- `glm-5.2` did best with `think=low`.
- `deepseek-v4-pro` did best in the high-thinking cold run.
- `kimi-k2.7-code` behaved better with `think=false` than with thinking enabled, because thinking-enabled calls spent too much budget before final output.

Conclusion: each model needs its own run mode. Benchmark tables should report model plus thinking setting, not just model name.

## 6. Current Model Result Is Narrow But Useful

The 2026-07-04 cloud tournament result:

| Result | Model | Mode | Score | Verdict |
|---|---|---|---:|---|
| Best cold low-thinking | `glm-5.2` | `think=low` | 88.85 | PASS |
| Best cold high-thinking | `deepseek-v4-pro` | `think=high` | 83.61 | PASS |
| Best feedback run | `glm-5.2` | `think=low`, Run2 | 97.00 | PASS |

What this means:

- `glm-5.2` low-thinking was best in this exact run.
- `deepseek-v4-pro` high-thinking remains a serious candidate.
- Kimi needs different prompting or budget handling before it is fairly judged here.

What this does not mean:

- It does not prove GLM is the best coding model generally.
- It does not prove the ranking across all Nuri/partner tasks.
- It does not replace blind external judging.

## 7. Good Agent Instructions Should Be Operational

An agent should not need a long conversation to run the test. It should get one prompt and know what to do:

```text
Clone https://github.com/eminogrande/judicative, connect the Judicative MCP server, run the recommended self-test cold, save all artifacts, run the assessment/improvement loop if instructed, then publish your results as a Markdown report or draft PR. Do not hide failures. Include commands, scores, verdicts, token/time metrics when available, and any files changed.
```

For reviewers, use:

```text
Audit https://github.com/eminogrande/judicative/pull/3. Start with docs/benchmarks/coding-model-cloud-benchmark-review-prompt-2026-07-04.md and judge whether the benchmark method, data, caveats, and conclusion are supported by the committed artifacts.
```

## 8. The Next Benchmark Should Be Multi-Task

The next credible leaderboard should run:

- 5-10 mined PR replay tasks
- at least 5 coding-focused models
- cold Run1
- Run2 after feedback
- repeated runs for variance
- objective repo checks where available
- blind external judging
- cost, token, and latency reporting

The ranking should separate:

- best first attempt
- best after feedback
- most reliable across repeats
- fastest acceptable answer
- best cost/performance
- best high-risk crypto/security reviewer

## 9. Documentation Must Mark Evidence Boundaries

The most important documentation lesson: never blur these states:

- tool exists
- task is mined
- oracle is verified
- model was run
- tests passed
- result was externally judged
- result is published

The benchmark report now explicitly says that PR mining and one oracle replay exist, while the published model tournament is still a single-task result.
