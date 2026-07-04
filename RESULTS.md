# Judicative Self-Test Results — claude-fable-5

**Date:** 2026-07-04 · **Rubric:** v2.1.0 (data-driven, nuri-com) · **Score model:** global-penalty-v2 ("hard mode") · **Task:** `task-001-secure-key-storage`

## Headline

| Run | Static score (reproducible) | Full score (static + judge) | Verdict | Δ |
|---|---|---|---|---|
| **Run 1** — cold, no special instructions | 100.0 (upper bound) | **46.36** | FAIL | — |
| **Run 2** — with extracted instructions | 100.0 (upper bound) | **89.55** | PASS | **+43.19** |

One improvement loop — solve → judge → extract "what I did wrong" → generalize into instructions → re-run — moved the score by **43 points**. The instruction extract is in [`runs/claude-fable-5/instructions_run2.md`](runs/claude-fable-5/instructions_run2.md); it is generalized, not task-specific, so it should transfer to other tasks.

## Reference calibration (synthetic fixtures, static-only, fully reproducible)

| Solution | Score | Verdict |
|---|---|---|
| agent_good | 100.0 | PASS |
| agent_partial | 86.79 | PASS |
| agent_bad (5 critical security violations) | 0.0 | FAIL (hard-gate capped at 25 by rule; penalties drove it to 0) |

Reproduce with: `python3 judge.py --task test_fixtures/task_smoke.json --rubric rubric_v2.json --static-only`

## What I did wrong (run 1) — the court's opinion

Strict self-review of my own cold attempt found **6 real issues** (full detail with per-rule scores in [`runs/claude-fable-5/assessments_run1.json`](runs/claude-fable-5/assessments_run1.json) and [`runs/claude-fable-5/report.md`](runs/claude-fable-5/report.md)):

1. **RACE-005 (critical, −24.0 pts):** `createAndStoreSeed()` had no mutex or in-flight dedup. Two concurrent calls generate two seeds; both write the same alias; one caller holds a seed that was never persisted. In a wallet, that can orphan funds. *This is exactly the #1 category in the source repos (498 review comments) — and I walked straight into it.*
2. **SEC-010 (major, −8.4 pts):** no zeroization of key material, no `zeroize()` helper, extra base64 string copies of the seed.
3. **LS-001 (critical-adjacent, −5.0 pts):** web path stored the **raw seed** (base64) in IndexedDB — not localStorage, but still same-origin-readable plaintext at rest.
4. **OTA-001/002 (−7.3 pts):** native module called without an availability/fingerprint check — OTA-shipped code would crash on older binaries.
5. **VALID-001 (major, −2.3 pts):** seed read back from storage never validated to be 32 bytes; corrupted data would flow into signing.
6. **NAME-001 (minor, −0.4 pts):** docstring claimed "non-extractable storage" that the code did not deliver — a misleading security claim.

Plus smaller hits: no dedup of concurrent storage ops (DATA-005), per-call IndexedDB open (PERF-001), no user verification on the web path (UV-001).

## What changed in run 2

Every fix maps 1:1 to an instruction in the extract: a mutex + in-flight dedup, `zeroize()` + failure-path wiping, AES-GCM encryption at rest under a non-extractable WebCrypto key, `isAvailableAsync()` gating, 32-byte shape validation on load, cached DB connection, and documentation that claims exactly what the code does. Residual deductions (−10.45) are things a module honestly cannot fix: JS strings are immutable (native base64 copy), and the web platform has no user-verification primitive for storage access.

## Methodology & honesty caveats

- **The static layer is fully reproducible** — regex rules, deterministic, no model in the loop. Anyone gets the same 100/86.79/0 on the fixtures.
- **The LLM-rule layer for my runs is self-judged.** I wrote the code AND scored it. I was strict (I failed my own run 1), but self-judgment is structurally biased — I know what I intended, and I knew a rubric existed even though run 1 was written before re-reading it. The per-rule scores + explanations are committed as JSON precisely so **any other LLM can re-judge the identical code** and diff the verdicts: `python3 judge.py --issue tasks/task-001-secure-key-storage/issue.md --solutions runs/claude-fable-5/run1/ runs/claude-fable-5/run2/ --rubric rubric_v2.json --assessments <their-scores>.json`
- **Run 2 knew run 1's findings.** That is the point (measuring instruction-driven improvement), but it means run-2 scores are not comparable to another model's cold run — compare cold-vs-cold and improved-vs-improved.
- **Second opinion pending:** no external LLM has judged these runs yet. See [`AGENT_PROMPT.md`](AGENT_PROMPT.md) for the exact prompt to give another model, both to take the test and to act as second judge.

## Self-critique of the test itself

- One task is an anecdote, not a benchmark. The kit needs 5–10 tasks across the top rubric categories before scores between models mean much.
- Static-only scores compress at 100 for careful code; discrimination lives in the judge layer, which makes judge quality (and judge agreement across models) the thing to measure next.
- The rubric is wallet-specific by design — that's a feature for *your* use case (find the best agent for *your* job), but scores don't transfer across rubrics.
