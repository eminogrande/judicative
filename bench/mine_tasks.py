#!/usr/bin/env python3
"""Mine personalized replay-benchmark tasks from GitHub PR history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ORG = "nuri-com"
DEFAULT_NURI_REPOS = [
    "nuri-expo",
    "server-arkade-v4",
    "nuri-prf-signer",
    "nuri-mcp-bitcoin-swapkit",
    "nuri-wirex-mcp",
    "nuri-gnosis-mcp",
    "server-near-intents-solver",
    "passkey-server",
]
DEFAULT_REPOS = DEFAULT_NURI_REPOS

PARTNER_CRYPTO_ORGS = [
    "nuri-com",
    "arkade-os",
    "wirexapp",
    "zerodevapp",
    "safe-global",
]

DEPENDENCY_AUTHORS = {"dependabot[bot]", "renovate[bot]"}

DOMAIN_KEYWORDS = {
    "arkade": ["arkade", "vtxo", "boarding", "wallet summary", "signer rotation"],
    "zerodev": ["zerodev", "zero dev", "kernel account", "kernel plugin", "kernel v3"],
    "safe": ["safe-global", "gnosis safe", "safe smart account", "safe multisig", "safe-core", "safe apps"],
    "account_abstraction": [
        "account abstraction",
        "eip-4337",
        "erc-4337",
        "userop",
        "user operation",
        "bundler",
        "paymaster",
        "entrypoint",
        "smart account",
    ],
    "multisig": ["multisig", "multi-sig", "threshold signature", "owners threshold"],
    "passkey": ["passkey", "webauthn", "credential", "biometric", "face id"],
    "prf": ["prf", "pseudo-random", "secure enclave"],
    "mcp": ["mcp", "tools/list", "initialize", "model context protocol"],
    "wirex": ["wirex"],
    "gnosis": ["gnosis", "safe"],
    "monerium": ["monerium", "iban"],
    "near_intents": ["near intents", "1click", "defuse", "solver"],
    "bitcoin": ["bitcoin", "btc", "sats", "on-chain", "onchain"],
    "lightning": ["lightning", "lnurl", "bolt11", "invoice"],
    "recovery": ["recover", "recovery", "sweep", "deprecated signer"],
    "security": ["security", "crypto", "keychain", "seed", "private key", "nonce"],
    "race_condition": ["race", "in-flight", "abort", "cancel", "concurrent", "leak"],
    "stale_state": ["stale", "cache", "refetch", "revalidate", "ghost balance"],
    "data_integrity": ["integrity", "dedup", "duplicate", "wrong address", "fatal"],
    "ota_native_boundary": ["ota", "native module", "binary", "fingerprint"],
    "ui": ["modal", "screen", "keyboard", "onboarding", "layout"],
    "docs": ["docs", "documentation", "readme"],
}

TEST_FILE_RE = re.compile(
    r"(^|/)(test|tests|__tests__)/|(\.|-)(test|spec)\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs)$",
    re.IGNORECASE,
)
ISSUE_REF_RE = re.compile(
    r"(?:(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+)?#(?P<number>[1-9][0-9]{0,6})",
    re.IGNORECASE,
)
TASK_NOISE_RE = re.compile(
    r"\b(dependabot|dependency|bump|release candidate|rc v?\d|chore\(deps\)|lockfile)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GhClient:
    org: str
    cache_dir: Path
    refresh: bool = False
    sleep_seconds: float = 0.15

    def api(self, path: str, *, cache_key: str | None = None) -> Any:
        if cache_key:
            cache_path = self.cache_dir / f"{safe_name(cache_key)}.json"
            if cache_path.exists() and not self.refresh:
                return json.loads(cache_path.read_text())
        else:
            cache_path = None

        cmd = ["gh", "api", path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"gh api failed for {path}: {proc.stderr.strip()[:500]}")
        data = json.loads(proc.stdout or "null")

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2, sort_keys=True))
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        return data

    def paged(self, path: str, *, max_pages: int) -> list[Any]:
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in path else "?"
            page_path = f"{path}{sep}per_page=100&page={page}"
            page_items = self.api(page_path, cache_key=f"{page_path}")
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(page_items)
            if len(page_items) < 100:
                break
        return items


@dataclass(frozen=True)
class RepoTarget:
    owner: str
    repo: str


def safe_name(value: str) -> str:
    digest = hashlib.sha1(value.encode()).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120]
    return f"{stem}-{digest}"


def list_owner_repos(
    client: GhClient,
    *,
    max_pages: int,
    include_archived: bool = False,
    include_forks: bool = False,
) -> list[str]:
    """List source repositories for one GitHub org/user owner."""
    paths = [
        f"orgs/{client.org}/repos?type=sources&sort=pushed&direction=desc",
        f"users/{client.org}/repos?type=owner&sort=pushed&direction=desc",
    ]
    repos: list[dict[str, Any]] = []
    last_error = None
    for path in paths:
        try:
            repos = client.paged(path, max_pages=max_pages)
            if repos:
                break
        except RuntimeError as exc:
            last_error = exc
    if not repos and last_error:
        raise last_error

    names = []
    for repo in repos:
        if not include_archived and repo.get("archived"):
            continue
        if not include_forks and repo.get("fork"):
            continue
        name = repo.get("name")
        if name:
            names.append(name)
    return sorted(set(names))


def parse_repo_targets(repo_specs: list[str], owners: list[str]) -> list[RepoTarget]:
    targets = []
    if len(owners) != 1:
        bare = [spec for spec in repo_specs if "/" not in spec]
        if bare:
            raise ValueError(
                "Bare --repos names are ambiguous with multiple owners; use owner/repo for: "
                + ", ".join(bare)
            )
    default_owner = owners[0] if owners else DEFAULT_ORG
    for spec in repo_specs:
        if "/" in spec:
            owner, repo = spec.split("/", 1)
        else:
            owner, repo = default_owner, spec
        owner, repo = owner.strip(), repo.strip()
        if not owner or not repo:
            raise ValueError(f"Invalid repo spec: {spec}")
        targets.append(RepoTarget(owner=owner, repo=repo))
    return sorted(set(targets), key=lambda target: (target.owner, target.repo))


def resolve_targets(args: argparse.Namespace) -> list[RepoTarget]:
    if args.profile == "partner-crypto":
        owners = PARTNER_CRYPTO_ORGS
        discover_repos = True
    else:
        owners = args.orgs or ([args.org] if args.org else [DEFAULT_ORG])
        discover_repos = args.discover_repos or bool(args.orgs)

    if args.repos:
        return parse_repo_targets(args.repos, owners)

    targets: list[RepoTarget] = []
    for owner in owners:
        if discover_repos or owner != DEFAULT_ORG:
            client = GhClient(org=owner, cache_dir=Path(args.cache_dir), refresh=args.refresh)
            repos = list_owner_repos(
                client,
                max_pages=args.repo_pages,
                include_archived=args.include_archived,
                include_forks=args.include_forks,
            )
        else:
            repos = DEFAULT_NURI_REPOS
        targets.extend(RepoTarget(owner=owner, repo=repo) for repo in repos)
    return sorted(set(targets), key=lambda target: (target.owner, target.repo))


def compact_text(value: str | None, limit: int = 4000) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path))


def extract_issue_refs(*texts: str) -> list[int]:
    refs: set[int] = set()
    for text in texts:
        for match in ISSUE_REF_RE.finditer(text or ""):
            refs.add(int(match.group("number")))
    return sorted(refs)


def tag_domains(text: str, paths: Iterable[str]) -> list[str]:
    haystack = " ".join([text.lower(), " ".join(paths).lower()])
    tags = []
    for tag, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            tags.append(tag)
    return tags


def infer_test_command_hints(repo: str, paths: list[str]) -> list[str]:
    has_go = any(path.endswith(".go") for path in paths)
    has_python = any(path.endswith(".py") for path in paths)
    has_js = any(path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")) for path in paths)

    if repo == "nuri-expo":
        return ["npm test -- --runInBand", "npm run typecheck", "npm run lint"]
    if repo.startswith("server-") or repo.endswith("-mcp") or "mcp" in repo or has_js:
        return ["npm test", "npm run typecheck", "npm run lint"]
    if has_go:
        return ["go test ./..."]
    if has_python:
        return ["python3 -m pytest"]
    return []


def pr_delta(pr: dict[str, Any], files: list[dict[str, Any]]) -> tuple[int, int]:
    additions = pr.get("additions")
    deletions = pr.get("deletions")
    if additions is None:
        additions = sum(int(item.get("additions") or 0) for item in files)
    if deletions is None:
        deletions = sum(int(item.get("deletions") or 0) for item in files)
    return int(additions or 0), int(deletions or 0)


def task_score(
    *,
    pr: dict[str, Any],
    files: list[dict[str, Any]],
    inline_comments: list[dict[str, Any]],
    general_comments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    issue_refs: list[int],
    tags: list[str],
    replay_base_sha: str | None,
) -> tuple[int, list[str], list[str]]:
    score = 0
    strengths: list[str] = []
    cautions: list[str] = []

    author = ((pr.get("user") or {}).get("login") or "").lower()
    title = pr.get("title") or ""
    additions, deletions = pr_delta(pr, files)
    changed_count = len(files)
    test_files = [f for f in files if is_test_file(f.get("filename", ""))]

    if pr.get("merged_at"):
        score += 20
        strengths.append("merged_pr")
    else:
        cautions.append("not_merged")

    if replay_base_sha:
        score += 15
        strengths.append("replay_base_from_merge_parent")
    else:
        cautions.append("missing_replay_base")

    if author not in DEPENDENCY_AUTHORS:
        score += 10
    else:
        score -= 25
        cautions.append("dependency_bot")

    if issue_refs:
        score += 10
        strengths.append("linked_issue_refs")

    if inline_comments:
        score += min(12, 3 + len(inline_comments))
        strengths.append("inline_review_signal")
    if reviews:
        score += min(8, 2 + len(reviews))
        strengths.append("review_summary_signal")
    if general_comments:
        score += min(6, 1 + len(general_comments))

    if test_files:
        score += 15
        strengths.append("has_test_changes")
    else:
        cautions.append("no_changed_tests")

    high_value_tags = {
        "arkade",
        "zerodev",
        "safe",
        "account_abstraction",
        "multisig",
        "passkey",
        "prf",
        "mcp",
        "security",
        "race_condition",
        "stale_state",
        "data_integrity",
        "recovery",
        "lightning",
    }
    tag_hits = high_value_tags.intersection(tags)
    if tag_hits:
        score += min(18, 4 * len(tag_hits))
        strengths.append("high_value_domain_tags")

    total_delta = additions + deletions
    is_large_rollup = total_delta > 1800 or changed_count > 50
    is_noisy_task = bool(TASK_NOISE_RE.search(title) or TASK_NOISE_RE.search(pr.get("body") or ""))

    if 20 <= total_delta <= 900 and 1 <= changed_count <= 25:
        score += 10
        strengths.append("replayable_patch_size")
    elif is_large_rollup:
        score -= 30
        cautions.append("large_rollup")
    elif total_delta < 8:
        score -= 8
        cautions.append("very_small_change")

    if is_noisy_task:
        score -= 30
        cautions.append("task_noise")

    if is_large_rollup:
        score = min(score, 60)
    if is_noisy_task:
        score = min(score, 45)

    return max(0, min(score, 100)), strengths, cautions


def difficulty(score: int, files: list[dict[str, Any]], tags: list[str]) -> str:
    changed_count = len(files)
    high_complexity = {"arkade", "passkey", "prf", "mcp", "race_condition", "stale_state"}
    if score >= 78 and (changed_count >= 8 or high_complexity.intersection(tags)):
        return "hard"
    if score >= 55:
        return "medium"
    return "low"


def evaluation_mode(changed_tests: list[str], score: int, review_signal_count: int) -> str:
    if changed_tests:
        return "test_backed"
    if score >= 55 and review_signal_count >= 2:
        return "review_backed"
    return "weak_oracle"


def fetch_pr_context(client: GhClient, repo: str, pr: dict[str, Any]) -> dict[str, Any]:
    number = pr["number"]
    prefix = f"repos/{client.org}/{repo}/pulls/{number}"
    issue_prefix = f"repos/{client.org}/{repo}/issues/{number}"
    cache_prefix = f"{client.org}-{repo}-{number}"
    detail = client.api(prefix, cache_key=f"{cache_prefix}-detail")
    files = client.api(f"{prefix}/files?per_page=100", cache_key=f"{cache_prefix}-files")
    inline_comments = client.api(f"{prefix}/comments?per_page=100", cache_key=f"{cache_prefix}-inline")
    reviews = client.api(f"{prefix}/reviews?per_page=100", cache_key=f"{cache_prefix}-reviews")
    general_comments = client.api(f"{issue_prefix}/comments?per_page=100", cache_key=f"{cache_prefix}-issue-comments")
    merge_commit = None
    merge_sha = pr.get("merge_commit_sha")
    if pr.get("merged_at") and merge_sha:
        try:
            merge_commit = client.api(
                f"repos/{client.org}/{repo}/commits/{merge_sha}",
                cache_key=f"{cache_prefix}-merge-{merge_sha}",
            )
        except RuntimeError as exc:
            print(f"warning: could not fetch merge commit for {repo}#{number}: {exc}", file=sys.stderr)

    return {
        "detail": detail if isinstance(detail, dict) else pr,
        "files": files if isinstance(files, list) else [],
        "inline_comments": inline_comments if isinstance(inline_comments, list) else [],
        "reviews": reviews if isinstance(reviews, list) else [],
        "general_comments": general_comments if isinstance(general_comments, list) else [],
        "merge_commit": merge_commit,
    }


def replay_base_from_merge(merge_commit: dict[str, Any] | None) -> str | None:
    if not merge_commit:
        return None
    parents = merge_commit.get("parents") or []
    if not parents:
        return None
    return parents[0].get("sha")


def fetch_linked_issues(client: GhClient, repo: str, issue_refs: list[int], pr_number: int) -> list[dict[str, Any]]:
    linked = []
    for issue_number in issue_refs[:5]:
        if issue_number == pr_number:
            continue
        try:
            issue = client.api(
                f"repos/{client.org}/{repo}/issues/{issue_number}",
                cache_key=f"{client.org}-{repo}-issue-{issue_number}",
            )
        except RuntimeError:
            continue
        if not isinstance(issue, dict) or issue.get("pull_request"):
            continue
        try:
            comments = client.api(
                f"repos/{client.org}/{repo}/issues/{issue_number}/comments?per_page=20",
                cache_key=f"{client.org}-{repo}-issue-{issue_number}-comments",
            )
        except RuntimeError:
            comments = []
        linked.append(
            {
                "number": issue_number,
                "title": issue.get("title"),
                "state": issue.get("state"),
                "url": issue.get("html_url"),
                "labels": [label.get("name") for label in issue.get("labels") or []],
                "body": compact_text(issue.get("body"), 4000),
                "comments": [
                    {
                        "author": (comment.get("user") or {}).get("login"),
                        "body": compact_text(comment.get("body"), 1200),
                        "created_at": comment.get("created_at"),
                    }
                    for comment in (comments if isinstance(comments, list) else [])[:10]
                ],
            }
        )
    return linked


def build_task(client: GhClient, repo: str, pr: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    pr = context.get("detail") or pr
    files = context["files"]
    inline_comments = context["inline_comments"]
    general_comments = context["general_comments"]
    reviews = context["reviews"]
    merge_commit = context["merge_commit"]
    paths = [f.get("filename", "") for f in files]
    changed_tests = [path for path in paths if is_test_file(path)]
    review_signal_count = len(inline_comments) + len(general_comments) + len(reviews)

    review_text = " ".join(
        compact_text(item.get("body"), 1000)
        for item in [*inline_comments[:10], *general_comments[:5], *reviews[:5]]
    )
    issue_refs = extract_issue_refs(pr.get("title") or "", pr.get("body") or "", review_text)
    linked_issues = fetch_linked_issues(client, repo, issue_refs, pr["number"])
    linked_issue_parts: list[str] = []
    for issue in linked_issues:
        linked_issue_parts.append(issue.get("title") or "")
        linked_issue_parts.append(issue.get("body") or "")
        linked_issue_parts.extend(comment.get("body") or "" for comment in issue.get("comments", []))
    linked_issue_text = " ".join(linked_issue_parts)
    tags = tag_domains(" ".join([pr.get("title") or "", pr.get("body") or "", review_text]), paths)
    tags = sorted(set(tags).union(tag_domains(linked_issue_text, [])))
    replay_base_sha = replay_base_from_merge(merge_commit)
    additions, deletions = pr_delta(pr, files)
    score, strengths, cautions = task_score(
        pr=pr,
        files=files,
        inline_comments=inline_comments,
        general_comments=general_comments,
        reviews=reviews,
        issue_refs=issue_refs,
        tags=tags,
        replay_base_sha=replay_base_sha,
    )

    head = pr.get("head") or {}
    base = pr.get("base") or {}
    user = pr.get("user") or {}
    changed_file_summaries = [
        {
            "path": item.get("filename"),
            "status": item.get("status"),
            "additions": item.get("additions"),
            "deletions": item.get("deletions"),
            "changes": item.get("changes"),
        }
        for item in files
    ]

    task = {
        "schema_version": "judicative.replay_task.v1",
        "task_id": f"{client.org}-{repo}-pr-{pr['number']}",
        "owner": client.org,
        "org": client.org,
        "repo": repo,
        "source": {
            "type": "github_pull_request",
            "pr_number": pr["number"],
            "title": pr.get("title"),
            "url": pr.get("html_url"),
            "author": user.get("login"),
            "merged_at": pr.get("merged_at"),
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "labels": [label.get("name") for label in pr.get("labels") or []],
        },
        "replay": {
            "base_ref": base.get("ref"),
            "base_sha_from_pr": base.get("sha"),
            "replay_base_sha": replay_base_sha,
            "real_fix_head_sha": head.get("sha"),
            "merge_commit_sha": pr.get("merge_commit_sha"),
            "test_command_hints": infer_test_command_hints(repo, paths),
        },
        "prompt_context": {
            "issue_title": pr.get("title") or "",
            "issue_body": compact_text(pr.get("body"), 6000),
            "linked_issue_refs": issue_refs,
            "linked_issues": linked_issues,
            "review_excerpt": compact_text(review_text, 6000),
        },
        "oracle": {
            "changed_files": changed_file_summaries,
            "changed_test_files": changed_tests,
            "review_signal": {
                "inline_comments": len(inline_comments),
                "general_comments": len(general_comments),
                "reviews": len(reviews),
            },
        },
        "personalization": {
            "domain_tags": tags,
            "difficulty": difficulty(score, files, tags),
            "evaluation_mode": evaluation_mode(changed_tests, score, review_signal_count),
            "candidate_score": score,
            "strengths": strengths,
            "cautions": cautions,
        },
        "stats": {
            "changed_files": len(files),
            "additions": additions,
            "deletions": deletions,
        },
    }
    return task


def mine_repo(client: GhClient, repo: str, *, limit_per_repo: int, max_pages: int) -> list[dict[str, Any]]:
    if limit_per_repo <= 0:
        return []
    pulls = client.paged(
        f"repos/{client.org}/{repo}/pulls?state=closed&sort=updated&direction=desc",
        max_pages=max_pages,
    )
    tasks: list[dict[str, Any]] = []
    for pr in pulls:
        if not pr.get("merged_at"):
            continue
        context = fetch_pr_context(client, repo, pr)
        task = build_task(client, repo, pr, context)
        tasks.append(task)
        if len(tasks) >= limit_per_repo:
            break
    return tasks


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def print_summary(tasks: list[dict[str, Any]]) -> None:
    print(f"mined_tasks={len(tasks)}")
    by_repo: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    for task in tasks:
        repo_key = f"{task.get('owner') or task.get('org')}/{task['repo']}"
        by_repo[repo_key] = by_repo.get(repo_key, 0) + 1
        diff = task["personalization"]["difficulty"]
        by_difficulty[diff] = by_difficulty.get(diff, 0) + 1
        mode = task["personalization"]["evaluation_mode"]
        by_mode[mode] = by_mode.get(mode, 0) + 1
    print("repos=" + json.dumps(dict(sorted(by_repo.items())), sort_keys=True))
    print("difficulty=" + json.dumps(dict(sorted(by_difficulty.items())), sort_keys=True))
    print("evaluation_mode=" + json.dumps(dict(sorted(by_mode.items())), sort_keys=True))
    for task in sorted(tasks, key=lambda item: item["personalization"]["candidate_score"], reverse=True)[:10]:
        source = task["source"]
        pers = task["personalization"]
        print(
            f"{pers['candidate_score']:3d} {pers['difficulty']:6s} "
            f"{pers['evaluation_mode']:13s} "
            f"{task.get('owner') or task.get('org')}/{task['repo']}#{source['pr_number']} "
            f"{','.join(pers['domain_tags'][:5]) or '-'} "
            f"{source['title']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine replay benchmark tasks from GitHub PR history.")
    parser.add_argument(
        "--profile",
        choices=["nuri", "partner-crypto"],
        default="nuri",
        help="nuri keeps the curated Nuri repo set; partner-crypto discovers repos from Nuri, Arkade, Wirex, ZeroDev, and Safe.",
    )
    parser.add_argument("--org", default=None, help="Single GitHub org/user owner. Defaults to nuri-com.")
    parser.add_argument("--orgs", nargs="+", help="Multiple GitHub org/user owners; repos are discovered unless --repos is set.")
    parser.add_argument(
        "--repos",
        nargs="+",
        default=None,
        help="Repo names for one owner, or fully-qualified owner/repo specs.",
    )
    parser.add_argument("--discover-repos", action="store_true", help="Discover all non-archived, non-fork repos for the selected owner(s).")
    parser.add_argument("--include-archived", action="store_true", help="Include archived repos when discovering.")
    parser.add_argument("--include-forks", action="store_true", help="Include forks when discovering.")
    parser.add_argument("--repo-pages", type=int, default=3, help="Pages of owner repos to inspect during discovery.")
    parser.add_argument("--limit-per-repo", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--cache-dir", default="bench/cache/github")
    parser.add_argument("--output", default="bench/tasks/nuri-hard-v1.jsonl")
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument(
        "--evaluation-modes",
        nargs="+",
        choices=["test_backed", "review_backed", "weak_oracle"],
        default=None,
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cached GitHub responses.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = resolve_targets(args)
    all_tasks: list[dict[str, Any]] = []

    print(f"targets={len(targets)}", file=sys.stderr)
    if args.limit_per_repo <= 0:
        write_jsonl(Path(args.output), [])
        print_summary([])
        print(f"wrote={args.output}")
        return 0

    for target in targets:
        client = GhClient(org=target.owner, cache_dir=Path(args.cache_dir), refresh=args.refresh)
        print(f"mining {target.owner}/{target.repo}...", file=sys.stderr)
        try:
            all_tasks.extend(
                mine_repo(client, target.repo, limit_per_repo=args.limit_per_repo, max_pages=args.max_pages)
            )
        except Exception as exc:
            print(f"warning: failed to mine {target.owner}/{target.repo}: {exc}", file=sys.stderr)

    all_tasks.sort(
        key=lambda task: (
            task["personalization"]["candidate_score"],
            task["source"].get("merged_at") or "",
        ),
        reverse=True,
    )
    if args.min_score:
        all_tasks = [
            task for task in all_tasks
            if task["personalization"]["candidate_score"] >= args.min_score
        ]
    if args.evaluation_modes:
        allowed_modes = set(args.evaluation_modes)
        all_tasks = [
            task for task in all_tasks
            if task["personalization"]["evaluation_mode"] in allowed_modes
        ]
    write_jsonl(Path(args.output), all_tasks)
    print_summary(all_tasks)
    print(f"wrote={args.output}")
    return 0 if all_tasks else 1


if __name__ == "__main__":
    raise SystemExit(main())
