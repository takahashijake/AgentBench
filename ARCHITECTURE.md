# AgentBench V4 Architecture

AgentBench V4 is organized around two invariants:

> **Evaluation claims must be traceable to reproducible evidence.**

> **New capabilities must enter through explicit extension boundaries rather than
> increasing coupling in the orchestration core.**

V4 keeps the hardened V1 execution lifecycle, V2 statistical semantics, and V3 extension architecture, then
restructures extension points around dependency inversion, composition roots, and
portable contracts.

## Dependency direction

The intended dependency flow is:

```text
transport / composition
  CLI            FastAPI routers
   │                  │
   └────────┬─────────┘
            ▼
       workflow services
   Suite → Experiment → Benchmark
            │              │
            │              ▼
            │        adapter abstraction
            │              ▲
            │              │
            │        adapter registry
            │
            ▼
   persisted canonical data
            │
      ┌─────┴────────┐
      ▼              ▼
 statistics      result bundles
      │              │
      └──────┬───────┘
             ▼
        presentation

benchmark-pack provider protocol
             │
             ▼
       pack registry
             │
             ▼
       materializer
             │
             ▼
       suite manifest
```

The provider protocol does not own I/O. Statistics does not know about services.
Reporting does not execute benchmarks. Transport code composes services but does
not reimplement their semantics.

## Composition roots

There are two primary composition roots.

### CLI

`src/agentbench/cli.py` parses arguments and composes domain/services. Expensive
or security-sensitive logic lives in dedicated modules such as
`result_bundles.py`, `provenance.py`, and the service layer.

### FastAPI

`src/agentbench/api/app.py` exposes `create_app()` and includes focused routers:

- `routers/system.py`
- `routers/pages.py`
- `routers/resources.py`
- `routers/runs.py`
- `routers/experiments.py`

`api/__init__.py` remains a thin compatibility/composition surface.

## 1. Benchmark-pack domain

**Paths:**

- `src/agentbench/benchmark_packs/models.py`
- `src/agentbench/benchmark_packs/provider.py`
- `src/agentbench/benchmark_packs/discovery.py`
- `src/agentbench/benchmark_packs/materializer.py`
- `src/agentbench/benchmark_packs/builtin.py`

### Domain models

`BenchmarkPack` and `PackTaskSpec` are immutable dataclasses. They validate
stable IDs, task files, timeouts, and duplicate definitions.

They contain description, not behavior.

### Provider SPI

`BenchmarkPackProvider` is a structural protocol:

```python
class BenchmarkPackProvider(Protocol):
    @property
    def provider_id(self) -> str: ...
    def packs(self) -> tuple[BenchmarkPack, ...]: ...
```

`PackRegistry` owns global pack-ID uniqueness and provider identity.

The provider contract must not import filesystem/Git/process concerns.

### Optional discovery

Third-party providers may register through the Python entry-point group:

```text
agentbench.pack_providers
```

Discovery is a fault boundary: a broken optional plugin is reported in
`discovery_errors` but does not remove built-in packs.

### Materialization

`PackMaterializer` owns:

- output-directory validation
- deterministic fixture file creation
- Git initialization/commit identity
- generated schema-4 manifest creation

Provider code does not receive filesystem responsibilities.

### Compatibility façade

`src/agentbench/packs.py` preserves V2 imports while delegating to the new package.

## 2. Manifest layer

**Path:** `src/agentbench/manifests.py`

Responsibilities:

- schema-v1/v2/v3/v4 YAML/JSON validation
- resource identity and selection
- relative repository-path resolution
- canonical manifest serialization/hash
- pack ID/version/provider metadata

Generated V4 manifests use schema 4. Older schemas remain readable.

## 3. Provenance and suite locks

**Path:** `src/agentbench/provenance.py`

New V4 locks use lock schema 3. Lock schemas 1 and 2 remain readable so historical V2
artifacts can be diagnosed and compared.

Locks capture bounded material inputs:

- suite schema + canonical manifest digest
- pack ID/version/provider
- exact resolved task commits
- prompt digests
- task execution commands/timeouts
- selected matrix/repetitions
- agent command definition
- executable name/version/binary hash
- AgentBench/Python/platform/Git identity

They deliberately avoid credentials and indiscriminate environment dumps.

Replay remains fail-closed on drift.

## 4. Adapter port and registry

**Paths:**

- `src/agentbench/adapters/base.py`
- `src/agentbench/adapters/registry.py`
- `src/agentbench/adapters/shell.py`

`AgentAdapter` is the execution port consumed by benchmark orchestration.

`AdapterRegistry` maps stable adapter/executable identities to factories.
`BenchmarkService` depends on the registry, not on a concrete shell adapter.

The generic shell implementation exposes `process_result()` through the abstract
adapter contract, eliminating concrete `isinstance` checks in orchestration.

The default Codex/Qwen/Claude/Gemini entries currently select the hardened
shell-backed execution implementation. V3 does not label them as native adapters.
A future native adapter can replace a factory registration without changing
`BenchmarkService`.

## 5. Dependency injection through workflows

### BenchmarkService

Accepts an optional `AdapterRegistry`.

### ExperimentService

Accepts an optional `BenchmarkService`. An injected service must share the same
SQLAlchemy session.

### SuiteService

Accepts an optional `ExperimentService`, with the same session invariant.

This means a custom adapter is usable through the normal
suite → experiment → benchmark product path, not only through an isolated unit
test.

Cross-session dependency injection is rejected because mixing persistence units
of work would make transaction semantics ambiguous.

## 6. Benchmark execution

**Path:** `src/agentbench/services/benchmark.py`

Owns exactly one benchmark lifecycle:

1. resolve task/agent state
2. verify source Git repository
3. allocate write-once artifacts
4. capture bounded run provenance
5. create detached worktree at pinned commit
6. run optional bounded setup
7. construct adapter through registry
8. run bounded agent process
9. capture Git evidence **before tests**
10. run bounded tests
11. force-clean/remove worktree
12. persist one canonical `BenchmarkRun`

No benchmark-pack provider or HTTP router bypasses this lifecycle.

## 7. Experiment orchestration

**Path:** `src/agentbench/services/experiment.py`

Owns:

- deterministic tasks × agents × repetitions planning
- frozen task/agent snapshots
- trial state transitions
- idempotency of terminal cells
- definition-drift rejection
- orchestration error separation
- delegation of each cell to `BenchmarkService`
- aggregation from canonical persisted data

Analysis schema 4 adds explicit resource-skipped/eligible counts while preserving paired comparison and ranking semantics
explicit and deterministic.

## 8. Suite workflow

**Path:** `src/agentbench/services/suite.py`

Owns:

- stable imported resource names
- idempotent task/agent upsert
- manifest-to-persistence binding
- experiment creation/execution composition
- report envelope construction

It does not parse adapter executables or create benchmark runs directly.

## 9. Statistical analysis

**Path:** `src/agentbench/statistics.py`

This is a presentation-independent analysis module.

It owns:

- Wilson success intervals
- numeric summaries
- Student-t mean intervals
- conservative lower-Wilson ranking
- task-level pairwise win/loss/tie counts
- paired mean success-rate difference
- exact two-sided sign test over decisive tasks

The sign test is reported as descriptive evidence and does not influence rank.

Statistics does not depend on database models, services, API, or CLI modules.

## 10. Portable result bundles

**Path:** `src/agentbench/result_bundles.py`

Result bundles are a local service boundary, not an HTTP transport concern.

Export produces a deterministic ZIP with:

- `bundle.json`
- `report.json`
- `report.md`
- portable `experiment.json`
- immutable run artifacts

The bundle manifest authenticates every payload with size + SHA-256 and has its
own canonical identity digest.

Portability rules remove host-local:

- repository paths
- worktree paths
- artifact-store paths
- raw command templates from portable snapshots

Artifact references become logical paths inside the bundle.

Verification happens before extraction. Path traversal, duplicate members,
undeclared payloads, digest mismatches, and oversized archives are rejected.

## 11. API architecture

The HTTP layer is deliberately split by concern. Routers perform:

- request/response translation
- persistence dependency acquisition
- HTTP error mapping
- service composition

They do not own benchmark semantics.

Filesystem result-bundle export remains CLI/local-service functionality rather
than being exposed as an arbitrary server-side file operation.

## 12. Architecture QA

**Path:** `tests/test_architecture.py`

Architecture tests assert structural rules such as:

- `BenchmarkService` does not import `adapters.shell`
- provider contracts do not import materialization dependencies
- statistics/reporting do not depend on orchestration services/models
- `api/__init__.py` stays thin
- result-bundle code does not depend on CLI/API transport

Behavioral extension tests additionally verify:

- third-party provider registration
- global pack-ID collision rejection
- optional plugin failure isolation
- custom adapter factory injection
- injection through experiment/suite workflows
- cross-session injection rejection

This converts architectural intent into executable regression protection.

## 13. Schema evolution policy

V4 distinguishes independent persisted/public formats:

- suite manifest schema: **4**
- analysis schema: **4**
- suite report schema: **4**
- suite lock schema: **3**
- result-bundle schema: **1**

Schema versions change when compatibility expectations change; they are not tied
mechanically to the AgentBench package version.

Readers should remain backward-compatible where doing so is safe and explicit.
Writers emit the current schema.

## Integrity invariants

V4 is incomplete if any of these regress:

1. source repositories remain unchanged by trials
2. trial workspaces are isolated
3. pinned commits are exact
4. process execution is bounded
5. agent evidence is captured before tests
6. non-ignored untracked files survive as evidence
7. artifacts are unique/write-once
8. worktree cleanup is forced and stale metadata pruned
9. benchmark failure remains measurement data
10. orchestration failures remain distinct
11. experiment definitions are frozen
12. terminal trials are not silently rerun
13. definition drift is rejected
14. suite imports remain stable/idempotent
15. lock identity is canonical and tamper-evident
16. replay rejects material drift
17. optional provider failure cannot disable built-ins
18. provider IDs and pack IDs are collision-safe
19. benchmark orchestration does not depend on concrete adapters
20. injected workflow services share one DB session
21. missing telemetry remains missing rather than zero
22. statistical rank rules remain disclosed
23. pairwise ties remain ties
24. sign-test results do not silently affect rank
25. result bundles verify contents before extraction
26. result bundles reject unsafe paths
27. portable metadata excludes host-local paths
28. HTTP transport does not own local bundle filesystem operations

## Post-V3 direction

V4 should build on these seams rather than widen central services. High-value
directions include:

- genuinely native family-specific adapters with typed telemetry contracts
- larger external benchmark providers distributed as separate packages
- static/shareable report publication from verified result bundles
- stronger corpus compatibility/version policy
- richer paired analysis where assumptions are defensible
- explicit persistence repository interfaces if storage backends need to diversify

Distributed workers, cloud control planes, and hosted SaaS are still lower
priority than deepening the local evaluation product.

## V4 resource-awareness boundary

**Path:** `src/agentbench/resources.py`

`TaskRequirements` is immutable benchmark metadata. Requirements flow provider → manifest → lock → experiment snapshot → pre-execution eligibility.

`ExperimentService` owns eligibility because it owns matrix semantics. `BenchmarkService` still owns only a benchmark trial that is actually eligible to execute.

A resource-incompatible cell becomes `skipped`; it is neither an agent failure nor an orchestration error. Analysis schema 4 therefore separates planned, eligible, skipped, benchmark, and orchestration-error counts.

V4 deliberately does not wrap a single SQLAlchemy session in thread workers. Parallel/distributed scheduling requires an explicit persistence/session design rather than cosmetic concurrency.
