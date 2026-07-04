#!/usr/bin/env python3
"""Unit tests for benchmark task mining helpers."""

from bench.mine_tasks import (
    difficulty,
    evaluation_mode,
    extract_issue_refs,
    infer_test_command_hints,
    is_test_file,
    parse_repo_targets,
    tag_domains,
    task_score,
)


def test_extract_issue_refs():
    assert extract_issue_refs("Fixes #123", "also see #45") == [45, 123]


def test_is_test_file():
    assert is_test_file("services/auth/__tests__/passkey.test.ts")
    assert is_test_file("src/worker-mcp.test.ts")
    assert not is_test_file("src/worker.ts")


def test_tag_domains():
    tags = tag_domains("Fix Arkade passkey PRF stale balance race", ["services/arkade/foo.ts"])
    assert "arkade" in tags
    assert "passkey" in tags
    assert "prf" in tags
    assert "stale_state" in tags
    assert "race_condition" in tags


def test_tag_domains_partner_crypto():
    tags = tag_domains(
        "Fix ZeroDev kernel account paymaster validation for Safe multisig userOp",
        ["packages/kernel/src/paymaster.ts"],
    )
    assert "zerodev" in tags
    assert "safe" in tags
    assert "account_abstraction" in tags
    assert "multisig" in tags


def test_parse_repo_targets_supports_owner_repo_specs():
    targets = parse_repo_targets(["arkade-os/ark", "safe-global/safe-core-sdk"], ["nuri-com", "safe-global"])
    assert [(target.owner, target.repo) for target in targets] == [
        ("arkade-os", "ark"),
        ("safe-global", "safe-core-sdk"),
    ]


def test_infer_test_commands_for_mcp_repo():
    hints = infer_test_command_hints("nuri-wirex-mcp", ["src/server.ts"])
    assert "npm test" in hints
    assert "npm run typecheck" in hints


def test_task_score_prefers_reviewed_tested_merged_tasks():
    pr = {
        "merged_at": "2026-01-01T00:00:00Z",
        "title": "fix(arkade): recover stale signer funds",
        "body": "Fixes #42",
        "additions": 120,
        "deletions": 40,
        "user": {"login": "eminogrande"},
    }
    files = [
        {"filename": "services/arkade/recovery.ts"},
        {"filename": "services/arkade/recovery.test.ts"},
    ]
    score, strengths, cautions = task_score(
        pr=pr,
        files=files,
        inline_comments=[{"body": "review"}],
        general_comments=[],
        reviews=[{"body": "summary"}],
        issue_refs=[42],
        tags=["arkade", "stale_state", "recovery"],
        replay_base_sha="abc123",
    )
    assert score >= 80
    assert "has_test_changes" in strengths
    assert "replay_base_from_merge_parent" in strengths
    assert "no_changed_tests" not in cautions
    assert difficulty(score, files, ["arkade"]) == "hard"


def test_evaluation_mode():
    assert evaluation_mode(["x.test.ts"], 20, 0) == "test_backed"
    assert evaluation_mode([], 80, 3) == "review_backed"
    assert evaluation_mode([], 80, 0) == "weak_oracle"


if __name__ == "__main__":
    tests = [
        test_extract_issue_refs,
        test_is_test_file,
        test_tag_domains,
        test_tag_domains_partner_crypto,
        test_parse_repo_targets_supports_owner_repo_specs,
        test_infer_test_commands_for_mcp_repo,
        test_task_score_prefers_reviewed_tested_merged_tasks,
        test_evaluation_mode,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
