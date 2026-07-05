# External Review Prompt - Coding Model Cloud Benchmark 2026-07-04

You are an independent benchmark reviewer. Review the Judicative cloud coding-model benchmark and decide whether the conclusions are supported by the committed artifacts.

Repository and branch:

- Repository: `eminogrande/judicative`
- Pull request: `https://github.com/eminogrande/judicative/pull/3`
- Branch: `judicative/glm-5.2/task-001-secure-key-storage`
- Report: `docs/benchmarks/coding-model-cloud-benchmark-2026-07-04.md`
- Machine data: `docs/benchmarks/coding-model-cloud-benchmark-2026-07-04.json`

Important files to inspect:

- `bench/model_tournament.py`
- `judge.py`
- `mcp_server.py`
- `bench/mine_tasks.py`
- `bench/verify_task_oracle.py`
- `bench/tasks/nuri-hard-v1-focused.jsonl`
- `bench/oracle-results/nuri-expo-pr-769.md`
- `test_model_tournament.py`
- `test_judge.py`
- `test_mcp_server.py`

Context:

- The benchmark used direct Ollama Cloud API calls to `https://ollama.com/api/chat`.
- It did not use local Ollama models, local Ollama endpoints, or device-key local CLI execution.
- The measured cloud tournament used one hard Judicative task: `task-001-secure-key-storage`.
- The branch also contains a PR replay mining pipeline, but the model tournament results were not yet run across the full mined PR replay suite.
- The claimed best overall result is `glm-5.2` with `think=low`, Run2 score `97.00 PASS`.
- The claimed best cold high-thinking result is `deepseek-v4-pro` with `think=high`, score `83.61 PASS`.

Please audit the benchmark with this structure:

1. Method accuracy
   - Does the report accurately describe what was run?
   - Does it clearly separate the single-task cloud tournament from the mined PR replay pipeline?
   - Does the report avoid overclaiming that the whole PR replay suite was already run?

2. Data integrity
   - Do the tables in the Markdown report match the JSON summary?
   - Are model names, scores, pass/fail verdicts, token counts, and seconds internally consistent?
   - Are failed or malformed model outputs disclosed instead of hidden?

3. Cloud-only guardrail
   - Does the code reject local Ollama base URLs?
   - Does it use the native Ollama Cloud API shape rather than a local CLI flow?
   - Is there any committed evidence of local model execution being used for these results?

4. Replay benchmark readiness
   - Does `bench/mine_tasks.py` extract enough information from merged PRs to create real replay tasks?
   - Does the oracle verification for `nuri-expo-pr-769` prove that at least one mined PR can be replayed from its pre-fix base?
   - What is still missing before this becomes a serious multi-task coding benchmark?

5. Conclusion quality
   - Is "`glm-5.2` with `think=low` was best in this exact run" supported?
   - Is "`deepseek-v4-pro` with `think=high` remains a serious competitor but needs repeats" supported?
   - Are the caveats strong enough?

Output format:

```markdown
# Independent Benchmark Review

## Verdict
Choose one: supported / mostly supported / partially supported / unsupported

## High-Severity Issues
- ...

## Medium-Severity Issues
- ...

## Low-Severity Issues
- ...

## Confirmed Claims
- ...

## Missing Evidence
- ...

## Recommended Next Benchmark
- ...

## Final Ranking Interpretation
Explain whether the current data supports GLM low-thinking as the best result for this run, and what would be needed before calling it the best model generally.
```

Do not rerun models unless explicitly asked. This is an audit of the committed evidence and methodology.
