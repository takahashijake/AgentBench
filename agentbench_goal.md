# AgentBench multi-session objective

Continue developing AgentBench into a trustworthy local coding-agent benchmarking and comparison platform.

## First action in every fresh session

Read `ARCHITECTURE.md`, then run:

```bash
PYTHONPATH=src pytest -q
```

If QA fails, repair the regression before adding features.

## Current completed foundations

### Single-run benchmark integrity

The benchmark core already provides:

- detached worktree isolation at an exact base commit
- safe argv-based agent prompt invocation
- bounded setup/agent/test execution
- process-tree termination on timeout
- pre-test Git evidence capture
- tracked + non-ignored untracked change preservation
- unique write-once artifact bundles
- forced dirty-worktree cleanup
- deterministic integration coverage

### Experiment matrix / comparison engine

`ExperimentService` provides:

```text
tasks × agents × repetitions
```

with persisted `ExperimentTrial` cells, execution through the existing `BenchmarkService`, idempotent handling of terminal trials, frozen definitions, drift rejection, and aggregate overall/per-agent/per-task/per-cell metrics.

Do not duplicate either execution layer.

### Versioned suite manifests and CLI

AgentBench now supports reproducible YAML/JSON suite files with:

- schema-versioned validation
- stable suite/task/agent identifiers
- relative repository-path resolution
- canonical manifest SHA-256 digests
- idempotent task/agent import
- deterministic experiment planning from manifest selection order
- CLI commands for validate/import/run/results
- machine-readable JSON suite reports
- end-to-end tests proving the suite path still executes through `ExperimentService` and `BenchmarkService`

The suite layer lives in:

- `src/agentbench/manifests.py`
- `src/agentbench/services/suite.py`
- `src/agentbench/cli.py`

Do not reimplement experiment or benchmark execution there.

## Next major milestone

Build **reproducibility provenance + lock/replay support**.

A strong next implementation should include:

- capture of the concrete agent executable/version used for each run
- lightweight environment fingerprints relevant to reproducibility
- a lock artifact containing resolved task commits, agent definitions, manifest digest, and execution metadata
- a replay/verify path that can detect material drift before running
- deterministic serialization suitable for committing alongside benchmark reports
- tests that prove identical inputs yield the same lock identity and meaningful drift is rejected or surfaced clearly

Avoid collecting huge environment dumps or secrets. Prefer a bounded, documented provenance contract.

## Preserve these boundaries

- API: transport only
- manifests/CLI: versioned definitions and workflow composition only
- services/experiment.py: matrix planning/execution/aggregation
- services/benchmark.py: one benchmark run
- adapters/: agent invocation
- execution/: process lifecycle
- utils/git.py: worktree lifecycle
- evidence.py: benchmark evidence
- artifacts.py: immutable artifacts
- models/schemas: persistence

Do not prioritize dashboards, cloud deployment, authentication, distributed workers, or LLM-as-a-judge ahead of reproducibility provenance.

Each fresh Qwen session should implement one bounded high-value slice, run tests, fix regressions, and leave one concise next objective.

Do not commit or push from Qwen sessions.
