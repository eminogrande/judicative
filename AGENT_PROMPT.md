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

## Role 1b — Examinee over MCP (preferred)

Give the agent this repo link and ask it to install the MCP:

```text
Clone https://github.com/eminogrande/judicative, then install the MCP server:

claude mcp add judicative -- python3 /absolute/path/to/judicative/mcp_server.py

You are taking a scored coding self-test. Protocol — follow it exactly:

1. Call list_tasks, then start_self_test with task_id "task-001-secure-key-storage"
   and agent_id "<your-model-name>".
2. For run1, read only the task returned by start_self_test. Do NOT call
   get_rubric and do NOT read rubric_v2.json, test_fixtures/, runs/, RESULTS.md,
   or PANEL_REPORT.md before writing run1.
3. Submit run1 with submit_solution using run_id "run1" and a files object
   containing every solution file.
4. Now call get_assessment_template. Read the rubric rules and score every
   LLM-only rule from 0.0 to 1.0 with one concrete explanation per rule.
   Be harsh; finding your own real bugs is the assignment.
5. Call score_saved_run for run1 with those assessments. Read the returned
   mistakes report and write generalized instructions for run2.
6. Submit run2 with submit_solution using run_id "run2". Self-assess and
   re-score run2 the same way.
7. Call prepare_results_pr. Open the returned PR_BODY.md and use the returned
   git/gh commands to publish a draft PR with everything under runs/<agent>/<task>/.
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

## Role 3 — Blind panel judge (anonymous committee member)

Prepare the packet first (`python3 panel.py prepare ...` — see README), then give
each judge ONLY the packet, never the mapping or the repo:

```text
You are one judge on a blind code review panel. Attached is a self-contained
review packet: the task, the rubric rules, and N anonymized submissions.
You must not try to identify the authors or let style hints influence you.
Follow the packet's instructions exactly and return ONLY the JSON verdict in
the format it specifies: a holistic 0-100 score, PASS/FAIL verdict, strengths,
weaknesses, and per-rule deductions for every submission, plus a full ranking.
Review each submission independently. Be strict: 100 means you found nothing
to improve. Cite line numbers in every explanation.
```

Aggregate with `python3 panel.py aggregate ...`. Use at least 3 judges; mix in
the known-good/known-bad fixture solutions as controls and discard any judge
that passes the known-bad control.

## Role 3b — OpenRouter judge team

After `panel.py prepare`, run a multi-model committee through OpenRouter:

```bash
OPENROUTER_API_KEY=... python3 openrouter_panel.py \
  --packet panel_run/packet.md \
  --out panel_run/openrouter_judges \
  --models <model-1> <model-2> <model-3>

python3 panel.py aggregate --dir panel_run \
  --mapping panel_run/mapping.SEALED.json \
  --judges panel_run/openrouter_judges/*.json \
  --rubric rubric_v2.json \
  --report PANEL_REPORT_OPENROUTER.md
```

Use different model families when possible. The panel packet is already blinded;
do not give the OpenRouter judges the mapping file.

## Comparing results

- Compare **cold run1 vs cold run1** and **improved run2 vs improved run2** —
  never a cold run against an improved one.
- The static score is deterministic; any difference there is real.
- For judged scores, the interesting number is also the **judge disagreement**:
  if two judges differ wildly on the same code, the rubric rule descriptions
  need tightening (open an issue with the disagreement table).
- Prefer the MCP protocol for new agents: it writes a reproducible
  `runs/<agent>/<task>/SUMMARY.md` plus per-run `RESULT.md`, `result.json`,
  `mistakes_report.md`, optional `assessments.json`, and a `PR_BODY.md` for
  publishing the run as a draft PR.
