# Benchmark packs

AgentBench V3 separates benchmark-pack **description** from **materialization**.

Providers return immutable pack/task domain objects. `PackMaterializer` turns a
selected pack into deterministic local Git repositories and a schema-3 suite.

## Built-in provider

The built-in provider identity is:

```text
agentbench.builtin
```

Available built-in packs are listed by:

```bash
agentbench pack list
```

### smoke-v2

Two tasks for fast installation/CI/replay validation.

### core-v2

The stable four-task V2 corpus:

- bugfix-duration-parser
- feature-slug-normalizer
- regression-ttl-cache
- refactor-lazy-batching

### core-v3

V3 expands the corpus to eight tasks:

| Task | Category | Difficulty | Engineering behavior |
|---|---|---|---|
| bugfix-duration-parser | bugfix | easy | parsing/unit conversion |
| feature-slug-normalizer | feature | medium | API contract/string normalization |
| regression-ttl-cache | regression | medium | state/time boundary behavior |
| refactor-lazy-batching | refactor | medium | iterator/laziness semantics |
| bugfix-config-overlay | bugfix | medium | recursive config merge across modules |
| feature-dependency-order | feature | medium | deterministic graph ordering/cycle rejection |
| regression-safe-path | regression | medium | safe path containment and prefix edge cases |
| refactor-event-bus | refactor | hard | mutation-safe stateful observer API |

The additional V3 tasks deliberately introduce more multi-file and design/state
reasoning while remaining deterministic and fast enough for repeated trials.

## Materialization

```bash
agentbench pack materialize core-v3 \
  -o ./benchmarks/core-v3 \
  --agent 'qwen=qwen -p "{prompt}" --approval-mode auto-edit' \
  --agent 'codex=codex exec --full-auto "{prompt}"' \
  --repetitions 5
```

Output:

```text
benchmarks/core-v3/
  suite.yaml
  repositories/
    bugfix-duration-parser/
    feature-slug-normalizer/
    regression-ttl-cache/
    refactor-lazy-batching/
    bugfix-config-overlay/
    feature-dependency-order/
    regression-safe-path/
    refactor-event-bus/
```

Fixture commits use fixed contents, author/committer identity, timestamps, and
commit messages. The resulting commit IDs are written into the suite.

## External providers

Providers can be registered explicitly or discovered through:

```text
agentbench.pack_providers
```

See [EXTENSIONS.md](EXTENSIONS.md).

Pack IDs are globally unique inside one registry. A collision raises an error
instead of allowing provider order to silently change which corpus runs.

Optional discovery failures are isolated and surfaced as diagnostics.

## Corpus design requirements

A high-quality task should:

1. have a narrow reviewable engineering contract
2. start from a deterministic unsolved state
3. use deterministic local tests
4. avoid network/services where practical
5. finish quickly enough for repetitions
6. exercise a distinct engineering behavior
7. identify category/difficulty/tags
8. avoid secrets and external credentials
9. preserve the source/worktree integrity model
10. add deterministic materialization + unsolved-fixture QA

## Scope

Built-in packs are deliberately inspectable evaluation fixtures. They do not
claim to estimate universal coding ability.

Large public or organization-specific corpora should be separate providers, not
new branches in BenchmarkService.
