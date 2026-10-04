# AgentBench

AgentBench is a local-first benchmark and comparison harness for coding agents. It runs agents against pinned Git commits in isolated worktrees, preserves reproducible evidence, and can execute persisted experiment matrices across multiple tasks, agents, and repetitions.

## Benchmark integrity

- Every benchmark starts from an exact `base_commit` in a detached Git worktree.
- The benchmark target repository is not used as the artifact directory.
- Agent commands are parsed into argv and prompts are not interpolated through a shell.
- Agent, setup, and test processes have bounded timeouts with process-tree termination.
- Git evidence is captured before tests run.
- Non-ignored untracked agent files are copied into the artifact bundle before cleanup.
- Each benchmark run receives a unique write-once artifact directory.
- Dirty benchmark worktrees are force-removed and stale Git worktree metadata is pruned.

By default, artifacts are written under:

```text
~/.local/share/agentbench/runs/
```

Override that location with `AGENTBENCH_RUNS_DIR`.

## Experiment matrices

Experiments are persisted as:

```text
tasks × agents × repetitions
```

Each matrix cell is an `ExperimentTrial`. A trial points to a normal `BenchmarkRun` after successful orchestration, so the experiment engine reuses the hardened single-run path rather than duplicating execution logic.

Task and agent definitions are snapshotted when the experiment is planned. If an execution-relevant definition drifts before a trial runs, the trial is recorded as an orchestration error instead of silently benchmarking a different configuration.

Experiment summaries include completion/success rates, benchmark failures versus orchestration errors, tests passed/failed, runtime statistics, token totals when available, code-change totals, and per-agent/per-task/per-cell aggregates.

A coding agent returning a non-zero exit code is a valid benchmark measurement and does **not** become an experiment orchestration error.

## Versioned suite manifests

A complete comparison can now be defined in a version-controlled YAML or JSON file instead of manually constructing database rows.

Example:

```yaml
schema_version: 1
id: qwen-vs-codex-smoke
name: Qwen vs Codex smoke suite
description: Small reproducible comparison over two coding agents.

agents:
  - id: qwen-local
    command_template: qwen -p "{prompt}"
    description: Local Qwen coding agent

  - id: codex
    command_template: codex exec "{prompt}"
    description: Codex CLI

tasks:
  - id: parser-fix
    description: Fix the parser regression and keep the test suite green.
    repository_path: ../fixtures/parser-project
    base_commit: 0123456789abcdef0123456789abcdef01234567
    agent_prompt: |
      Fix the parser regression described by the failing tests.
      Do not weaken or delete tests.
    setup_command: python -m pip install -e .
    test_command: pytest -q
    timeout: 600

experiment:
  tasks: [parser-fix]
  agents: [qwen-local, codex]
  repetitions: 3
  stop_on_error: false
```

Repository paths are resolved relative to the manifest file. Resource IDs are stable: imports persist them as `<suite-id>/<resource-id>`, so importing the same suite again updates the existing task/agent records instead of silently duplicating them. Manifest validation also rejects duplicate IDs, unknown selections, disabled selected resources, unsupported schema versions, malformed commit IDs, and matrices above the existing 10,000-run safety limit.

### CLI

Validate without touching the database:

```bash
PYTHONPATH=src python -m agentbench.cli validate suites/smoke.yaml
```

Idempotently import tasks and agents:

```bash
PYTHONPATH=src python -m agentbench.cli import suites/smoke.yaml
```

Import, plan, execute, aggregate, and export a machine-readable report:

```bash
PYTHONPATH=src python -m agentbench.cli run suites/smoke.yaml \
  --output results/smoke.json
```

Export aggregate results for an already persisted experiment:

```bash
PYTHONPATH=src python -m agentbench.cli results 12 \
  --output results/experiment-12.json
```

The suite report includes the canonical manifest SHA-256, resolved task repositories/base commits, stable resource IDs and database IDs, experiment metadata, and the existing aggregate comparison metrics.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). The execution path is:

```text
suite manifest / API
  -> SuiteService (manifest workflows only)
      -> ExperimentService
          -> planned ExperimentTrial matrix
          -> BenchmarkService for each trial
              -> Git worktree lifecycle
              -> AgentAdapter
                  -> process execution
              -> Git evidence capture
              -> immutable artifact store
              -> bounded tests
              -> BenchmarkRun
          -> aggregate comparison metrics
```

The CLI and suite layer do not reimplement benchmark execution; they resolve versioned file definitions into the same persisted services used by the API.

## Local QA

From the repository root:

```bash
python -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
```

GitHub Actions runs the suite on Python 3.11 and 3.13.

## Run the local API

```bash
PYTHONPATH=src uvicorn agentbench.api:app --reload
```

The API initializes missing database tables on application startup.

### Experiment API

Create a matrix:

```http
POST /api/experiments
{
  "name": "Qwen vs Codex",
  "task_ids": [1, 2, 3],
  "agent_config_ids": [1, 2],
  "repetitions": 3
}
```

Execute its remaining planned trials:

```http
POST /api/experiments/1/run
```

Read aggregated results without re-running anything:

```http
GET /api/experiments/1/results
```

Calling the run endpoint again after all trials are terminal does not create duplicate benchmark runs.

## Development direction

Keep the integrity, experiment-matrix, and suite-manifest tests green. The next useful milestone is stronger run provenance: environment/tool version fingerprints and a suite lock/replay format that can prove a later rerun used the same resolved repositories, agent definitions, and execution environment.
