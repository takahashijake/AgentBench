# AgentBench Architecture

AgentBench is organized around benchmark integrity and composable comparison. Future coding-agent passes should extend the appropriate layer instead of placing execution logic in the API or dashboard.

## 1. API layer

**Path:** `src/agentbench/api/`

Responsibilities:

- validate HTTP inputs
- load ORM records
- invoke benchmark/experiment services
- return persisted runs, matrices, and aggregate results

The API must not implement Git worktree logic, process management, evidence capture, or metric calculation.

## 2. Experiment orchestration

**Path:** `src/agentbench/services/experiment.py`

`ExperimentService` owns:

- validating experiment dimensions
- creating deterministic `tasks × agents × repetitions` trial matrices
- persisting planned trials before execution
- freezing task/agent definition snapshots at planning time
- rejecting definition drift rather than silently changing a comparison
- invoking `BenchmarkService` once per trial
- distinguishing benchmark failures from orchestration errors
- avoiding duplicate execution of terminal trials
- aggregating overall, per-agent, and per-task metrics

The experiment layer never reimplements a benchmark run.

### Experiment state

Experiments use these states:

- `pending`: planned but not started
- `running`: at least one planned trial is being processed
- `completed`: every trial reached a benchmark run with no orchestration errors
- `completed_with_errors`: every trial is terminal, but one or more cells could not be orchestrated
- `failed`: `stop_on_error` halted the matrix while planned trials remain

Trials use:

- `planned`
- `running`
- `completed`: a `BenchmarkRun` was produced, regardless of benchmark success/failure
- `error`: AgentBench could not produce a benchmark run for that cell

## 3. Benchmark orchestration

**Path:** `src/agentbench/services/benchmark.py`

`BenchmarkService` owns exactly one benchmark lifecycle:

1. verify the source repository
2. allocate a unique artifact bundle
3. create an isolated worktree at `base_commit`
4. run optional setup
5. run the coding agent
6. capture Git evidence **before tests**
7. run bounded tests
8. clean up the worktree
9. persist the `BenchmarkRun`

## 4. Agent adapters

**Path:** `src/agentbench/adapters/`

Adapters translate a common benchmark prompt into a concrete agent invocation. `ShellAgentAdapter` parses `command_template` with `shlex.split`, replaces `{prompt}` as an argv value, and delegates process execution to the execution layer.

Future Codex, Claude Code, Gemini CLI, Qwen variants, or API-backed adapters belong here.

## 5. Process execution

**Path:** `src/agentbench/execution/`

Responsibilities:

- spawn commands
- enforce wall-clock timeouts
- capture stdout/stderr
- terminate process groups/trees on timeout
- provide explicit shell execution only for trusted setup/test commands

## 6. Git workspace lifecycle

**Path:** `src/agentbench/utils/git.py`

Responsibilities:

- recognize repositories
- resolve commits
- create detached temporary worktrees
- force-remove dirty worktrees
- prune stale worktree metadata
- expose basic status/diff helpers

Worktrees are disposable. Anything needed after cleanup must already be persisted.

## 7. Evidence capture

**Path:** `src/agentbench/evidence.py`

Evidence is captured immediately after the agent exits and before tests run. It includes HEAD, status, binary tracked diff, numstat, agent commits, untracked-file copies/hashes, and aggregate change metrics.

## 8. Artifact storage

**Path:** `src/agentbench/artifacts.py`

Every benchmark run gets a unique write-once directory outside the benchmark repository by default.

## 9. Persistence

**Paths:** `src/agentbench/models/`, `src/agentbench/schemas/`

Core entities are:

```text
AgentConfig
BenchmarkTask
BenchmarkRun
Experiment
ExperimentTrial
```

`ExperimentTrial.benchmark_run_id` links matrix planning to the canonical single-run result. This avoids adding experiment-specific semantics to `BenchmarkRun`.

## Experiment metrics

Aggregates expose at least:

- planned/terminal/benchmark run counts
- completion rate
- success rate over planned trials
- success rate over produced benchmark runs
- orchestration error count
- tests passed/failed
- runtime total/average/min/max
- token totals and measurement count
- files changed / insertions / deletions totals and averages

Metrics are produced for the whole experiment, each agent, each task, and each (task, agent) cell across repetitions.

## Integrity rules

A change is not complete unless these remain true:

1. The source repository is unchanged by benchmark execution.
2. The agent executes only in the isolated worktree.
3. Tests cannot overwrite captured agent evidence.
4. Untracked agent files survive worktree deletion.
5. Timeouts do not leave the normal child process tree running.
6. Benchmark artifact directories are unique/write-once.
7. Dirty worktrees are removed without stale registrations.
8. Experiment execution calls `BenchmarkService`; it does not duplicate it.
9. A benchmark failure is a measurement, not an orchestration error.
10. Terminal experiment trials are not automatically executed again.
11. Historical aggregation uses frozen experiment snapshots rather than mutable labels.
12. Definition drift is rejected before a trial executes.
13. A running trial blocks a second concurrent execution request for the same experiment.
14. Core failure paths are deterministic and tested.

## Next major milestone

Build a reproducible benchmark-suite/task manifest and CLI layer on top of these services. Suite definitions should be versionable files that resolve repositories/base commits/tasks, create experiment matrices, execute them, and export machine-readable comparison reports without bypassing the existing services.
