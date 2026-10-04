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

Experiment summaries include:

- completion rate
- success rate and benchmark-only success rate
- benchmark failures versus orchestration errors
- tests passed/failed
- total/average/min/max runtime
- token totals when adapters report them
- files changed, insertions, and deletions
- per-agent metrics
- per-task metrics
- per-(task, agent) cell metrics across repetitions

A coding agent returning a non-zero exit code is a valid benchmark measurement and does **not** become an experiment orchestration error.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). The main execution path is:

```text
API
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

Keep the integrity and experiment-matrix tests green. The next useful layer is a reproducible benchmark-suite/task manifest and CLI so experiment definitions can be versioned, imported, executed, and exported without constructing database rows manually.
