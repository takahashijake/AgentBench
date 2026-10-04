# Changelog

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
