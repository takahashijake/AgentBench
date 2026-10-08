# Running Benchmarks

The reliable workflow is **preflight → materialize → validate → lock → verify → replay → report**.

Use `agentbench pack list` to discover corpora, `agentbench pack show <id>` to inspect one, and `agentbench pack preflight <id>` to check host eligibility before materialization.

For a real comparison:

```bash
agentbench pack materialize core-v3 \
  --output ./benchmarks/core-v3 \
  --agent 'qwen=qwen -p "{prompt}" --approval-mode auto-edit' \
  --agent 'codex=codex exec --full-auto "{prompt}"' \
  --repetitions 5 \
  --workers 4

agentbench validate ./benchmarks/core-v3/suite.yaml
agentbench preflight ./benchmarks/core-v3/suite.yaml
agentbench lock ./benchmarks/core-v3/suite.yaml -o ./benchmarks/core-v3/suite.lock.json
agentbench verify ./benchmarks/core-v3/suite.yaml ./benchmarks/core-v3/suite.lock.json
agentbench replay ./benchmarks/core-v3/suite.yaml ./benchmarks/core-v3/suite.lock.json \
  --output results/core-v3.json \
  --markdown results/core-v3.md
```

Do not edit a locked suite and continue as though it is the same experiment. Verification is designed to fail closed when material inputs drift.


## Parallel execution

V5 local parallelism is a **suite input**, not a hidden runtime optimization.
Materialization writes `experiment.max_workers`; locking/replay preserve it.

Workers never share a SQLAlchemy session. Different task repositories can execute
concurrently. Trials that share a source repository are serialized around the Git
worktree lifecycle to avoid repository-metadata races.

For a manually persisted experiment, `agentbench execute <id> --workers N`
records a separate execution attempt with the chosen worker count.

If a process is interrupted, do not blindly reset running cells. First confirm no
worker remains, then run:

```bash
agentbench recover <experiment-id> --confirm-inactive
agentbench execute <experiment-id> --workers 4
```

## Codex structured execution (V11 focused integration)

Configure an agent with `command_template: "codex exec '{prompt}'"`. The dedicated Codex adapter adds `--json` automatically after `exec`, preserving the prompt as one subprocess argument without shell interpolation. The command must start with `codex exec`; interactive Codex entry points are rejected. Keep your existing AgentBench isolation, task workspace, and agent timeout policies in place. Codex CLI must already be installed and authenticated in the execution environment.

The adapter stores a bounded `execution_evidence` object under the existing `adapter_metadata` run result: `source` (Codex JSONL when recognized), `turn_completed`, `tool_activity_count` (distinct IDs for observed command/file/MCP/web events), and `termination_reason` (timeout, process_error, completed, or unknown). Incomplete/malformed lines are ignored; absent activity and cost telemetry are null, not zero estimates. Generic structured token usage is extracted by the existing usage parser where present. This is not a pricing estimator or a proof that tasks succeeded; benchmark tests remain the success authority.

Reproducible no-account check: `python -m pytest tests/test_codex_adapter.py tests/test_result_bundles.py -q`. Running a real agent additionally requires a configured locked benchmark suite, installed Codex CLI, credentials, and permission to run it; CI fixture tests do not establish those prerequisites.
