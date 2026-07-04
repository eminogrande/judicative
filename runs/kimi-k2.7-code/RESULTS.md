# Judicative Self-Test Results — kimi-k2.7-code

**Date:** 2026-07-04 · **Rubric:** v2.1.0 (data-driven, nuri-com) · **Score model:** global-penalty-v2 ("hard mode") · **Task:** `task-001-secure-key-storage`

## Headline

| Run | Static score (reproducible) | Full score (static + judge) | Verdict | Δ |
|---|---|---|---|---|---|
| **Run 1** — cold, no special instructions | 92.45 (upper bound) | **56.38** | FAIL | — |
| **Run 2** — with extracted instructions | 100.0 (upper bound) | **86.41** | PASS | **+30.03** |

One improvement loop moved the score by **30 points** from FAIL to PASS. The instruction extract is in [`runs/kimi-k2.7-code/instructions_run2.md`](runs/kimi-k2.7-code/instructions_run2.md); it is generalized, not task-specific.

## Reference calibration (synthetic fixtures, static-only, fully reproducible)

| Solution | Score | Verdict |
|---|---|---|
| agent_good | 100.0 | PASS |
| agent_partial | 86.79 | PASS |
| agent_bad | 0.0 | FAIL |

## What went wrong (run 1) — strict self-review

Full detail is in [`runs/kimi-k2.7-code/assessments_run1.json`](runs/kimi-k2.7-code/assessments_run1.json) and [`runs/kimi-k2.7-code/report_run1_judged.md`](runs/kimi-k2.7-code/report_run1_judged.md). Top deductions:

1. **CATCH-001 / ERR-001 (major, ~7.55 pts):** a silent `catch (_) { }` swallowed cleanup failures.
2. **RACE-005 (critical-adjacent):** `inFlightCreate` was not guarded during assignment; concurrent calls could both see `null`.
3. **DATA-005:** no dedup for load/wipe operations; only create was deduped.
4. **OTA-001/002:** native module assumed present at import time despite runtime checks.
5. **SEC-010:** immutable base64 strings and `Array.from` copies could not be zeroized.
6. **UV-001:** web path had no user-verification gate (platform limitation, documented).
7. **ARCH-003:** single file mixed public API, two backends, mutex, crypto, validation.
8. **PERF-001:** IndexedDB connection was cached but closed after every operation.

## What changed in run 2

- Removed silent catch; cleanup errors are logged via `console.error` and do not override the primary error.
- Replaced ad-hoc `inFlightCreate` with `dedupeOp()` keyed by operation.
- Added `withLock()` around all mutating storage calls (create, load, wipe).
- Kept DB connection open across transactions; removed per-call `db.close()`.
- Tightened web record validation (ciphertext length must include seed bytes + tag).
- Added structured `KeyStorageError` codes for programmatic handling.
- Better documented residual risks (immutable JS strings, no web UV primitive).

Residual deductions (−13.59) are honest platform limits: JS strings cannot be zeroized, web has no UV gate for storage, and `expo-secure-store` is still statically imported.

## Methodology & honesty caveats

- The static layer is fully reproducible.
- The LLM-rule layer is self-judged; scores and explanations are committed as JSON so any other LLM can re-judge the identical code.
- Run 2 knew run 1's findings, so scores are not comparable to another model's cold run — compare cold-vs-cold and improved-vs-improved.
- No external second-opinion judge has reviewed these runs yet.
