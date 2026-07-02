#!/usr/bin/env python3
"""
judge.py — Automated judge for coding-task solutions.

Judges multiple agent solutions against a rubric derived from real code-review
practices. Supports static analysis (regex) and LLM-assisted review.

Usage:
    # Judge multiple solutions to the same issue
    python judge.py --issue issue.md --solutions agent_a/ agent_b/ agent_c/ --rubric rubric.json

    # Judge from a task JSON file (multiple solutions)
    python judge.py --task task.json --rubric rubric.json --output results.json

    # Static-only (no LLM API key needed)
    python judge.py --task task.json --rubric rubric.json --static-only

Architecture (3 layers):
    Layer 1: Static Analysis (regex-based, fast, deterministic)
    Layer 2: LLM Verification (per-finding, eliminates false positives) [optional]
    Layer 3: LLM Holistic Review (per-solution, scores LLM-only rules) [optional]

LLM Provider:
    Set JUDGE_LLM_PROVIDER and corresponding API key env var:
      - openai:    OPENAI_API_KEY, model: gpt-4o (default)
      - anthropic: ANTHROPIC_API_KEY, model: claude-sonnet-4-20250514
      - ollama:    OLLAMA_API_KEY (if cloud), model: glm-5.2 / kimi-k2.6 etc.
      - openrouter: OPENROUTER_API_KEY, model: any
    Or use --static-only to skip LLM entirely.
"""

import json
import re
import argparse
import sys
import os
import subprocess
import textwrap
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path

# ==================== Data Models ====================

@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: str
    description: str
    file: str
    line: int
    match: str = ""
    source: str = "static"  # "static" or "llm"
    explanation: str = ""

@dataclass
class CategoryResult:
    name: str
    score: float = 100.0
    weight: float = 0.0
    hard_gate: bool = False
    findings: List[Finding] = field(default_factory=list)
    llm_scores: List[dict] = field(default_factory=list)
    hard_gate_triggered: bool = False

@dataclass
class SolutionResult:
    agent_id: str
    total_score: float = 0.0
    verdict: str = "FAIL"
    category_results: Dict[str, CategoryResult] = field(default_factory=dict)
    all_findings: List[Finding] = field(default_factory=list)
    files_analyzed: int = 0
    lines_analyzed: int = 0

# ==================== Rubric Loader ====================

def load_rubric(path: str) -> dict:
    with open(path, 'r') as f:
        rubric = json.load(f)
    # Validate
    if 'categories' not in rubric:
        raise ValueError(f"Rubric missing 'categories' key")
    if 'scoring' not in rubric:
        raise ValueError(f"Rubric missing 'scoring' key")
    for cat_name, cat in rubric['categories'].items():
        if 'rules' not in cat:
            raise ValueError(f"Category '{cat_name}' missing 'rules'")
        if 'weight' not in cat:
            raise ValueError(f"Category '{cat_name}' missing 'weight'")
    return rubric

# ==================== Code Utilities ====================

def strip_comments(code: str, file_ext: str) -> str:
    """Strip comments from code to avoid false positives in regex matching.
    Uses a char-by-char state machine that tracks string literals (single,
    double, template) to avoid stripping comments inside strings. This
    prevents corruption of URLs like https://example.com and strings
    containing /* or //."""
    if file_ext in ('.ts', '.tsx', '.js', '.jsx', '.json', '.go', '.java', '.c', '.cpp', '.h', '.rs', '.swift'):
        result = []
        i = 0
        n = len(code)
        in_single = False   # '...'
        in_double = False   # "..."
        in_template = False # `...`
        in_line_comment = False   # // ...
        in_block_comment = False  # /* ... */
        escape = False

        while i < n:
            ch = code[i]
            nxt = code[i + 1] if i + 1 < n else ''

            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                    result.append(ch)
                i += 1
                continue

            if in_block_comment:
                if ch == '*' and nxt == '/':
                    in_block_comment = False
                    i += 2  # skip */
                    continue
                i += 1
                continue

            if in_single:
                if ch == '\\':
                    escape = True
                    result.append(ch)
                elif ch == "'":
                    in_single = False
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

            if in_double:
                if ch == '\\':
                    escape = True
                    result.append(ch)
                elif ch == '"':
                    in_double = False
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

            if in_template:
                if ch == '\\':
                    escape = True
                    result.append(ch)
                elif ch == '`':
                    in_template = False
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

            # Not in any string or comment
            if ch == '/' and nxt == '/':
                in_line_comment = True
                i += 2
                continue
            elif ch == '/' and nxt == '*':
                in_block_comment = True
                i += 2
                continue
            elif ch == "'":
                in_single = True
                result.append(ch)
            elif ch == '"':
                in_double = True
                result.append(ch)
            elif ch == '`':
                in_template = True
                result.append(ch)
            else:
                result.append(ch)
            i += 1

        return ''.join(result)

    elif file_ext in ('.py',):
        # Python: strip # comments (string-aware) and triple-quoted docstrings
        result = []
        i = 0
        n = len(code)
        in_single = False   # '...'
        in_double = False   # "..."
        in_triple_single = False  # '''...'''
        in_triple_double = False  # """..."""
        in_line_comment = False
        escape = False

        while i < n:
            ch = code[i]
            nxt = code[i + 1] if i + 1 < n else ''
            nxt2 = code[i + 2] if i + 2 < n else ''

            if escape:
                result.append(ch)
                escape = False
                i += 1
                continue

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                    result.append(ch)
                i += 1
                continue

            if in_triple_single:
                if ch == "'" and nxt == "'" and nxt2 == "'":
                    in_triple_single = False
                    result.extend("'''")
                    i += 3
                    continue
                i += 1
                continue

            if in_triple_double:
                if ch == '"' and nxt == '"' and nxt2 == '"':
                    in_triple_double = False
                    result.extend('"""')
                    i += 3
                    continue
                i += 1
                continue

            if in_single:
                if ch == '\\':
                    escape = True
                    result.append(ch)
                elif ch == "'":
                    in_single = False
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

            if in_double:
                if ch == '\\':
                    escape = True
                    result.append(ch)
                elif ch == '"':
                    in_double = False
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

            # Check for triple-quoted strings first
            if ch == "'" and nxt == "'" and nxt2 == "'":
                in_triple_single = True
                i += 3
                continue
            if ch == '"' and nxt == '"' and nxt2 == '"':
                in_triple_double = True
                i += 3
                continue

            if ch == '#':
                in_line_comment = True
                i += 1
                continue
            elif ch == "'":
                in_single = True
                result.append(ch)
            elif ch == '"':
                in_double = True
                result.append(ch)
            else:
                result.append(ch)
            i += 1

        return ''.join(result)

    elif file_ext in ('.md', '.markdown'):
        return code

    return code

def load_solution_files(path: str) -> Dict[str, str]:
    """Load all source files from a path (file or directory).
    Returns dict of {relative_path: content}."""
    files = {}
    source_exts = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp', '.h',
                   '.go', '.rs', '.swift', '.rb', '.php', '.kt', '.scala', '.clj',
                   '.md', '.markdown', '.html', '.css', '.scss', '.vue', '.svelte',
                   '.yaml', '.yml', '.json', '.toml', '.sh', '.bash', '.sql'}

    p = Path(path)
    if p.is_file():
        try:
            content = p.read_text(encoding='utf-8', errors='replace')
            files[p.name] = content
        except:
            pass
    elif p.is_dir():
        for root, _, filenames in os.walk(p):
            # Skip common non-source directories
            parts = Path(root).parts
            if any(skip in parts for skip in ['node_modules', '.git', 'dist', 'build', '__pycache__', '.next']):
                continue
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in source_exts:
                    fpath = os.path.join(root, fname)
                    relpath = os.path.relpath(fpath, p)
                    try:
                        content = open(fpath, encoding='utf-8', errors='replace').read()
                        files[relpath] = content
                    except:
                        pass
    return files

def parse_diff(diff_text: str) -> Dict[str, str]:
    """Parse a unified diff and return {filepath: added_content}.
    Only includes added lines (+ lines), not context."""
    files = {}
    current_file = None
    current_lines = []

    for line in diff_text.split('\n'):
        if line.startswith('+++ b/'):
            if current_file and current_lines:
                files[current_file] = '\n'.join(current_lines)
            current_file = line[6:]
            current_lines = []
        elif line.startswith('+++ '):
            if current_file and current_lines:
                files[current_file] = '\n'.join(current_lines)
            current_file = line[4:]
            current_lines = []
        elif line.startswith('+') and not line.startswith('+++'):
            current_lines.append(line[1:])
        elif line.startswith('@@') and current_file:
            # New hunk — keep accumulating
            pass

    if current_file and current_lines:
        files[current_file] = '\n'.join(current_lines)

    return files

# ==================== Layer 1: Static Analysis ====================

def run_static_checks(file_path: str, code: str, rules: List[dict]) -> List[Finding]:
    """Run regex-based static checks against a single file."""
    findings = []
    ext = os.path.splitext(file_path)[1].lower()

    # Strip comments to avoid false positives
    clean_code = strip_comments(code, ext)

    for rule in rules:
        if rule.get('check_type') != 'static':
            continue
        pattern = rule.get('pattern')
        if not pattern:
            continue

        try:
            for match in re.finditer(pattern, clean_code, re.MULTILINE | re.IGNORECASE):
                line_num = clean_code.count('\n', 0, match.start()) + 1
                findings.append(Finding(
                    rule_id=rule['id'],
                    rule_name=rule['name'],
                    severity=rule['severity'],
                    description=rule['description'],
                    file=file_path,
                    line=line_num,
                    match=match.group(0)[:100],
                    source='static',
                ))
        except re.error as e:
            # Invalid regex — skip this rule
            print(f"  WARNING: Invalid regex in {rule['id']}: {e}", file=sys.stderr)

    return findings

def run_linters(file_path: str, code: str) -> List[Finding]:
    """Run available linters (eslint, tsc) if configured. Stub for now."""
    # TODO: integrate eslint --format json, tsc --noEmit, swiftlint, clippy
    return []

# ==================== Layer 2+3: LLM Analysis ====================

class LLMBackend:
    """Pluggable LLM backend. Supports OpenAI, Anthropic, Ollama, OpenRouter."""

    def __init__(self):
        self.provider = os.environ.get('JUDGE_LLM_PROVIDER', '').lower()
        self.model = os.environ.get('JUDGE_LLM_MODEL', '')
        self.api_key = (
            os.environ.get('OPENAI_API_KEY') or
            os.environ.get('ANTHROPIC_API_KEY') or
            os.environ.get('OPENROUTER_API_KEY') or
            os.environ.get('OLLAMA_API_KEY') or
            ''
        )
        self.base_url = os.environ.get('JUDGE_LLM_BASE_URL', '')
        self.available = False

        if not self.provider:
            # Auto-detect from available keys
            if os.environ.get('OPENAI_API_KEY'):
                self.provider = 'openai'
                self.api_key = os.environ['OPENAI_API_KEY']
                self.model = self.model or 'gpt-4o'
                self.available = True
            elif os.environ.get('ANTHROPIC_API_KEY'):
                self.provider = 'anthropic'
                self.api_key = os.environ['ANTHROPIC_API_KEY']
                self.model = self.model or 'claude-sonnet-4-20250514'
                self.available = True
            elif os.environ.get('OPENROUTER_API_KEY'):
                self.provider = 'openrouter'
                self.api_key = os.environ['OPENROUTER_API_KEY']
                self.model = self.model or 'anthropic/claude-sonnet-4'
                self.available = True
            elif os.environ.get('OLLAMA_API_KEY') or os.environ.get('OLLAMA_BASE_URL'):
                self.provider = 'ollama'
                self.api_key = os.environ.get('OLLAMA_API_KEY', '')
                self.base_url = self.base_url or os.environ.get('OLLAMA_BASE_URL', 'https://api.ollama.cloud/v1')
                self.model = self.model or 'glm-5.2'
                self.available = True
        elif self.provider and self.api_key:
            self.available = True
            if not self.model:
                defaults = {'openai': 'gpt-4o', 'anthropic': 'claude-sonnet-4-20250514',
                           'ollama': 'glm-5.2', 'openrouter': 'anthropic/claude-sonnet-4'}
                self.model = defaults.get(self.provider, 'gpt-4o')

        if self.available:
            # Set default base URLs
            if not self.base_url:
                self.base_url = {
                    'openai': 'https://api.openai.com/v1',
                    'anthropic': 'https://api.anthropic.com/v1',
                    'openrouter': 'https://openrouter.ai/api/v1',
                }.get(self.provider, '')

    def call(self, prompt: str, system: str = "You are an expert code reviewer.", temperature: float = 0.0) -> dict:
        """Call the LLM and return parsed JSON dict. Returns {'score': float, 'explanation': str}."""
        if not self.available:
            return {"score": 0.5, "explanation": "LLM not configured — neutral score."}

        try:
            if self.provider in ('openai', 'openrouter', 'ollama'):
                return self._call_openai_compatible(prompt, system, temperature)
            elif self.provider == 'anthropic':
                return self._call_anthropic(prompt, system, temperature)
        except Exception as e:
            print(f"  LLM call error: {e}", file=sys.stderr)
            return {"score": 0.5, "explanation": f"LLM call failed: {e}"}

    def _call_openai_compatible(self, prompt: str, system: str, temperature: float) -> dict:
        """OpenAI-compatible API (OpenAI, OpenRouter, Ollama Cloud)."""
        import urllib.request, urllib.error

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.provider == 'openrouter':
            headers["HTTP-Referer"] = "https://github.com/nuri-com/judicative"
            headers["X-Title"] = "Judicative Code Judge"

        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 8000,
        }).encode()

        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

        text = data['choices'][0]['message']['content']
        # Extract JSON from response (may be wrapped in ```json blocks)
        text = re.sub(r'^```json\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text.strip())
        return json.loads(text)

    def _call_anthropic(self, prompt: str, system: str, temperature: float) -> dict:
        """Anthropic Claude API."""
        import urllib.request, urllib.error

        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = json.dumps({
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 8000,
        }).encode()

        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

        text = data['content'][0]['text']
        text = re.sub(r'^```json\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text.strip())
        return json.loads(text)

# ==================== LLM Rule Evaluation ====================

def build_llm_prompt(rule: dict, issue: str, solution_code: str, file_path: str) -> str:
    """Build a focused prompt for a single LLM rule evaluation."""
    return f"""You are reviewing a code submission for a coding task.

TASK/ISSUE DESCRIPTION:
{issue[:2000]}

FILE: {file_path}

SUBMITTED CODE (from this file):
```
{solution_code[:4000]}
```

RULE TO EVALUATE:
{rule['id']}: {rule['name']}
{rule['description']}

Evaluate whether the submitted code satisfies this rule.
Respond with ONLY a JSON object (no markdown fences, no extra text):
{{"score": <0.0 to 1.0>, "explanation": "<brief explanation referencing specific lines>"}}

Score guide:
  1.0 = fully satisfies the rule, no issues
  0.5 = partially satisfies, minor concerns
  0.0 = violates the rule, serious issues
"""

def build_holistic_prompt(rubric: dict, issue: str, solution_code: str, file_list: List[str],
                           static_findings: List[Finding]) -> str:
    """Build a holistic review prompt for all LLM rules at once."""
    # Collect all LLM rules
    llm_rules = []
    for cat_name, cat in rubric['categories'].items():
        for rule in cat['rules']:
            if rule.get('check_type') == 'llm':
                llm_rules.append(f"  {rule['id']}: {rule['name']} — {rule['description']}")

    # Summarize static findings
    findings_summary = "\n".join(
        f"  [{f.severity}] {f.rule_id} in {f.file}:{f.line}: {f.match}"
        for f in static_findings[:20]
    ) or "  (none)"

    return f"""You are reviewing a code submission for a coding task.

TASK/ISSUE DESCRIPTION:
{issue[:3000]}

FILES IN SOLUTION:
{chr(10).join(f'  - {f}' for f in file_list[:30])}

CODE TO REVIEW (concatenated, truncated):
```
{solution_code[:6000]}
```

PRE-DETECTED STATIC FINDINGS (already identified by regex):
{findings_summary}

RULES TO EVALUATE (score each 0.0-1.0):
{chr(10).join(llm_rules)}

Respond with ONLY a JSON object:
{{
  "rule_scores": [
    {{"rule_id": "SEC-004", "score": 0.8, "explanation": "..."}},
    ...
  ]
}}

Score guide:
  1.0 = fully satisfies the rule
  0.5 = partial / minor concerns
  0.0 = violates the rule
"""

def evaluate_llm_rules(llm: LLMBackend, rubric: dict, issue: str,
                       solution_files: Dict[str, str],
                       static_findings: List[Finding]) -> List[dict]:
    """Run all LLM rules against the solution. Returns list of assessments."""
    assessments = []

    if not llm.available:
        # No LLM — return neutral scores for LLM rules
        for cat_name, cat in rubric['categories'].items():
            for rule in cat['rules']:
                if rule.get('check_type') == 'llm':
                    assessments.append({
                        'rule_id': rule['id'],
                        'rule_name': rule['name'],
                        'severity': rule['severity'],
                        'score': 0.5,
                        'explanation': 'LLM not configured — neutral score.',
                    })
        return assessments

    # Holistic approach: send all LLM rules in one call with concatenated code
    # Truncate total code to ~6000 chars to stay within context limits
    all_code = ""
    file_list = list(solution_files.keys())
    for fpath in file_list:
        content = solution_files[fpath]
        all_code += f"\n--- {fpath} ---\n{content}\n"
        if len(all_code) > 6000:
            all_code = all_code[:6000] + "\n... (truncated)"
            break

    prompt = build_holistic_prompt(rubric, issue, all_code, file_list, static_findings)
    result = llm.call(prompt, system="You are an expert code reviewer for a Bitcoin/Lightning wallet project. Be strict but fair.")

    # Parse the holistic response
    if 'rule_scores' in result:
        # Build a lookup for rule metadata
        rule_lookup = {}
        for cat_name, cat in rubric['categories'].items():
            for rule in cat['rules']:
                rule_lookup[rule['id']] = rule

        for rs in result['rule_scores']:
            rid = rs.get('rule_id', '')
            if rid in rule_lookup:
                rule = rule_lookup[rid]
                assessments.append({
                    'rule_id': rid,
                    'rule_name': rule['name'],
                    'severity': rule['severity'],
                    'score': float(rs.get('score', 0.5)),
                    'explanation': rs.get('explanation', ''),
                })
    else:
        print(f"  LLM WARNING: response missing 'rule_scores' key. Got: {str(result)[:200]}", file=sys.stderr)

    return assessments

# ==================== Scoring ====================

def compute_category_score(findings: List[Finding], llm_assessments: List[dict],
                           severity_weights: dict) -> Tuple[float, dict]:
    """Compute a category score (0-100). Returns (score, details)."""
    penalty = 0.0

    for f in findings:
        w = severity_weights.get(f.severity, 1.0)
        penalty += w

    for a in llm_assessments:
        w = severity_weights.get(a['severity'], 1.0)
        penalty += (1.0 - a['score']) * w

    score = max(0.0, 100.0 - penalty)

    details = {
        'raw_penalty': round(penalty, 2),
        'static_findings_count': len(findings),
        'llm_assessments_count': len(llm_assessments),
        'score_before_weight': round(score, 2),
    }
    return score, details

def judge_solution(rubric: dict, issue: str, solution_files: Dict[str, str],
                   agent_id: str, llm: Optional[LLMBackend] = None,
                   static_only: bool = False) -> SolutionResult:
    """Judge a single solution against the rubric."""
    result = SolutionResult(agent_id=agent_id)
    result.files_analyzed = len(solution_files)
    result.lines_analyzed = sum(len(c.split('\n')) for c in solution_files.values())

    severity_weights = rubric.get('severity_weights', {
        'critical': 3.0, 'major': 2.0, 'minor': 1.0, 'nitpick': 0.25
    })

    all_static_findings = []
    all_llm_assessments = []

    # Layer 1: Static analysis per file
    for fpath, code in solution_files.items():
        all_rules = []
        for cat_name, cat in rubric['categories'].items():
            all_rules.extend(cat['rules'])

        static_rules = [r for r in all_rules if r.get('check_type') == 'static']
        file_findings = run_static_checks(fpath, code, static_rules)
        all_static_findings.extend(file_findings)

    # Layer 3: LLM holistic review
    if not static_only and llm and llm.available:
        all_llm_assessments = evaluate_llm_rules(llm, rubric, issue, solution_files, all_static_findings)

    # Score each category
    for cat_name, cat in rubric['categories'].items():
        cat_rule_ids = {r['id'] for r in cat['rules']}

        cat_findings = [f for f in all_static_findings if f.rule_id in cat_rule_ids]
        cat_assessments = [a for a in all_llm_assessments if a['rule_id'] in cat_rule_ids]

        score, details = compute_category_score(cat_findings, cat_assessments, severity_weights)

        cat_result = CategoryResult(
            name=cat_name,
            score=score,
            weight=cat['weight'],
            hard_gate=cat.get('hard_gate', False),
            findings=cat_findings,
            llm_scores=cat_assessments,
        )
        cat_result.__dict__.update(details)

        # Hard gate: if any critical finding in a hard_gate category, score = 0
        if cat.get('hard_gate', False):
            critical_findings = [f for f in cat_findings if f.severity == 'critical']
            critical_llm = [a for a in cat_assessments if a['severity'] == 'critical' and a['score'] < 0.3]
            if critical_findings or critical_llm:
                cat_result.score = 0.0
                cat_result.hard_gate_triggered = True

        result.category_results[cat_name] = cat_result

    # Compute weighted total
    total_weight = sum(cat['weight'] for cat in rubric['categories'].values())
    weighted_sum = sum(
        result.category_results[cat_name].score * cat['weight']
        for cat_name, cat in rubric['categories'].items()
    )
    result.total_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0

    # Verdict
    pass_threshold = rubric['scoring']['pass_threshold']
    # Hard gate veto: any triggered hard gate = automatic FAIL, regardless of score
    any_hard_gate = any(cat.hard_gate_triggered for cat in result.category_results.values())
    if any_hard_gate:
        result.verdict = 'FAIL'
    else:
        result.verdict = 'PASS' if result.total_score >= pass_threshold else 'FAIL'

    result.all_findings = all_static_findings
    return result

# ==================== Task Loading ====================

def load_task(path: str) -> dict:
    """Load a task JSON file with issue + solutions."""
    with open(path, 'r') as f:
        task = json.load(f)

    if 'issue' not in task:
        raise ValueError("Task file missing 'issue' key")
    if 'solutions' not in task:
        raise ValueError("Task file missing 'solutions' key")

    return task

def build_task_from_args(issue_path: str, solution_paths: List[str]) -> dict:
    """Build a task dict from CLI args."""
    with open(issue_path, 'r') as f:
        issue_text = f.read()

    solutions = []
    for i, spath in enumerate(solution_paths):
        files = load_solution_files(spath)
        agent_id = os.path.basename(spath.rstrip('/')) or f"agent_{i}"
        solutions.append({
            'agent_id': agent_id,
            'files': files,
        })

    return {
        'issue': {'title': '', 'body': issue_text},
        'solutions': solutions,
    }

# ==================== Reporting ====================

def result_to_dict(result: SolutionResult) -> dict:
    """Convert SolutionResult to a JSON-serializable dict."""
    return {
        'agent_id': result.agent_id,
        'total_score': round(result.total_score, 2),
        'verdict': result.verdict,
        'files_analyzed': result.files_analyzed,
        'lines_analyzed': result.lines_analyzed,
        'categories': {
            cat_name: {
                'score': round(cat.score, 2),
                'weight': cat.weight,
                'hard_gate': cat.hard_gate,
                'hard_gate_triggered': cat.hard_gate_triggered,
                'static_findings': len(cat.findings),
                'llm_assessments': len(cat.llm_scores),
                'findings': [
                    {
                        'rule_id': f.rule_id,
                        'rule_name': f.rule_name,
                        'severity': f.severity,
                        'file': f.file,
                        'line': f.line,
                        'match': f.match,
                    }
                    for f in cat.findings
                ],
                'llm_scores': [
                    {
                        'rule_id': a['rule_id'],
                        'rule_name': a['rule_name'],
                        'score': a['score'],
                        'explanation': a['explanation'][:200],
                    }
                    for a in cat.llm_scores
                ],
            }
            for cat_name, cat in result.category_results.items()
        },
    }

def print_summary(results: List[dict], verbose: bool = False):
    """Print a human-readable summary of results."""
    print("\n" + "=" * 70)
    print("  JUDGMENT RESULTS")
    print("=" * 70)

    # Sort by score descending
    sorted_results = sorted(results, key=lambda r: r['total_score'], reverse=True)

    for rank, r in enumerate(sorted_results, 1):
        medal = ['🥇', '🥈', '🥉', '4.', '5.', '6.', '7.', '8.'][min(rank - 1, 7)]
        print(f"\n  {medal} {r['agent_id']}")
        print(f"     Score: {r['total_score']}/100  Verdict: {r['verdict']}")
        print(f"     Files: {r['files_analyzed']}  Lines: {r['lines_analyzed']}")
        for cat_name, cat in r['categories'].items():
            gate = " [HARD GATE TRIGGERED]" if cat['hard_gate_triggered'] else ""
            print(f"     {cat_name:30s} {cat['score']:6.1f}  (weight={cat['weight']}){gate}")
            if verbose:
                for f in cat['findings']:
                    print(f"       [{f['severity']:8s}] {f['rule_id']} {f['file']}:{f['line']} — {f['match'][:60]}")
                for a in cat['llm_scores']:
                    print(f"       [LLM {a['score']:.1f}] {a['rule_id']} — {a['explanation'][:80]}")

    print(f"\n{'=' * 70}")
    best = sorted_results[0] if sorted_results else None
    if best:
        print(f"  BEST: {best['agent_id']} ({best['total_score']}/100)")
    print("=" * 70)

# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description='Judge coding task submissions against a rubric.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          # Judge from task JSON
          python judge.py --task task.json --rubric rubric.json

          # Judge from issue file + solution directories
          python judge.py --issue issue.md --solutions agent_a/ agent_b/ --rubric rubric.json

          # Static-only (no LLM needed)
          python judge.py --task task.json --rubric rubric.json --static-only

          # With LLM (set env vars first)
          JUDGE_LLM_PROVIDER=openai OPENAI_API_KEY=sk-... python judge.py --task task.json --rubric rubric.json
        """)
    )
    parser.add_argument('--task', help='Path to task JSON file (issue + solutions)')
    parser.add_argument('--issue', help='Path to issue description file')
    parser.add_argument('--solutions', nargs='+', help='Paths to solution directories/files')
    parser.add_argument('--rubric', default='rubric.json', help='Path to rubric JSON')
    parser.add_argument('--output', '-o', help='Write JSON report to this file')
    parser.add_argument('--static-only', action='store_true', help='Skip LLM analysis (regex only)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    # Load rubric
    rubric = load_rubric(args.rubric)

    # Load task
    if args.task:
        task = load_task(args.task)
        issue_text = task['issue'].get('body', '') or json.dumps(task['issue'])
        solutions = task['solutions']
    elif args.issue and args.solutions:
        task = build_task_from_args(args.issue, args.solutions)
        issue_text = task['issue']['body']
        solutions = task['solutions']
    else:
        parser.error("Provide either --task or both --issue and --solutions")

    # Initialize LLM backend
    llm = LLMBackend()
    if llm.available and not args.static_only:
        print(f"LLM: {llm.provider} / {llm.model}", file=sys.stderr)
    elif not args.static_only:
        print("LLM: not configured (set JUDGE_LLM_PROVIDER + API key). Running static-only.", file=sys.stderr)
        args.static_only = True

    # Judge each solution
    all_results = []
    for sol in solutions:
        agent_id = sol.get('agent_id', 'unknown')
        files = sol.get('files', {})

        if not files:
            print(f"  WARNING: No files found for solution '{agent_id}'", file=sys.stderr)
            continue

        print(f"\nJudging: {agent_id} ({len(files)} files)...", file=sys.stderr)

        result = judge_solution(
            rubric=rubric,
            issue=issue_text,
            solution_files=files,
            agent_id=agent_id,
            llm=llm if not args.static_only else None,
            static_only=args.static_only,
        )

        all_results.append(result_to_dict(result))

    # Print summary
    print_summary(all_results, verbose=args.verbose)

    # Write output
    report = {
        'rubric_version': rubric.get('version', 'unknown'),
        'issue': issue_text[:500],
        'results': all_results,
    }

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))

    # Exit code: 0 if best solution passes, 1 if all fail
    any_pass = any(r['verdict'] == 'PASS' for r in all_results)
    sys.exit(0 if any_pass else 1)

if __name__ == '__main__':
    main()