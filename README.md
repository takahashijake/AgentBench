# AgentBench

AgentBench is a local-first benchmark harness for coding agents. It runs an agent against a pinned Git commit in an isolated worktree, captures the agent's filesystem/Git evidence before tests can mutate it, runs bounded tests, and stores write-once artifacts outside the benchmark repository.

## Current invariants

- Every benchmark starts from an exact \`base_commit\` in a detached Git worktree.
- The benchmark target repository is not used as the artifact directory.
- Agent commands are parsed into argv and executed without prompt interpolation through a shell.
- Agent, setup, and test processes have bounded timeouts; timed-out process groups are terminated.
- Git evidence is captured before tests run.
- Untracked, non-ignored agent files are copied into the run artifact bundle before worktree cleanup.
- Each run receives a unique write-once artifact directory.
- Dirty benchmark worktrees are force-removed and Git worktree metadata is pruned.

By default, artifacts are written under:

\`\`\`text
~/.local/share/agentbench/runs/
\`\`\`

Override that location with \`AGENTBENCH_RUNS_DIR\`.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). The short version is:

\`\`\`text
API
  -> BenchmarkService (orchestration)
      -> Git worktree lifecycle
      -> AgentAdapter
          -> process execution
      -> Git evidence capture
      -> immutable artifact store
      -> bounded tests
      -> database result
\`\`\`

The benchmark core intentionally remains separate from dashboards and experiment-matrix features.

## Local QA

From the repository root:

\`\`\`bash
python -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
\`\`\`

The GitHub Actions workflow runs the same suite on supported Python versions.

## Run the local API

\`\`\`bash
PYTHONPATH=src uvicorn agentbench.api:app --reload
\`\`\`

The API initializes its database on application startup.

## Development direction

Before expanding into a tasks × agents × repetitions comparison engine, keep the benchmark integrity tests green. New benchmark behavior should normally land with a deterministic test covering its isolation, evidence, timeout, or cleanup semantics.
