# Coding Model Cloud Benchmark - 2026-07-04

Scope:

- Direct Ollama Cloud only: `https://ollama.com/api/chat`
- No local Ollama models, no local endpoint, no device-key flow
- Task: `task-001-secure-key-storage`
- Models: `glm-5.2`, `kimi-k2.7-code`, `minimax-m3`, `deepseek-v4-pro`, `deepseek-v4-flash`, `qwen3-coder:480b`
- Published machine-readable data: `docs/benchmarks/coding-model-cloud-benchmark-2026-07-04.json`
- Local raw metrics and responses were saved per call under `runs/tournaments/` during the run.

Important caveat: these scores use the Judicative rubric plus model self-assessment where configured. They are useful first-pass benchmark signals, but final ranking should still use an external blind panel.

## Method

Each model was asked to solve the same secure key-storage coding task through Judicative's tournament runner. The runner used Ollama's native cloud API with `stream: false`, `format: "json"`, and the configured `think` setting. It captured model response metadata when Ollama returned it, including `prompt_eval_count`, `eval_count`, `total_duration`, and assistant `thinking` length.

The tournament was split into:

1. Cold Run1 with `think=low`.
2. Cold Run1 with `think=high`.
3. Cold Run1 with `think=false`.
4. Run2 feedback loops for the strongest or most interesting candidates from the cold runs.

Representative commands:

```bash
python3 bench/model_tournament.py \
  --tournament-id coding-low-run1-20260704 \
  --models glm-5.2 kimi-k2.7-code minimax-m3 deepseek-v4-pro deepseek-v4-flash qwen3-coder:480b \
  --think-levels low --assessment-think low \
  --max-tokens 8000 --skip-run2 --skip-panel

python3 bench/model_tournament.py \
  --tournament-id coding-high-run1-20260704 \
  --models glm-5.2 kimi-k2.7-code minimax-m3 deepseek-v4-pro deepseek-v4-flash qwen3-coder:480b \
  --think-levels high --assessment-think low \
  --max-tokens 40000 --skip-run2 --skip-panel

python3 bench/model_tournament.py \
  --tournament-id coding-no-think-run1-20260704 \
  --models glm-5.2 kimi-k2.7-code minimax-m3 deepseek-v4-pro deepseek-v4-flash qwen3-coder:480b \
  --think-levels false --assessment-think false \
  --max-tokens 8000 --skip-run2 --skip-panel
```

## Cold Run1 - Think Low

Source: `runs/tournaments/coding-low-run1-20260704/SUMMARY.md`

| Model | Score | Verdict | Tokens | Seconds | Notes |
|---|---:|---|---:|---:|---|
| `glm-5.2` | 88.85 | PASS | 18,263 | 78.19 | Best low-thinking cold run |
| `deepseek-v4-flash` | 60.85 | FAIL | 12,369 | 27.62 | Fast, partial |
| `minimax-m3` | 41.47 | FAIL | 29,988 | 165.26 | Slow, weak score |
| `deepseek-v4-pro` | 25.00 | FAIL | 15,667 | 68.72 | Poor in low mode |
| `qwen3-coder:480b` | 0.00 | FAIL | 8,703 | 56.13 | Failed hard |
| `kimi-k2.7-code` | failure | FAIL | 16,593 | 120.36 | Consumed budget in thinking, no final content |

## Cold Run1 - Think High

Source: `runs/tournaments/coding-high-run1-20260704/SUMMARY.md`

| Model | Score | Verdict | Tokens | Seconds | Notes |
|---|---:|---|---:|---:|---|
| `deepseek-v4-pro` | 83.61 | PASS | 16,388 | 76.79 | Best high-thinking cold run |
| `glm-5.2` | 39.68 | FAIL | 18,241 | 98.30 | Worse than low mode |
| `qwen3-coder:480b` | 21.15 | FAIL | 9,091 | 19.81 | Fast but weak |
| `minimax-m3` | 21.05 | FAIL | 37,585 | 200.01 | Very slow and weak |
| `kimi-k2.7-code` | 19.44 | FAIL | 43,402 | 356.05 | Very slow, heavy thinking |
| `deepseek-v4-flash` | 16.50 | FAIL | 14,741 | 45.46 | Weak in high mode |

## Cold Run1 - Think False

Source: `runs/tournaments/coding-no-think-run1-20260704/SUMMARY.md`

| Model | Score | Verdict | Tokens | Seconds | Notes |
|---|---:|---|---:|---:|---|
| `kimi-k2.7-code` | 63.18 | FAIL | 8,508 | 23.84 | Best no-thinking run |
| `minimax-m3` | 57.19 | FAIL | 23,402 | 115.45 | Moderate, still fail |
| `qwen3-coder:480b` | 25.00 | FAIL | 8,540 | 17.65 | Fast but weak |
| `glm-5.2` | 24.37 | FAIL | 12,975 | 95.67 | Needs thinking for this task |
| `deepseek-v4-pro` | 12.55 | FAIL | 11,191 | 58.20 | Needs high thinking |
| `deepseek-v4-flash` | 0.00 | FAIL | 10,491 | 19.35 | Failed hard |

## Run2 With Feedback

Sources:

- `runs/tournaments/coding-run2-glm-low-20260704/SUMMARY.md`
- `runs/tournaments/coding-run2-deepseek-pro-high-20260704/SUMMARY.md`
- `runs/tournaments/coding-run2-kimi-false-20260704/SUMMARY.md`

| Model | Mode | Run1 | Run2 | Delta | Run2 Verdict | Tokens | Seconds | Notes |
|---|---|---:|---:|---:|---|---:|---:|---|
| `glm-5.2` | low | 90.11 | 97.00 | +6.89 | PASS | 45,259 | 310.07 | Best overall result |
| `deepseek-v4-pro` | high | 0.00 | 80.00 | +80.00 | PASS | 43,466 | 173.04 | Strong rescue after feedback, but unstable cold run |
| `kimi-k2.7-code` | false | 61.92 | 45.27 | -16.65 | FAIL | 21,990 | 56.29 | Feedback made it worse |

## Current Read

1. Best cold mode depends heavily on thinking:
   - `glm-5.2` wins in `think=low`.
   - `deepseek-v4-pro` wins in `think=high`.
   - `kimi-k2.7-code` only behaves reasonably with `think=false`.

2. Best overall tested result:
   - `glm-5.2` with `think=low`, after feedback: `97.00 PASS`.

3. Best high-thinking model:
   - `deepseek-v4-pro`, cold: `83.61 PASS`.
   - It also repaired to `80.00 PASS` in a separate feedback run, but the cold score varied, so repeat runs are needed.

4. Kimi behavior:
   - `think=low` and `think=high` spent large budgets in thinking and often failed to produce final content.
   - `think=false` produced usable content, but scores stayed below pass.

5. Next fair judging step:
   - Build a blind panel packet from the best saved `solution/` directories.
   - Use a separate judge team instead of self-assessment to avoid model self-scoring bias.
