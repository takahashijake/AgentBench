# AgentBench multi-session objective

AgentBench has reached the **Portfolio V2** architecture. Preserve the V1/V2
integrity core and expand evaluation depth rather than rebuilding the runner.

## First action in every fresh coding-agent session

Read `ARCHITECTURE.md`, then run:

```bash
pytest
agentbench pack list
```

If QA fails, repair the regression before adding features.

## V2 completed product boundary

### Reproducibility core

- exact Git commit worktree isolation
- argv-safe prompt invocation
- bounded setup/agent/test execution
- pre-test evidence capture
- immutable artifacts
- deterministic suite locks and replay drift rejection
- per-run executable/environment provenance

### Benchmark corpus

- built-in smoke-v2 and core-v2 packs
- deterministic Git fixture materialization
- schema-v2 pack/category/difficulty/tag metadata
- portable generated suite manifests

### Comparison engine

- persisted tasks × agents × repetitions
- frozen definitions and drift rejection
- benchmark failure vs orchestration-error separation
- overall/per-agent/per-task/per-cell aggregates
- Wilson success intervals
- Student-t numeric summaries
- conservative lower-Wilson reliability ranking
- pairwise task outcomes

### Agent telemetry

- agent-family detection
- conservative JSON/JSONL usage extraction
- canonical prompt/completion/total token persistence
- explicit telemetry coverage

### Product surface

- installed AgentBench 2.0.0 CLI
- pack materialization workflow
- leaderboard command
- JSON + Markdown V2 reports
- experiment leaderboard UI
- pack and leaderboard API endpoints
- V2 corpus/statistics methodology documentation
- CI product-workflow smoke on Python 3.11 and 3.13

## Next major direction: V3

Build **corpus scale + stronger paired comparison** while retaining all V2
semantics.

Recommended sequence:

1. external/plug-in benchmark-pack provider interface
2. larger deterministic multi-file task corpus
3. native Codex/Qwen/Claude/Gemini adapters with explicit structured telemetry
4. paired per-task statistical comparison when assumptions are defensible
5. result-bundle export/import for sharing benchmark outcomes
6. public static report generation suitable for GitHub Pages
7. corpus versioning/migration policy and benchmark-result compatibility checks

Do not prioritize distributed workers, cloud auth, or a hosted SaaS control plane
until local evaluation depth is substantially stronger.

## Preserve layer ownership

- packs: corpus materialization
- manifests: suite validation
- provenance: locks/fingerprints/replay verification
- suite service: workflow composition
- experiment service: matrix semantics
- statistics: analysis only
- benchmark service: one run lifecycle
- adapters: agent invocation
- usage: structured telemetry extraction
- execution: process lifecycle
- Git utils: worktrees
- evidence: pre-test evidence
- artifacts: write-once storage
- reporting: presentation only
- API/CLI: transport and composition

Each coding-agent pass should implement one bounded high-value slice, run QA, fix
regressions, and leave the repository coherent.

Do not commit or push from Qwen sessions.
