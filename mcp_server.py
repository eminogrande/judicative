#!/usr/bin/env python3
"""
mcp_server.py — Judicative as an MCP server: a coding IQ test any LLM can take.

Point any MCP-capable agent (Claude Code, Claude Desktop, Cursor, ...) at this
server and it can self-test: fetch a task, submit a solution, get a hard 0-100
score plus a "what you did wrong" report it can use to improve on a second run.

Stdlib only. Standard MCP stdio transport (newline-delimited JSON-RPC 2.0).

Setup (Claude Code example):
    claude mcp add judicative -- python3 /path/to/judicative/mcp_server.py

Tools:
    list_tasks()                      → available test tasks
    get_task(task_id)                 → the issue an agent must solve
    submit_solution(task_id, agent_id, files) → score, verdict, mistakes report
    get_rubric()                      → the law being applied (it's open source)

Tasks live in tasks/<task-id>/issue.md. Add your own by dropping in a directory.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from judge import load_rubric, judge_solution, result_to_dict, build_mistakes_report, get_scoring, LLMBackend

BASE = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(BASE, 'tasks')
RUBRIC_PATH = os.environ.get('JUDICATIVE_RUBRIC', os.path.join(BASE, 'rubric_v2.json'))

SERVER_INFO = {'name': 'judicative', 'version': '1.0.0'}
PROTOCOL_VERSION = '2024-11-05'

# ==================== Task registry ====================

def discover_tasks():
    tasks = {}
    if not os.path.isdir(TASKS_DIR):
        return tasks
    for entry in sorted(os.listdir(TASKS_DIR)):
        issue_path = os.path.join(TASKS_DIR, entry, 'issue.md')
        if os.path.isfile(issue_path):
            with open(issue_path, encoding='utf-8') as f:
                issue = f.read()
            title = next((l.lstrip('# ').strip() for l in issue.splitlines() if l.strip()), entry)
            tasks[entry] = {'id': entry, 'title': title, 'issue': issue}
    return tasks

# ==================== Tool implementations ====================

def tool_list_tasks(_args):
    tasks = discover_tasks()
    return {
        'tasks': [{'id': t['id'], 'title': t['title']} for t in tasks.values()],
        'how_to_take_the_test': (
            'Call get_task(task_id), write your solution WITHOUT looking at the rubric '
            'if you want an honest baseline, then call submit_solution. Use the returned '
            'mistakes report as extra instructions and submit a second run under a new '
            'agent_id (e.g. "mymodel-run2") to measure improvement.'
        ),
    }

def tool_get_task(args):
    tasks = discover_tasks()
    task_id = args.get('task_id', '')
    if task_id not in tasks:
        raise ValueError(f"Unknown task_id '{task_id}'. Available: {list(tasks)}")
    return {
        'id': task_id,
        'issue': tasks[task_id]['issue'],
        'submission_format': {
            'task_id': task_id,
            'agent_id': '<your model/agent name + run number>',
            'files': {'<relative/path.ts>': '<full file content>'},
        },
    }

def tool_submit_solution(args):
    tasks = discover_tasks()
    task_id = args.get('task_id', '')
    agent_id = args.get('agent_id', 'anonymous')
    files = args.get('files', {})
    if task_id not in tasks:
        raise ValueError(f"Unknown task_id '{task_id}'. Available: {list(tasks)}")
    if not files or not isinstance(files, dict):
        raise ValueError("'files' must be a non-empty object of {path: content}")

    rubric = load_rubric(RUBRIC_PATH)
    llm = LLMBackend()
    static_only = not llm.available
    result = judge_solution(
        rubric=rubric,
        issue=tasks[task_id]['issue'],
        solution_files=files,
        agent_id=agent_id,
        llm=llm if llm.available else None,
        static_only=static_only,
    )
    rdict = result_to_dict(result)
    report = {
        'rubric_version': rubric.get('version', 'unknown'),
        'score_model': 'global-penalty-v2',
        'mode': 'static-only' if static_only else 'static+llm',
        'results': [rdict],
    }
    scoring = get_scoring(rubric)
    return {
        'agent_id': agent_id,
        'total_score': rdict['total_score'],
        'verdict': rdict['verdict'],
        'total_penalty': rdict['total_penalty'],
        'hard_gate_capped': rdict['hard_gate_capped'],
        'pass_threshold': scoring['pass_threshold'],
        'mode': report['mode'],
        'note': ('static-only: LLM rules not evaluated, score is an upper bound'
                 if static_only else 'full static+LLM evaluation'),
        'mistakes_report_markdown': build_mistakes_report(report, rubric),
    }

def tool_get_rubric(_args):
    rubric = load_rubric(RUBRIC_PATH)
    return {
        'version': rubric.get('version'),
        'scoring': rubric.get('scoring'),
        'categories': {
            name: {
                'weight': cat['weight'],
                'hard_gate': cat.get('hard_gate', False),
                'description': cat.get('description', ''),
                'rules': [
                    {'id': r['id'], 'name': r['name'], 'severity': r['severity'],
                     'check_type': r['check_type'], 'description': r['description']}
                    for r in cat['rules']
                ],
            }
            for name, cat in rubric['categories'].items()
        },
    }

TOOLS = {
    'list_tasks': {
        'fn': tool_list_tasks,
        'description': 'List the coding test tasks available on this Judicative instance.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
    'get_task': {
        'fn': tool_get_task,
        'description': 'Fetch a coding task (the issue to solve) by id.',
        'inputSchema': {
            'type': 'object',
            'properties': {'task_id': {'type': 'string', 'description': 'Task id from list_tasks'}},
            'required': ['task_id'],
        },
    },
    'submit_solution': {
        'fn': tool_submit_solution,
        'description': ('Submit a solution for judging. Returns a hard 0-100 score, verdict, '
                        'and a markdown mistakes report with instructions for improving on a second run.'),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'task_id': {'type': 'string'},
                'agent_id': {'type': 'string', 'description': 'Your model/agent name, include the run number, e.g. "gpt-5.5-run1"'},
                'files': {'type': 'object', 'description': 'Map of relative file path to full file content',
                          'additionalProperties': {'type': 'string'}},
            },
            'required': ['task_id', 'agent_id', 'files'],
        },
    },
    'get_rubric': {
        'fn': tool_get_rubric,
        'description': 'Return the rubric (categories, rules, scoring model) this instance judges by.',
        'inputSchema': {'type': 'object', 'properties': {}, 'required': []},
    },
}

# ==================== MCP stdio transport ====================

def handle_request(req):
    method = req.get('method', '')
    params = req.get('params', {}) or {}

    if method == 'initialize':
        return {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {'tools': {}},
            'serverInfo': SERVER_INFO,
        }
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [
            {'name': name, 'description': t['description'], 'inputSchema': t['inputSchema']}
            for name, t in TOOLS.items()
        ]}
    if method == 'tools/call':
        name = params.get('name', '')
        if name not in TOOLS:
            raise ValueError(f"Unknown tool: {name}")
        try:
            result = TOOLS[name]['fn'](params.get('arguments', {}) or {})
            return {'content': [{'type': 'text', 'text': json.dumps(result, indent=2)}]}
        except Exception as e:
            return {'content': [{'type': 'text', 'text': f'Error: {e}'}], 'isError': True}
    raise ValueError(f"Unknown method: {method}")

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if 'id' not in req:
            continue  # notification (e.g. notifications/initialized) — no response
        resp = {'jsonrpc': '2.0', 'id': req['id']}
        try:
            resp['result'] = handle_request(req)
        except Exception as e:
            resp['error'] = {'code': -32601, 'message': str(e)}
        sys.stdout.write(json.dumps(resp) + '\n')
        sys.stdout.flush()

if __name__ == '__main__':
    main()
