# AgentBench V5 portfolio demo

This walkthrough is designed for a technical reviewer: **preflight → locked concurrency → reproducibility → execution → statistics → portable evidence**.

## 1. Install and inspect

```bash
python -m pip install -e ".[dev]"
agentbench --version
agentbench doctor
agentbench pack list
agentbench pack show engineering-v4
agentbench pack preflight engineering-v4
```

For repository health, `make qa` runs the local lint, format, type, test, docs,
package-build, and smoke gates enforced by CI.

## 2. Materialize the V5 suite

```bash
agentbench pack materialize engineering-v4 \
  --output ./benchmarks/engineering-v4 \
  --agent 'qwen=qwen -p "{prompt}" --approval-mode auto-edit' \
  --agent 'codex=codex exec --full-auto "{prompt}"' \
  --repetitions 5 \
  --workers 4

agentbench validate ./benchmarks/engineering-v4/suite.yaml
agentbench preflight ./benchmarks/engineering-v4/suite.yaml
```

The 12-task V4 engineering corpus is retained. V5 materialization emits a
schema-5 suite manifest where `experiment.max_workers: 4` is a reproducible
execution input rather than a hidden runtime switch.

## 3. Lock and verify exact inputs

```bash
agentbench lock ./benchmarks/engineering-v4/suite.yaml \
  --output ./benchmarks/engineering-v4/suite.lock.json

agentbench verify \
  ./benchmarks/engineering-v4/suite.yaml \
  ./benchmarks/engineering-v4/suite.lock.json
```

Lock schema 4 includes task requirements and worker count. Changing either is
material replay drift.

## 4. Execute repeated trials

```bash
mkdir -p results
agentbench replay \
  ./benchmarks/engineering-v4/suite.yaml \
  ./benchmarks/engineering-v4/suite.lock.json \
  --output results/engineering-v4.json \
  --markdown results/engineering-v4.md
```

With 12 tasks, two agents, five repetitions, and four workers, the planned matrix
contains 120 cells. Different task repositories may execute concurrently. Trials
sharing a source repository serialize their Git lifecycle.

Execution history records mode, worker count, status, timestamps, and recovery
metadata. Resource-incompatible cells remain explicit `skipped` observations.

## 5. Inspect comparisons and execution evidence

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md
```

Review observed success rate, Wilson intervals, conservative reliability ranking,
runtime summaries, telemetry coverage, task comparisons, and
`latest_execution` / `execution_history`.

## 6. Resume or recover a persisted experiment

Normal suite replay should use the locked manifest worker count. For a persisted
experiment that still has planned cells:

```bash
agentbench execute 1 --workers 4
```

If a local process died and left an execution lease behind, first verify that no
worker remains, then:

```bash
agentbench recover 1 --confirm-inactive
agentbench execute 1 --workers 4
```

Recovery marks the abandoned attempt `interrupted`.

## 7. Export portable evidence

```bash
agentbench bundle export 1 -o results/experiment-1.zip
agentbench bundle verify results/experiment-1.zip
agentbench bundle inspect results/experiment-1.zip
```

Portable experiment metadata includes execution history; the verified ZIP
envelope remains content-addressed and traversal/tamper resistant.

## 8. Inspect the local UI

```bash
agentbench serve
```

Open `http://127.0.0.1:8000`. The experiment detail page shows the latest
execution mode, worker count, and status.

## What the demo proves

AgentBench does not claim 12 tasks universally rank coding models. The portfolio
contribution is a reproducible evaluation system with deterministic corpora,
host/readiness preflight, locked concurrency, isolated evidence capture,
independent worker persistence units, honest failure/skip semantics, explicit
uncertainty, crash recovery, and verified portable artifacts.
