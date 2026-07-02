#!/usr/bin/env python3
"""
scan_all.py — Comprehensive scan of ALL nuri-com repos.
Fetches: PRs, PR inline comments, PR general comments, PR reviews,
         issues, issue comments, commit comments.
Saves per-repo JSON files to disk.
Rate-limit aware with retry logic.
"""

import subprocess, json, os, time, sys, re
from pathlib import Path

OUT = "/Users/eminmahrt/Developer/judicative/full-scan"
os.makedirs(OUT, exist_ok=True)

def gh_api(url_path, paginate=True, max_pages=20):
    """Fetch raw JSON from GitHub API. URL must include query params."""
    cmd = ["gh", "api", url_path]
    if paginate:
        cmd.append("--paginate")
    for attempt in range(3):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                return r.stdout, None
            # Check for rate limit
            if "rate limit" in r.stderr.lower() or "403" in r.stderr:
                wait = 30 * (attempt + 1)
                print(f"  RATE LIMITED, waiting {wait}s...", file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            # TLS timeout or network error — retry
            if "timeout" in r.stderr.lower() or "TLS" in r.stderr:
                wait = 5 * (attempt + 1)
                print(f"  Network error, retry in {wait}s...", file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            return None, r.stderr[:300]
        except subprocess.TimeoutExpired:
            wait = 5 * (attempt + 1)
            print(f"  Timeout, retry in {wait}s...", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
    return None, "max retries exceeded"

def gh_api_paged(url_path, per_page=100, max_pages=30):
    """Fetch with manual pagination for reliability."""
    all_items = []
    for page in range(1, max_pages + 1):
        sep = '&' if '?' in url_path else '?'
        url = f"{url_path}{sep}per_page={per_page}&page={page}"
        cmd = ["gh", "api", url]
        for attempt in range(3):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    try:
                        items = json.loads(r.stdout)
                        if not items:
                            return all_items  # Empty page = done
                        all_items.extend(items)
                        if len(items) < per_page:
                            return all_items  # Last page
                        break  # Next page
                    except json.JSONDecodeError:
                        return all_items
                if "rate limit" in r.stderr.lower() or "403" in r.stderr:
                    wait = 30 * (attempt + 1)
                    print(f"  RATE LIMITED, waiting {wait}s...", file=sys.stderr, flush=True)
                    time.sleep(wait)
                    continue
                return all_items  # Error — return what we have
            except subprocess.TimeoutExpired:
                time.sleep(3)
                continue
        else:
            return all_items  # All retries failed for this page
        time.sleep(0.15)  # Small delay between pages
    return all_items

# Step 1: Get all repos
print("=" * 60, file=sys.stderr)
print("STEP 1: Enumerating all repos", file=sys.stderr)
print("=" * 60, file=sys.stderr)

repos_raw, err = gh_api("orgs/nuri-com/repos?per_page=100&type=all")
if err:
    print(f"FATAL: can't list repos: {err}", file=sys.stderr)
    sys.exit(1)

repos = json.loads(repos_raw)
repo_names = sorted([r['name'] for r in repos])
print(f"Found {len(repo_names)} repos", file=sys.stderr)

with open(os.path.join(OUT, "repos.json"), "w") as f:
    json.dump(repos, f, indent=2)

# Summary file
summary = {}

# Step 2: For each repo, fetch everything
print(f"\n{'=' * 60}", file=sys.stderr)
print(f"STEP 2: Scanning all {len(repo_names)} repos", file=sys.stderr)
print(f"{'=' * 60}", file=sys.stderr)

for idx, repo in enumerate(repo_names, 1):
    print(f"\n[{idx}/{len(repo_names)}] {repo}", file=sys.stderr, flush=True)
    repo_data = {
        'repo': repo,
        'prs': 0, 'pr_inline_comments': 0, 'pr_general_comments': 0,
        'pr_reviews': 0, 'issues': 0, 'issue_comments': 0,
        'commit_comments': 0, 'total_comments': 0,
    }

    # 2a: Fetch all PRs
    prs = gh_api_paged(f"repos/nuri-com/{repo}/pulls?state=all&sort=updated&direction=desc")
    repo_data['prs'] = len(prs)
    print(f"  PRs: {len(prs)}", file=sys.stderr, flush=True)

    if prs:
        with open(os.path.join(OUT, f"{repo}_prs.json"), "w") as f:
            # Save compact PR data
            compact_prs = [{
                'number': p.get('number'),
                'title': p.get('title'),
                'state': p.get('state'),
                'merged_at': p.get('merged_at'),
                'user': p.get('user', {}).get('login') if p.get('user') else None,
                'created_at': p.get('created_at'),
                'updated_at': p.get('updated_at'),
                'changed_files': p.get('changed_files'),
                'additions': p.get('additions'),
                'deletions': p.get('deletions'),
                'labels': [l.get('name') for l in p.get('labels', [])],
                'body': (p.get('body') or '')[:2000],
            } for p in prs]
            json.dump(compact_prs, f, indent=2)

    # 2b: For each PR, fetch inline comments + general comments + reviews
    all_inline = []
    all_general = []
    all_reviews = []

    for pr in prs:
        pr_num = pr.get('number')
        pr_title = pr.get('title', '')

        # Inline review comments (code-level)
        inline = gh_api_paged(f"repos/nuri-com/{repo}/pulls/{pr_num}/comments", max_pages=10)
        for c in inline:
            all_inline.append({
                'pr_number': pr_num,
                'pr_title': pr_title,
                'comment_id': c.get('id'),
                'author': c.get('user', {}).get('login') if c.get('user') else None,
                'body': (c.get('body') or '')[:3000],
                'path': c.get('path'),
                'line': c.get('line'),
                'original_line': c.get('original_line'),
                'diff_hunk': (c.get('diff_hunk') or '')[:500],
                'created_at': c.get('created_at'),
                'updated_at': c.get('updated_at'),
                'in_reply_to_id': c.get('in_reply_to_id'),
                'reactions': {k: v for k, v in (c.get('reactions') or {}).items()
                              if k not in ('url', 'total_count') and isinstance(v, int) and v > 0},
            })
        time.sleep(0.1)

        # General PR comments (via issues API — PRs are issues)
        general = gh_api_paged(f"repos/nuri-com/{repo}/issues/{pr_num}/comments", max_pages=10)
        for c in general:
            all_general.append({
                'pr_number': pr_num,
                'pr_title': pr_title,
                'comment_id': c.get('id'),
                'author': c.get('user', {}).get('login') if c.get('user') else None,
                'body': (c.get('body') or '')[:3000],
                'created_at': c.get('created_at'),
                'updated_at': c.get('updated_at'),
                'reactions': {k: v for k, v in (c.get('reactions') or {}).items()
                              if k not in ('url', 'total_count') and isinstance(v, int) and v > 0},
            })
        time.sleep(0.1)

        # PR reviews (approve/request changes/comment)
        reviews = gh_api_paged(f"repos/nuri-com/{repo}/pulls/{pr_num}/reviews", max_pages=5)
        for rv in reviews:
            all_reviews.append({
                'pr_number': pr_num,
                'pr_title': pr_title,
                'review_id': rv.get('id'),
                'author': rv.get('user', {}).get('login') if rv.get('user') else None,
                'state': rv.get('state'),  # APPROVED, CHANGES_REQUESTED, COMMENTED, etc.
                'body': (rv.get('body') or '')[:3000],
                'submitted_at': rv.get('submitted_at'),
            })
        time.sleep(0.1)

    repo_data['pr_inline_comments'] = len(all_inline)
    repo_data['pr_general_comments'] = len(all_general)
    repo_data['pr_reviews'] = len(all_reviews)

    if all_inline:
        with open(os.path.join(OUT, f"{repo}_pr_inline_comments.json"), "w") as f:
            json.dump(all_inline, f, indent=2)
    if all_general:
        with open(os.path.join(OUT, f"{repo}_pr_general_comments.json"), "w") as f:
            json.dump(all_general, f, indent=2)
    if all_reviews:
        with open(os.path.join(OUT, f"{repo}_pr_reviews.json"), "w") as f:
            json.dump(all_reviews, f, indent=2)

    print(f"  PR inline comments: {len(all_inline)}", file=sys.stderr, flush=True)
    print(f"  PR general comments: {len(all_general)}", file=sys.stderr, flush=True)
    print(f"  PR reviews: {len(all_reviews)}", file=sys.stderr, flush=True)

    # 2c: Fetch all issues (non-PR)
    issues = gh_api_paged(f"repos/nuri-com/{repo}/issues?state=all&sort=updated&direction=desc")
    # Filter out PRs (they appear in issues API)
    issues_only = [i for i in issues if 'pull_request' not in i]
    repo_data['issues'] = len(issues_only)
    print(f"  Issues: {len(issues_only)}", file=sys.stderr, flush=True)

    if issues_only:
        with open(os.path.join(OUT, f"{repo}_issues.json"), "w") as f:
            compact_issues = [{
                'number': i.get('number'),
                'title': i.get('title'),
                'state': i.get('state'),
                'user': i.get('user', {}).get('login') if i.get('user') else None,
                'created_at': i.get('created_at'),
                'updated_at': i.get('updated_at'),
                'comments_count': i.get('comments'),
                'labels': [l.get('name') for l in i.get('labels', [])],
                'body': (i.get('body') or '')[:2000],
            } for i in issues_only]
            json.dump(compact_issues, f, indent=2)

    # 2d: For each issue with comments, fetch issue comments
    all_issue_comments = []
    for issue in issues_only:
        ic = issue.get('comments', 0)
        if ic and ic > 0:
            comments = gh_api_paged(f"repos/nuri-com/{repo}/issues/{issue.get('number')}/comments", max_pages=5)
            for c in comments:
                all_issue_comments.append({
                    'issue_number': issue.get('number'),
                    'issue_title': issue.get('title'),
                    'comment_id': c.get('id'),
                    'author': c.get('user', {}).get('login') if c.get('user') else None,
                    'body': (c.get('body') or '')[:3000],
                    'created_at': c.get('created_at'),
                    'reactions': {k: v for k, v in (c.get('reactions') or {}).items()
                                  if k not in ('url', 'total_count') and isinstance(v, int) and v > 0},
                })
            time.sleep(0.1)

    repo_data['issue_comments'] = len(all_issue_comments)
    if all_issue_comments:
        with open(os.path.join(OUT, f"{repo}_issue_comments.json"), "w") as f:
            json.dump(all_issue_comments, f, indent=2)
    print(f"  Issue comments: {len(all_issue_comments)}", file=sys.stderr, flush=True)

    # 2e: Commit comments (repo-level)
    commit_comments = gh_api_paged(f"repos/nuri-com/{repo}/comments", max_pages=5)
    repo_data['commit_comments'] = len(commit_comments)
    if commit_comments:
        with open(os.path.join(OUT, f"{repo}_commit_comments.json"), "w") as f:
            json.dump([{
                'comment_id': c.get('id'),
                'author': c.get('user', {}).get('login') if c.get('user') else None,
                'body': (c.get('body') or '')[:3000],
                'commit_id': c.get('commit_id'),
                'path': c.get('path'),
                'line': c.get('line'),
                'created_at': c.get('created_at'),
            } for c in commit_comments], f, indent=2)
    if commit_comments:
        print(f"  Commit comments: {len(commit_comments)}", file=sys.stderr, flush=True)

    repo_data['total_comments'] = (
        repo_data['pr_inline_comments'] +
        repo_data['pr_general_comments'] +
        repo_data['pr_reviews'] +
        repo_data['issue_comments'] +
        repo_data['commit_comments']
    )

    summary[repo] = repo_data
    print(f"  TOTAL COMMENTS: {repo_data['total_comments']}", file=sys.stderr, flush=True)

    # Save summary incrementally
    with open(os.path.join(OUT, "scan_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

# Final summary
print(f"\n{'=' * 60}", file=sys.stderr)
print(f"SCAN COMPLETE", file=sys.stderr)
print(f"{'=' * 60}", file=sys.stderr)

total_prs = sum(s['prs'] for s in summary.values())
total_issues = sum(s['issues'] for s in summary.values())
total_all_comments = sum(s['total_comments'] for s in summary.values())
total_inline = sum(s['pr_inline_comments'] for s in summary.values())
total_general = sum(s['pr_general_comments'] for s in summary.values())
total_reviews = sum(s['pr_reviews'] for s in summary.values())
total_issue_comments = sum(s['issue_comments'] for s in summary.values())
total_commit_comments = sum(s['commit_comments'] for s in summary.values())

print(f"  Repos scanned: {len(summary)}", file=sys.stderr)
print(f"  Total PRs: {total_prs}", file=sys.stderr)
print(f"  Total issues: {total_issues}", file=sys.stderr)
print(f"  Total PR inline comments: {total_inline}", file=sys.stderr)
print(f"  Total PR general comments: {total_general}", file=sys.stderr)
print(f"  Total PR reviews: {total_reviews}", file=sys.stderr)
print(f"  Total issue comments: {total_issue_comments}", file=sys.stderr)
print(f"  Total commit comments: {total_commit_comments}", file=sys.stderr)
print(f"  GRAND TOTAL COMMENTS: {total_all_comments}", file=sys.stderr)
print(f"{'=' * 60}", file=sys.stderr)