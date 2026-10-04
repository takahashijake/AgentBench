# AgentBench multi-session objective

AgentBench has reached **Portfolio V1**. Preserve the reproducibility core and
expand benchmark depth rather than rebuilding the execution architecture.

## First action in every fresh coding-agent session

Read `ARCHITECTURE.md`, then run:

```bash
pytest
```

If QA fails, repair the regression before adding features.

## V1 completed product

### Benchmark integrity

- exact Git commit worktree isolation
- safe argv-based agent prompt invocation
- bounded setup/agent/test execution
- process-tree termination on timeout
- evidence capture before tests
- tracked + non-ignored untracked evidence preservation
- unique write-once artifact bundles
- forced dirty-worktree cleanup

### Comparison engine

- persisted `tasks × agents × repetitions` matrices
- deterministic trial ordering
- frozen task/agent definitions
- drift rejection
- benchmark failure vs orchestration-error separation
- idempotent terminal trials
- overall/per-agent/per-task/per-cell aggregates

### Suite workflow

- versioned YAML/JSON manifests
- deterministic validation and manifest digest
- stable idempotent resource imports
- installed `agentbench` CLI
- JSON and Markdown exports

### Reproducibility provenance

- exact resolved task commits
- task prompt digests
- agent executable/version/binary fingerprints
- AgentBench/Python/platform/Git identity
- canonical tamper-evident lock files
- verify/replay drift gate
- per-run provenance artifacts

### Presentation

- packaged local dashboard
- five-minute demo
- self-hosted Qwen-vs-Codex example suite
- V1 changelog and architecture documentation
- CI installation + CLI smoke test + Python 3.11/3.13 QA

## Next major direction

Build **benchmark corpus + statistical comparison depth** while keeping every V1
integrity invariant.

Recommended sequence:

1. curated multi-task benchmark packs with deterministic fixtures
2. native adapter metadata/token accounting for Qwen/Codex/other agents
3. repeated-trial statistics and confidence intervals
4. ranking/report views based only on persisted measurements
5. exportable benchmark-pack results suitable for public comparison

Do not prioritize cloud deployment, authentication, distributed workers, or
LLM-as-a-judge before the benchmark corpus itself is strong.

## Preserve layer ownership

- manifests: file validation
- provenance: locks/fingerprints/replay verification
- suite service: workflow composition
- experiment service: matrix semantics
- benchmark service: one run lifecycle
- adapters: agent invocation
- execution: process lifecycle
- Git utils: worktrees
- evidence: pre-test evidence
- artifacts: write-once storage
- reporting: presentation only
- API/CLI: transport and composition

Each coding-agent pass should implement one bounded high-value slice, run QA, fix
regressions, and leave the repository in a coherent state.

Do not commit or push from Qwen sessions.
