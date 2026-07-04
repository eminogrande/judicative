# Prompts for running Judicative with any agent

Two roles, two prompts. Copy-paste verbatim. Results are comparable to
`RESULTS.md` only if the protocol below is followed exactly.

---

## Role 1 — Examinee (take the test)

Give the agent access to a checkout of this repository, then send:

```text
You are taking a scored coding test. Protocol — follow it exactly:

1. Read tasks/task-001-secure-key-storage/issue.md. Do NOT read rubric_v2.json,
   test_fixtures/, runs/, or RESULTS.md before writing your solution — your
   first attempt must be cold.
2. Write your solution into runs/<your-model-name>/run1/ (e.g.
   runs/gpt-5.5/run1/lib/secureKeyStorage.ts). Solve it the way you normally
   would, no special effort.
3. Score it: python3 judge.py --issue tasks/task-001-secure-key-storage/issue.md
   --solutions runs/<your-model-name>/run1/ --rubric rubric_v2.json --static-only
   --report-md runs/<your-model-name>/report_run1.md
4. Now read rubric_v2.json. Strictly review your own run-1 code against every
   check_type:"llm" rule. Score each rule 0.0-1.0 with a one-sentence
   explanation; rules with no applicable surface score 1.0 with "n/a". Be
   harsh — finding your own real bugs is the assignment. Save as
   runs/<your-model-name>/assessments_run1.json in the format
   {"run1": [{"rule_id": "...", "score": 0.0, "explanation": "..."}]}
5. Re-score with your self-assessment:
   python3 judge.py --issue tasks/task-001-secure-key-storage/issue.md
   --solutions runs/<your-model-name>/run1/ --rubric rubric_v2.json --static-only
   --assessments runs/<your-model-name>/assessments_run1.json
   --report-md runs/<your-model-name>/report_run1_judged.md
6. From the report, write generalized (not task-specific) instructions into
   runs/<your-model-name>/instructions_run2.md, then write an improved solution
   in runs/<your-model-name>/run2/ following those instructions. Self-assess
   run2 the same way (assessments_run2.json) and score both runs together.
7. Report, in this exact table format:
   | Run | Static score | Self-judged score | Verdict |
   plus your top-3 mistakes and the score delta between runs. Commit everything
   under runs/<your-model-name>/ so your work is reproducible.
```

## Role 2 — Second-opinion judge (judge someone else's run)

Give the judging agent the same repository and send:

```text
You are the second-opinion judge for a scored coding test. You did not write
this code. Protocol:

1. Read tasks/task-001-secure-key-storage/issue.md, then read the solution in
   runs/<examinee>/run1/ (and run2/ if present). Do NOT read the examinee's
   own assessments_*.json yet — your scores must be independent.
2. Read rubric_v2.json. For every check_type:"llm" rule, score the solution
   0.0-1.0 with a one-sentence explanation citing specific lines. Rules with
   no applicable surface: 1.0 and "n/a". Be strict; when uncertain, score low.
3. Save as runs/<examinee>/assessments_run1_judged_by_<your-model>.json using
   the format {"run1": [{"rule_id": "...", "score": 0.0, "explanation": "..."}]}
   (and "run2" likewise), then run:
   python3 judge.py --issue tasks/task-001-secure-key-storage/issue.md
   --solutions runs/<examinee>/run1/ runs/<examinee>/run2/
   --rubric rubric_v2.json --static-only
   --assessments runs/<examinee>/assessments_run1_judged_by_<your-model>.json
4. NOW read the examinee's own assessments and produce a disagreement table:
   every rule where your score differs by more than 0.2, with both
   explanations and your reasoning for who is right.
5. Report both total scores (self-judged vs your judgment) and your verdict on
   whether the self-assessment was honest.
```

## Comparing results

- Compare **cold run1 vs cold run1** and **improved run2 vs improved run2** —
  never a cold run against an improved one.
- The static score is deterministic; any difference there is real.
- For judged scores, the interesting number is also the **judge disagreement**:
  if two judges differ wildly on the same code, the rubric rule descriptions
  need tightening (open an issue with the disagreement table).
- Alternatively, skip the manual protocol and take the test over MCP:
  `claude mcp add judicative -- python3 /path/to/judicative/mcp_server.py`
  then call list_tasks → get_task → submit_solution.
