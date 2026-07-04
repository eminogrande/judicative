#!/usr/bin/env python3
"""
mcp_server.py - Judicative as an MCP server agents can actually use.

Point any MCP-capable agent (Claude Code, Claude Desktop, Cursor, etc.) at this
server and it can run a self-test end to end:

1. start_self_test: receive the task, protocol, and artifact locations.
2. submit_solution: submit run files, get a score, and persist PR-ready results.
3. get_assessment_template: receive every LLM-only rubric rule to self-score.
4. score_saved_run: re-score a saved run with self/external assessments.
5. prepare_results_pr: generate a PR body and optional git/gh commands.

Stdlib only. Standard MCP stdio transport (newline-delimited JSON-RPC 2.0).

Setup:
    claude mcp add judicative -- python3 /path/to/judicative/mcp_server.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judge import (  # noqa: E402
    LLMBackend,
    build_mistakes_report,
    get_scoring,
    judge_solution,
    load_rubric,
    result_to_dict,
)

BASE = Path(__file__).resolve().parent
TASKS_DIR = BASE / "tasks"
RUNS_DIR = BASE / "runs"
BENCH_TASKS_DIR = BASE / "bench" / "tasks"
RUBRIC_PATH = Path(os.environ.get("JUDICATIVE_RUBRIC", BASE / "rubric_v2.json"))

SERVER_INFO = {"name": "judicative", "version": "1.2.0"}
PROTOCOL_VERSION = "2024-11-05"


# ==================== Small utilities ====================

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(BASE).as_posix()


def slug(value: str, fallback: str = "anonymous") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", (value or "").strip()).strip("-._")
    return cleaned[:80] or fallback


def safe_solution_path(raw_path: str) -> Path:
    raw = str(raw_path or "").replace("\\", "/").strip()
    if not raw:
        raise ValueError("file paths must be non-empty")
    posix = PurePosixPath(raw)
    if posix.is_absolute():
        raise ValueError(f"absolute solution paths are not allowed: {raw_path}")
    if any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError(f"path traversal is not allowed in solution path: {raw_path}")
    return Path(*posix.parts)


def run_root(agent_id: str, task_id: str) -> Path:
    return RUNS_DIR / slug(agent_id) / slug(task_id, "task")


def run_dir(agent_id: str, task_id: str, run_id: str) -> Path:
    return run_root(agent_id, task_id) / slug(run_id, "run1")


def task_issue_path(task_id: str) -> Path:
    return TASKS_DIR / task_id / "issue.md"


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def repo_url() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=BASE,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return None
    value = proc.stdout.strip()
    return value or None


def command_string(argv: list[str]) -> str:
    def quote(part: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_./:=@+-]+", part):
            return part
        return "'" + part.replace("'", "'\"'\"'") + "'"
    return " ".join(quote(part) for part in argv)


# ==================== Task registry ====================

def discover_tasks() -> dict[str, dict[str, str]]:
    tasks: dict[str, dict[str, str]] = {}
    if not TASKS_DIR.is_dir():
        return tasks
    for entry in sorted(TASKS_DIR.iterdir()):
        issue_path = entry / "issue.md"
        if issue_path.is_file():
            issue = issue_path.read_text(encoding="utf-8")
            title = next((line.lstrip("# ").strip() for line in issue.splitlines() if line.strip()), entry.name)
            tasks[entry.name] = {
                "id": entry.name,
                "title": title,
                "issue": issue,
                "issue_path": repo_relative(issue_path),
            }
    return tasks


def require_task(task_id: str) -> dict[str, str]:
    tasks = discover_tasks()
    if task_id not in tasks:
        raise ValueError(f"Unknown task_id '{task_id}'. Available: {sorted(tasks)}")
    return tasks[task_id]


def safe_suite_name(raw: str | None) -> str:
    name = raw or "nuri-hard-v1-focused.jsonl"
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid benchmark suite name: {name}")
    if not name.endswith(".jsonl"):
        name += ".jsonl"
    return name


def load_benchmark_tasks(suite: str | None = None) -> list[dict[str, Any]]:
    suite_name = safe_suite_name(suite)
    path = BENCH_TASKS_DIR / suite_name
    if not path.is_file():
        available = sorted(p.name for p in BENCH_TASKS_DIR.glob("*.jsonl")) if BENCH_TASKS_DIR.is_dir() else []
        raise ValueError(f"Unknown benchmark suite '{suite_name}'. Available: {available}")
    tasks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def find_benchmark_task(task_id: str, suite: str | None = None) -> dict[str, Any]:
    for task in load_benchmark_tasks(suite):
        if task.get("task_id") == task_id:
            return task
    raise ValueError(f"Unknown benchmark task '{task_id}' in suite {safe_suite_name(suite)}")


def load_files_from_solution_dir(solution_dir: Path) -> dict[str, str]:
    if not solution_dir.is_dir():
        raise ValueError(f"No saved solution directory found at {repo_relative(solution_dir)}")
    files: dict[str, str] = {}
    for path in sorted(solution_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(solution_dir).as_posix()
            files[rel] = path.read_text(encoding="utf-8", errors="replace")
    if not files:
        raise ValueError(f"No saved solution files found at {repo_relative(solution_dir)}")
    return files


def write_solution_files(solution_dir: Path, files: dict[str, str]) -> None:
    if not isinstance(files, dict) or not files:
        raise ValueError("'files' must be a non-empty object of {path: content}")

    if solution_dir.exists():
        shutil.rmtree(solution_dir)
    solution_dir.mkdir(parents=True, exist_ok=True)

    for raw_path, content in files.items():
        rel = safe_solution_path(raw_path)
        dest = solution_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(str(content), encoding="utf-8")


# ==================== Rubric and assessments ====================

def rubric_llm_rules(rubric: dict) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for category_name, category in rubric["categories"].items():
        for rule in category["rules"]:
            if rule.get("check_type") == "llm":
                rules.append({
                    "rule_id": rule["id"],
                    "category": category_name,
                    "name": rule["name"],
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "score": None,
                    "explanation": "",
                })
    return rules


def normalize_assessments(value: Any, agent_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]] | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        assessments = value
    elif isinstance(value, dict):
        if agent_id and isinstance(value.get(agent_id), list):
            assessments = value[agent_id]
        elif run_id and isinstance(value.get(run_id), list):
            assessments = value[run_id]
        elif "assessments" in value and isinstance(value["assessments"], list):
            assessments = value["assessments"]
        else:
            raise ValueError("assessments must be a list or an object keyed by agent_id/run_id")
    else:
        raise ValueError("assessments must be a list or object")

    normalized = []
    for item in assessments:
        if not isinstance(item, dict):
            raise ValueError("each assessment must be an object")
        rid = str(item.get("rule_id") or "").strip()
        if not rid:
            raise ValueError("each assessment needs rule_id")
        score = float(item.get("score", 0.5))
        normalized.append({
            "rule_id": rid,
            "score": max(0.0, min(1.0, score)),
            "explanation": str(item.get("explanation") or ""),
        })
    return normalized


def judge_files(
    *,
    task: dict[str, str],
    agent_id: str,
    files: dict[str, str],
    assessments: list[dict[str, Any]] | None,
    static_only: bool,
) -> tuple[dict[str, Any], str, str]:
    rubric = load_rubric(str(RUBRIC_PATH))
    llm = LLMBackend()
    use_external = bool(assessments)
    use_static_only = static_only or use_external or not llm.available

    result = judge_solution(
        rubric=rubric,
        issue=task["issue"],
        solution_files=files,
        agent_id=agent_id,
        llm=llm if not use_static_only else None,
        static_only=use_static_only,
        external_assessments=assessments,
    )
    rdict = result_to_dict(result)
    if use_external:
        mode = "static+external-judge"
    elif use_static_only:
        mode = "static-only"
    else:
        mode = "static+llm"
    report = {
        "rubric_version": rubric.get("version", "unknown"),
        "score_model": "global-penalty-v2",
        "mode": mode,
        "issue": task["issue"][:500],
        "results": [rdict],
    }
    return report, build_mistakes_report(report, rubric), mode


# ==================== Artifact rendering ====================

def result_markdown(
    *,
    task: dict[str, str],
    agent_id: str,
    run_id: str,
    report: dict[str, Any],
    mistakes_report: str,
    solution_dir: Path,
    task_json_path: Path,
    assessments_path: Path | None,
) -> str:
    result = report["results"][0]
    lines = [
        "# Judicative Self-Test Result",
        "",
        f"- Agent: `{agent_id}`",
        f"- Task: `{task['id']}` - {task['title']}",
        f"- Run: `{run_id}`",
        f"- Generated: `{utc_now()}`",
        f"- Mode: `{report['mode']}`",
        f"- Benchmark lane: `{report.get('benchmark_lane', 'unknown')}`",
        f"- Judge: `{report.get('judge', {}).get('kind', 'unknown')}`"
        + (f" (`{report.get('judge', {}).get('id')}`)" if report.get("judge", {}).get("id") else ""),
        f"- Score model: `{report['score_model']}`",
        f"- Score: **{result['total_score']}/100**",
        f"- Verdict: **{result['verdict']}**",
        f"- Penalty: `-{result['total_penalty']}`",
        f"- Solution files: `{repo_relative(solution_dir)}/`",
        f"- Reproducible task JSON: `{repo_relative(task_json_path)}`",
    ]
    if assessments_path:
        lines.append(f"- External/self assessments: `{repo_relative(assessments_path)}`")
    if result.get("hard_gate_capped"):
        lines.append("- Hard gate: score capped and verdict forced to FAIL")
    lines.extend([
        "",
        "## Reproduce",
        "",
        "```bash",
    ])
    cmd = [
        "python3", "judge.py",
        "--task", repo_relative(task_json_path),
        "--rubric", repo_relative(RUBRIC_PATH),
        "--static-only",
    ]
    if assessments_path:
        cmd.extend(["--assessments", repo_relative(assessments_path)])
    lines.append(command_string(cmd))
    lines.extend(["```", "", mistakes_report.strip(), ""])
    return "\n".join(lines)


def write_run_summary(root: Path, agent_id: str, task_id: str) -> Path:
    rows = []
    for metadata_path in sorted(root.glob("*/metadata.json")):
        try:
            metadata = read_json(metadata_path)
            result = read_json(metadata_path.parent / "result.json")["results"][0]
        except Exception:
            continue
        rows.append((metadata.get("run_id", metadata_path.parent.name), metadata, result))

    lines = [
        "# Judicative Self-Test Summary",
        "",
        f"- Agent: `{agent_id}`",
        f"- Task: `{task_id}`",
        f"- Generated: `{utc_now()}`",
        "",
        "| Run | Lane | Mode | Judge | Score | Verdict | Penalty | Result |",
        "|---|---|---|---|---:|---|---:|---|",
    ]
    for run_id, metadata, result in rows:
        result_rel = Path(run_id) / "RESULT.md"
        judge = metadata.get("judge", {})
        judge_label = judge.get("kind", "?")
        if judge.get("id"):
            judge_label += f" ({judge['id']})"
        lines.append(
            f"| `{run_id}` | `{metadata.get('benchmark_lane', '?')}` | `{metadata.get('mode', '?')}` | "
            f"{judge_label} | {result['total_score']} | "
            f"{result['verdict']} | -{result['total_penalty']} | [{result_rel.as_posix()}]({result_rel.as_posix()}) |"
        )
    lines.append("")
    if len(rows) >= 2:
        first_meta = rows[0][1]
        last_meta = rows[-1][1]
        comparable = (
            first_meta.get("benchmark_lane") == last_meta.get("benchmark_lane")
            and first_meta.get("mode") == last_meta.get("mode")
            and first_meta.get("judge") == last_meta.get("judge")
        )
        if comparable:
            first = rows[0][2]["total_score"]
            last = rows[-1][2]["total_score"]
            lines.append(f"Comparable score delta from first to latest run: **{round(last - first, 2)}**.")
        else:
            lines.append(
                "Score delta omitted: these runs use different lanes, modes, or judges. "
                "Use same-lane cold runs for model comparisons."
            )
        lines.append("")

    path = root / "SUMMARY.md"
    write_text(path, "\n".join(lines))
    return path


def persist_run(
    *,
    task: dict[str, str],
    agent_id: str,
    run_id: str,
    files: dict[str, str],
    assessments: list[dict[str, Any]] | None,
    static_only: bool,
    benchmark_lane: str,
    judge_id: str | None = None,
) -> dict[str, Any]:
    root = run_root(agent_id, task["id"])
    current_run_dir = run_dir(agent_id, task["id"], run_id)
    solution_dir = current_run_dir / "solution"
    write_solution_files(solution_dir, files)
    write_text(root / "task.md", task["issue"])

    scoring_agent_id = f"{agent_id}-{run_id}"
    task_json_path = current_run_dir / "task.json"
    write_json(task_json_path, {
        "issue": {"title": task["title"], "body": task["issue"]},
        "solutions": [{"agent_id": scoring_agent_id, "files": files}],
    })

    assessments_path = None
    if assessments:
        assessments_path = current_run_dir / "assessments.json"
        write_json(assessments_path, {scoring_agent_id: assessments, run_id: assessments})

    report, mistakes, mode = judge_files(
        task=task,
        agent_id=scoring_agent_id,
        files=files,
        assessments=assessments,
        static_only=static_only,
    )
    if assessments:
        judge_kind = "self_assessed" if (judge_id or agent_id) == agent_id else "external_assessed"
    elif mode == "static+llm":
        judge_kind = "live_llm"
    elif mode == "static-only":
        judge_kind = "static_only"
    else:
        judge_kind = "unknown"
    report["benchmark_lane"] = benchmark_lane
    report["judge"] = {
        "id": judge_id or (agent_id if assessments else ""),
        "kind": judge_kind,
    }
    metadata = {
        "agent_id": agent_id,
        "task_id": task["id"],
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": mode,
        "benchmark_lane": benchmark_lane,
        "judge": report["judge"],
        "solution_dir": repo_relative(solution_dir),
        "task_json": repo_relative(task_json_path),
        "rubric": repo_relative(RUBRIC_PATH),
    }
    write_json(current_run_dir / "metadata.json", metadata)
    write_json(current_run_dir / "result.json", report)
    write_text(current_run_dir / "mistakes_report.md", mistakes)
    result_md = result_markdown(
        task=task,
        agent_id=agent_id,
        run_id=run_id,
        report=report,
        mistakes_report=mistakes,
        solution_dir=solution_dir,
        task_json_path=task_json_path,
        assessments_path=assessments_path,
    )
    write_text(current_run_dir / "RESULT.md", result_md)
    summary_path = write_run_summary(root, agent_id, task["id"])

    result = report["results"][0]
    return {
        "agent_id": agent_id,
        "task_id": task["id"],
        "run_id": run_id,
        "score": result["total_score"],
        "verdict": result["verdict"],
        "total_penalty": result["total_penalty"],
        "hard_gate_capped": result["hard_gate_capped"],
        "mode": mode,
        "benchmark_lane": benchmark_lane,
        "judge": report["judge"],
        "artifacts": {
            "run_dir": repo_relative(current_run_dir),
            "solution_dir": repo_relative(solution_dir),
            "task_json": repo_relative(task_json_path),
            "result_json": repo_relative(current_run_dir / "result.json"),
            "result_markdown": repo_relative(current_run_dir / "RESULT.md"),
            "mistakes_report": repo_relative(current_run_dir / "mistakes_report.md"),
            "summary_markdown": repo_relative(summary_path),
            **({"assessments": repo_relative(assessments_path)} if assessments_path else {}),
        },
        "mistakes_report_markdown": mistakes,
    }


# ==================== PR preparation ====================

def build_pr_body(agent_id: str, task_id: str, root: Path) -> str:
    summary = root / "SUMMARY.md"
    summary_text = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return "\n".join([
        f"# Judicative self-test: {agent_id} on {task_id}",
        "",
        "This PR contains a reproducible Judicative self-test run.",
        "",
        "## Artifacts",
        "",
        f"- Summary: `{repo_relative(summary)}`",
        f"- Task: `{repo_relative(root / 'task.md')}`",
        f"- Runs directory: `{repo_relative(root)}/`",
        "",
        "## Current summary",
        "",
        summary_text.strip() or "(No summary generated yet.)",
        "",
        "## Committee instructions",
        "",
        "Review the committed `RESULT.md`, `result.json`, assessments, and solution files. "
        "For blind review, prepare a panel packet from the saved `solution/` directories. "
        "Only compare runs that share the same benchmark lane, context budget, and independent judge.",
        "",
    ])


def git_status_paths() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=BASE,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    paths = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def run_git(argv: list[str]) -> dict[str, Any]:
    proc = subprocess.run(argv, cwd=BASE, text=True, capture_output=True, timeout=180)
    return {
        "cmd": command_string(argv),
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


# ==================== Tool implementations ====================

def tool_list_tasks(_args: dict[str, Any]) -> dict[str, Any]:
    tasks = discover_tasks()
    return {
        "server": SERVER_INFO,
        "repository": repo_url(),
        "install_command": f"claude mcp add judicative -- python3 {BASE / 'mcp_server.py'}",
        "tasks": [{"id": t["id"], "title": t["title"], "issue_path": t["issue_path"]} for t in tasks.values()],
        "warning": (
            "These local tasks are protocol smoke tests. They verify that an agent can use MCP and persist artifacts. "
            "They are not a fair model leaderboard. Use list_benchmark_tasks for real replay candidates."
        ),
        "recommended_flow": [
            "Call start_self_test(task_id, agent_id).",
            "For a cold run, do not call get_rubric until after run1 is submitted.",
            "Submit run1 with submit_solution(task_id, agent_id, run_id='run1', files={...}).",
            "Self-scored run2 is diagnostic only; do not compare it to another model's cold run.",
            "For real comparison, call list_benchmark_tasks and run same-lane cold tasks.",
        ],
    }


def tool_list_benchmark_tasks(args: dict[str, Any]) -> dict[str, Any]:
    suite = safe_suite_name(args.get("suite"))
    tasks = load_benchmark_tasks(suite)
    modes = args.get("evaluation_modes") or []
    if modes:
        allowed = set(modes)
        tasks = [task for task in tasks if task.get("personalization", {}).get("evaluation_mode") in allowed]
    return {
        "suite": suite,
        "count": len(tasks),
        "warning": (
            "Benchmark tasks are real PR replay candidates. Compare models only on the same task set, "
            "same context, same tool budget, same number of attempts, and same independent scorer."
        ),
        "tasks": [
            {
                "task_id": task["task_id"],
                "repo": task["repo"],
                "source": task["source"],
                "replay": task["replay"],
                "personalization": task["personalization"],
                "stats": task["stats"],
            }
            for task in tasks
        ],
    }


def tool_start_benchmark_task(args: dict[str, Any]) -> dict[str, Any]:
    task = find_benchmark_task(args.get("task_id", ""), args.get("suite"))
    return {
        "suite": safe_suite_name(args.get("suite")),
        "benchmark_lane": "cold_fixed_replay",
        "task_id": task["task_id"],
        "repo": task["repo"],
        "source": task["source"],
        "replay": task["replay"],
        "prompt_context": task["prompt_context"],
        "oracle_summary": {
            "changed_test_files": task.get("oracle", {}).get("changed_test_files", []),
            "review_signal": task.get("oracle", {}).get("review_signal", {}),
        },
        "protocol": [
            "This is a real replay benchmark task, not the toy protocol smoke test.",
            "Use replay.replay_base_sha as the starting point.",
            "Do not read the real fix patch or oracle.changed_files before producing the patch.",
            "Do not call get_assessment_template for the cold run.",
            "Return a git patch plus exact test commands/results. Self-scores are not accepted as leaderboard scores.",
        ],
        "expected_artifacts": {
            "patch": "unified git diff against replay_base_sha",
            "test_log": "raw command output for every command you ran",
            "notes": "short explanation of behavior and known residual risk",
        },
    }


def tool_start_self_test(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    agent_id = args.get("agent_id") or "anonymous"
    root = run_root(agent_id, task["id"])
    root.mkdir(parents=True, exist_ok=True)
    write_text(root / "task.md", task["issue"])
    return {
        "task_id": task["id"],
        "title": task["title"],
        "issue": task["issue"],
        "run_root": repo_relative(root),
        "protocol": {
            "cold_run": [
                "Read only this task before writing run1.",
                "Do not read rubric_v2.json, existing runs, test_fixtures, or RESULTS.md before run1 if you want an honest baseline.",
                "Submit your complete solution files with submit_solution using run_id='run1'.",
            ],
            "self_judged_run": [
                "After run1 is saved, call get_assessment_template.",
                "Read the rubric rules and score every LLM-only rule from 0.0 to 1.0 with concrete line-based explanations.",
                "Call score_saved_run with those assessments to produce the judged run1 report.",
            ],
            "improvement_run": [
                "Use the mistakes report to write generalized instructions.",
                "Submit run2 with the improved solution.",
                "Call prepare_results_pr so the committee can review a reproducible markdown artifact.",
            ],
        },
        "submission_schema": {
            "task_id": task["id"],
            "agent_id": agent_id,
            "run_id": "run1",
            "files": {"relative/path.ext": "full file content"},
        },
    }


def tool_get_task(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    return {
        "id": task["id"],
        "title": task["title"],
        "issue": task["issue"],
        "submission_format": {
            "task_id": task["id"],
            "agent_id": "<your model/agent name>",
            "run_id": "run1",
            "files": {"<relative/path.ts>": "<full file content>"},
        },
    }


def tool_submit_solution(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    agent_id = args.get("agent_id", "anonymous")
    run_id = args.get("run_id", "run1")
    assessments = normalize_assessments(args.get("assessments"), agent_id=agent_id, run_id=run_id)
    benchmark_lane = args.get("benchmark_lane") or ("diagnostic_self_assessed_retry" if assessments else "protocol_smoke")
    return persist_run(
        task=task,
        agent_id=agent_id,
        run_id=run_id,
        files=args.get("files", {}),
        assessments=assessments,
        static_only=bool(args.get("static_only", False)),
        benchmark_lane=benchmark_lane,
        judge_id=args.get("judge_id"),
    )


def tool_get_assessment_template(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    rubric = load_rubric(str(RUBRIC_PATH))
    return {
        "task_id": task["id"],
        "rubric_version": rubric.get("version"),
        "instructions": (
            "Score every listed LLM-only rule from 0.0 to 1.0. "
            "1.0 means no issue; 0.0 means clear severe violation. "
            "Cite concrete lines or say 'n/a' only when the rule has no applicable surface. "
            "Self-assessment is diagnostic and must not be used as a leaderboard score."
        ),
        "format": [{"rule_id": "RACE-005", "score": 0.4, "explanation": "line 12: ..."}],
        "assessments": rubric_llm_rules(rubric),
    }


def tool_score_saved_run(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    agent_id = args.get("agent_id", "anonymous")
    run_id = args.get("run_id", "run1")
    current_run_dir = run_dir(agent_id, task["id"], run_id)
    files = load_files_from_solution_dir(current_run_dir / "solution")
    assessments = normalize_assessments(args.get("assessments"), agent_id=agent_id, run_id=run_id)
    benchmark_lane = args.get("benchmark_lane") or ("diagnostic_self_assessed_retry" if assessments else "protocol_smoke")
    return persist_run(
        task=task,
        agent_id=agent_id,
        run_id=run_id,
        files=files,
        assessments=assessments,
        static_only=bool(args.get("static_only", False)),
        benchmark_lane=benchmark_lane,
        judge_id=args.get("judge_id"),
    )


def tool_prepare_results_pr(args: dict[str, Any]) -> dict[str, Any]:
    task = require_task(args.get("task_id", ""))
    agent_id = args.get("agent_id", "anonymous")
    root = run_root(agent_id, task["id"])
    if not root.is_dir():
        raise ValueError(f"No run artifacts found at runs/{slug(agent_id)}/{slug(task['id'])}")
    write_run_summary(root, agent_id, task["id"])
    body = build_pr_body(agent_id, task["id"], root)
    body_path = root / "PR_BODY.md"
    write_text(body_path, body)

    branch = args.get("branch") or f"judicative/{slug(agent_id)}/{slug(task['id'])}"
    title = args.get("title") or f"Add Judicative self-test results for {agent_id}"
    root_rel = repo_relative(root)
    commands = [
        ["git", "switch", "-c", branch],
        ["git", "add", root_rel],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--draft", "--title", title, "--body-file", repo_relative(body_path)],
    ]
    response: dict[str, Any] = {
        "task_id": task["id"],
        "agent_id": agent_id,
        "branch": branch,
        "pr_body": repo_relative(body_path),
        "commands": [command_string(cmd) for cmd in commands],
        "execute": bool(args.get("execute", False)),
    }
    if not args.get("execute", False):
        response["note"] = "Set execute=true to run these git/gh commands in this checkout."
        return response

    dirty = git_status_paths()
    outside = [path for path in dirty if not (path == root_rel or path.startswith(root_rel + "/"))]
    if outside:
        raise ValueError(
            "Refusing to create PR while unrelated local changes exist: "
            + ", ".join(outside[:12])
            + (" ..." if len(outside) > 12 else "")
        )

    results = []
    for cmd in commands:
        if cmd[:3] == ["git", "switch", "-c"]:
            existing = subprocess.run(["git", "rev-parse", "--verify", branch], cwd=BASE, capture_output=True)
            cmd = ["git", "switch", branch] if existing.returncode == 0 else cmd
        result = run_git(cmd)
        results.append(result)
        if result["returncode"] != 0:
            response["command_results"] = results
            raise RuntimeError(f"Command failed: {result['cmd']}\n{result['stderr']}")
    response["command_results"] = results
    return response


def tool_get_rubric(_args: dict[str, Any]) -> dict[str, Any]:
    rubric = load_rubric(str(RUBRIC_PATH))
    return {
        "version": rubric.get("version"),
        "scoring": rubric.get("scoring"),
        "categories": {
            name: {
                "weight": cat["weight"],
                "hard_gate": cat.get("hard_gate", False),
                "description": cat.get("description", ""),
                "rules": [
                    {
                        "id": rule["id"],
                        "name": rule["name"],
                        "severity": rule["severity"],
                        "check_type": rule["check_type"],
                        "description": rule["description"],
                    }
                    for rule in cat["rules"]
                ],
            }
            for name, cat in rubric["categories"].items()
        },
    }


TOOLS = {
    "list_tasks": {
        "fn": tool_list_tasks,
        "description": "List available Judicative self-test tasks and the recommended MCP flow.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "start_self_test": {
        "fn": tool_start_self_test,
        "description": "Start a self-test session and get the task, protocol, and run artifact paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id from list_tasks"},
                "agent_id": {"type": "string", "description": "Your model/agent name"},
            },
            "required": ["task_id", "agent_id"],
        },
    },
    "list_benchmark_tasks": {
        "fn": tool_list_benchmark_tasks,
        "description": "List real GitHub PR replay benchmark tasks mined from nuri-com history.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "description": "JSONL suite name under bench/tasks"},
                "evaluation_modes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter: test_backed, review_backed, weak_oracle",
                },
            },
            "required": [],
        },
    },
    "start_benchmark_task": {
        "fn": tool_start_benchmark_task,
        "description": "Start a real replay benchmark task with fixed cold-run protocol and replay metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "description": "JSONL suite name under bench/tasks"},
                "task_id": {"type": "string", "description": "task_id from list_benchmark_tasks"},
            },
            "required": ["task_id"],
        },
    },
    "get_task": {
        "fn": tool_get_task,
        "description": "Fetch a coding task by id. start_self_test is preferred for full runs.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task id from list_tasks"}},
            "required": ["task_id"],
        },
    },
    "submit_solution": {
        "fn": tool_submit_solution,
        "description": (
            "Submit solution files for judging and persist a reproducible run under runs/<agent>/<task>/<run>. "
            "Optionally include assessments to score LLM-only rules."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "agent_id": {"type": "string", "description": "Your model/agent name"},
                "run_id": {"type": "string", "description": "run1, run2, etc."},
                "files": {
                    "type": "object",
                    "description": "Map of relative file path to full file content",
                    "additionalProperties": {"type": "string"},
                },
                "assessments": {
                    "type": ["array", "object"],
                    "description": "Optional LLM-rule scores as [{rule_id, score, explanation}]",
                },
                "static_only": {"type": "boolean", "description": "Force static-only scoring"},
                "benchmark_lane": {"type": "string", "description": "protocol_smoke, cold_fixed, diagnostic_self_assessed_retry, etc."},
                "judge_id": {"type": "string", "description": "Independent judge id when assessments are supplied"},
            },
            "required": ["task_id", "agent_id", "files"],
        },
    },
    "get_assessment_template": {
        "fn": tool_get_assessment_template,
        "description": "Return every LLM-only rubric rule the agent must self-score after a cold run.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    "score_saved_run": {
        "fn": tool_score_saved_run,
        "description": "Re-score an already saved run, usually with self/external LLM-rule assessments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "run_id": {"type": "string"},
                "assessments": {"type": ["array", "object"]},
                "static_only": {"type": "boolean"},
                "benchmark_lane": {"type": "string"},
                "judge_id": {"type": "string"},
            },
            "required": ["task_id", "agent_id", "run_id"],
        },
    },
    "prepare_results_pr": {
        "fn": tool_prepare_results_pr,
        "description": "Create PR body/commands for publishing saved self-test artifacts. Can execute git/gh when requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "branch": {"type": "string"},
                "title": {"type": "string"},
                "execute": {"type": "boolean", "description": "Default false. If true, run git commit/push/gh pr create."},
            },
            "required": ["task_id", "agent_id"],
        },
    },
    "get_rubric": {
        "fn": tool_get_rubric,
        "description": "Return the rubric categories, rules, and scoring model.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
}


# ==================== MCP stdio transport ====================

def handle_request(req: dict[str, Any]) -> dict[str, Any]:
    method = req.get("method", "")
    params = req.get("params", {}) or {}

    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {
            "tools": [
                {"name": name, "description": tool["description"], "inputSchema": tool["inputSchema"]}
                for name, tool in TOOLS.items()
            ]
        }
    if method == "tools/call":
        name = params.get("name", "")
        if name not in TOOLS:
            raise ValueError(f"Unknown tool: {name}")
        try:
            result = TOOLS[name]["fn"](params.get("arguments", {}) or {})
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}
    raise ValueError(f"Unknown method: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in req:
            continue
        resp: dict[str, Any] = {"jsonrpc": "2.0", "id": req["id"]}
        try:
            resp["result"] = handle_request(req)
        except Exception as exc:
            resp["error"] = {"code": -32601, "message": str(exc)}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
