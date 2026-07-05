# Judicative Bench

This folder is for a personal replay benchmark: real issues and PRs from Nuri
and partner crypto repos turned into hard model-evaluation tasks.

The benchmark should answer one practical question:

> Which model or model system produces patches that would actually survive this
> organization's repos, tests, review norms, and safety boundaries?

## Task Mining

Mine candidate replay tasks from GitHub:

```bash
python3 bench/mine_tasks.py \
  --org nuri-com \
  --limit-per-repo 20 \
  --output bench/tasks/nuri-hard-v1.jsonl
```

Mine the broader partner crypto suite from Nuri, Arkade, Wirex, ZeroDev, and Safe:

```bash
python3 bench/mine_tasks.py \
  --profile partner-crypto \
  --limit-per-repo 10 \
  --max-pages 3 \
  --repo-pages 3 \
  --min-score 55 \
  --evaluation-modes test_backed review_backed \
  --output bench/tasks/partner-crypto-hard-v1.jsonl
```

For one partner org only:

```bash
python3 bench/mine_tasks.py \
  --org arkade-os \
  --discover-repos \
  --limit-per-repo 10 \
  --output bench/tasks/arkade-hard-v1.jsonl
```

For exact repos:

```bash
python3 bench/mine_tasks.py \
  --repos arkade-os/<repo> wirexapp/<repo> zerodevapp/<repo> safe-global/<repo> \
  --limit-per-repo 20 \
  --output bench/tasks/selected-partners-v1.jsonl
```

Generate a stricter first suite:

```bash
python3 bench/mine_tasks.py \
  --limit-per-repo 20 \
  --min-score 55 \
  --evaluation-modes test_backed review_backed \
  --output bench/tasks/nuri-hard-v1-focused.jsonl
```

The default `nuri` profile keeps a curated Nuri repo set:

- `nuri-expo`
- `server-arkade-v4`
- `nuri-prf-signer`
- `nuri-mcp-bitcoin-swapkit`
- `nuri-wirex-mcp`
- `nuri-gnosis-mcp`
- `server-near-intents-solver`
- `passkey-server`

The `partner-crypto` profile discovers non-archived, non-fork repositories from:

- `nuri-com`
- `arkade-os`
- `wirexapp`
- `zerodevapp`
- `safe-global`

Each JSONL row is a candidate replay task with:

- PR metadata and links
- replay base candidate from the merge commit's first parent
- real fix head/merge commit
- changed files and added/modified test files
- review and issue-comment counts
- linked issue references discovered from PR/issue text
- personalized domain tags such as `arkade`, `wirex`, `zerodev`, `safe`,
  `account_abstraction`, `multisig`, `passkey`, `mcp`, `race_condition`
- a heuristic difficulty/replay score
- an evaluation mode:
  - `test_backed`: the real PR added or changed tests
  - `review_backed`: no changed tests, but enough issue/review context for referee review
  - `weak_oracle`: not enough test or review signal yet

## What Makes A Good Task

Prefer tasks that are:

- merged and non-dependabot
- linked to an issue or rich PR body
- reviewed by humans or review bots
- small enough to replay, but not trivial
- backed by added or modified tests
- in high-value domains: Arkade, passkeys/PRF, MCP, security, data integrity,
  stale state, race conditions, recovery, Lightning/Bitcoin

Avoid tasks that are:

- dependency bumps
- pure formatting/docs chores
- giant release-candidate rollups
- generated-only changes

## Next Runner Shape

The next layer should consume mined tasks:

```bash
python3 bench/run.py \
  --tasks bench/tasks/nuri-hard-v1.jsonl \
  --models configs/models.yaml \
  --out runs/latest
```

The runner should check out each `replay_base_sha`, ask each contestant model to
patch the repo, then score:

- patch applies
- repo tests/typecheck/lint pass
- real PR added tests pass
- Judicative hard gates do not fire
- patch size and touched-file scope are reasonable
- cost and duration

After objective scoring works, add blind pairwise referee review and Elo ranking
on top of the artifacts.

## Referee Committee

The committee should judge artifacts after the runner has produced patches and
test logs. Keep referees independent from contestant models where possible.

Recommended panel:

- implementation reviewer: correctness, minimality, repo fit
- safety reviewer: security, key handling, money movement, data integrity
- regression reviewer: tests, edge cases, stale state, race conditions
- product reviewer: UX, copy, operational fit
- adversarial reviewer: looks for ways the patch only satisfies the visible test

Use blind pairwise voting first: patch A vs patch B for the same task, randomized
order, with contestant identities hidden. Convert wins into Elo. Absolute scores
can be recorded, but should not be the primary ranking.
