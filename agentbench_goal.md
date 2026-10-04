# AgentBench multi-session objective

AgentBench has reached the **Portfolio V3** architecture. Preserve the V1/V2
evaluation guarantees and V3 extension boundaries before adding breadth.

## First action in every fresh coding-agent session

Read `ARCHITECTURE.md`, then run:

```bash
python -m compileall -q src tests
pytest
agentbench pack list
```

If QA or architecture tests fail, repair the regression before implementing new
features.

## V3 completed product boundary

### Reproducibility core

- exact Git commit worktree isolation
- argv-safe prompt invocation
- bounded setup/agent/test execution
- pre-test evidence capture
- immutable run artifacts
- schema-versioned suite locks and fail-closed replay
- per-run executable/environment provenance

### Extensible corpus architecture

- immutable `BenchmarkPack` / `PackTaskSpec`
- `BenchmarkPackProvider` protocol
- collision-safe `PackRegistry`
- optional Python entry-point discovery
- plugin failure isolation
- provider/materializer separation
- schema-3 provider provenance
- built-in smoke-v2, core-v2, and eight-task core-v3

### Extensible agent architecture

- `AgentAdapter` execution port
- `AdapterRegistry` factory boundary
- no concrete shell-adapter dependency in `BenchmarkService`
- injection through Benchmark → Experiment → Suite workflow
- cross-session injection guards
- shell-backed family profiles for Codex/Qwen/Claude/Gemini
- no false claim that those profiles are native adapters

### Comparison engine

- deterministic tasks × agents × repetitions
- frozen definitions and drift rejection
- Wilson success intervals
- Student-t numeric summaries
- conservative reliability ranking
- pairwise wins/losses/ties
- mean paired success-rate difference
- exact two-sided sign test over decisive tasks
- no unsupported significance/ranking claims

### Portable results

- deterministic result ZIP bundles
- bundle identity + per-file SHA-256
- portable host-independent metadata
- immutable run artifacts
- verify / inspect / safe extract commands
- traversal / duplicate / tamper / undeclared payload rejection

### Product architecture

- FastAPI `create_app()` composition root
- focused HTTP routers
- local filesystem bundle operations kept out of HTTP
- architecture tests enforcing dependency direction
- Python 3.11 and 3.13 CI product workflows

## Next major direction: V4

Prefer depth through the V3 seams, in this order:

1. **Native adapter contracts** for one or two coding-agent families with typed,
   family-specific telemetry; do not duplicate orchestration.
2. **External corpus package proof**: publish or fixture-test a provider in a
   separate installable package that registers only through the entry-point SPI.
3. **Verified static publication**: render a self-contained shareable report from
   a verified result bundle without database access.
4. **Corpus compatibility policy**: stable task identity, deprecation, migration,
   and result comparability rules across pack versions.
5. **Paired analysis depth** only where assumptions are explicit and defensible.
6. Introduce persistence repository interfaces only if a real second storage
   implementation justifies the abstraction.

Do not prioritize distributed workers, cloud auth, remote execution, or hosted
SaaS until the local extension/plugin story is proven by real integrations.

## Architecture rules

- providers describe corpus data; materializers perform I/O
- registries select implementations; orchestration consumes abstractions
- SuiteService composes ExperimentService; ExperimentService composes
  BenchmarkService; BenchmarkService alone owns one trial lifecycle
- statistics/reporting never execute or persist benchmarks
- result-bundle code stays transport-independent
- HTTP routers perform translation/composition, not business logic
- injected services must share one persistence session
- schema changes are explicit and independently versioned
- optional plugin failures must be isolated
- compatibility façades may delegate but must not become new logic centers
- new features require tests at the extension boundary, not only happy-path tests

Each agent pass should implement one bounded slice, run full QA, and leave the
dependency graph cleaner or no worse than it started.
