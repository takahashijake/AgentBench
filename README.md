# AgentBench V2

**Reproducible benchmark packs, repeated-trial statistics, and transparent leaderboards for coding agents.**

AgentBench is a local-first evaluation platform for coding agents. It materializes deterministic software-engineering tasks as real Git repositories, runs agents against identical pinned commits in isolated worktrees, captures what the agent changed before tests can mutate the workspace, and turns repeated trials into uncertainty-aware comparisons.

V2 moves the project beyond a benchmark harness into a complete evaluation workflow:

- deterministic built-in benchmark packs
- versioned suite manifests and reproducibility locks
- tasks × agents × repetitions experiment matrices
- pre-test Git evidence and immutable run artifacts
- structured token/cost metadata extraction when agents emit JSON
- 95% Wilson intervals for success rates
- Student-t summaries for repeated numeric measurements
- conservative reliability rankings
- pairwise task-level comparisons
- JSON, Markdown, API, and local dashboard outputs

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

## Run a real V2 comparison

Materialize the portable `core-v2` corpus with the coding agents installed on your machine:

```bash
agentbench pack materialize core-v2 \
  --output ./benchmarks/core-v2 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5
```

This creates four standalone Git repositories plus a schema-v2 suite manifest.

Inspect and validate it:

```bash
agentbench validate ./benchmarks/core-v2/suite.yaml
```

Lock the exact benchmark definition and toolchain:

```bash
agentbench lock ./benchmarks/core-v2/suite.yaml \
  --output ./benchmarks/core-v2/suite.lock.json

agentbench verify \
  ./benchmarks/core-v2/suite.yaml \
  ./benchmarks/core-v2/suite.lock.json
```

Run the comparison and export both machine- and reviewer-readable reports:

```bash
agentbench replay \
  ./benchmarks/core-v2/suite.yaml \
  ./benchmarks/core-v2/suite.lock.json \
  --output results/core-v2.json \
  --markdown results/core-v2.md
```

Inspect the experiment-level leaderboard later:

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md
```

Launch the local evaluation UI:

```bash
agentbench serve
```

Then open `http://127.0.0.1:8000`.

## Built-in benchmark packs

List the available packs:

```bash
agentbench pack list
agentbench pack show core-v2
```

### core-v2

| Task | Category | Difficulty | What it probes |
|---|---|---|---|
| `bugfix-duration-parser` | bugfix | easy | parsing, unit conversion, focused regression repair |
| `feature-slug-normalizer` | feature | medium | API contract implementation, string normalization |
| `regression-ttl-cache` | regression | medium | state, time boundaries, stale-data cleanup |
| `refactor-lazy-batching` | refactor | medium | iterator semantics, laziness, one-pass inputs |

The `smoke-v2` pack contains the first two tasks for fast pipeline validation.

Pack repositories are generated with fixed source content, commit message, author/committer identity, and timestamps. Materializing the same pack version produces the same task commit identities, making the corpus portable rather than tied to one checkout path.

AgentBench intentionally ships these as **small deterministic engineering tasks**, not as a claim to replace large public benchmarks such as SWE-bench. Their role is to make the full evaluation pipeline easy to reproduce, inspect, extend, and demonstrate.

## Why repeated trials matter

One run is weak evidence for stochastic coding agents. V2 treats repetition as a first-class experiment dimension:

```text
tasks × agents × repetitions
```

For every aggregate—overall, per agent, per task, and per task/agent cell—AgentBench preserves the original counts and adds descriptive uncertainty.

### Success rates

V2 reports a two-sided **95% Wilson score interval** for success proportions. Wilson intervals behave substantially better than the naive `p ± 1.96·SE` interval for small samples and extreme success rates.

### Runtime, token, and code-change measurements

When at least two measurements exist, numeric summaries include:

- total
- average
- median
- minimum / maximum
- sample standard deviation
- two-sided 95% Student-t interval for the sample mean

These are descriptive uncertainty estimates. AgentBench does not claim repeated trials are statistically independent and does not label rank differences as statistically significant.

## Conservative leaderboard

The V2 ranking is intentionally explicit.

Agents are ordered by:

1. lower bound of the 95% Wilson success-rate interval
2. observed success rate
3. orchestration error rate
4. median runtime
5. stable agent identity

The first value is exposed as the **reliability score**. This makes a tiny perfect sample less likely to outrank a well-tested agent solely because it happened to go 1/1.

Pairwise task comparison is even more conservative: it compares observed success rate per task. Equal-quality outcomes remain ties; runtime is not used to manufacture a task win.

## Structured usage metadata

The shell adapter detects common agent families such as Codex, Qwen, Claude, and Gemini from the executable name.

When stdout/stderr contains complete JSON or JSONL events with recognizable usage fields, AgentBench conservatively extracts:

- prompt/input tokens
- completion/output tokens
- total tokens
- cached-input tokens
- reported USD cost

Only complete JSON objects are inspected. Numbers embedded in arbitrary prose are ignored.

When usage is unavailable, token fields remain null and aggregate reports show token **coverage** instead of pretending missing measurements are zero.

## Reproducibility lock

`agentbench lock` resolves a suite into a tamper-evident identity containing bounded, non-secret inputs that materially affect replay:

- suite schema and manifest SHA-256
- benchmark-pack identity/version when present
- exact resolved task commits
- task prompt SHA-256
- setup/test commands and timeouts
- task category/difficulty/tags
- selected tasks, agents, and repetitions
- agent command templates
- resolved executable name
- executable version output when available
- executable binary SHA-256
- AgentBench version
- Python implementation/version
- OS release/machine architecture
- Git version

It intentionally does **not** dump environment variables, credentials, home-directory state, or arbitrary machine identifiers.

`agentbench verify` exits with code `3` when material drift is detected. `agentbench replay` fails closed instead of spending compute under a different configuration.

## Execution integrity

Every trial still flows through the hardened V1 execution core:

```text
suite / pack manifest
        │
        ├── provenance lock / replay gate
        ▼
   SuiteService
        ▼
 ExperimentService
        ▼
 BenchmarkService
        │
        ├── verify source repository
        ├── create detached worktree at exact commit
        ├── bounded setup
        ├── bounded coding-agent process
        ├── capture Git evidence  ◀── before tests
        ├── bounded tests
        ├── force-clean worktree
        └── persist BenchmarkRun + immutable artifacts
        ▼
 statistical analysis
        │
        ├── uncertainty
        ├── leaderboard
        └── pairwise task comparison
```

Core invariants include:

1. source repositories are not benchmark workspaces
2. agents start from exact pinned commits
3. prompts are argv values, not shell-interpolated strings
4. setup/agent/test execution is bounded
5. agent evidence is captured before tests
6. non-ignored untracked files survive cleanup as evidence
7. run artifact directories are unique and write-once
8. dirty worktrees are force-removed and stale metadata is pruned
9. benchmark failure is a measurement, not an orchestration failure
10. experiment task/agent definitions are frozen at planning time
11. terminal experiment cells are not silently rerun
12. replay rejects provenance drift

## Suite schema V2

V2 remains backward compatible with schema-v1 suite files and adds optional corpus metadata.

```yaml
schema_version: 2
id: my-comparison
name: My coding-agent comparison

benchmark_pack:
  id: core-v2
  version: 2.0.0

agents:
  - id: qwen
    command_template: qwen -p "{prompt}"

  - id: codex
    command_template: codex exec "{prompt}"

tasks:
  - id: task-a
    description: Example benchmark task
    repository_path: ./repositories/task-a
    base_commit: 0123456789abcdef0123456789abcdef01234567
    agent_prompt: Fix the regression without weakening tests.
    test_command: python -m unittest -q
    timeout: 600
    category: bugfix
    difficulty: medium
    tags: [python, regression]

experiment:
  tasks: [task-a]
  agents: [qwen, codex]
  repetitions: 5
  stop_on_error: false
```

See [docs/MANIFEST.md](docs/MANIFEST.md) and [docs/BENCHMARK_PACKS.md](docs/BENCHMARK_PACKS.md).

## CLI surface

```text
agentbench pack list
agentbench pack show <pack>
agentbench pack materialize <pack> -o <dir> --agent <id=command>...

agentbench validate <suite>
agentbench doctor
agentbench lock <suite>
agentbench verify <suite> <lock>
agentbench import <suite>
agentbench run <suite>
agentbench replay <suite> <lock>
agentbench results <experiment-id>
agentbench leaderboard <experiment-id>
agentbench serve
```

`run`, `replay`, `results`, and `leaderboard` support JSON export; the result commands also support human-readable Markdown.

## Local UI and API

The local UI now has two levels:

- **Experiments** — repeated-trial matrices, uncertainty, leaderboard, pairwise outcomes
- **Runs** — canonical execution evidence and provenance for individual trials

Useful V2 endpoints include:

```text
GET /api/health
GET /api/packs
GET /api/packs/{pack_id}
GET /api/experiments
GET /api/experiments/{id}/results
GET /api/experiments/{id}/leaderboard
GET /api/runs
GET /api/runs/{id}
```

Interactive OpenAPI documentation remains at `/docs`.

## Run artifacts

By default, immutable run bundles live under:

```text
~/.local/share/agentbench/runs/
```

Override with `AGENTBENCH_RUNS_DIR`.

A bundle can contain task/provenance manifests, agent/setup/test logs, pre-test Git status and binary diffs, copied untracked files, cleanup evidence, and the final run manifest.

## Quality assurance

CI validates the product on Python 3.11 and 3.13 by:

- installing the package
- smoke-testing the installed CLI
- listing and inspecting built-in packs
- materializing `smoke-v2`
- validating the generated schema-v2 suite
- creating and verifying a reproducibility lock
- running the complete pytest suite

Development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Architecture

Major boundaries are deliberately separate:

- `packs.py` — deterministic benchmark corpus materialization
- `manifests.py` — suite schema and validation
- `provenance.py` — locks, fingerprints, replay verification
- `services/suite.py` — workflow composition
- `services/experiment.py` — matrix execution and persisted aggregation
- `statistics.py` — uncertainty, ranking, pairwise analysis
- `services/benchmark.py` — exactly one benchmark lifecycle
- `adapters/` — agent invocation
- `usage.py` — conservative structured usage extraction
- `execution/` — bounded process lifecycle
- `evidence.py` — pre-test Git evidence
- `artifacts.py` — write-once result storage
- `reporting.py` — presentation only
- `api/` and `cli.py` — transport and product composition

See [ARCHITECTURE.md](ARCHITECTURE.md).

## Project status

**AgentBench V2 is the portfolio release for local coding-agent evaluation.**

It can now answer a concrete question end to end:

> Given the same deterministic engineering corpus and the same repeated-trial policy, which coding agent appears more reliable, what uncertainty surrounds that measurement, how do they compare task-by-task, and can the entire result be replayed against the same code and toolchain?

The next major direction is corpus scale and stronger inferential comparison: larger task packs, native agent adapters, paired statistical tests where assumptions are defensible, result-bundle import/export, and public benchmark-result publication.

See [CHANGELOG.md](CHANGELOG.md) for release history.
