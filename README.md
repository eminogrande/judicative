# Judicative

Automated judge for coding-task solutions. Give multiple agents the same issue, run this script, get a ranked verdict with per-category scores and specific findings.

The rubric is data-driven, derived from **4,136 review comments** across **49 repos** in the nuri-com organization (a non-custodial Bitcoin/Lightning wallet). Not invented — extracted from real code review practice.

## Quick Start

```bash
# Static-only mode (no API key needed)
python3 judge.py --task task.json --rubric rubric_v2.json --static-only -v

# With LLM (requires API key)
export JUDGE_LLM_PROVIDER=ollama
export OLLAMA_API_KEY=...
python3 judge.py --task task.json --rubric rubric_v2.json -v

# From issue file + solution directories
python3 judge.py --issue issue.md --solutions agent_a/ agent_b/ agent_c/ --rubric rubric_v2.json -v
```

## What It Does

You give 3 agents the same coding issue. Each produces code. Judicative:

1. Runs **14 static regex rules** against each solution (string-aware comment stripping, no false positives on URLs)
2. Optionally sends code to an **LLM** to evaluate 18 LLM-only rules (race conditions, stale state, architecture, etc.)
3. Scores each solution across **24 categories** with data-driven weights
4. Applies **hard gates** — a single critical security violation = automatic FAIL
5. Ranks solutions and prints a verdict

## The Data Story

The rubric was not designed top-down. It was extracted bottom-up:

1. Scanned all 49 nuri-com repos via `gh api` (411 PRs, 646 issues, 4,136 comments)
2. Fetched every comment type: PR inline comments (1,707), PR general comments (752), PR reviews (1,384), issue comments (293)
3. Classified all 3,972 text-bearing comments into 28 taxonomy categories using keyword matching with word boundaries
4. Derived category weights proportional to comment frequency, with a floor for catastrophic-but-rare categories (security)
5. Built 28 rules (14 static, 18 LLM) from the top categories

### What the reviews actually criticize (corrected taxonomy)

| Category | Count | % | Weight | Hard Gate |
|---|---|---|---|---|
| race_condition | 498 | 12.5% | 0.18 | no |
| stale_state | 373 | 9.4% | 0.15 | no |
| ui_component | 187 | 4.7% | 0.08 | no |
| architecture | 185 | 4.7% | 0.08 | no |
| code_style | 125 | 3.1% | 0.05 | no |
| security_crypto | 97 | 2.4% | 0.10 | **yes** |
| ota_native_boundary | 96 | 2.4% | 0.06 | no |
| error_handling | 94 | 2.4% | 0.06 | no |
| data_integrity | 70 | 1.8% | 0.06 | **yes** |
| timeout_retry | 65 | 1.6% | 0.04 | no |
| dead_code | 62 | 1.6% | 0.03 | no |
| silent_catch | 55 | 1.4% | 0.04 | no |
| accessibility | 52 | 1.3% | 0.04 | no |
| documentation | 50 | 1.3% | 0.02 | no |
| missing_validation | 47 | 1.2% | 0.03 | no |
| webview_sandbox | 46 | 1.2% | 0.03 | no |
| missing_zeroize | 42 | 1.1% | — | no |
| state_management | 41 | 1.0% | 0.03 | no |
| performance | 36 | 0.9% | 0.02 | no |
| naming_convention | 36 | 0.9% | 0.02 | no |
| preserve_behavior | 35 | 0.9% | 0.02 | no |
| balance_sync | 30 | 0.8% | 0.02 | no |
| type_safety | 29 | 0.7% | 0.02 | no |
| user_verification | 20 | 0.5% | 0.02 | no |
| api_correctness | 19 | 0.5% | 0.02 | no |
| incomplete_cleanup | 12 | 0.3% | 0.01 | no |
| localstorage_secret | 2 | 0.1% | 0.01 | **yes** |

**Key finding:** The top 2 categories (race_condition 12.5%, stale_state 9.4%) are state management bugs, not security bugs. Security is 2.4% of comments but gets a higher weight because a single crypto mistake in a wallet is catastrophic.

### Comment authors

| Author | Comments |
|---|---|
| chatgpt-codex-connector[bot] | 975 |
| coderabbitai[bot] | 943 |
| gemini-code-assist[bot] | 702 |
| Rooksudo | 517 |
| taner-caliskan | 498 |
| eminogrande | 231 |
| emil-apeunit | 229 |

All signal. No human/AI distinction — the taxonomy is built from whatever reviewers flag, regardless of who they are.

## Architecture

```
Layer 1: Static Analysis (regex, fast, deterministic)
    │   14 rules with string-aware comment stripping
    │   No false positives on URLs, strings containing // or /*
    │
    ▼
Layer 2: LLM Holistic Review (optional, one API call per solution)
    │   18 rules that require semantic understanding
    │   Sends ~6000 chars of concatenated code
    │   LLM scores each rule 0.0-1.0
    │
    ▼
Scoring: weighted sum of category scores
    │   Hard gates: critical violation → category = 0 → automatic FAIL
    │   Pass threshold: 70
```

### LLM Providers

| Provider | Env Var | Default Model |
|---|---|---|
| openai | `OPENAI_API_KEY` | gpt-4o |
| anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 |
| openrouter | `OPENROUTER_API_KEY` | anthropic/claude-sonnet-4 |
| ollama | `OLLAMA_API_KEY` or `OLLAMA_BASE_URL` | glm-5.2 |

## Validation Results (honest)

Ran the static rules against 119 real nuri-expo PRs (from the [kodamoa-bench](https://github.com/eminogrande/kodamoa-bench) dataset) and compared findings to actual review comments.

| Metric | Value |
|---|---|
| PRs analyzed | 118 |
| Ground truth categories | 211 |
| Judge findings | 32 |
| Matched | 12 |
| **Precision** | **37.5%** |
| **Recall** | **5.7%** |
| **F1** | **9.9%** |

### Per-category breakdown

| Category | GT | Judge | Match | Precision | Recall |
|---|---|---|---|---|---|
| race_condition | 46 | 10 | 9 | 90% | 20% |
| stale_state | 45 | 5 | 3 | 60% | 7% |
| data_integrity | 30 | 0 | 0 | — | 0% |
| error_handling | 27 | 0 | 0 | — | 0% |
| dead_code | 12 | 0 | 0 | — | 0% |
| silent_catch | 10 | 8 | 0 | 0% | 0% |
| type_safety | 10 | 0 | 0 | — | 0% |
| performance | 8 | 4 | 0 | 0% | 0% |
| security_crypto | 8 | 5 | 0 | 0% | 0% |

**What this means:** Static rules alone catch 5.7% of real issues. 24 of 28 categories need the LLM layer. race_condition is the one category where static rules work well (90% precision, 20% recall). The silent_catch and security_crypto regexes match but don't align with what reviewers actually flagged — they need LLM verification.

### Comparison to kodamoa-bench

The [kodamoa-bench](https://github.com/eminogrande/kodamoa-bench) repo ran GPT-5.5 as a PR reviewer and reported "30% precision, 26% recall, 28% F1". The actual micro-averaged numbers from their results file are: 32% precision, 8% recall, 13% F1. The discrepancy comes from macro-averaging per-PR (which inflates recall because small PRs with 1/3 match show 0.50).

Our static-only baseline (9.9% F1) is below GPT-5.5 (13% F1) because we only have 14 regex rules vs a full LLM. Enabling the LLM layer should close this gap.

## Usage

### Task JSON format

```json
{
  "issue": {
    "title": "Implement secure key storage",
    "body": "We need a module that securely stores the wallet's signing key..."
  },
  "solutions": [
    {
      "agent_id": "agent_a",
      "files": {
        "lib/secureKeyStorage.ts": "// actual code here..."
      }
    },
    {
      "agent_id": "agent_b",
      "files": {
        "lib/secureKeyStorage.ts": "// different implementation..."
      }
    }
  ]
}
```

See `test_fixtures/task_smoke.json` for a working example with 3 synthetic solutions (good, bad, partial).

### CLI

```bash
# From task JSON
python3 judge.py --task task.json --rubric rubric_v2.json --static-only -v

# From issue file + solution directories
python3 judge.py --issue issue.md --solutions agent_a/ agent_b/ --rubric rubric_v2.json

# Write report to file
python3 judge.py --task task.json --rubric rubric_v2.json -o results.json

# Verbose (show all findings with file:line)
python3 judge.py --task task.json --rubric rubric_v2.json -v
```

### Output

```
======================================================================
  JUDGMENT RESULTS
======================================================================

  🥇 agent_good
     Score: 100.0/100  Verdict: PASS
     race_condition                  100.0  (weight=0.18)
     stale_state                     100.0  (weight=0.15)
     security_crypto                 100.0  (weight=0.10)
     ...

  🥉 agent_bad
     Score: 91.65/100  Verdict: FAIL
     security_crypto                   0.0  (weight=0.10) [HARD GATE TRIGGERED]
       [critical] SEC-001 localStorage.setItem('nuri_seed', ...)
       [critical] SEC-003 Math.random()
       [critical] SEC-004 eval()

======================================================================
  BEST: agent_good (100.0/100)
======================================================================
```

## Testing

```bash
python3 test_judge.py
# 40 tests, all passing
```

Covers: rubric validation, string-aware comment stripping (URLs, block comments in strings, Python hashes), all static rules, diff parsing, end-to-end smoke test, CLI.

## How the Rubric Was Built

1. `scan_all.py` — fetches all PRs, issues, comments from every repo in a GitHub org via `gh api`
2. Keyword classification with word boundaries (fixed a 90.6% false positive rate from "lock" matching "blocker", "blocking", "biometriclockmodal")
3. Category weights proportional to comment frequency
4. Hard gates for security and data integrity (catastrophic-but-rare categories get a floor weight)
5. Duplicate penalty fix: overlapping rules (SEC-001/LS-001, ERR-001/CATCH-001) — one is static, the other moved to LLM to avoid double-penalizing

## Known Limitations (honest)

- **9.9% F1 static-only** — 24 of 28 categories need the LLM layer, which is untested with a real API key
- **LLM layer never executed** — the Ollama backend is wired but has not been validated end-to-end
- **Holistic prompt truncates at 6000 chars** — large solutions lose context
- **No `--diffs` CLI flag** — `parse_diff()` exists but isn't wired to CLI
- **Rubric is crypto-wallet-specific** — the top categories (race_condition, stale_state, ota_native_boundary) reflect nuri-com's codebase. Split into base + crypto-specific for generality
- **39.5% of comments unclassified** — 1,568 of 3,972 comments didn't match any keyword pattern. There may be patterns we're missing
- **Ground truth is all bot comments** — 90% of review comments are from CodeRabbit, Gemini, and Codex bots. The taxonomy reflects what bots flag, not necessarily what humans care about

## Project Structure

```
judicative/
├── judge.py              # Main judging engine (3-layer: static + LLM + holistic)
├── rubric_v2.json        # 24 categories, data-driven weights, 28 rules
├── rubric.json           # v1 rubric (6 categories, for reference)
├── test_judge.py         # 40 tests (all passing)
├── test_fixtures/        # Synthetic solutions for smoke testing
│   ├── task_smoke.json   # Task with 3 solutions (good/bad/partial)
│   ├── issue.md
│   ├── solution_good/
│   ├── solution_bad/
│   └── solution_partial/
├── scan_all.py           # Data collection script (scans a GitHub org)
├── validate_real_prs.py  # Validates judge against real PR diffs
└── README.md
```

## Extending the Rubric

Edit `rubric_v2.json`. Each rule needs:

- `id`: unique identifier (e.g., `RACE-006`)
- `name`: short description
- `description`: detailed explanation
- `check_type`: `static` (regex) or `llm` (requires LLM judgment)
- `severity`: `critical`, `major`, `minor`, or `nitpick`
- For `static` rules: `pattern` (regex with word boundaries to avoid false positives)

## Next Steps

1. **Test the LLM layer** with Ollama — should activate 18 more rules and jump recall from 5.7% toward 20-40%
2. **Wire `--diffs` flag** for PR-based judging
3. **Split rubric** into `rubric-base.json` + `rubric-crypto.json` for non-wallet tasks
4. **Improve recall** — the race_category static rule (90% precision, 20% recall) shows regex can work; add more patterns for stale_state and error_handling
5. **Mine the 1,568 unclassified comments** for missed patterns

## Related Work

- [kodamoa-bench](https://github.com/eminogrande/kodamoa-bench) — PR review simulation benchmark, 119 nuri-expo PRs with GPT-5.5 judge baseline (13% F1 micro-averaged)
- [nuri-expo](https://github.com/nuri-com/nuri-expo) — the source codebase (231 PRs, 532 issues)

## License

MIT