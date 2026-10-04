# AgentBench V4

**Extensible, reproducible evaluation infrastructure for coding agents.**

AgentBench is a local-first platform for comparing coding agents on deterministic
software-engineering tasks. It pins benchmark inputs to Git commits, executes every
trial in an isolated worktree, captures agent evidence before tests can mutate the
workspace, aggregates repeated trials with explicit uncertainty, and can export a
verified portable result bundle.

V3 is primarily a **software-engineering release**. The goal is not to add more
conditionals to a benchmark runner; it is to make AgentBench safe to extend.


## V4 benchmark ecosystem

V4 turns the V3 extension architecture into a larger benchmark ecosystem with explicit host-capability contracts.

- `engineering-v4` expands the built-in engineering corpus from 8 to 12 tasks.
- Tasks can declare minimum CPU, memory, platform, and executable requirements.
- `agentbench pack preflight engineering-v4` reports compatibility before a run.
- Resource-incompatible trials are recorded as `skipped`, not agent failures.
- Manifest/report/analysis/lock schemas advance to 4/4/4/3 so requirements remain reproducible evidence.

V4 intentionally keeps execution sequential. Resource eligibility is explicit; unsafe thread-level scheduling over one SQLAlchemy session is not introduced.

## V3 foundation retained

- **Benchmark-pack provider SPI** — corpus definitions are immutable domain data
  supplied through a registry. Built-ins are one provider, not a special case in
  orchestration code.
- **Optional provider discovery** — third-party Python packages can register pack
  providers through the `agentbench.pack_providers` entry-point group. A broken
  optional provider is isolated and reported instead of disabling built-ins.
- **Separated materialization** — providers describe tasks; `PackMaterializer`
  owns filesystem and Git I/O.
- **Adapter registry** — `BenchmarkService` depends on an adapter factory
  abstraction instead of importing `ShellAgentAdapter`.
- **Dependency injection through the product path** — a custom
  `BenchmarkService` can be injected into `ExperimentService`, and a custom
  `ExperimentService` into `SuiteService`.
- **Application factory + focused HTTP routers** — FastAPI composition is thin;
  system, pages, resources, runs, and experiments are separate route modules.
- **Portable result bundles** — experiments can be exported as deterministic,
  digest-verified ZIP bundles with immutable run artifacts and host-independent
  metadata.
- **Schema V3** — generated suite manifests identify both benchmark-pack version
  and provider. V1/V2 suite manifests remain readable.
- **Suite-lock schema 2** — new locks are explicitly versioned while schema-1 V2
  locks remain readable for drift analysis.
- **Expanded `core-v3` corpus** — eight deterministic tasks, including multi-file
  configuration, dependency-graph, path-safety, and stateful API work.
- **Paired task statistics** — pairwise comparisons now include mean success-rate
  difference and an exact two-sided sign test over decisive tasks.
- **Architecture tests** — tests assert dependency direction, thin composition
  roots, plugin failure isolation, cross-session injection guards, and safe bundle
  verification.

V1's execution-integrity invariants and V2's uncertainty-aware analysis remain in
force.

## Quick start

Requires Python 3.11+ and Git.

```bash
git clone https://github.com/takahashijake/AgentBench.git
cd AgentBench
python -m pip install -e ".[dev]"

agentbench --version
agentbench doctor
agentbench pack list
agentbench pack preflight engineering-v4
pytest
```

## Run a V3 comparison

Materialize the eight-task V3 corpus with agents already installed on your
machine:

```bash
agentbench pack materialize core-v3 \
  --output ./benchmarks/core-v3 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5
```

The generated suite uses manifest schema 3 and records:

```yaml
benchmark_pack:
  id: core-v3
  version: 3.0.0
  provider: agentbench.builtin
```

Validate and lock the exact experiment:

```bash
agentbench validate ./benchmarks/core-v3/suite.yaml

agentbench lock ./benchmarks/core-v3/suite.yaml \
  --output ./benchmarks/core-v3/suite.lock.json

agentbench verify \
  ./benchmarks/core-v3/suite.yaml \
  ./benchmarks/core-v3/suite.lock.json
```

Run against the verified lock:

```bash
mkdir -p results

agentbench replay \
  ./benchmarks/core-v3/suite.yaml \
  ./benchmarks/core-v3/suite.lock.json \
  --output results/core-v3.json \
  --markdown results/core-v3.md
```

Inspect the ranking:

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md
```

## Built-in corpora

`agentbench pack list` is authoritative.

| Pack | Tasks | Purpose |
|---|---:|---|
| `smoke-v2` | 2 | fast pipeline / installation validation |
| `core-v2` | 4 | stable V2 compatibility corpus |
| `core-v3` | 8 | V3 compatibility corpus with multi-file engineering tasks |
| `engineering-v4` | 12 | V4 engineering corpus with host requirements and broader task semantics |

`core-v3` contains:

| Task | Category | Difficulty | Focus |
|---|---|---|---|
| `bugfix-duration-parser` | bugfix | easy | parsing and unit conversion |
| `feature-slug-normalizer` | feature | medium | API-contract implementation |
| `regression-ttl-cache` | regression | medium | state/time boundary semantics |
| `refactor-lazy-batching` | refactor | medium | iterator/laziness semantics |
| `bugfix-config-overlay` | bugfix | medium | recursive multi-file config merge |
| `feature-dependency-order` | feature | medium | deterministic graph ordering |
| `regression-safe-path` | regression | medium | path containment / security edge cases |
| `refactor-event-bus` | refactor | hard | mutation-safe observer API semantics |

These are intentionally small deterministic engineering fixtures. They are not
presented as a substitute for large external benchmarks. The provider interface
exists so larger corpora can be added without changing experiment execution.

## Extension architecture

### Benchmark-pack providers

The stable corpus boundary is `BenchmarkPackProvider`:

```python
class MyProvider:
    provider_id = "acme.benchmarks"

    def packs(self):
        return (my_pack,)
```

Third-party distributions can publish the provider with:

```toml
[project.entry-points."agentbench.pack_providers"]
acme = "acme_agentbench:Provider"
```

Provider code describes immutable `BenchmarkPack` / `PackTaskSpec` values.
Materialization and execution stay in AgentBench infrastructure.

See [docs/EXTENSIONS.md](docs/EXTENSIONS.md).

### Agent adapters

`BenchmarkService` receives an `AdapterRegistry`. The default registry maps
known CLI families and falls back to the generic shell-backed adapter. Custom
factories can be injected without editing benchmark orchestration.

The V3 design intentionally does **not** pretend the current shell-backed Codex,
Qwen, Claude, and Gemini profiles are native integrations. The registry is the
stable seam for future family-specific adapters.

## Portable result bundles

Export one persisted experiment:

```bash
agentbench bundle export 1 -o results/experiment-1.zip
agentbench bundle verify results/experiment-1.zip
agentbench bundle inspect results/experiment-1.zip
agentbench bundle extract results/experiment-1.zip -o results/experiment-1
```

A bundle contains:

- canonical `bundle.json` with an identity SHA-256
- `report.json`
- `report.md`
- portable `experiment.json`
- immutable run artifacts under `artifacts/run-<id>/...`

Every declared payload has a size and SHA-256. Verification rejects duplicate
members, undeclared files, digest mismatches, oversized archives, absolute paths,
backslashes, and traversal components. Extraction verifies first and never calls
`ZipFile.extractall`.

Host-local repository/worktree/artifact paths and raw command templates are not
copied into portable experiment metadata.

See [docs/RESULT_BUNDLES.md](docs/RESULT_BUNDLES.md).

## Statistics

V3 preserves V2's:

- two-sided 95% Wilson intervals for success proportions
- Student-t mean intervals for repeated numeric measurements
- conservative lower-Wilson reliability ranking
- explicit telemetry coverage for measured token counts

Pairwise agent comparisons additionally report:

- task wins / losses / ties
- mean paired success-rate difference
- exact two-sided sign-test p-value over decisive tasks

The sign test is **descriptive** and is not used to manufacture leaderboard rank.
AgentBench does not claim benchmark tasks or repeated trials are independent.

See [docs/STATISTICS.md](docs/STATISTICS.md).

## Execution integrity

Every real trial still flows through the canonical lifecycle:

```text
provider → materializer → manifest → lock
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
                  adapter registry/factory
                            │
                            ▼
                  isolated Git worktree
                            │
         setup → agent → pre-test evidence → tests
                            │
                            ▼
                    immutable artifacts
                            │
                            ▼
              statistics / reports / bundle
```

Important invariants include:

1. source repositories are not benchmark workspaces
2. every trial starts from its pinned commit
3. prompts are argv values, not shell-interpolated strings
4. setup/agent/test processes are bounded
5. agent evidence is captured before tests
6. non-ignored untracked agent files are preserved
7. artifact directories are unique and write-once
8. dirty worktrees are force-cleaned and deregistered
9. benchmark failure remains measurement data
10. orchestration failures remain separate
11. experiment definitions are frozen
12. drift is rejected before execution
13. terminal cells are not silently rerun
14. optional plugins cannot disable built-in providers
15. core orchestration does not import concrete shell adapters
16. portable bundles are content-verified before extraction

## Local UI and API

```bash
agentbench serve
```

Open `http://127.0.0.1:8000`.

The FastAPI application is built through `create_app()`; route modules are split
by concern. Filesystem result-bundle export intentionally remains a local service /
CLI operation instead of being smuggled into an HTTP endpoint.

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

agentbench bundle export <experiment-id> -o <file.zip>
agentbench bundle verify <file.zip>
agentbench bundle inspect <file.zip>
agentbench bundle extract <file.zip> -o <directory>

agentbench serve
```

## Software-engineering design

V3 uses explicit boundaries rather than a growing central service:

- `benchmark_packs/models.py` — immutable corpus domain models
- `benchmark_packs/provider.py` — provider protocol and registry
- `benchmark_packs/discovery.py` — optional entry-point discovery
- `benchmark_packs/materializer.py` — Git/filesystem materialization
- `adapters/base.py` — adapter port
- `adapters/registry.py` — adapter construction / dependency inversion
- `services/benchmark.py` — one trial lifecycle
- `services/experiment.py` — matrix semantics
- `services/suite.py` — suite workflow
- `statistics.py` — pure analysis
- `result_bundles.py` — portable export/verification boundary
- `api/app.py` — application composition
- `api/routers/` — focused HTTP transport
- `reporting.py` — presentation only

`tests/test_architecture.py` asserts key dependency rules so architectural
boundaries are executable constraints, not just documentation.

See [ARCHITECTURE.md](ARCHITECTURE.md).

## Development and quality assurance

Install the development toolchain and run the repository-wide local gate:

```bash
python -m pip install -e ".[dev]"
make qa
```

Individual targets include `make lint`, `make format-check`, `make typecheck`,
`make test`, `make docs`, `make build`, and `make smoke`. Docker users can
also run `make docker-smoke`.

CI runs a dedicated quality job plus integration jobs on Python 3.11 and 3.13.
It verifies:

- the installed dependency graph
- source/test compilation
- Ruff lint and formatting
- type checking of stable domain/extension contracts
- the complete pytest suite with a coverage floor
- strict documentation builds
- wheel and source-distribution builds plus Twine validation
- installed CLI and deterministic pack/lock smoke workflows
- application-factory construction
- provider and adapter injection
- pairwise statistics and result-bundle integrity
- architecture dependency tests
- Docker image build and container CLI smoke behavior

Tag builds create validated release-candidate artifacts but do not publish them
automatically.

## Documentation and contribution

The MkDocs tree under `docs/` covers installation, quickstart, configuration,
execution semantics, result interpretation, schemas, extensions, testing, and
release procedure. A practical wiki-ready navigation layer is under `wiki/`.

Contributors should start with `CONTRIBUTING.md`; security reporting guidance is
in `SECURITY.md`. The issue and pull-request templates ask for reproducible,
sanitized diagnostics rather than credentials or private benchmark data.

## Project status

**AgentBench V4 is the benchmark-ecosystem and resource-awareness release.**

The core question it now answers is broader than V2:

> Can a coding-agent benchmark grow new corpora, adapters, transports, and
> shareable result formats without weakening the reproducibility guarantees or
> coupling every new feature into one central runner?

V3's architecture is designed so the answer is yes.
