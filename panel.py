#!/usr/bin/env python3
"""
panel.py — Blind panel review on top of the deterministic judge.

Simulates an anonymous human review committee: submissions are blinded
(content-hash labels, author names sealed), a panel of independent judges
(LLMs, agents, or humans) reviews every submission holistically AND against
the rubric's LLM rules, and the results are aggregated with the median so a
single outlier judge cannot swing a verdict.

Two opinions per submission:
  1. Deterministic + rubric score (judge.py, panel-median rule scores)
  2. Holistic panel opinion (0-100, "how would a strict senior reviewer rate this")
Plus: per-rule disagreement stats and pairwise ranking agreement between judges.

Workflow:
  # 1. Prepare a blind packet (mapping is written SEALED to a separate path)
  python3 panel.py prepare \
      --issue tasks/task-001-secure-key-storage/issue.md \
      --solutions runs/agent-x/run1/ runs/agent-y/run1/ test_fixtures/solution_bad/ \
      --rubric rubric_v2.json --out panel_run/ --mapping-out /somewhere/sealed/mapping.json

  # 2. Give panel_run/packet.md to each judge independently. Each judge writes
  #    a JSON verdict (format documented inside the packet).

  # 3. Aggregate
  python3 panel.py aggregate --dir panel_run/ \
      --mapping /somewhere/sealed/mapping.json \
      --judges judge1.json judge2.json judge3.json \
      --rubric rubric_v2.json --report PANEL_REPORT.md

Stdlib only. Blinding is deterministic (content hash), so prepare is
reproducible: same solutions in, same labels out.
"""

import argparse
import hashlib
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judge import load_rubric, judge_solution, get_scoring, load_solution_files, result_to_dict

# ==================== Blinding ====================

def content_fingerprint(files: dict) -> str:
    """Deterministic fingerprint of a submission's content (paths + bytes)."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode())
        h.update(b'\x00')
        h.update(files[path].encode())
        h.update(b'\x00')
    return h.hexdigest()

def blind_submissions(named_solutions):
    """[(name, files)] → (submissions {label: files}, mapping {label: name}).
    Labels are assigned in fingerprint order, so they are stable across runs
    and carry no trace of author name or argument order."""
    ordered = sorted(named_solutions, key=lambda ns: content_fingerprint(ns[1]))
    submissions, mapping = {}, {}
    for i, (name, files) in enumerate(ordered):
        label = f"SUBMISSION-{chr(ord('A') + i)}"
        submissions[label] = files
        mapping[label] = name
    return submissions, mapping

# ==================== Packet ====================

JUDGE_INSTRUCTIONS = """\
## Your role

You are one judge on a blind review panel. You do not know who or what wrote
these submissions (human, LLM, junior, senior) and you must not try to guess
or let style hints influence you. Judge only the code in front of you, as a
strict senior reviewer at a Bitcoin wallet company would.

Review each submission INDEPENDENTLY — do not let one submission's quality
recalibrate your standards for another. Penalize only what you can point to in
the code; cite lines in your explanations.

## What to produce

For EVERY submission:
1. `holistic_score` (0-100, integer): your overall verdict as a reviewer.
   Calibration: 90+ = ship it, exemplary; 70-89 = mergeable after nits;
   40-69 = needs significant rework; <40 = reject. Be strict: 100 means you
   found nothing to improve.
2. `verdict`: "PASS" if you would approve the PR, else "FAIL".
3. `strengths` / `weaknesses`: short bullet strings, specific.
4. `rule_deductions`: for each rubric rule below that the submission violates
   (fully or partially), an entry {"rule_id", "score", "explanation"} where
   score is 0.0 (clear violation) to 1.0 (no issue). ONLY list rules you
   deduct on (score < 1.0); unlisted rules count as 1.0. If a rule has no
   applicable surface in the submission, do not list it.

Finally, `ranking`: all submission labels, best first.

## Response format (return EXACTLY this JSON shape)

{
  "judge_id": "<your name/model>",
  "reviews": {
    "SUBMISSION-A": {
      "holistic_score": 72,
      "verdict": "PASS",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "rule_deductions": [
        {"rule_id": "RACE-005", "score": 0.4, "explanation": "lines 12-30: ..."}
      ]
    }
  },
  "ranking": ["SUBMISSION-B", "SUBMISSION-A"]
}
"""

def build_packet(issue: str, submissions: dict, rubric: dict) -> str:
    """Self-contained blind review packet for one judge."""
    lines = ["# Blind Review Packet\n"]
    lines.append(JUDGE_INSTRUCTIONS)

    lines.append("## The task the submissions were asked to solve\n")
    lines.append(issue.strip() + "\n")

    lines.append("## Rubric rules (deduct against these)\n")
    for cat_name, cat in rubric['categories'].items():
        for rule in cat['rules']:
            if rule.get('check_type') == 'llm':
                lines.append(f"- **{rule['id']}** [{rule['severity']}] {rule['name']}: {rule['description']}")
    lines.append("")

    lines.append("## Submissions\n")
    for label in sorted(submissions):
        lines.append(f"### {label}\n")
        for path in sorted(submissions[label]):
            lines.append(f"`{path}`:")
            lines.append("```")
            lines.append(submissions[label][path].rstrip('\n'))
            lines.append("```\n")
    return "\n".join(lines) + "\n"

# ==================== Aggregation ====================

def median_rule_scores(judge_reviews, label: str):
    """Median score per rule across judges for one submission.
    A judge who didn't list a rule implicitly scored it 1.0."""
    rule_ids = set()
    for jr in judge_reviews:
        for d in jr['reviews'].get(label, {}).get('rule_deductions', []):
            rule_ids.add(d['rule_id'])

    merged = []
    disagreements = []
    for rid in sorted(rule_ids):
        per_judge = []
        explanations = []
        for jr in judge_reviews:
            listed = {d['rule_id']: d for d in jr['reviews'].get(label, {}).get('rule_deductions', [])}
            if rid in listed:
                score = max(0.0, min(1.0, float(listed[rid].get('score', 1.0))))
                per_judge.append(score)
                if listed[rid].get('explanation'):
                    explanations.append(f"{jr.get('judge_id', '?')}: {listed[rid]['explanation']}")
            else:
                per_judge.append(1.0)
        med = statistics.median(per_judge)
        spread = max(per_judge) - min(per_judge)
        merged.append({'rule_id': rid, 'score': med,
                       'explanation': ' | '.join(explanations)[:400]})
        if spread > 0.3:
            disagreements.append({'rule_id': rid, 'scores': per_judge, 'spread': round(spread, 2)})
    return merged, disagreements

def ranking_agreement(rankings):
    """Mean pairwise agreement on ordered pairs across judges (1.0 = identical rankings)."""
    if len(rankings) < 2:
        return 1.0
    def ordered_pairs(rank):
        pos = {label: i for i, label in enumerate(rank)}
        labels = sorted(pos)
        return {(a, b): pos[a] < pos[b] for a in labels for b in labels if a < b}
    agreements = []
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            pi, pj = ordered_pairs(rankings[i]), ordered_pairs(rankings[j])
            common = set(pi) & set(pj)
            if common:
                agreements.append(sum(pi[k] == pj[k] for k in common) / len(common))
    return round(sum(agreements) / len(agreements), 3) if agreements else 1.0

def aggregate_panel(issue, submissions, mapping, judge_reviews, rubric):
    """Compute the two opinions per submission + agreement stats."""
    scoring = get_scoring(rubric)
    rows = []
    all_disagreements = {}

    for label in sorted(submissions):
        merged, disagreements = median_rule_scores(judge_reviews, label)
        all_disagreements[label] = disagreements

        result = judge_solution(rubric, issue, submissions[label], label,
                                static_only=True, external_assessments=merged)

        holistic = [jr['reviews'][label]['holistic_score']
                    for jr in judge_reviews if label in jr['reviews']]
        verdict_votes = [jr['reviews'][label].get('verdict', 'FAIL')
                         for jr in judge_reviews if label in jr['reviews']]
        rows.append({
            'label': label,
            'author': mapping.get(label, '?'),
            'rubric_panel_score': result.total_score,
            'rubric_verdict': result.verdict,
            'hard_gate_capped': result.hard_gate_capped,
            'holistic_median': statistics.median(holistic) if holistic else None,
            'holistic_min': min(holistic) if holistic else None,
            'holistic_max': max(holistic) if holistic else None,
            'panel_pass_votes': sum(1 for v in verdict_votes if v == 'PASS'),
            'panel_votes': len(verdict_votes),
            'result': result_to_dict(result),
        })

    rows.sort(key=lambda r: -(r['rubric_panel_score']))
    return {
        'rows': rows,
        'disagreements': all_disagreements,
        'ranking_agreement': ranking_agreement([jr.get('ranking', []) for jr in judge_reviews]),
        'judges': [jr.get('judge_id', '?') for jr in judge_reviews],
        'pass_threshold': scoring['pass_threshold'],
    }

def render_panel_report(agg, judge_reviews) -> str:
    lines = ["# Blind Panel Report\n"]
    lines.append(f"Judges: {', '.join(agg['judges'])} — "
                 f"pairwise ranking agreement: **{agg['ranking_agreement']}** (1.0 = identical orderings)\n")

    lines.append("## Two opinions per submission (unblinded)\n")
    lines.append("| Label | Author | Rubric+panel score | Verdict | Holistic median | Holistic range | Panel PASS votes |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in agg['rows']:
        cap = " (capped)" if r['hard_gate_capped'] else ""
        lines.append(f"| {r['label']} | {r['author']} | {r['rubric_panel_score']}/100{cap} | {r['rubric_verdict']} "
                     f"| {r['holistic_median']} | {r['holistic_min']}–{r['holistic_max']} "
                     f"| {r['panel_pass_votes']}/{r['panel_votes']} |")
    lines.append("")

    lines.append("## Judge disagreements (rule score spread > 0.3)\n")
    any_dis = False
    for label, dis in agg['disagreements'].items():
        for d in dis:
            any_dis = True
            lines.append(f"- **{label} / {d['rule_id']}**: scores {d['scores']} (spread {d['spread']})")
    if not any_dis:
        lines.append("None — judges agreed within 0.3 on every rule.")
    lines.append("")

    lines.append("## Individual judge opinions\n")
    for jr in judge_reviews:
        lines.append(f"### {jr.get('judge_id', '?')}\n")
        lines.append(f"Ranking: {' > '.join(jr.get('ranking', []))}\n")
        for label in sorted(jr.get('reviews', {})):
            rev = jr['reviews'][label]
            lines.append(f"**{label}** — holistic {rev.get('holistic_score')}/100, {rev.get('verdict')}")
            for w in rev.get('weaknesses', [])[:5]:
                lines.append(f"  - {w}")
            lines.append("")
    return "\n".join(lines) + "\n"

# ==================== CLI ====================

def cmd_prepare(args):
    rubric = load_rubric(args.rubric)
    with open(args.issue) as f:
        issue = f.read()

    named = []
    for spath in args.solutions:
        files = load_solution_files(spath)
        if not files:
            print(f"WARNING: no files in {spath}", file=sys.stderr)
            continue
        name = os.path.normpath(spath)
        named.append((name, files))

    submissions, mapping = blind_submissions(named)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'packet.md'), 'w') as f:
        f.write(build_packet(issue, submissions, rubric))
    with open(os.path.join(args.out, 'submissions.json'), 'w') as f:
        json.dump({'issue': issue, 'submissions': submissions}, f, indent=2)

    mapping_path = args.mapping_out or os.path.join(args.out, 'mapping.SEALED.json')
    with open(mapping_path, 'w') as f:
        json.dump(mapping, f, indent=2)

    print(f"Packet: {os.path.join(args.out, 'packet.md')} ({len(submissions)} blind submissions)")
    print(f"SEALED mapping: {mapping_path} — do NOT show this to judges.")

def cmd_aggregate(args):
    rubric = load_rubric(args.rubric)
    with open(os.path.join(args.dir, 'submissions.json')) as f:
        bundle = json.load(f)
    mapping_path = args.mapping or os.path.join(args.dir, 'mapping.SEALED.json')
    with open(mapping_path) as f:
        mapping = json.load(f)

    judge_reviews = []
    for jpath in args.judges:
        with open(jpath) as f:
            judge_reviews.append(json.load(f))

    agg = aggregate_panel(bundle['issue'], bundle['submissions'], mapping, judge_reviews, rubric)
    report = render_panel_report(agg, judge_reviews)

    with open(args.report, 'w') as f:
        f.write(report)
    print(f"Panel report: {args.report}")

    if args.json_out:
        slim = {k: agg[k] for k in ('disagreements', 'ranking_agreement', 'judges', 'pass_threshold')}
        slim['rows'] = [{k: v for k, v in r.items() if k != 'result'} for r in agg['rows']]
        with open(args.json_out, 'w') as f:
            json.dump(slim, f, indent=2)
        print(f"Panel JSON: {args.json_out}")

def main():
    parser = argparse.ArgumentParser(description='Blind panel review for coding-task solutions.')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('prepare', help='Blind the submissions and build the judge packet')
    p.add_argument('--issue', required=True)
    p.add_argument('--solutions', nargs='+', required=True)
    p.add_argument('--rubric', default='rubric_v2.json')
    p.add_argument('--out', required=True, help='Output directory for packet + submissions')
    p.add_argument('--mapping-out', help='Write the SEALED label→author mapping here (keep away from judges)')
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser('aggregate', help='Aggregate judge verdicts into a panel report')
    p.add_argument('--dir', required=True, help='Directory produced by prepare')
    p.add_argument('--mapping', help='Path to the sealed mapping (if not in --dir)')
    p.add_argument('--judges', nargs='+', required=True, help='Judge response JSON files')
    p.add_argument('--rubric', default='rubric_v2.json')
    p.add_argument('--report', required=True, help='Write the markdown panel report here')
    p.add_argument('--json-out', help='Also write aggregate data as JSON')
    p.set_defaults(fn=cmd_aggregate)

    args = parser.parse_args()
    args.fn(args)

if __name__ == '__main__':
    main()
