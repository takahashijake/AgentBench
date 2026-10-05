# Suite manifest and lock reference

AgentBench accepts YAML or JSON suite manifests.

- **schema_version 1** — original custom suites
- **schema_version 2** — V2 benchmark-pack metadata
- **schema_version 3** — V3 provider identity for extensible corpora
- **schema_version 4** — V4 declarative task host requirements
- **schema_version 5** — V5 locked local execution concurrency

All five remain readable in V5.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | `1`, `2`, `3`, `4`, or `5` |
| `id` | yes | stable suite identifier |
| `name` | no | display name |
| `description` | no | human description |
| `benchmark_pack` | no | corpus identity/version/provider |
| `agents` | yes | one or more agent definitions |
| `tasks` | yes | one or more benchmark tasks |
| `experiment` | no | matrix selection and execution policy |

Resource IDs may contain letters, numbers, `.`, `_`, and `-`.

## V3 benchmark-pack metadata

Generated V3 packs include the provider:

```yaml
schema_version: 3
id: agentbench-core-v3
name: AgentBench Core V3

benchmark_pack:
  id: core-v3
  version: 3.0.0
  provider: agentbench.builtin
  description: Expanded deterministic Python engineering corpus.
```

Provider identity participates in canonical manifest hashing, reports, and suite
locks.

V2 schema-2 manifests without `provider` remain valid.

## Agent

```yaml
- id: qwen
  description: Local Qwen CLI
  command_template: qwen -p "{prompt}" --approval-mode auto-edit
  enabled: true
```

The shell-backed adapter parses templates with `shlex` and substitutes
`{prompt}` into argv tokens. Prompt content is not shell-interpolated.

Built-in pack materialization requires `{prompt}`.

## Task

```yaml
- id: parser-fix
  description: Repair parser regression
  repository_path: ./repositories/parser-fix
  base_commit: 0123456789abcdef0123456789abcdef01234567
  agent_prompt: Fix the parser without weakening tests.
  setup_command: python -m pip install -e .
  test_command: pytest -q
  timeout: 600
  enabled: true
  category: bugfix
  difficulty: medium
  tags: [python, parser, regression]
```

`repository_path` is resolved relative to the manifest.

Category/difficulty/tags are descriptive corpus metadata and participate in the
manifest identity.

## Experiment

```yaml
experiment:
  name: Qwen vs Codex
  tasks: [parser-fix]
  agents: [qwen, codex]
  repetitions: 5
  stop_on_error: false
```

If task/agent selections are omitted, all enabled resources are selected in
manifest order.

The safety limit remains 10,000 planned runs.

## Canonical manifest identity

After validation, AgentBench serializes normalized model data with deterministic
JSON key ordering and computes SHA-256.

YAML whitespace/comments therefore do not change identity, while provider,
commands, task definitions, selections, or other semantic fields do.

## Suite locks

V5 writers emit:

```json
{"lock_schema_version": 4}
```

Lock schemas 1, 2, and 3 remain readable. This is important for diagnosing historical V2
locks: an old lock can be loaded even though replay verification may correctly
report environment/version/configuration drift.

Current locks include:

- suite ID/schema/canonical manifest digest
- pack ID/version/provider when present
- resolved task commits
- agent-prompt digests
- setup/test commands and timeouts
- task category/difficulty/tags
- selected matrix/repetitions
- agent command templates
- executable identity/version/binary SHA-256
- bounded AgentBench/Python/platform/Git identity
- canonical lock identity SHA-256

## Drift behavior

`agentbench verify` returns:

- exit `0` — current resolution matches
- exit `3` — material drift
- exit `2` — invalid input/runtime error

`agentbench replay` verifies before execution and fails closed on mismatch.

## Bounded provenance

Locks deliberately do not capture:

- environment variables
- credentials/tokens
- home-directory contents
- full package inventories
- arbitrary machine identifiers

The contract records inputs useful for benchmark reproducibility without turning
a lock file into a system dump.

## V4 task requirements

Schema 4 tasks may declare:

```yaml
requirements:
  min_cpu_count: 2
  min_memory_mb: 4096
  supported_platforms: [linux, darwin]
  required_commands: [python, git]
```

Requirements are normalized into the manifest identity, suite lock, experiment task snapshot, report, and portable result metadata.
Before each trial, AgentBench evaluates the frozen requirements. An incompatible host produces a `skipped` trial before agent execution.

Use `agentbench pack preflight <pack>` to inspect compatibility before materialization or a larger benchmark run.


## V5 execution policy

Schema 5 experiments may lock bounded local concurrency:

```yaml
experiment:
  tasks: [parser-fix]
  agents: [qwen, codex]
  repetitions: 5
  stop_on_error: false
  max_workers: 4
```

`max_workers` must be between 1 and 32. It participates in canonical manifest
identity and suite-lock identity. `agentbench run` and `agentbench replay` use
the worker count from the manifest; there is intentionally no unrecorded runtime
override.

Parallel workers use independent SQLAlchemy sessions. AgentBench serializes the
full Git lifecycle for trials backed by the same source repository while allowing
different repositories to execute concurrently.

With `stop_on_error: true`, AgentBench stops scheduling new cells after the
first orchestration error; work already in flight is allowed to finish.

A crashed local execution may leave `running` claims. After confirming no worker
process remains, use `agentbench recover <experiment-id> --confirm-inactive`.
Recovery resets those claims to planned and marks the abandoned execution attempt
`interrupted`.
