#!/usr/bin/env python3
"""
validate_real_prs.py — Run the judge against real nuri-expo PR diffs.

Loads the kodamoa-bench dataset (119 PRs with diffs + 948 review comments),
runs static rules against each PR's added code, and compares findings to
the ground-truth review comments (mapped to taxonomy categories).

Reports: precision, recall, F1 (micro-averaged).
"""

import json, re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import load_rubric, strip_comments, run_static_checks, parse_diff

DATASET = "/tmp/kodamoa-bench/pr-sim/data/dataset-full.json"
RUBRIC = os.path.join(os.path.dirname(__file__), "rubric_v2.json")

# ============================================================
# 1. Load dataset
# ============================================================
print("Loading dataset...", file=sys.stderr)
with open(DATASET) as f:
    prs = json.load(f)
print(f"Loaded {len(prs)} PRs with {sum(len(p.get('reviewComments',[])) for p in prs)} comments", file=sys.stderr)

# ============================================================
# 2. Load rubric and extract static rules
# ============================================================
rubric = load_rubric(RUBRIC)
static_rules = []
for cat_name, cat in rubric['categories'].items():
    for rule in cat['rules']:
        if rule.get('check_type') == 'static':
            static_rules.append(rule)
print(f"Static rules: {len(static_rules)}", file=sys.stderr)

# ============================================================
# 3. Map review comments to taxonomy categories
# ============================================================
# Build keyword → category mapping (same as taxonomy analysis)
taxonomy_keywords = {
    'race_condition': [r'\brace\b', r'\bracing\b', r'\bconcurrent\b', r'\bparallel\b',
        r'\bcancel\w*\b', r'\babort\w*\b', r'\bin-flight\b', r'\bdispose\b',
        r'\bunmount\b', r'floating.*promise', r'unhandled.*promise',
        r'\bmutex\b', r'\bdeadlock\b', r'\batomic\b', r'\bleak\b',
        r'orphan.*listener', r'subscription.*not.*clean',
        r'\block\b', r'\blocked\b', r'\blocking\b'],
    'stale_state': [r'\bstale\b', r'\bcache[ds]?\b', r'\boutdated\b',
        r'async gap', r'revalidat\w*', r'ghost balance',
        r'missing dependency', r'dependency array',
        r'closure.*stale', r'\brefetch\b'],
    'silent_catch': [r'silent.*catch', r'empty.*catch', r'catch\s*\{\s*\}',
        r'\bswallow\b', r'void.*promise', r'ignored.*error'],
    'accessibility': [r'accessib', r'\baria\b', r'a11y', r'screen reader',
        r'focus.*state', r'outline.*none', r'zoom.*disable',
        r'maximum-scale', r'user-scalable', r'WCAG'],
    'ota_native_boundary': [r'\bOTA\b', r'over-the-air', r'native.*module',
        r'binary.*update', r'OTA.*safe', r'native.*dependency',
        r'\bfingerprint\b', r'binary.*version'],
    'security_crypto': [r'\bsecurity\b', r'vulnerab', r'\bexploit\b',
        r'key.*exposure', r'nonce.*reuse', r'Math\.random',
        r'crypto.*wrong', r'signature.*verify', r'timing.*attack',
        r'\beval\b', r'innerHTML', r'localStorage.*key',
        r'localStorage.*secret', r'localStorage.*seed'],
    'error_handling': [r'error.*propagation', r'error.*handling',
        r'propagat.*error', r'throw.*error', r're-?throw',
        r'error.*boundary', r'try.*catch.*missing'],
    'data_integrity': [r'data.*integrity', r'address.*source',
        r'default.*address', r'silent.*downgrade', r'stale.*armed',
        r'fatal.*operation', r'\bdedup\b', r'duplicate.*request',
        r'\bunify\b', r'consisten\w*'],
    'dead_code': [r'dead.*code', r'unreachable', r'unused.*import',
        r'unused.*variable', r'unused.*function', r'remove.*unused',
        r'orphan', r'duplicate.*code', r'redundant'],
    'type_safety': [r'type.*any', r'as any', r'type.*cast',
        r'typescript.*error', r'type.*mismatch', r'enum.*wrong',
        r'invalid.*enum', r'BIOMETRIC_STRONG', r'does not exist'],
    'performance': [r'\bperformance\b', r'\bslow\b', r'\boptimize\b',
        r'memory.*leak', r're-?render', r'\bmemo\b',
        r'bundle.*size', r'unnecessary.*init'],
    'webview_sandbox': [r'\bsandbox\b', r'iframe.*sandbox',
        r'webview.*sandbox', r'\bCSP\b', r'content.*security.*policy'],
    'missing_zeroize': [r'zeroiz\w*', r'wipe.*memory', r'clear.*sensitive',
        r'sensitive.*data', r'Uint8Array.*not.*wiped', r'secure.*wipe'],
    'localstorage_secret': [r'localStorage.*key', r'localStorage.*secret',
        r'localStorage.*seed', r'localStorage.*password',
        r'localStorage.*mnemonic', r'localStorage.*private'],
}

def classify_comment(body):
    """Classify a review comment into a taxonomy category. Returns category name or None."""
    text = body[:500].lower()
    for cat, keywords in taxonomy_keywords.items():
        for kw in keywords:
            if re.search(kw.lower(), text):
                return cat
    return None

# ============================================================
# 4. Map static rules to taxonomy categories
# ============================================================
rule_to_category = {}
for cat_name, cat in rubric['categories'].items():
    for rule in cat['rules']:
        rule_to_category[rule['id']] = cat_name

# ============================================================
# 5. Run validation
# ============================================================
print(f"\n{'='*60}", file=sys.stderr)
print(f"RUNNING VALIDATION AGAINST {len(prs)} REAL PRs", file=sys.stderr)
print(f"{'='*60}", file=sys.stderr)

results = []
total_gt = 0          # ground truth findings (comments in categories we can detect)
total_judge = 0       # judge findings (static rule matches)
total_matched = 0     # judge findings that match a ground truth comment

for i, pr in enumerate(prs, 1):
    pr_num = pr['number']
    pr_title = pr.get('title', '')
    diff = pr.get('diff', '')
    comments = pr.get('reviewComments', [])

    # Parse diff → get added code per file
    added_code = parse_diff(diff)
    if not added_code:
        continue

    # Run static rules on added code
    judge_findings = []
    for fpath, code in added_code.items():
        ext = os.path.splitext(fpath)[1].lower()
        clean = strip_comments(code, ext)
        findings = run_static_checks(fpath, clean, static_rules)
        judge_findings.extend(findings)

    # Classify ground truth comments
    gt_categories = set()
    for c in comments:
        cat = classify_comment(c.get('body', ''))
        if cat:
            gt_categories.add(cat)

    # Map judge findings to categories
    judge_categories = set()
    for f in judge_findings:
        cat = rule_to_category.get(f.rule_id)
        if cat:
            judge_categories.add(cat)

    # Match: categories that appear in BOTH ground truth and judge findings
    matched = gt_categories & judge_categories

    total_gt += len(gt_categories)
    total_judge += len(judge_categories)
    total_matched += len(matched)

    results.append({
        'pr_number': pr_num,
        'pr_title': pr_title[:60],
        'gt_categories': sorted(gt_categories),
        'judge_categories': sorted(judge_categories),
        'matched': sorted(matched),
        'precision': len(matched) / len(judge_categories) if judge_categories else 0,
        'recall': len(matched) / len(gt_categories) if gt_categories else 0,
        'judge_finding_count': len(judge_findings),
        'gt_comment_count': len(comments),
    })

    if i % 20 == 0:
        print(f"  Processed {i}/{len(prs)} PRs...", file=sys.stderr)

# ============================================================
# 6. Report results
# ============================================================
precision = total_matched / total_judge if total_judge > 0 else 0
recall = total_matched / total_gt if total_gt > 0 else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

print(f"\n{'='*60}")
print(f"VALIDATION RESULTS — STATIC RULES vs REAL REVIEW COMMENTS")
print(f"{'='*60}")
print(f"  PRs analyzed:           {len(results)}")
print(f"  Ground truth categories: {total_gt} (from {sum(r['gt_comment_count'] for r in results)} comments)")
print(f"  Judge findings:         {total_judge} (from {sum(r['judge_finding_count'] for r in results)} static matches)")
print(f"  Matched:                {total_matched}")
print(f"")
print(f"  Precision: {precision:.1%}  (of categories the judge flagged, how many were real)")
print(f"  Recall:    {recall:.1%}  (of real categories, how many the judge caught)")
print(f"  F1:        {f1:.1%}")
print(f"{'='*60}")

# Per-PR breakdown for first 10
print(f"\nPer-PR breakdown (first 15):")
print(f"  {'PR':>6}  {'GT cats':>8}  {'Judge':>7}  {'Match':>6}  {'P':>5}  {'R':>5}  Title")
for r in results[:15]:
    print(f"  #{r['pr_number']:4d}  {len(r['gt_categories']):8d}  {len(r['judge_categories']):7d}  {len(r['matched']):6d}  {r['precision']:.0%}  {r['recall']:.0%}  {r['pr_title'][:40]}")

# Category-level analysis
print(f"\n{'='*60}")
print(f"CATEGORY-LEVEL ANALYSIS")
print(f"{'='*60}")
cat_gt = collections.Counter()
cat_judge = collections.Counter()
cat_matched = collections.Counter()

for r in results:
    for c in r['gt_categories']:
        cat_gt[c] += 1
    for c in r['judge_categories']:
        cat_judge[c] += 1
    for c in r['matched']:
        cat_matched[c] += 1

print(f"  {'Category':30s} {'GT':>5} {'Judge':>6} {'Match':>5} {'P':>5} {'R':>5}")
for cat in sorted(cat_gt.keys() | cat_judge.keys(), key=lambda c: -(cat_gt.get(c, 0))):
    gt = cat_gt.get(cat, 0)
    j = cat_judge.get(cat, 0)
    m = cat_matched.get(cat, 0)
    p = m / j if j > 0 else 0
    r = m / gt if gt > 0 else 0
    print(f"  {cat:30s} {gt:5d} {j:6d} {m:5d} {p:5.0%} {r:5.0%}")

# Save full results
output_path = os.path.join(os.path.dirname(__file__), "full-scan", "validation_results.json")
with open(output_path, 'w') as f:
    json.dump({
        'summary': {
            'prs_analyzed': len(results),
            'total_gt': total_gt,
            'total_judge': total_judge,
            'total_matched': total_matched,
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
        },
        'per_pr': results,
        'per_category': {
            cat: {
                'gt': cat_gt.get(cat, 0),
                'judge': cat_judge.get(cat, 0),
                'matched': cat_matched.get(cat, 0),
            }
            for cat in sorted(cat_gt.keys() | cat_judge.keys())
        },
    }, f, indent=2)
print(f"\nFull results saved to {output_path}")