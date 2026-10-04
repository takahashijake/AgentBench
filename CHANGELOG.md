# Changelog

## 7.0.0 — Capability-aware Heterogeneous Scheduling

### Scheduling

- persist durable worker registrations with normalized CPU, memory, platform,
  executable, and label capabilities
- match frozen task requirements before a worker acquires durable ownership
- scan planned trials deterministically and skip incompatible rows without
  mutating them
- add queue diagnostics for eligible owners and unmatched planned work

### Worker product surface

- `agentbench worker register <experiment> --owner <id> [--label ...]`
- `agentbench worker queue <experiment>`
- `worker run` auto-registers host capabilities needed by the experiment
- worker registration heartbeat/update support

### Evidence and privacy

- analysis/report schema 7 exposes active worker registrations and capabilities
- lease-attempt details retain the capability snapshot used for scheduling
- portable bundles hash raw owner IDs instead of exporting host-derived worker
  identities
- AgentBench package/API version 7.0.0


## 6.0.0 — Durable Cross-process Worker Leases

### Worker protocol

- added database-backed worker ownership records with owner IDs and opaque lease tokens
- added bounded lease duration plus periodic heartbeat extension
- added cooperative `agentbench worker run` processes for shared experiments
- added worker status inspection and explicit expired-claim recovery
- added API worker status and recovery surfaces

### Correctness

- separated trial claiming from already-claimed execution
- added fencing callbacks so stale/recovered workers cannot mutate canonical trial state
- mixed local-coordinator/distributed-worker execution is rejected
- expired claims are never automatically requeued

### Evidence

- analysis schema 6 adds worker attempt history and aggregate worker state
- suite report schema 6
- portable bundles include worker ownership history without lease tokens
- package/API version 6.0.0

### QA

- multi-session competing claim coverage
- heartbeat extension coverage
- expiry/requeue coverage
- stale-owner fencing regression coverage
- end-to-end worker execution evidence tests


## 5.0.0 — Bounded Local Parallel Execution

### Execution engine

- added bounded local parallel trial scheduling (1–32 workers)
- each worker owns an independent SQLAlchemy session and BenchmarkService
- added atomic experiment coordinator leasing and atomic planned-to-running trial claims
- serialize Git lifecycle per source repository while allowing independent repositories to overlap
- parallel stop-on-error stops new scheduling while allowing in-flight work to finish

### Persistence and recovery

- added additive `experiment_executions` history table
- persist mode, max worker count, status, timestamps, and bounded execution details
- explicit recovery resets stale running claims only with user acknowledgement
- abandoned running execution attempts are marked `interrupted`

### Reproducibility

- suite manifest schema 5 adds `experiment.max_workers`
- suite-lock schema 4 locks worker count and detects concurrency drift
- analysis/report schema 5 expose execution history/latest execution
- portable result bundles include execution attempts
- suite run/replay use locked worker count; no hidden concurrency override

### Product surface

- AgentBench package/API version 5.0.0
- `agentbench execute <experiment-id> --workers N`
- `agentbench recover <experiment-id> --confirm-inactive`
- pack materialization accepts `--workers N`
- local UI and Markdown reports expose latest execution mode/worker count


## 4.0.0 — Benchmark Ecosystem and Resource-aware Execution

### Corpus

- added `engineering-v4`, a twelve-task deterministic software-engineering corpus
- added bounded-retry, JSONL diagnostics, plugin-registry architecture, and atomic configuration-state tasks
- retained V2/V3 packs as compatibility corpora

### Resource requirements

- added immutable task requirements for CPU count, physical memory, platform allowlists, and required commands
- added `agentbench pack preflight <pack>` with machine-readable eligibility diagnostics
- incompatible trials terminate as explicit `skipped` cells before agent execution
- success-rate denominators use eligible planned runs so host limitations are not scored as agent failures

### Reproducibility

- suite manifest schema 4 carries task requirements
- suite-lock schema 3 includes requirements in drift detection
- analysis schema 4 distinguishes planned, eligible, skipped, benchmark, and orchestration-error counts
- suite report schema 4 and portable task snapshots expose frozen requirements

### Product surface

- AgentBench package/API version 4.0.0
- CI and local smoke workflows preflight the V4 corpus
- resource contracts are included in targeted type checking

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
