# Changelog

## 2.0.0 — Portfolio V2

AgentBench V2 turns the reproducible V1 runner into a complete local coding-agent
evaluation product.

### Benchmark corpus

- built-in `smoke-v2` and `core-v2` benchmark packs
- deterministic materialization into standalone Git repositories
- four core task categories: bugfix, feature, regression, and refactor
- schema-v2 corpus metadata: pack identity/version, category, difficulty, and tags
- CLI workflows for pack listing, inspection, and materialization

### Statistical analysis

- analysis schema version 2
- 95% Wilson score intervals for success proportions
- median, sample standard deviation, and Student-t mean intervals for repeated
  runtime/token/change measurements
- conservative agent ranking using the lower Wilson success bound
- deterministic tie-break rules
- pairwise task-level win/loss/tie comparisons
- explicit statistical interpretation and non-significance caveats

### Agent metadata

- agent-family detection for common coding-agent CLIs
- conservative JSON/JSONL usage extraction
- persisted prompt, completion, and total token counts when available
- aggregate token-coverage reporting so missing telemetry is not treated as zero

### Product surface

- `agentbench leaderboard`
- V2 Markdown comparison reports
- experiment index and leaderboard pages in the local dashboard
- pack and leaderboard API endpoints
- updated README, architecture, demo, corpus, manifest, and statistics docs

### QA

CI now exercises the installed V2 workflow itself:

- installed CLI smoke
- built-in pack discovery
- deterministic pack materialization
- generated suite validation
- lock creation and verification
- full pytest suite on Python 3.11 and 3.13

## 1.0.0 — Portfolio V1

AgentBench V1 turns the original benchmark harness into a reproducible local
coding-agent comparison product.

### Product surface

- installable `agentbench` CLI
- versioned YAML/JSON benchmark suites
- persisted tasks × agents × repetitions experiment matrices
- deterministic suite locks and replay verification
- machine-readable JSON reports
- reviewer-friendly Markdown comparison reports
- local FastAPI run dashboard

### Integrity

- exact Git commit resolution
- detached disposable worktrees
- bounded setup/agent/test processes
- pre-test Git evidence capture
- preservation of tracked and non-ignored untracked agent changes
- write-once run artifact directories
- dirty worktree cleanup and stale metadata pruning
- frozen experiment definitions and drift rejection
- per-run agent executable and environment provenance
- tamper-evident lock identities

### QA

The project is tested on Python 3.11 and 3.13. CI installs the package, smoke
tests the CLI, and runs the complete pytest suite.
