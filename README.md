# Judicative

Automated judge for coding-task solutions. Give multiple agents the same issue, run this script, get a ranked verdict on a hard 0–100 scale with per-category findings, a "what you did wrong" report, and instructions for the next run.

The rubric is data-driven, derived from **4,136 review comments** across **49 repos** in the nuri-com organization (a non-custodial Bitcoin/Lightning wallet). Not invented — extracted from real code review practice.

## The three branches

The name is deliberate — the kit separates powers:

- **Legislative** — `scan_all.py` + the rubrics: mines your chosen repos (commits, PRs, review comments) and writes the law. Point it at different repos and you get a different constitution.
- **Judicative** — `judge.py`: applies the law to any submission. Deterministic static layer + LLM layer, hard 0–100 score, written opinion (`--report-md`).
- **Executive** — the agent under test + the improvement loop: takes the ruling, extracts generalized instructions, and executes the next run better. `AGENT_PROMPT.md` and `mcp_server.py` are its interface.

Measured on myself: one loop through all three branches moved my score from **46.36 (FAIL) to 89.55 (PASS)** — see [RESULTS.md](RESULTS.md).

Latest Ollama Cloud coding-model benchmark: [docs/benchmarks/coding-model-cloud-benchmark-2026-07-04.md](docs/benchmarks/coding-model-cloud-benchmark-2026-07-04.md). External audit prompt: [docs/benchmarks/coding-model-cloud-benchmark-review-prompt-2026-07-04.md](docs/benchmarks/coding-model-cloud-benchmark-review-prompt-2026-07-04.md).

## Quick Start

```bash
# Static-only mode (no API key needed)
python3 judge.py --task task.json --rubric rubric_v2.json --static-only -v

# With LLM (requires API key)
export JUDGE_LLM_PROVIDER=ollama
export JUDGE_LLM_MODEL=glm-5.2
export OLLAMA_API_KEY=...
python3 judge.py --task task.json --rubric rubric_v2.json -v

# From issue file + solution directories
python3 judge.py --issue issue.md --solutions agent_a/ agent_b/ agent_c/ --rubric rubric_v2.json -v
```

## What It Does

You give 3 agents the same coding issue. Each produces code. Judicative:

1. Runs **14 static regex rules** against each solution (string-aware comment stripping, no false positives on URLs)
2. Optionally evaluates the LLM-only rules (race conditions, stale state, architecture, etc.) via an **LLM API** or an **external judge file** (`--assessments` — any model can judge without this process holding a key)
3. Scores on **one hard 0–100 scale** — every finding costs real points (global penalty model, see below)
4. Applies **hard gates** — a single critical security violation caps the score at 25 and forces FAIL
5. Ranks solutions, prints a verdict, and writes a **mistakes report** (`--report-md`) with instructions for the next run

## Scoring (global penalty model — "hard mode")

The old model averaged 24 per-category scores that each started at a free 100; a solution with 5 critical security violations still scored 91.65. That is compression, not judgment. Now:

```
score = max(0, 100 − Σ penalties)          — one scale, no free points

penalty per finding = point_penalty[severity] × emphasis[category]
    critical 20 · major 6 · minor 2 · nitpick 0.25
    emphasis = category_weight / mean_weight, clamped to [0.5, 2.0]
      (data-driven: race_condition and security cost 2×)

repeated hits of the same rule decay geometrically (×0.5 each)
    → one spammy regex can cost at most 2× its single-hit penalty
identical matches found by two rules count once (costliest kept)
LLM rules deduct (1 − judge_score) × the same penalty

hard gate: critical violation in a gated category
    → total capped at 25 AND verdict = FAIL (score and verdict can't disagree)
```

All knobs live in the rubric's `scoring` block, so the model is reproducible from the JSON alone. Calibration on the synthetic fixtures (static-only): **good 100 · partial 86.79 · bad 0** — instead of the old 100 / 99.71 / 91.65.

Static-only scores are an **upper bound**: a clean static run means "nothing a regex can catch". The discrimination between careful solutions lives in the LLM-rule layer.

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
    │   Duplicate matches across rules deduped
    │
    ▼
Layer 2: LLM Holistic Review (optional, one API call per solution)
    │   Rules that require semantic understanding
    │   LLM scores each rule 0.0-1.0
    │   OR: --assessments file from any external judge (no API key needed)
    │
    ▼
Scoring: global penalty model (see above)
    │   Every finding costs points on one 0-100 scale
    │   Hard gates: critical violation → capped at 25 → automatic FAIL
    │   Pass threshold: 70
```

### LLM Providers

| Provider | Env Var | Default Model |
|---|---|---|
| openai | `OPENAI_API_KEY` | gpt-4o |
| anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 |
| openrouter | `OPENROUTER_API_KEY` | anthropic/claude-sonnet-4 |
| ollama | `OLLAMA_API_KEY` with `https://ollama.com/api/chat` | glm-5.2 |

By default, the judge is deterministic static analysis plus whatever LLM backend
is configured through `JUDGE_LLM_PROVIDER`. If no LLM key is configured, runs are
`static-only` and the score is only a preliminary upper bound. Final model
results should use either external assessments or a blind panel.

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

# Mistakes report: "what you did wrong" + instructions for the next run
python3 judge.py --task task.json --rubric rubric_v2.json --report-md report.md

# External judge (any LLM scores the llm-rules, no API key in this process):
# assessments.json = {"agent_a": [{"rule_id": "RACE-005", "score": 0.4, "explanation": "..."}]}
python3 judge.py --task task.json --rubric rubric_v2.json --static-only --assessments assessments.json
```

### Blind panel — a review committee on top of the score

`panel.py` simulates an anonymous human review committee as a second, independent opinion next to the deterministic score:

```bash
# 1. Blind the submissions (labels = content hashes; author mapping written SEALED elsewhere)
python3 panel.py prepare --issue tasks/task-001-secure-key-storage/issue.md \
    --solutions runs/agent-x/run1/ runs/agent-y/run1/ test_fixtures/solution_bad/ \
    --rubric rubric_v2.json --out panel_run/ --mapping-out /sealed/mapping.json

# 2. Give panel_run/packet.md to N independent judges (LLMs, agents, humans).
#    Each returns a JSON verdict: holistic 0-100 + per-rule deductions + ranking.

# 3. Aggregate: per-rule MEDIAN (one outlier judge can't swing it), holistic median,
#    disagreement table, pairwise ranking agreement — then unblind.
python3 panel.py aggregate --dir panel_run/ --mapping /sealed/mapping.json \
    --judges j1.json j2.json j3.json --rubric rubric_v2.json --report PANEL_REPORT.md
```

Mix known-good/known-bad fixture solutions into the packet as **controls**: a judge who passes the known-bad submission has disqualified itself. See [PANEL_REPORT.md](PANEL_REPORT.md) for a real 3-judge blind panel over the committed runs.

### OpenRouter judge team

You can turn any blind packet into a multi-model OpenRouter committee:

```bash
# 1. Build the blind packet.
python3 panel.py prepare --issue tasks/task-001-secure-key-storage/issue.md \
    --solutions runs/agent-a/task-001-secure-key-storage/run1/solution/ \
                runs/agent-b/task-001-secure-key-storage/run1/solution/ \
                test_fixtures/solution_bad/ \
    --rubric rubric_v2.json --out panel_run/ \
    --mapping-out panel_run/mapping.SEALED.json

# 2. Ask OpenRouter models to judge independently.
OPENROUTER_API_KEY=... python3 openrouter_panel.py \
    --packet panel_run/packet.md \
    --out panel_run/openrouter_judges \
    --models <model-1> <model-2> <model-3>

# 3. Aggregate the committee.
python3 panel.py aggregate --dir panel_run \
    --mapping panel_run/mapping.SEALED.json \
    --judges panel_run/openrouter_judges/*.json \
    --rubric rubric_v2.json \
    --report PANEL_REPORT_OPENROUTER.md
```

Use at least three models where possible. Keep contestant identities out of the
packet, and include known-good/known-bad controls so a weak judge can disqualify
itself.

### MCP server — point any LLM at the test

```bash
# Send this repo link, then in the agent's checkout:
git clone https://github.com/eminogrande/judicative.git
cd judicative
claude mcp add judicative -- python3 /path/to/judicative/mcp_server.py
```

The MCP exposes a full self-test flow, not just a score endpoint:

1. `list_tasks` — discover available tests and the recommended flow
2. `start_self_test` — get the issue, cold-run rules, and artifact paths
3. `submit_solution` — submit run files, score them, and persist artifacts under `runs/<agent>/<task>/<run>/`
4. `get_assessment_template` — get every LLM-only rule the agent must self-score after the cold run
5. `score_saved_run` — re-score a saved run with self/external assessments
6. `prepare_results_pr` — write `PR_BODY.md` and return the exact git/gh commands to publish the run as a draft PR

The persisted bundle is committee-friendly: `solution/` contains only the submitted code, while `RESULT.md`, `result.json`, `mistakes_report.md`, `assessments.json`, and `SUMMARY.md` contain the evidence. A judging committee can review the PR directly or use the saved `solution/` directories to build a blind panel packet with `panel.py`.

Stdlib only. Tasks live in `tasks/<task-id>/issue.md` — add a directory to add a task. `AGENT_PROMPT.md` has copy-paste prompts for running any agent as examinee, second-opinion judge, or blind panel judge.

### Output

```
======================================================================
  JUDGMENT RESULTS
  (static-only: LLM rules not evaluated — scores are an UPPER BOUND)
======================================================================

  🥇 agent_good
     Score: 100.0/100  Verdict: PASS  Penalty: -0.0

  🥈 agent_partial
     Score: 86.79/100  Verdict: PASS  Penalty: -13.21
     error_handling                   58.0  (-13.21 pts, emphasis=1.26x)
       [major   ] ERR-001 lib/secureKeyStorage.ts:20 — catch (error) { }
       ...

  🥉 agent_bad
     Score: 0.0/100  Verdict: FAIL  Penalty: -205.21
     security_crypto                   0.0  (-192.00 pts, emphasis=2.0x) [HARD GATE TRIGGERED]
       [critical] SEC-001 lib/secureKeyStorage.ts:14 — localStorage.setItem('nuri_seed', ...
       [critical] SEC-003 lib/secureKeyStorage.ts:8 — Math.random(
       [critical] SEC-004 lib/secureKeyStorage.ts:40 — eval(
       ...

======================================================================
  BEST: agent_good (100.0/100)
======================================================================
```

## Testing

```bash
python3 test_judge.py
python3 test_mcp_server.py
python3 test_openrouter_panel.py
# judge: 56 tests, all passing
```

Covers: rubric validation, string-aware comment stripping (URLs, block comments in strings, Python hashes), all static rules, diff parsing, the scoring model (hard-gate cap, repeat decay, dedup determinism, emphasis clamping, score/verdict coherence, v1+v2 calibration), end-to-end smoke test, CLI, and the MCP self-test artifact flow.

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
├── judge.py              # Judicative: judging engine, global penalty scoring, mistakes report
├── mcp_server.py         # MCP server — self-test flow, persisted results, PR prep
├── rubric_v2.json        # The law: 26 categories, data-driven weights, 28 rules
├── rubric.json           # v1 rubric (6 categories, for reference)
├── scan_all.py           # Legislative: mines a GitHub org into rubric data
├── validate_real_prs.py  # Validates judge against real PR diffs
├── test_judge.py         # 50 tests (all passing)
├── tasks/                # Test tasks served by the MCP server
│   └── task-001-secure-key-storage/issue.md
├── runs/                 # Executive: recorded test runs per agent
│   └── claude-fable-5/   # run1 (cold), run2 (instructed), assessments, report
├── test_fixtures/        # Synthetic solutions for smoke testing
├── test_mcp_server.py    # MCP self-test artifact flow tests
├── RESULTS.md            # Self-test results: 46.36 → 89.55 in one loop
├── AGENT_PROMPT.md       # Copy-paste prompts: examinee + second-opinion judge
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

1. **Second opinions** — have other LLMs judge the committed runs (`AGENT_PROMPT.md`, Role 2) and measure judge disagreement per rule
2. **More tasks** — 5–10 tasks covering the top rubric categories, so scores are a benchmark rather than an anecdote
3. **Test the LLM layer live** with an API key — activates the remaining rules and should lift recall from 5.7% toward 20-40%
4. **Multi-org legislative** — run `scan_all.py` against additional respected orgs/accounts and merge rubrics
5. **Wire `--diffs` flag** for PR-based judging
6. **Mine the 1,568 unclassified comments** for missed patterns

## Related Work

- [kodamoa-bench](https://github.com/eminogrande/kodamoa-bench) — PR review simulation benchmark, 119 nuri-expo PRs with GPT-5.5 judge baseline (13% F1 micro-averaged)
- [nuri-expo](https://github.com/nuri-com/nuri-expo) — the source codebase (231 PRs, 532 issues)

## License

MIT
