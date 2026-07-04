#!/usr/bin/env python3
"""Unit tests for the Judicative MCP self-test workflow."""

import shutil

import mcp_server as mcp


TASK_ID = "task-001-secure-key-storage"
AGENT_ID = "mcp-flow-test-agent"


def cleanup():
    shutil.rmtree(mcp.RUNS_DIR / mcp.slug(AGENT_ID), ignore_errors=True)


def sample_solution():
    return {
        "lib/secureKeyStorage.ts": """
export async function createAndStoreSeed(): Promise<string> {
  const seed = Math.random().toString(36)
  localStorage.setItem('nuri_seed', seed)
  return seed
}

export async function wipeSeed(): Promise<void> {
  try {
    localStorage.removeItem('nuri_seed')
  } catch (error) {
  }
}
""".strip()
    }


def test_self_test_workflow():
    cleanup()
    try:
        listed = mcp.tool_list_tasks({})
        assert any(task["id"] == TASK_ID for task in listed["tasks"])

        started = mcp.tool_start_self_test({"task_id": TASK_ID, "agent_id": AGENT_ID})
        assert started["task_id"] == TASK_ID
        assert "submit_solution" in " ".join(started["protocol"]["cold_run"])

        submitted = mcp.tool_submit_solution({
            "task_id": TASK_ID,
            "agent_id": AGENT_ID,
            "run_id": "run1",
            "files": sample_solution(),
            "static_only": True,
        })
        assert submitted["mode"] == "static-only"
        assert submitted["benchmark_lane"] == "protocol_smoke"
        assert submitted["judge"]["kind"] == "static_only"
        assert submitted["verdict"] == "FAIL"
        assert (mcp.BASE / submitted["artifacts"]["result_markdown"]).is_file()
        assert (mcp.BASE / submitted["artifacts"]["summary_markdown"]).is_file()

        template = mcp.tool_get_assessment_template({"task_id": TASK_ID})
        assert template["assessments"]
        assessments = [
            {"rule_id": item["rule_id"], "score": 1.0, "explanation": "n/a"}
            for item in template["assessments"]
        ]
        rescored = mcp.tool_score_saved_run({
            "task_id": TASK_ID,
            "agent_id": AGENT_ID,
            "run_id": "run1",
            "assessments": assessments,
            "judge_id": AGENT_ID,
        })
        assert rescored["mode"] == "static+external-judge"
        assert rescored["benchmark_lane"] == "diagnostic_self_assessed_retry"
        assert rescored["judge"]["kind"] == "self_assessed"
        assert "assessments" in rescored["artifacts"]

        pr = mcp.tool_prepare_results_pr({
            "task_id": TASK_ID,
            "agent_id": AGENT_ID,
        })
        assert pr["execute"] is False
        assert (mcp.BASE / pr["pr_body"]).is_file()
        assert any("gh pr create" in command for command in pr["commands"])
    finally:
        cleanup()


def test_mcp_tools_list_includes_self_test_tools():
    response = mcp.handle_request({"method": "tools/list", "params": {}, "id": 1})
    names = {tool["name"] for tool in response["tools"]}
    assert {
        "start_self_test",
        "list_benchmark_tasks",
        "start_benchmark_task",
        "submit_solution",
        "score_saved_run",
        "prepare_results_pr",
    } <= names


def test_benchmark_task_tools():
    listed = mcp.tool_list_benchmark_tasks({
        "suite": "nuri-hard-v1-focused.jsonl",
        "evaluation_modes": ["test_backed", "review_backed"],
    })
    assert listed["count"] >= 1
    first = listed["tasks"][0]
    started = mcp.tool_start_benchmark_task({
        "suite": "nuri-hard-v1-focused.jsonl",
        "task_id": first["task_id"],
    })
    assert started["benchmark_lane"] == "cold_fixed_replay"
    assert started["replay"]["replay_base_sha"]
    assert "Self-scores are not accepted" in " ".join(started["protocol"])


if __name__ == "__main__":
    test_self_test_workflow()
    print("PASS test_self_test_workflow")
    test_mcp_tools_list_includes_self_test_tools()
    print("PASS test_mcp_tools_list_includes_self_test_tools")
    test_benchmark_task_tools()
    print("PASS test_benchmark_task_tools")
