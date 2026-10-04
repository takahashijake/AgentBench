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

`ExperimentService` now provides:

```text
tasks × agents × repetitions
```

with persisted `ExperimentTrial` cells, execution through the existing `BenchmarkService`, idempotent handling of terminal trials, and aggregate overall/per-agent/per-task metrics.

Do not duplicate either execution layer.

## Next major milestone

Build a **versionable benchmark-suite/task manifest + CLI**.

The goal is to make a complete experiment reproducible from files and commands instead of manually creating database rows.

A strong implementation should include:

- a documented suite manifest format
- deterministic loading/validation
- task definitions with repository path/base commit/prompt/setup/test/timeout
- agent references or definitions
- experiment repetitions and stop-on-error policy
- CLI commands to validate/import/run a suite
- machine-readable JSON result export
- stable identifiers so repeated imports do not silently duplicate suites/tasks/agents
- tests proving manifest round-tripping and deterministic experiment creation

The CLI must call existing services. It must not reimplement benchmark or experiment execution.

## Preserve these boundaries

- API: transport only
- services/experiment.py: matrix planning/execution/aggregation
- services/benchmark.py: one benchmark run
- adapters/: agent invocation
- execution/: process lifecycle
- utils/git.py: worktree lifecycle
- evidence.py: benchmark evidence
- artifacts.py: immutable artifacts
- models/schemas: persistence

Do not prioritize dashboards, cloud deployment, authentication, distributed workers, or LLM-as-a-judge ahead of reproducible suite/CLI workflows.

Each fresh Qwen session should implement one bounded high-value slice, run tests, fix regressions, and leave one concise next objective.

Do not commit or push from Qwen sessions.
