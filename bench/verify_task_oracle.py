#!/usr/bin/env python3
"""Verify that a mined replay task can replay its real PR patch.

This does not grade a model. It validates the benchmark task itself:
can we check out the pre-fix commit and apply the historical PR diff?
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def load_task(task_file: Path, task_id: str) -> dict[str, Any]:
    with task_file.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            task = json.loads(line)
            if task.get("task_id") == task_id:
                return task
    raise SystemExit(f"task_id not found in {task_file}: {task_id}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Oracle Replay Verification",
        "",
        f"- Task: `{result['task_id']}`",
        f"- Repository: `{result['org']}/{result['repo']}`",
        f"- PR: `{result['source_url']}`",
        f"- Replay base: `{result['replay_base_sha']}`",
        f"- Workdir: `{result['workdir']}`",
        f"- Apply check: **{'PASS' if result['apply_check_passed'] else 'FAIL'}**",
        f"- Apply: **{'PASS' if result['apply_passed'] else 'FAIL'}**",
        f"- Expected changed files: `{len(result['expected_changed_files'])}`",
        f"- Actual changed files after apply: `{len(result['actual_changed_files'])}`",
        f"- Missing expected files: `{len(result['missing_expected_files'])}`",
        "",
    ]
    if result["changed_test_files"]:
        lines.append("## Changed Test Files")
        lines.extend(f"- `{path}`" for path in result["changed_test_files"])
        lines.append("")
    if result["missing_expected_files"]:
        lines.append("## Missing Expected Files")
        lines.extend(f"- `{path}`" for path in result["missing_expected_files"][:50])
        lines.append("")
    setup_errors = [
        ("Clone", result.get("clone_stderr", "")),
        ("Fetch", result.get("fetch_stderr", "")),
        ("Checkout", result.get("checkout_stderr", "")),
        ("Diff Fetch", result.get("diff_stderr", "")),
    ]
    for label, stderr in setup_errors:
        if stderr:
            lines.extend([f"## {label} Stderr", "```", stderr[-4000:].rstrip(), "```", ""])
    if result["apply_check_stderr"]:
        lines.extend(["## Apply Check Stderr", "```", result["apply_check_stderr"][-4000:].rstrip(), "```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a mined benchmark task's historical PR patch applies.")
    parser.add_argument("--task-file", default="bench/tasks/nuri-hard-v1-focused.jsonl")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--out-dir", default="bench/oracle-results")
    parser.add_argument("--work-root", default="/private/tmp/judicative-oracle")
    args = parser.parse_args()

    task = load_task(Path(args.task_file), args.task_id)
    org = task["org"]
    repo = task["repo"]
    pr_number = str(task["source"]["pr_number"])
    replay_base_sha = task["replay"]["replay_base_sha"]
    if not replay_base_sha:
        raise SystemExit(f"task has no replay_base_sha: {args.task_id}")

    work_root = Path(args.work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{args.task_id}-", dir=work_root))
    checkout = temp_dir / repo
    diff_path = temp_dir / f"pr-{pr_number}.diff"

    clone = run(["gh", "repo", "clone", f"{org}/{repo}", str(checkout), "--", "--no-checkout"])
    if clone["returncode"] != 0:
        clone = run(["git", "clone", "--quiet", "--no-checkout", f"https://github.com/{org}/{repo}.git", str(checkout)])
    fetch = run(["git", "fetch", "--quiet", "origin", replay_base_sha], cwd=checkout) if clone["returncode"] == 0 else {"returncode": 1, "stderr": "clone failed", "stdout": ""}
    checkout_cmd = run(["git", "checkout", "--quiet", replay_base_sha], cwd=checkout) if fetch["returncode"] == 0 else {"returncode": 1, "stderr": "fetch failed", "stdout": ""}
    diff = run(["gh", "pr", "diff", pr_number, "--repo", f"{org}/{repo}"]) if checkout_cmd["returncode"] == 0 else {"returncode": 1, "stderr": "checkout failed", "stdout": ""}
    if diff["returncode"] == 0:
        diff_path.write_text(diff["stdout"], encoding="utf-8")

    apply_check = run(["git", "apply", "--check", str(diff_path)], cwd=checkout) if diff["returncode"] == 0 else {"returncode": 1, "stderr": diff.get("stderr", "diff fetch failed"), "stdout": diff.get("stdout", "")}
    apply = run(["git", "apply", str(diff_path)], cwd=checkout) if apply_check["returncode"] == 0 else {"returncode": 1, "stderr": "apply check failed", "stdout": ""}
    changed = run(["git", "diff", "--name-only"], cwd=checkout) if apply["returncode"] == 0 else {"returncode": 1, "stderr": "apply failed", "stdout": ""}
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=checkout) if apply["returncode"] == 0 else {"returncode": 1, "stderr": "apply failed", "stdout": ""}

    expected = [item["path"] for item in task.get("oracle", {}).get("changed_files", [])]
    actual = sorted(
        {
            line.strip()
            for output in (changed.get("stdout", ""), untracked.get("stdout", ""))
            for line in output.splitlines()
            if line.strip()
        }
    )
    missing = sorted(set(expected) - set(actual))

    result = {
        "task_id": task["task_id"],
        "org": org,
        "repo": repo,
        "source_url": task["source"]["url"],
        "replay_base_sha": replay_base_sha,
        "workdir": str(temp_dir),
        "diff_path": str(diff_path),
        "clone_returncode": clone["returncode"],
        "fetch_returncode": fetch["returncode"],
        "checkout_returncode": checkout_cmd["returncode"],
        "diff_returncode": diff["returncode"],
        "clone_stderr": clone.get("stderr", ""),
        "fetch_stderr": fetch.get("stderr", ""),
        "checkout_stderr": checkout_cmd.get("stderr", ""),
        "diff_stderr": diff.get("stderr", ""),
        "apply_check_passed": apply_check["returncode"] == 0,
        "apply_passed": apply["returncode"] == 0,
        "apply_check_stderr": apply_check.get("stderr", ""),
        "apply_stderr": apply.get("stderr", ""),
        "expected_changed_files": expected,
        "actual_changed_files": actual,
        "changed_returncode": changed["returncode"],
        "untracked_returncode": untracked["returncode"],
        "missing_expected_files": missing,
        "changed_test_files": task.get("oracle", {}).get("changed_test_files", []),
        "evaluation_mode": task.get("personalization", {}).get("evaluation_mode"),
    }

    out_dir = Path(args.out_dir)
    out_json = out_dir / f"{args.task_id}.json"
    out_md = out_dir / f"{args.task_id}.md"
    write_json(out_json, result)
    out_md.write_text(render_markdown(result), encoding="utf-8")
    print(render_markdown(result))
    print(f"json={out_json}")
    print(f"markdown={out_md}")
    return 0 if result["apply_check_passed"] and result["apply_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
