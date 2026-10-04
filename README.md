# AgentBench

**Reproducible local benchmarking and comparison for coding agents.**

AgentBench runs coding agents against pinned Git commits in isolated worktrees,
preserves what the agent actually changed **before tests can mutate the workspace**,
persists comparison matrices, and locks the toolchain/environment so later replays
can detect meaningful drift.

> **Portfolio V1:** installable CLI, suite manifests, experiment matrices,
> provenance locks, replay verification, immutable run evidence, JSON/Markdown
> reports, and a local dashboard.

## Why AgentBench exists

Comparing coding agents is deceptively hard. A useful benchmark needs more than
"run two CLIs and compare exit codes":

- both agents must start from the same code
- the source checkout must not be contaminated by a run
- setup, agent execution, and tests must be bounded
- tests must not overwrite the evidence being evaluated
- historical experiments must not silently change when task/agent definitions do
- a later replay should know if the agent binary or execution environment changed

AgentBench treats those constraints as the product rather than as afterthoughts.

## Quick start

Requires Python 3.11+ and Git.

```bash
git clone https://github.com/takahashijake/AgentBench.git
cd AgentBench

python -m pip install -e ".[dev]"

agentbench --version
agentbench doctor
pytest
```

The installed command is:

```text
agentbench
```

Run the local dashboard/API with:

```bash
agentbench serve
```

Then open `http://127.0.0.1:8000`.

## Five-minute demo

A self-hosted Qwen-vs-Codex suite is included at
[`examples/qwen-vs-codex.yaml`](examples/qwen-vs-codex.yaml).

### 1. Validate the benchmark definition

```bash
agentbench validate examples/qwen-vs-codex.yaml
```

### 2. Resolve and lock the exact benchmark

```bash
mkdir -p results

agentbench lock examples/qwen-vs-codex.yaml \
  --output results/qwen-vs-codex.lock.json
```

The lock captures:

- canonical suite-manifest SHA-256
- exact resolved task commits
- selected task/agent matrix and repetitions
- agent command definitions
- resolved agent executable identity
- executable version output when available
- executable binary SHA-256
- AgentBench version
- Python implementation/version
- OS release/machine architecture
- Git version

No environment-variable dump or secrets are collected.

### 3. Verify before spending compute

```bash
agentbench verify \
  examples/qwen-vs-codex.yaml \
  results/qwen-vs-codex.lock.json
```

Exit code `0` means the current suite/toolchain matches the lock. Exit code `3`
means reproducibility drift was detected; the JSON response identifies changed
fields.

### 4. Replay and export

```bash
agentbench replay \
  examples/qwen-vs-codex.yaml \
  results/qwen-vs-codex.lock.json \
  --output results/qwen-vs-codex.json \
  --markdown results/qwen-vs-codex.md
```

The JSON export is analysis-friendly. The Markdown export is designed to be
reviewed directly in a repository, experiment log, or portfolio.

For a guided walkthrough, see [docs/DEMO.md](docs/DEMO.md).

## Suite format

A complete benchmark comparison lives in a version-controlled YAML or JSON file:

```yaml
schema_version: 1
id: parser-comparison
name: Parser repair comparison

agents:
  - id: qwen
    command_template: qwen -p "{prompt}"

  - id: codex
    command_template: codex exec "{prompt}"

tasks:
  - id: parser-regression
    description: Repair the parser without weakening tests.
    repository_path: ../target-project
    base_commit: 0123456789abcdef0123456789abcdef01234567
    agent_prompt: |
      Fix the parser regression demonstrated by the failing tests.
      Do not weaken, skip, or remove tests.
    setup_command: python -m pip install -e .
    test_command: pytest -q
    timeout: 600

experiment:
  tasks: [parser-regression]
  agents: [qwen, codex]
  repetitions: 3
  stop_on_error: false
```

Repository paths are resolved relative to the manifest. Imported resource names
are stable (`<suite-id>/<resource-id>`), so repeated imports update the same
task/agent records instead of silently duplicating them.

## Execution integrity

Every benchmark run follows one path:

```text
Suite manifest
      │
      ▼
  SuiteService
      │
      ▼
ExperimentService
      │
      ▼
 BenchmarkService
      │
      ├── verify source repository
      ├── allocate write-once artifact bundle
      ├── create detached worktree at exact commit
      ├── run bounded setup
      ├── run coding agent
      ├── capture Git evidence  ◀── before tests
      ├── run bounded tests
      ├── force-clean worktree
      └── persist BenchmarkRun
```

Key guarantees:

1. The benchmark source checkout is not used as the run workspace.
2. The agent starts from an exact commit in a detached worktree.
3. Prompts are passed as argv values rather than shell-interpolated into the agent command.
4. Setup, agent, and test processes have wall-clock bounds.
5. Agent Git evidence is captured before tests run.
6. Non-ignored untracked agent files are copied before cleanup.
7. Run artifact directories are unique and write-once.
8. Dirty worktrees are force-removed and stale worktree metadata is pruned.
9. Agent benchmark failure is a measurement, not an experiment-orchestration failure.
10. Experiment task/agent definitions are frozen at planning time.
11. Terminal experiment cells are not silently executed twice.
12. Suite replay can reject changes in commits, definitions, binaries, or environment provenance.

See [ARCHITECTURE.md](ARCHITECTURE.md) for layer ownership and invariants.

## Experiment engine

Experiments are persisted as:

```text
tasks × agents × repetitions
```

Each cell is an `ExperimentTrial` linked to a canonical `BenchmarkRun`.

Aggregates include:

- planned, terminal, and produced benchmark-run counts
- completion rate
- success rate over the full plan
- success rate over produced benchmark runs
- orchestration-error count
- tests passed/failed
- total/average/min/max runtime
- token totals when adapters report them
- files changed, insertions, and deletions
- per-agent metrics
- per-task metrics
- per-(task, agent) cell metrics across repetitions

## CLI

```text
agentbench validate <suite>
agentbench doctor
agentbench lock <suite> [-o suite.lock.json]
agentbench verify <suite> <lock>
agentbench import <suite>
agentbench run <suite> [--lock lock.json] [--write-lock lock.json]
agentbench replay <suite> <lock>
agentbench results <experiment-id>
agentbench serve
```

`run`, `replay`, and `results` support JSON output with `--output` and
human-readable Markdown with `--markdown`.

## Run artifacts

By default, immutable run bundles are stored under:

```text
~/.local/share/agentbench/runs/
```

Override with `AGENTBENCH_RUNS_DIR`.

A run bundle can contain:

```text
task.json
provenance.json
manifest.json
cleanup.json
agent/
  stdout.log
  stderr.log
setup/
  stdout.log
  stderr.log
  git-status.txt
  diff.patch
test/
  stdout.log
  stderr.log
  git-status.txt
  diff.patch
git/
  ...
```

The Git evidence bundle preserves tracked diffs, numstat/status information,
agent-created commits, hashes/copies of non-ignored untracked files, and aggregate
change metrics.

## Local API

```bash
agentbench serve --host 127.0.0.1 --port 8000
```

Useful endpoints include:

```text
GET  /
GET  /dashboard
GET  /docs
GET  /api/agents
GET  /api/tasks
GET  /api/runs
POST /api/runs
GET  /api/experiments
POST /api/experiments
POST /api/experiments/{id}/run
GET  /api/experiments/{id}/results
```

The dashboard is intentionally local-first; the benchmarking engine and CLI are
the authoritative product surfaces.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

CI installs AgentBench as a package, smoke-tests the installed CLI, and runs the
full test suite on Python 3.11 and 3.13.

The architecture intentionally keeps responsibilities separate:

- `manifests.py`: suite-file validation
- `provenance.py`: locks, environment/tool fingerprints, replay verification
- `services/suite.py`: suite-to-persistence/service composition
- `services/experiment.py`: matrix planning/execution/aggregation
- `services/benchmark.py`: exactly one benchmark lifecycle
- `adapters/`: agent invocation
- `execution/`: bounded process lifecycle
- `utils/git.py`: worktree lifecycle
- `evidence.py`: pre-test Git evidence
- `artifacts.py`: immutable per-run storage
- `reporting.py`: presentation-only report rendering

## Project status

AgentBench V1 is a complete local benchmarking foundation. The next expansion
area is **benchmark-corpus depth and statistical comparison**: curated task packs,
native adapter metadata/token accounting, confidence intervals across repetitions,
and richer ranking/reporting without weakening the reproducibility core.

See [CHANGELOG.md](CHANGELOG.md) for the V1 release summary.
