# Judicative self-test: glm-5.2 on task-001-secure-key-storage

This PR contains a reproducible Judicative self-test run.

## Artifacts

- Summary: `runs/glm-5.2/task-001-secure-key-storage/SUMMARY.md`
- Task: `runs/glm-5.2/task-001-secure-key-storage/task.md`
- Runs directory: `runs/glm-5.2/task-001-secure-key-storage/`

## Current summary

# Judicative Self-Test Summary

- Agent: `glm-5.2`
- Task: `task-001-secure-key-storage`
- Generated: `2026-07-04T10:14:02+00:00`

| Run | Lane | Mode | Judge | Score | Verdict | Penalty | Result |
|---|---|---|---|---:|---|---:|---|
| `run1` | `diagnostic_self_assessed_retry` | `static+external-judge` | self_assessed (glm-5.2) | 0.0 | FAIL | -270.32 | [run1/RESULT.md](run1/RESULT.md) |
| `run2` | `diagnostic_self_assessed_retry` | `static+external-judge` | self_assessed (glm-5.2) | 76.4 | PASS | -23.6 | [run2/RESULT.md](run2/RESULT.md) |

Comparable score delta from first to latest run: **76.4**.

## Committee instructions

Review the committed `RESULT.md`, `result.json`, assessments, and solution files. For blind review, prepare a panel packet from the saved `solution/` directories. Only compare runs that share the same benchmark lane, context budget, and independent judge.
