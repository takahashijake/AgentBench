# Suite manifest and lock reference

## Suite manifest

AgentBench accepts YAML or JSON with `schema_version: 1`.

### Top level

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Currently `1` |
| `id` | yes | Stable suite identifier |
| `name` | no | Display name |
| `description` | no | Human description |
| `agents` | yes | One or more agent definitions |
| `tasks` | yes | One or more benchmark tasks |
| `experiment` | no | Matrix selection and policy |

Resource IDs may contain letters, numbers, `.`, `_`, and `-`.

### Agent

```yaml
- id: qwen
  description: Local Qwen agent
  command_template: qwen -p "{prompt}"
  enabled: true
```

`{prompt}` is replaced inside parsed argv tokens. The prompt is not interpolated
through a shell.

### Task

```yaml
- id: parser-fix
  description: Repair parser regression
  repository_path: ../project
  base_commit: 0123456789abcdef0123456789abcdef01234567
  agent_prompt: Fix the parser without weakening tests.
  setup_command: python -m pip install -e .
  test_command: pytest -q
  timeout: 600
  enabled: true
```

`repository_path` is resolved relative to the manifest file.

`setup_command` and `test_command` are trusted benchmark configuration and may
use shell syntax. Agent invocation itself remains argv-based.

### Experiment

```yaml
experiment:
  name: Qwen vs Codex
  tasks: [parser-fix]
  agents: [qwen, codex]
  repetitions: 3
  stop_on_error: false
```

If `tasks` or `agents` is omitted, all enabled definitions of that type are
selected in manifest order.

The experiment safety limit is 10,000 planned runs.

## Lock format

`agentbench lock` emits JSON with `lock_schema_version: 1`.

A lock contains:

- suite ID + manifest SHA-256
- resolved task commit(s)
- task prompt SHA-256
- setup/test commands and timeout
- selected experiment matrix
- agent command templates
- executable identity/version/binary SHA-256
- bounded environment identity
- canonical `identity_sha256`

The identity hash is computed over the canonical lock content excluding the
identity field itself.

## Drift behavior

`agentbench verify` returns:

- exit code `0` when the current resolution matches
- exit code `3` when material drift is detected
- exit code `2` for invalid input/runtime errors

Drift output includes field paths plus expected/actual values.

`agentbench replay` verifies first and refuses to execute if the lock does not
match.

## What the lock intentionally does not capture

AgentBench avoids indiscriminate environment snapshots. The lock does **not**
persist:

- environment variables
- API keys/tokens
- home-directory contents
- full installed-package inventories
- arbitrary machine identifiers

The provenance contract is intentionally bounded to inputs that materially help
explain benchmark reproducibility without collecting secrets.
