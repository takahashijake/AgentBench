# Extension contracts

AgentBench V3 is designed so new benchmark corpora and agent implementations can
be added without editing the benchmark lifecycle.

## Benchmark-pack providers

The provider SPI lives in `agentbench.benchmark_packs`.

A provider must expose:

```python
from agentbench.benchmark_packs import BenchmarkPack, PackTaskSpec


class Provider:
    provider_id = "example.corpora"

    def packs(self) -> tuple[BenchmarkPack, ...]:
        return (
            BenchmarkPack(
                id="example-pack",
                version="1.0.0",
                name="Example pack",
                description="Small external corpus.",
                tasks=(
                    PackTaskSpec(
                        id="example-task",
                        description="Implement the requested behavior.",
                        category="feature",
                        difficulty="medium",
                        tags=("python",),
                        prompt="Implement value() so the tests pass.",
                        files={
                            "value.py": "def value():\n    return 0\n",
                            "test_value.py": "...",
                        },
                    ),
                ),
            ),
        )
```

### Registration

Inside AgentBench code/tests, registration is explicit:

```python
from agentbench.benchmark_packs import PackRegistry

registry = PackRegistry()
registry.register(Provider())
```

A third-party distribution can publish a provider without modifying AgentBench:

```toml
[project.entry-points."agentbench.pack_providers"]
example = "example_agentbench:Provider"
```

The default registry registers built-ins first, then discovers optional entry
points.

### Provider rules

Providers should:

- return immutable pack/task definitions
- use globally stable pack IDs
- use stable provider IDs
- keep task IDs unique within a pack
- define deterministic fixture contents
- avoid filesystem, Git, network, database, and process side effects
- avoid importing AgentBench services

Provider discovery is intentionally fault-isolated. Loading one broken optional
provider records a diagnostic but does not make built-in packs unavailable.

### Materialization boundary

`PackMaterializer` performs:

- output directory checks
- fixture file creation
- deterministic Git initialization/commit
- schema-3 suite generation

That separation is intentional: a corpus provider describes **what** a benchmark
is; infrastructure decides **how** it becomes an executable local fixture.

## Agent adapters

`AgentAdapter` is the runtime port used by benchmark execution.

A custom adapter implements:

```python
class MyAdapter(AgentAdapter):
    def prepare(self, repository_path, base_commit):
        ...

    def run_task(self, prompt, timeout, cwd=None):
        ...

    def terminate(self):
        ...

    def collect_metadata(self):
        ...
```

If the adapter uses AgentBench's bounded process layer, it can also return the
concrete `ProcessResult` through `process_result()`.

### Adapter registry

Factories are registered by stable names:

```python
from agentbench.adapters import AdapterRegistry

registry = AdapterRegistry()
registry.register("my-agent", lambda config: MyAdapter(dict(config)))
```

`BenchmarkService` consumes the registry:

```python
benchmark = BenchmarkService(db, adapter_registry=registry)
```

The service does not import or branch on concrete adapter classes.

### Full-workflow injection

Custom benchmark behavior can travel through normal orchestration:

```python
benchmark = BenchmarkService(db, adapter_registry=registry)
experiments = ExperimentService(db, benchmark_service=benchmark)
suites = SuiteService(db, experiment_service=experiments)
```

Each injected service must use the same SQLAlchemy session. AgentBench rejects
cross-session composition rather than creating ambiguous transaction ownership.

## Default family profiles

The default registry recognizes:

- shell
- codex
- qwen
- claude
- gemini

In V3 these known family keys select the hardened shell-backed adapter. This is a
routing/profile mechanism, **not** a claim that native Codex/Qwen/Claude/Gemini
adapters exist.

A native adapter should be introduced by replacing or adding a factory through the
same registry interface, with family-specific telemetry isolated inside that
adapter.

## Compatibility rules

Extension implementations must preserve the benchmark contract:

- workspace supplied to an adapter is already isolated
- adapters must not mutate the source repository
- timeout/process lifecycle must remain bounded
- benchmark evidence is captured by BenchmarkService before tests
- adapters should return structured metadata without secrets
- plugins must not bypass ExperimentService/BenchmarkService persistence semantics

Architecture tests in `tests/test_architecture.py` and extension tests in
`tests/test_extension_points.py` guard these rules.
