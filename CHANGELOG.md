# Changelog

## Unreleased — Productization and Release Readiness

### Developer experience

- added a unified `Makefile` with install, lint, format, type-check, test, docs, build, smoke, and `make qa` targets
- added Ruff, mypy, MkDocs, build/Twine, coverage, and pre-commit development tooling
- documented Python 3.11–3.13 support and fresh-environment setup
- added Docker build/runtime artifacts for a minimal installed CLI environment

### CI and release engineering

- split CI into a static/package quality job and cross-version integration jobs
- added lint and formatter verification
- added targeted type-checking for stable domain/extension contracts
- added coverage reporting and an explicit critical-path floor
- added strict documentation builds and wheel/sdist validation
- added a tag-triggered release-candidate build workflow that uploads validated artifacts without publishing them

### Documentation and governance

- added an MkDocs documentation hierarchy for installation, configuration, execution, result interpretation, QA, schemas, and releases
- refreshed the portfolio demo from V2 to V3
- added wiki-ready operational pages
- added contribution, security, conduct, issue, and pull-request guidance
- expanded generated-artifact and secret hygiene

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

V3 adds tests for provider registration/collisions, optional provider failure isolation, adapter and workflow injection, architecture direction, deterministic/tamper-resistant bundles, host-independent portable metadata, application-factory parity, and schema compatibility.

## 2.0.0 — Portfolio V2

AgentBench V2 turns the reproducible V1 runner into a complete local coding-agent evaluation product.

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
