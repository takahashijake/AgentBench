# Suite manifest and lock reference

AgentBench accepts YAML or JSON suite manifests.

- **schema_version 1** remains supported for V1 custom suites.
- **schema_version 2** adds benchmark-corpus metadata used by V2 packs and reports.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | `1` or `2` |
| `id` | yes | stable suite identifier |
| `name` | no | display name |
| `description` | no | human description |
| `benchmark_pack` | no | corpus ID/version provenance |
| `agents` | yes | one or more agent definitions |
| `tasks` | yes | one or more benchmark tasks |
| `experiment` | no | matrix selection and execution policy |

Resource IDs may contain letters, numbers, `.`, `_`, and `-`.

## Benchmark pack metadata

Schema V2 can identify the corpus that generated the suite:

```yaml
benchmark_pack:
  id: core-v2
  version: 2.0.0
  description: Portable deterministic software-engineering tasks.
```

Pack metadata is included in canonical manifest hashing, reports, and
reproducibility locks.

## Agent

```yaml
- id: qwen
  description: Local Qwen agent
  command_template: qwen -p "{prompt}"
  enabled: true
```

The shell adapter parses the command template with `shlex` and substitutes
`{prompt}` inside argv tokens. The prompt itself is not shell-interpolated.

Built-in pack materialization requires `{prompt}` so generated suites cannot
accidentally define an agent that never receives the task.

## Task

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
  category: bugfix
  difficulty: medium
  tags: [python, parser, regression]
```

`repository_path` is resolved relative to the manifest.

V2's `category`, `difficulty`, and `tags` fields are optional descriptive
corpus metadata. They are included in the manifest identity and suite report.

`setup_command` and `test_command` are trusted benchmark configuration and may
use shell syntax. Agent invocation remains argv-based.

## Experiment

```yaml
experiment:
  name: Qwen vs Codex
  tasks: [parser-fix]
  agents: [qwen, codex]
  repetitions: 5
  stop_on_error: false
```

If `tasks` or `agents` is omitted, all enabled definitions of that type are
selected in manifest order.

The experiment safety limit is 10,000 planned runs.

## Canonical manifest identity

After validation, AgentBench serializes the normalized Pydantic model with sorted
JSON keys and hashes it with SHA-256.

This means semantically equivalent YAML formatting does not define a different
manifest merely because whitespace or key ordering changed.

## Reproducibility lock

`agentbench lock` emits a JSON lock envelope.

The lock includes:

- suite ID and schema version
- benchmark-pack metadata when present
- canonical manifest SHA-256
- resolved task commits
- task prompt SHA-256
- setup/test commands and timeout
- V2 task category/difficulty/tags
- selected experiment matrix
- agent command templates
- executable identity/version/binary SHA-256
- bounded environment identity
- canonical `identity_sha256`

The identity hash is computed over the canonical lock content excluding the
identity field itself.

## Drift behavior

`agentbench verify` returns:

- exit code `0` when current resolution matches
- exit code `3` when material drift is detected
- exit code `2` for invalid input/runtime errors

Drift output includes field paths plus expected/actual values.

`agentbench replay` verifies first and refuses execution when the lock does not
match.

## Bounded provenance

The lock deliberately does not capture:

- environment variables
- API keys/tokens
- home-directory contents
- full installed-package inventories
- arbitrary machine identifiers

The provenance contract is bounded to information that materially helps explain
benchmark reproducibility without collecting secrets.
