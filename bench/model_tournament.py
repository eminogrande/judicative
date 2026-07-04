#!/usr/bin/env python3
"""Run an end-to-end Judicative tournament against Ollama Cloud models.

Default target is Ollama Cloud:

  OLLAMA_API_KEY=... python3 bench/model_tournament.py \
    --models glm-5.2 kimi-k2.7-code minimax-m3 deepseek-v4-pro qwen3-coder:480b

Artifacts are written under runs/tournaments/<tournament-id>/ and mirrored into
the normal MCP run layout via mcp_server.persist_run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mcp_server as mcp  # noqa: E402


DEFAULT_BASE_URL = "https://ollama.com"
DEFAULT_MODELS = [
    "glm-5.2",
    "kimi-k2.7-code",
    "minimax-m3",
    "deepseek-v4-pro",
    "qwen3-coder:480b",
]

METRIC_FIELDS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._") or "model"


def is_cloud_model(model: str, available_models: set[str] | None = None) -> bool:
    return (
        model.endswith(":cloud")
        or model.endswith("-cloud")
        or (available_models is not None and model in available_models)
    )


def validate_cloud_models(models: list[str], available_models: set[str] | None = None) -> None:
    local = [model for model in models if not is_cloud_model(model, available_models)]
    if local:
        raise ValueError(
            "Refusing non-cloud model names: "
            + ", ".join(local)
            + ". Use direct Ollama Cloud catalog names from https://ollama.com/api/tags."
        )


def validate_ollama_cloud_base_url(base_url: str) -> None:
    parsed = urllib.parse.urlparse(base_url.rstrip("/"))
    if parsed.scheme != "https" or parsed.netloc != "ollama.com" or parsed.path not in ("", "/"):
        raise ValueError(
            "Refusing non-cloud Ollama base URL: "
            + base_url
            + ". Use https://ollama.com."
        )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json(text: str) -> Any:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start_obj = stripped.find("{")
        end_obj = stripped.rfind("}")
        if start_obj >= 0 and end_obj > start_obj:
            return json.loads(stripped[start_obj:end_obj + 1])
        start_arr = stripped.find("[")
        end_arr = stripped.rfind("]")
        if start_arr >= 0 and end_arr > start_arr:
            return json.loads(stripped[start_arr:end_arr + 1])
        raise


def ns_to_seconds(value: Any) -> float | None:
    try:
        ns = float(value)
    except (TypeError, ValueError):
        return None
    if ns <= 0:
        return None
    return round(ns / 1_000_000_000, 3)


def tokens_per_second(count: Any, duration_ns: Any) -> float | None:
    try:
        tokens = float(count)
        seconds = float(duration_ns) / 1_000_000_000
    except (TypeError, ValueError):
        return None
    if tokens <= 0 or seconds <= 0:
        return None
    return round(tokens / seconds, 2)


def parse_think_level(value: str) -> str | bool:
    normalized = value.strip().lower()
    if normalized == "false":
        return False
    if normalized == "true":
        return True
    return normalized


class ModelClient:
    def __init__(self, *, api_key: str, base_url: str, temperature: float, max_tokens: int):
        validate_ollama_cloud_base_url(base_url)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def list_models(self) -> set[str]:
        req = urllib.request.Request(
            f"{self.base_url}/api/tags",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return {str(item.get("name") or item.get("model")) for item in data.get("models", [])}

    def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        think: Any,
        available_models: set[str],
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        validate_cloud_models([model], available_models)
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": think,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.max_tokens,
            },
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        message = data.get("message") or {}
        content = message.get("content") or ""
        metrics = {field: data.get(field) for field in METRIC_FIELDS}
        metrics.update({
            "done": data.get("done"),
            "done_reason": data.get("done_reason"),
            "model_returned": data.get("model"),
            "content_chars": len(content),
            "thinking_chars": len(message.get("thinking") or ""),
            "output_tokens_per_second": tokens_per_second(data.get("eval_count"), data.get("eval_duration")),
            "prompt_tokens_per_second": tokens_per_second(data.get("prompt_eval_count"), data.get("prompt_eval_duration")),
            "total_seconds": ns_to_seconds(data.get("total_duration")),
            "eval_seconds": ns_to_seconds(data.get("eval_duration")),
            "prompt_eval_seconds": ns_to_seconds(data.get("prompt_eval_duration")),
        })
        return {"content": content, "metrics": metrics, "response": data}


def solution_prompt(task: dict[str, str]) -> str:
    return f"""You are taking a cold coding self-test.

Important protocol:
- Use ONLY the task text below.
- Do not assume hidden tests or hidden rubrics.
- Return ONLY valid JSON.
- Do not include markdown fences.

Task:
{task['issue']}

Return this exact JSON shape:
{{
  "files": {{
    "lib/secureKeyStorage.ts": "<complete TypeScript implementation>"
  }},
  "notes": "<short implementation notes>"
}}
"""


def improve_prompt(task: dict[str, str], run1_files: dict[str, str], mistakes_report: str) -> str:
    files_text = "\n\n".join(f"--- {path} ---\n{content}" for path, content in sorted(run1_files.items()))
    return f"""You are doing run2 of the same coding self-test.

You may use the run1 solution and the judge's mistakes report below. Produce a better complete solution.
Return ONLY valid JSON, no markdown fences.

Task:
{task['issue']}

Run1 solution:
{files_text[:14000]}

Judge mistakes report:
{mistakes_report[:16000]}

Return this exact JSON shape:
{{
  "files": {{
    "lib/secureKeyStorage.ts": "<complete improved TypeScript implementation>"
  }},
  "notes": "<short explanation of what changed>"
}}
"""


def normalize_solution(data: Any) -> dict[str, str]:
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError("model response missing files object")
    files = {str(path): str(content) for path, content in data["files"].items() if str(content).strip()}
    if not files:
        raise ValueError("model produced no files")
    return files


def assessment_prompt(task: dict[str, str], files: dict[str, str], template: list[dict[str, Any]]) -> str:
    files_text = "\n\n".join(f"--- {path} ---\n{content}" for path, content in sorted(files.items()))
    rules = [
        {
            "rule_id": item["rule_id"],
            "category": item["category"],
            "severity": item["severity"],
            "name": item["name"],
            "description": item["description"],
        }
        for item in template
    ]
    return f"""You are self-assessing your own coding-test solution.

Be strict. Score every rule from 0.0 to 1.0:
- 1.0 = no issue
- 0.5 = partial/minor concern
- 0.0 = clear serious violation

Return ONLY a JSON array. Each item must be:
{{"rule_id": "...", "score": 0.0, "explanation": "specific line-based explanation or n/a"}}

Task:
{task['issue']}

Solution:
{files_text[:16000]}

Rules:
{json.dumps(rules, indent=2)}
"""


def normalize_assessments(data: Any, template: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("assessments"), list):
        data = data["assessments"]
    if not isinstance(data, list):
        raise ValueError("assessment response must be a JSON array")
    by_rule = {str(item.get("rule_id")): item for item in data if isinstance(item, dict)}
    normalized = []
    for rule in template:
        rid = rule["rule_id"]
        item = by_rule.get(rid, {})
        try:
            score = float(item.get("score", 0.5))
        except Exception:
            score = 0.5
        normalized.append({
            "rule_id": rid,
            "score": max(0.0, min(1.0, score)),
            "explanation": str(item.get("explanation") or "missing assessment"),
        })
    return normalized


def ask_json(
    client: ModelClient,
    *,
    model: str,
    system: str,
    user: str,
    think: str | bool,
    available_models: set[str],
    out_raw: Path,
    out_metrics: Path,
    retries: int = 1,
) -> tuple[Any, list[dict[str, Any]]]:
    last_text = ""
    current_user = user
    call_records: list[dict[str, Any]] = []
    for attempt in range(retries + 1):
        call = client.chat(
            model=model,
            system=system,
            user=current_user,
            think=parse_think_level(str(think)),
            available_models=available_models,
        )
        text = call["content"]
        last_text = text
        out_raw.parent.mkdir(parents=True, exist_ok=True)
        out_raw.write_text(text, encoding="utf-8")
        attempt_raw = out_raw.with_name(f"{out_raw.stem}.attempt-{attempt + 1}{out_raw.suffix}")
        attempt_raw.write_text(text, encoding="utf-8")
        response_path = out_metrics.with_name(f"{out_metrics.stem}.attempt-{attempt + 1}.response.json")
        write_json(response_path, call["response"])
        record = {
            "attempt": attempt + 1,
            "parse_ok": False,
            "raw": str(attempt_raw.relative_to(ROOT)),
            "response": str(response_path.relative_to(ROOT)),
            "metrics": call["metrics"],
        }
        call_records.append(record)
        try:
            parsed = extract_json(text)
            record["parse_ok"] = True
            write_json(out_metrics, call_records)
            return parsed, call_records
        except Exception as exc:
            record["parse_error"] = str(exc)
            write_json(out_metrics, call_records)
            if attempt >= retries:
                raise
            current_user = (
                "Your previous answer was not valid JSON matching the requested shape. "
                "Return ONLY valid JSON for the original request below. Do not ask for clarification.\n\n"
                f"Parse/schema error: {exc}\n\n"
                f"Original request:\n{user[:20000]}\n\n"
                f"Previous answer:\n{last_text[:4000]}"
            )
    raise RuntimeError("unreachable")


def run_contestant(
    *,
    client: ModelClient,
    task: dict[str, str],
    template: list[dict[str, Any]],
    model: str,
    think: str,
    assessment_think: str,
    repeat_index: int,
    available_models: set[str],
    tournament_dir: Path,
    sleep_seconds: float,
    skip_run2: bool,
) -> dict[str, Any]:
    model_slug = safe_name(f"{model}__think-{think}__r{repeat_index}")
    agent_id = f"tournament-{tournament_dir.name}-{model_slug}"
    model_dir = tournament_dir / "contestants" / model_slug
    model_dir.mkdir(parents=True, exist_ok=True)
    call_metrics: dict[str, list[dict[str, Any]]] = {}
    system = "You are a senior TypeScript wallet engineer. Return only valid JSON."
    run1_prompt = solution_prompt(task)
    write_text(model_dir / "run1.prompt.txt", run1_prompt)

    run1_data, call_metrics["run1_solution"] = ask_json(
        client,
        model=model,
        system=system,
        user=run1_prompt,
        think=think,
        available_models=available_models,
        out_raw=model_dir / "run1.raw.txt",
        out_metrics=model_dir / "run1.metrics.json",
        retries=1,
    )
    run1_files = normalize_solution(run1_data)
    write_json(model_dir / "run1.solution.json", run1_data)
    time.sleep(sleep_seconds)

    run1_assessment_prompt = assessment_prompt(task, run1_files, template)
    write_text(model_dir / "run1.assessments.prompt.txt", run1_assessment_prompt)
    run1_assessment_data, call_metrics["run1_assessment"] = ask_json(
        client,
        model=model,
        system="You are a strict code reviewer. Return only valid JSON.",
        user=run1_assessment_prompt,
        think=assessment_think,
        available_models=available_models,
        out_raw=model_dir / "run1.assessments.raw.txt",
        out_metrics=model_dir / "run1.assessments.metrics.json",
        retries=1,
    )
    run1_assessments = normalize_assessments(run1_assessment_data, template)
    write_json(model_dir / "run1.assessments.json", run1_assessments)
    run1_result = mcp.persist_run(
        task=task,
        agent_id=agent_id,
        run_id="run1",
        files=run1_files,
        assessments=run1_assessments,
        static_only=True,
        benchmark_lane="protocol_smoke",
    )
    write_json(model_dir / "run1.result.json", run1_result)
    time.sleep(sleep_seconds)

    if skip_run2:
        return {
            "model": model,
            "think": think,
            "assessment_think": assessment_think,
            "repeat": repeat_index,
            "agent_id": agent_id,
            "model_slug": model_slug,
            "call_metrics": call_metrics,
            "run1": run1_result,
            "run2": None,
        }

    mistakes = (ROOT / run1_result["artifacts"]["mistakes_report"]).read_text(encoding="utf-8")
    write_text(model_dir / "run1.mistakes_report.md", mistakes)
    run2_prompt = improve_prompt(task, run1_files, mistakes)
    write_text(model_dir / "run2.prompt.txt", run2_prompt)
    run2_data, call_metrics["run2_solution"] = ask_json(
        client,
        model=model,
        system=system,
        user=run2_prompt,
        think=think,
        available_models=available_models,
        out_raw=model_dir / "run2.raw.txt",
        out_metrics=model_dir / "run2.metrics.json",
        retries=1,
    )
    run2_files = normalize_solution(run2_data)
    write_json(model_dir / "run2.solution.json", run2_data)
    time.sleep(sleep_seconds)

    run2_assessment_prompt = assessment_prompt(task, run2_files, template)
    write_text(model_dir / "run2.assessments.prompt.txt", run2_assessment_prompt)
    run2_assessment_data, call_metrics["run2_assessment"] = ask_json(
        client,
        model=model,
        system="You are a strict code reviewer. Return only valid JSON.",
        user=run2_assessment_prompt,
        think=assessment_think,
        available_models=available_models,
        out_raw=model_dir / "run2.assessments.raw.txt",
        out_metrics=model_dir / "run2.assessments.metrics.json",
        retries=1,
    )
    run2_assessments = normalize_assessments(run2_assessment_data, template)
    write_json(model_dir / "run2.assessments.json", run2_assessments)
    run2_result = mcp.persist_run(
        task=task,
        agent_id=agent_id,
        run_id="run2",
        files=run2_files,
        assessments=run2_assessments,
        static_only=True,
        benchmark_lane="diagnostic_self_assessed_retry",
    )
    write_json(model_dir / "run2.result.json", run2_result)

    return {
        "model": model,
        "think": think,
        "assessment_think": assessment_think,
        "repeat": repeat_index,
        "agent_id": agent_id,
        "model_slug": model_slug,
        "call_metrics": call_metrics,
        "run1": run1_result,
        "run2": run2_result,
    }


def command(argv: list[str]) -> None:
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv)} failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def aggregate_call_metrics(call_metrics: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for phase, attempts in call_metrics.items():
        for attempt in attempts:
            metrics = attempt.get("metrics") or {}
            rows.append({"phase": phase, "parse_ok": attempt.get("parse_ok"), **metrics})

    def sum_metric(name: str) -> float:
        return sum(float(row.get(name) or 0) for row in rows)

    total_eval = sum_metric("eval_count")
    total_prompt = sum_metric("prompt_eval_count")
    total_eval_duration = sum_metric("eval_duration")
    total_duration = sum_metric("total_duration")
    return {
        "calls": len(rows),
        "parse_retries": sum(1 for row in rows if not row.get("parse_ok", True)),
        "prompt_tokens": int(total_prompt),
        "output_tokens": int(total_eval),
        "total_tokens": int(total_prompt + total_eval),
        "total_seconds": ns_to_seconds(total_duration),
        "output_tokens_per_second": tokens_per_second(total_eval, total_eval_duration),
    }


def run_panel(
    *,
    client: ModelClient,
    task_id: str,
    tournament_dir: Path,
    contestants: list[dict[str, Any]],
    run_id: str,
    judge_models: list[str],
    judge_think: str,
    available_models: set[str],
    sleep_seconds: float,
) -> dict[str, Any]:
    panel_dir = tournament_dir / f"panel_{run_id}"
    mapping = panel_dir / "mapping.SEALED.json"
    solutions = [
        str(ROOT / item[run_id]["artifacts"]["solution_dir"])
        for item in contestants
    ]
    solutions.append(str(ROOT / "test_fixtures" / "solution_bad"))
    command([
        "python3", "panel.py", "prepare",
        "--issue", f"tasks/{task_id}/issue.md",
        "--solutions", *solutions,
        "--rubric", "rubric_v2.json",
        "--out", str(panel_dir.relative_to(ROOT)),
        "--mapping-out", str(mapping.relative_to(ROOT)),
    ])

    packet = (panel_dir / "packet.md").read_text(encoding="utf-8")
    judge_dir = panel_dir / "judges"
    judge_dir.mkdir(parents=True, exist_ok=True)
    judge_paths = []
    labels = sorted(set(re.findall(r"^###\s+(SUBMISSION-[A-Z]+)\s*$", packet, re.MULTILINE)))
    for model in judge_models:
        model_slug = safe_name(model)
        raw_path = judge_dir / f"{model_slug}.raw.txt"
        write_text(judge_dir / f"{model_slug}.prompt.txt", packet)
        data, metrics = ask_json(
            client,
            model=model,
            system="You are a strict blind code-review panel judge. Return only valid JSON.",
            user=packet,
            think=judge_think,
            available_models=available_models,
            out_raw=raw_path,
            out_metrics=judge_dir / f"{model_slug}.metrics.json",
            retries=1,
        )
        data.setdefault("judge_id", model)
        reviews = data.get("reviews", {})
        missing = [label for label in labels if label not in reviews]
        if missing:
            raise ValueError(f"{model} panel response missing labels: {missing}")
        if set(data.get("ranking", [])) != set(labels):
            raise ValueError(f"{model} panel ranking does not match labels")
        out_path = judge_dir / f"{model_slug}.json"
        write_json(out_path, data)
        write_json(judge_dir / f"{model_slug}.call_metrics.json", metrics)
        judge_paths.append(out_path)
        time.sleep(sleep_seconds)

    report_path = panel_dir / "PANEL_REPORT.md"
    json_path = panel_dir / "panel_aggregate.json"
    command([
        "python3", "panel.py", "aggregate",
        "--dir", str(panel_dir.relative_to(ROOT)),
        "--mapping", str(mapping.relative_to(ROOT)),
        "--judges", *[str(path.relative_to(ROOT)) for path in judge_paths],
        "--rubric", "rubric_v2.json",
        "--report", str(report_path.relative_to(ROOT)),
        "--json-out", str(json_path.relative_to(ROOT)),
    ])
    return {
        "panel_dir": str(panel_dir.relative_to(ROOT)),
        "report": str(report_path.relative_to(ROOT)),
        "json": str(json_path.relative_to(ROOT)),
    }


def render_summary(tournament_dir: Path, contestants: list[dict[str, Any]], panels: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Judicative Model Tournament",
        "",
        f"- Tournament: `{tournament_dir.name}`",
        "- Task: `task-001-secure-key-storage`",
        "",
        "## Self-Assessed Scores",
        "",
        "| Model | Think | Assess | Rep | Run1 | Verdict | Run2 | Verdict | Delta | Tokens | Seconds | Tok/s |",
        "|---|---|---|---:|---:|---|---:|---|---:|---:|---:|---:|",
    ]
    for item in sorted(contestants, key=lambda it: it["run1"]["score"], reverse=True):
        r1 = item["run1"]
        r2 = item.get("run2") or {}
        metrics = aggregate_call_metrics(item.get("call_metrics", {}))
        r2_score = r2.get("score", "")
        delta = "" if "score" not in r2 else round(r2["score"] - r1["score"], 2)
        lines.append(
            f"| `{item['model']}` | `{item.get('think', '?')}` | "
            f"`{item.get('assessment_think', '?')}` | {item.get('repeat', '?')} | "
            f"{r1['score']} | {r1['verdict']} | {r2_score} | {r2.get('verdict', '')} | "
            f"{delta} | {metrics['total_tokens']} | "
            f"{metrics['total_seconds']} | {metrics['output_tokens_per_second']} |"
        )

    failures_path = tournament_dir / "failures.json"
    if failures_path.is_file():
        failures = read_json(failures_path)
        if failures:
            lines.extend([
                "",
                "## Failures",
                "",
                "| Model | Think | Rep | Error |",
                "|---|---|---:|---|",
            ])
            for failure in failures:
                error = str(failure.get("error", "")).replace("\n", " ")[:180]
                lines.append(
                    f"| `{failure.get('model')}` | `{failure.get('think')}` | "
                    f"{failure.get('repeat')} | {error} |"
                )

    for run_id, panel in panels.items():
        data = read_json(ROOT / panel["json"])
        lines.extend([
            "",
            f"## Blind Panel {run_id}",
            "",
            f"- Report: `{panel['report']}`",
            f"- Ranking agreement: `{data.get('ranking_agreement')}`",
            "",
            "| Author | Rubric+Panel | Holistic median | PASS votes |",
            "|---|---:|---:|---:|",
        ])
        for row in data["rows"]:
            lines.append(
                f"| `{row['author']}` | {row['rubric_panel_score']} | "
                f"{row['holistic_median']} | {row['panel_pass_votes']}/{row['panel_votes']} |"
            )

    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Judicative model tournament.")
    parser.add_argument("--task-id", default="task-001-secure-key-storage")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--judge-models", nargs="+", default=None)
    parser.add_argument("--tournament-id", default=time.strftime("ollama-%Y%m%d-%H%M%S"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--think-levels", nargs="+", default=["max"])
    parser.add_argument("--assessment-think", default=None)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--judge-think", default="max")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--skip-panel", action="store_true")
    parser.add_argument("--skip-run2", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        print("OLLAMA_API_KEY is required", file=sys.stderr)
        return 2
    judge_models = args.judge_models or args.models
    validate_ollama_cloud_base_url(args.base_url)

    task = mcp.require_task(args.task_id)
    template = mcp.tool_get_assessment_template({"task_id": args.task_id})["assessments"]
    client = ModelClient(
        api_key=api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    available_models = client.list_models()
    tournament_dir = ROOT / "runs" / "tournaments" / safe_name(args.tournament_id)
    tournament_dir.mkdir(parents=True, exist_ok=True)
    validate_cloud_models([*args.models, *judge_models], available_models)
    write_json(tournament_dir / "config.json", {
        "task_id": args.task_id,
        "models": args.models,
        "judge_models": judge_models,
        "base_url": args.base_url,
        "cloud_only": True,
        "think_levels": args.think_levels,
        "assessment_think": args.assessment_think,
        "repeats": args.repeats,
        "judge_think": args.judge_think,
        "skip_run2": args.skip_run2,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    })
    write_json(tournament_dir / "available_models.json", sorted(available_models))

    contestants = []
    failures = []
    for repeat_index in range(1, args.repeats + 1):
        for think in args.think_levels:
            for model in args.models:
                print(f"contestant {model} think={think} repeat={repeat_index}...", file=sys.stderr)
                try:
                    assessment_think = args.assessment_think or think
                    contestants.append(
                        run_contestant(
                            client=client,
                            task=task,
                            template=template,
                            model=model,
                            think=think,
                            assessment_think=assessment_think,
                            repeat_index=repeat_index,
                            available_models=available_models,
                            tournament_dir=tournament_dir,
                            sleep_seconds=args.sleep,
                            skip_run2=args.skip_run2,
                        )
                    )
                    write_json(tournament_dir / "contestants.json", contestants)
                except Exception as exc:
                    print(f"FAILED contestant {model} think={think} repeat={repeat_index}: {exc}", file=sys.stderr)
                    failures.append({
                        "model": model,
                        "think": think,
                        "repeat": repeat_index,
                        "error": str(exc),
                    })
                    write_json(tournament_dir / "failures.json", failures)
                    write_json(tournament_dir / "contestants.partial.json", contestants)
                    if args.fail_fast:
                        return 1

    panels = {}
    if not args.skip_panel and args.skip_run2:
        print("Skipping panel because --skip-run2 was used.", file=sys.stderr)
    if not args.skip_panel and not args.skip_run2:
        for run_id in ("run1", "run2"):
            print(f"panel {run_id}...", file=sys.stderr)
            try:
                panels[run_id] = run_panel(
                    client=client,
                    task_id=args.task_id,
                    tournament_dir=tournament_dir,
                    contestants=contestants,
                    run_id=run_id,
                    judge_models=judge_models,
                    judge_think=args.judge_think,
                    available_models=available_models,
                    sleep_seconds=args.sleep,
                )
                write_json(tournament_dir / "panels.json", panels)
            except Exception as exc:
                print(f"FAILED panel {run_id}: {exc}", file=sys.stderr)
                write_json(tournament_dir / "panels.partial.json", panels)
                return 1

    summary = render_summary(tournament_dir, contestants, panels)
    (tournament_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"summary={tournament_dir.relative_to(ROOT) / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
