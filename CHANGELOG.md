# Changelog

## 3.0.0 — Extensibility and Software Engineering

AgentBench V3 restructures the project around explicit extension contracts while
preserving V1 execution integrity and V2 statistical semantics.

### Architecture

- added immutable benchmark-pack domain models
- added `BenchmarkPackProvider` protocol and collision-safe `PackRegistry`
- added optional entry-point discovery through `agentbench.pack_providers`
- isolated third-party provider failures from built-in corpus availability
- separated corpus description from Git/filesystem materialization
- added adapter factory registry and removed concrete shell-adapter dependency
  from `BenchmarkService`
- propagated dependency injection through `ExperimentService` and `SuiteService`
- rejected cross-session service injection
- refactored FastAPI into an application factory plus focused routers
- added executable architecture dependency tests

### Corpus

- retained `smoke-v2` and `core-v2` compatibility packs
- added `core-v3` with eight deterministic engineering tasks
- added multi-file configuration, graph ordering, path safety, and stateful
  observer/API tasks
- generated packs now use suite schema 3 and record provider identity

### Reproducibility

- V3 writers emit suite-lock schema 2
- schema-1 V2 locks remain readable
- provider identity participates in manifest/lock identity
- existing exact-commit, executable fingerprint, bounded-environment, and
  fail-closed replay guarantees remain intact

### Comparison

- analysis schema version 3
- pairwise task comparison adds mean success-rate difference
- exact two-sided sign test over decisive tasks
- paired statistics remain descriptive and do not alter leaderboard rank

### Result portability

- deterministic verified ZIP result bundles
- content-addressed payload manifest
- portable experiment/report metadata
- immutable run artifacts included by logical bundle path
- verification rejects traversal, duplicates, undeclared data, digest mismatch,
  and oversized archives
- safe extraction verifies before writing and never uses `extractall`
- host-local paths/raw command templates are excluded from portable metadata

### Product surface

- AgentBench package version 3.0.0
- `agentbench bundle export/verify/inspect/extract`
- pack API surfaces provider identities and discovery errors
- V3 paired statistics in Markdown and experiment UI
- updated architecture, extension, bundle, corpus, statistics, manifest, and
  portfolio-demo documentation

### QA

V3 adds tests for:

- provider registration and collisions
- optional provider failure isolation
- adapter dependency injection
- full workflow injection
- cross-session injection rejection
- architecture dependency direction
- deterministic result bundle bytes
- bundle tamper and path-traversal rejection
- host-independent portable metadata
- application-factory route parity
- V3 schema/version compatibility

CI compiles source/tests, exercises the installed V3 CLI, validates provider →
schema-3 manifest → lock workflows, builds the FastAPI application factory on
Python 3.11 and 3.13, and runs the complete test suite.

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
- median, sample standard deviation, and Student-t mean intervals
- conservative lower-Wilson reliability ranking
- pairwise task-level win/loss/tie comparisons

### Reproducibility and product surface

- deterministic suite locks and fail-closed replay
- per-run executable/environment provenance
- JSON and Markdown comparison reports
- experiment leaderboard UI/API
- structured usage extraction and explicit token coverage

## 1.0.0 — Portfolio V1

AgentBench V1 established the reproducible execution core:

- installable CLI and local FastAPI dashboard
- exact Git commit resolution
- detached disposable worktrees
- bounded setup/agent/test processes
- pre-test Git evidence capture
- preservation of tracked and non-ignored untracked changes
- write-once artifact directories
- dirty worktree cleanup/stale-registration pruning
- persisted experiment matrices and frozen definitions
