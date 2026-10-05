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
