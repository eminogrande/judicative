#!/usr/bin/env python3
"""
test_judge.py — Test suite for the judging engine.

Run with: python3 -m pytest test_judge.py -v
Or:       python3 test_judge.py
"""

import json
import os
import sys
import tempfile
import subprocess

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judge import (
    load_rubric, strip_comments, run_static_checks, parse_diff,
    load_solution_files, judge_solution, LLMBackend, build_task_from_args,
    result_to_dict, Finding, CategoryResult, SolutionResult
)

RUBRIC_PATH = os.path.join(os.path.dirname(__file__), 'rubric.json')
FIXTURES = os.path.join(os.path.dirname(__file__), 'test_fixtures')

# ==================== Test Helpers ====================

def get_rule(rubric, rule_id):
    """Get a rule by ID from the rubric."""
    for cat_name, cat in rubric['categories'].items():
        for rule in cat['rules']:
            if rule['id'] == rule_id:
                return rule
    return None

def run_single_rule(code, rule, filename='test.ts'):
    """Run a single static rule against code, return findings."""
    ext = os.path.splitext(filename)[1].lower()
    clean = strip_comments(code, ext)
    return run_static_checks(filename, clean, [rule])

# ==================== Rubric Tests ====================

class TestRubric:
    def test_rubric_loads(self):
        rubric = load_rubric(RUBRIC_PATH)
        assert 'categories' in rubric
        assert 'scoring' in rubric
        assert 'severity_weights' in rubric

    def test_rubric_has_all_categories(self):
        rubric = load_rubric(RUBRIC_PATH)
        expected = {'security_and_privacy', 'functional_correctness', 'data_integrity',
                    'performance', 'maintainability', 'completeness'}
        assert set(rubric['categories'].keys()) == expected

    def test_weights_sum_to_one(self):
        rubric = load_rubric(RUBRIC_PATH)
        total = sum(cat['weight'] for cat in rubric['categories'].values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    def test_all_rules_have_required_fields(self):
        rubric = load_rubric(RUBRIC_PATH)
        for cat_name, cat in rubric['categories'].items():
            for rule in cat['rules']:
                assert 'id' in rule, f"{cat_name} rule missing id"
                assert 'name' in rule, f"{rule.get('id')} missing name"
                assert 'severity' in rule, f"{rule['id']} missing severity"
                assert 'check_type' in rule, f"{rule['id']} missing check_type"
                assert rule['check_type'] in ('static', 'llm'), f"{rule['id']} invalid check_type"
                assert rule['severity'] in ('critical', 'major', 'minor', 'nitpick'), \
                    f"{rule['id']} invalid severity: {rule['severity']}"
                if rule['check_type'] == 'static':
                    assert 'pattern' in rule, f"{rule['id']} static rule missing pattern"

    def test_hard_gate_categories(self):
        rubric = load_rubric(RUBRIC_PATH)
        assert rubric['categories']['security_and_privacy']['hard_gate'] == True
        assert rubric['categories']['data_integrity']['hard_gate'] == True
        assert rubric['categories']['performance']['hard_gate'] == False

# ==================== strip_comments Tests ====================

class TestStripComments:
    def test_strips_line_comment(self):
        code = "const x = 1; // this is a comment"
        result = strip_comments(code, '.ts')
        assert 'comment' not in result
        assert 'const x = 1' in result

    def test_preserves_url_in_string(self):
        code = "const url = 'https://api.example.com/v1';"
        result = strip_comments(code, '.ts')
        assert 'https://api.example.com' in result, "URL in string was corrupted"

    def test_preserves_url_in_template_literal(self):
        code = "const url = `https://api.example.com/${path}`;"
        result = strip_comments(code, '.ts')
        assert 'https://api.example.com' in result

    def test_strips_block_comment(self):
        code = "const x = 1; /* block comment */ const y = 2;"
        result = strip_comments(code, '.ts')
        assert 'block comment' not in result
        assert 'const x = 1' in result
        assert 'const y = 2' in result

    def test_preserves_block_comment_in_string(self):
        code = "const msg = '/* not a comment */';"
        result = strip_comments(code, '.ts')
        assert '/* not a comment */' in result

    def test_python_comment(self):
        code = "x = 1  # this is a comment"
        result = strip_comments(code, '.py')
        assert 'comment' not in result
        assert 'x = 1' in result

    def test_python_preserves_hash_in_string(self):
        code = 's = "my#password"'
        result = strip_comments(code, '.py')
        assert 'my#password' in result

    def test_markdown_not_stripped(self):
        code = "# Header\n\nSome text // not a comment"
        result = strip_comments(code, '.md')
        assert '//' in result  # Should be preserved in markdown

# ==================== Static Rule Tests ====================

class TestSecurityRules:
    def setup_method(self):
        self.rubric = load_rubric(RUBRIC_PATH)

    def test_sec001_localstorage_key(self):
        rule = get_rule(self.rubric, 'SEC-001')
        code = "localStorage.setItem('nuri_seed', seed);"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'critical'

    def test_sec001_safe_localstorage(self):
        rule = get_rule(self.rubric, 'SEC-001')
        code = "localStorage.setItem('theme', 'dark');"  # Not a key/seed/secret
        findings = run_single_rule(code, rule)
        assert len(findings) == 0

    def test_sec002_hardcoded_secret(self):
        rule = get_rule(self.rubric, 'SEC-002')
        code = "const API_KEY = 'sk-1234567890abcdef';"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'critical'

    def test_sec003_math_random(self):
        rule = get_rule(self.rubric, 'SEC-003')
        code = "const nonce = Math.random();"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'critical'

    def test_sec003_crypto_getrandomvalues_safe(self):
        rule = get_rule(self.rubric, 'SEC-003')
        code = "crypto.getRandomValues(new Uint8Array(32));"
        findings = run_single_rule(code, rule)
        assert len(findings) == 0

    def test_sec008_eval(self):
        rule = get_rule(self.rubric, 'SEC-008')
        code = "eval(userInput);"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'critical'

    def test_sec008_function_constructor(self):
        rule = get_rule(self.rubric, 'SEC-008')
        code = "new Function('return ' + userInput)();"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1

    def test_sec009_innerhtml_dynamic(self):
        rule = get_rule(self.rubric, 'SEC-009')
        code = "div.innerHTML = '<p>' + userInput + '</p>';"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'major'

    def test_sec010_http_endpoint(self):
        rule = get_rule(self.rubric, 'SEC-010')
        code = "fetch('http://api.example.com/data');"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'major'

    def test_sec010_https_safe(self):
        rule = get_rule(self.rubric, 'SEC-010')
        code = "fetch('https://api.example.com/data');"
        findings = run_single_rule(code, rule)
        assert len(findings) == 0

    def test_sec010_localhost_safe(self):
        rule = get_rule(self.rubric, 'SEC-010')
        code = "fetch('http://localhost:3000/data');"
        findings = run_single_rule(code, rule)
        assert len(findings) == 0

class TestFunctionalRules:
    def setup_method(self):
        self.rubric = load_rubric(RUBRIC_PATH)

    def test_func002_empty_catch(self):
        rule = get_rule(self.rubric, 'FUNC-002')
        code = "try { doSomething(); } catch (e) {}"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'major'

    def test_func002_nonempty_catch_safe(self):
        rule = get_rule(self.rubric, 'FUNC-002')
        code = "try { doSomething(); } catch (e) { console.error(e); }"
        findings = run_single_rule(code, rule)
        assert len(findings) == 0

    def test_func005_outline_none(self):
        rule = get_rule(self.rubric, 'FUNC-005')
        code = "button:focus { outline: none; }"
        findings = run_single_rule(code, rule)
        assert len(findings) == 1
        assert findings[0].severity == 'minor'

    def test_func006_disable_zoom(self):
        rule = get_rule(self.rubric, 'FUNC-006')
        code = '<meta name="viewport" content="width=device-width, maximum-scale=1, user-scalable=no">'
        findings = run_single_rule(code, rule)
        assert len(findings) >= 1
        assert findings[0].severity == 'major'

class TestMaintainabilityRules:
    def setup_method(self):
        self.rubric = load_rubric(RUBRIC_PATH)

    def test_maint002_is_llm_rule(self):
        """MAINT-002 was moved to LLM check_type (regex can't distinguish opening/closing fences)."""
        rule = get_rule(self.rubric, 'MAINT-002')
        assert rule['check_type'] == 'llm'
        # Static checks should return 0 findings for LLM rules
        code = "Some text\n```\ncode here\n```\n"
        findings = run_single_rule(code, rule, 'README.md')
        assert len(findings) == 0  # LLM rule, no static check

    def test_maint005_is_llm_rule(self):
        """MAINT-005 was also moved to LLM check_type."""
        rule = get_rule(self.rubric, 'MAINT-005')
        assert rule['check_type'] == 'llm'

# ==================== parse_diff Tests ====================

class TestParseDiff:
    def test_parse_simple_diff(self):
        diff = """\
diff --git a/lib/utils.ts b/lib/utils.ts
index 1234567..abcdefg 100644
--- a/lib/utils.ts
+++ b/lib/utils.ts
@@ -1,3 +1,5 @@
 const old = 'line';
+const new1 = 'added';
+const new2 = 'also added';
 const unchanged = 'line';
"""
        files = parse_diff(diff)
        assert 'lib/utils.ts' in files
        assert "const new1 = 'added'" in files['lib/utils.ts']
        assert "const new2 = 'also added'" in files['lib/utils.ts']
        assert "const old" not in files['lib/utils.ts']  # Context line, not added

    def test_parse_multiple_files(self):
        diff = """\
diff --git a/file1.ts b/file1.ts
--- a/file1.ts
+++ b/file1.ts
@@ -1,1 +1,2 @@
 old
+new1
diff --git a/file2.ts b/file2.ts
--- a/file2.ts
+++ b/file2.ts
@@ -1,1 +1,2 @@
 old
+new2
"""
        files = parse_diff(diff)
        assert 'file1.ts' in files
        assert 'file2.ts' in files
        assert 'new1' in files['file1.ts']
        assert 'new2' in files['file2.ts']

    def test_parse_empty_diff(self):
        files = parse_diff("")
        assert len(files) == 0

# ==================== Integration Tests ====================

class TestSmokeTest:
    """Integration test: judge the 3 synthetic solutions and verify ranking."""

    def setup_method(self):
        self.rubric = load_rubric(RUBRIC_PATH)
        task_path = os.path.join(FIXTURES, 'task_smoke.json')
        with open(task_path) as f:
            self.task = json.load(f)

    def test_good_solution_scores_high(self):
        sol = self.task['solutions'][0]  # agent_good
        assert sol['agent_id'] == 'agent_good'
        result = judge_solution(self.rubric, self.task['issue']['body'], sol['files'], 'agent_good', static_only=True)
        assert result.total_score == 100.0
        assert result.verdict == 'PASS'
        assert len(result.all_findings) == 0

    def test_bad_solution_fails(self):
        sol = self.task['solutions'][1]  # agent_bad
        assert sol['agent_id'] == 'agent_bad'
        result = judge_solution(self.rubric, self.task['issue']['body'], sol['files'], 'agent_bad', static_only=True)
        assert result.verdict == 'FAIL'
        assert result.total_score < 70.0
        # Hard gate must be triggered
        assert result.category_results['security_and_privacy'].hard_gate_triggered == True
        assert result.category_results['security_and_privacy'].score == 0.0

    def test_partial_solution_passes_with_penalty(self):
        sol = self.task['solutions'][2]  # agent_partial
        assert sol['agent_id'] == 'agent_partial'
        result = judge_solution(self.rubric, self.task['issue']['body'], sol['files'], 'agent_partial', static_only=True)
        assert result.verdict == 'PASS'
        assert result.total_score < 100.0  # Has findings
        assert result.total_score > 90.0   # But still good
        # Should have FUNC-002 findings (silent catch)
        func_findings = [f for f in result.all_findings if f.rule_id == 'FUNC-002']
        assert len(func_findings) == 3

    def test_ranking_order(self):
        """Good > Partial > Bad"""
        results = []
        for sol in self.task['solutions']:
            r = judge_solution(self.rubric, self.task['issue']['body'], sol['files'],
                              sol['agent_id'], static_only=True)
            results.append(r)
        scores = {r.agent_id: r.total_score for r in results}
        assert scores['agent_good'] > scores['agent_partial'] > scores['agent_bad']

    def test_hard_gate_zeros_security(self):
        """A single critical security finding should zero the security category."""
        sol = self.task['solutions'][1]  # agent_bad
        result = judge_solution(self.rubric, self.task['issue']['body'], sol['files'], 'agent_bad', static_only=True)
        sec = result.category_results['security_and_privacy']
        assert sec.hard_gate_triggered == True
        assert sec.score == 0.0
        # Verify critical findings exist
        criticals = [f for f in sec.findings if f.severity == 'critical']
        assert len(criticals) >= 4  # localStorage, hardcoded secret, Math.random, eval

# ==================== CLI Tests ====================

class TestCLI:
    def test_cli_static_only(self):
        """Test the CLI with --static-only flag."""
        result = subprocess.run(
            ['python3', os.path.join(os.path.dirname(__file__), 'judge.py'),
             '--task', os.path.join(FIXTURES, 'task_smoke.json'),
             '--rubric', RUBRIC_PATH,
             '--static-only'],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0  # At least one solution passes
        assert 'agent_good' in result.stdout
        assert 'agent_bad' in result.stdout
        assert 'FAIL' in result.stdout
        assert 'PASS' in result.stdout

    def test_cli_output_file(self):
        """Test writing results to a file."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            output_path = tmp.name
        try:
            result = subprocess.run(
                ['python3', os.path.join(os.path.dirname(__file__), 'judge.py'),
                 '--task', os.path.join(FIXTURES, 'task_smoke.json'),
                 '--rubric', RUBRIC_PATH,
                 '--static-only',
                 '--output', output_path],
                capture_output=True, text=True, timeout=30
            )
            assert os.path.exists(output_path)
            with open(output_path) as f:
                report = json.load(f)
            assert 'results' in report
            assert len(report['results']) == 3
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

# ==================== Main ====================

if __name__ == '__main__':
    # Run without pytest
    import traceback

    test_classes = [
        TestRubric, TestStripComments, TestSecurityRules,
        TestFunctionalRules, TestMaintainabilityRules,
        TestParseDiff, TestSmokeTest, TestCLI
    ]

    passed = 0
    failed = 0
    errors = []

    for test_class in test_classes:
        class_name = test_class.__name__
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_')]
        for method in methods:
            test_name = f"{class_name}::{method}"
            try:
                if hasattr(instance, 'setup_method'):
                    instance.setup_method()
                getattr(instance, method)()
                passed += 1
                print(f"  PASS  {test_name}")
            except Exception as e:
                failed += 1
                errors.append((test_name, traceback.format_exc()))
                print(f"  FAIL  {test_name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    if errors:
        print("\nFAILURES:")
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)

    sys.exit(0 if failed == 0 else 1)