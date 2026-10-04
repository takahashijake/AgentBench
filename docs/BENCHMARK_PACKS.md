# Benchmark packs

AgentBench V2 ships deterministic local benchmark corpora that exercise the full
evaluation pipeline without requiring a large external dataset.

## Available packs

`agentbench pack list` is authoritative.

### smoke-v2

A fast two-task pipeline check:

- duration-parser bugfix
- slug-normalizer feature

Use this when validating installation, agent command syntax, provenance locks, or
CI integration.

### core-v2

The portfolio evaluation corpus:

| Task | Category | Difficulty | Primary behavior |
|---|---|---|---|
| bugfix-duration-parser | bugfix | easy | focused unit-conversion repair |
| feature-slug-normalizer | feature | medium | implement a string API contract |
| regression-ttl-cache | regression | medium | exact time-boundary semantics |
| refactor-lazy-batching | refactor | medium | laziness and iterator correctness |

## Materialization

A pack is not a collection of mutable folders checked into the AgentBench
repository. The CLI creates standalone Git repositories:

```bash
agentbench pack materialize core-v2 \
  -o ./benchmarks/core-v2 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5
```

Result:

```text
benchmarks/core-v2/
  suite.yaml
  repositories/
    bugfix-duration-parser/
    feature-slug-normalizer/
    regression-ttl-cache/
    refactor-lazy-batching/
```

Every task repository is initialized with fixed fixture content, commit message,
author/committer identity, and timestamps. The resulting commit is recorded in the
generated suite manifest.

Materializing the same pack version is intended to produce the same task commit
identities, which makes the corpus portable across workspaces.

## Agent definitions

`--agent` uses:

```text
<agent-id>=<command template>
```

and must contain `{prompt}`.

Examples:

```bash
--agent 'qwen=qwen -p "{prompt}"'
--agent 'codex=codex exec "{prompt}"'
--agent 'custom=python my_agent.py --task "{prompt}"'
```

AgentBench parses the template into argv tokens before substituting the prompt,
so the prompt itself is not shell-interpolated.

## Why the fixtures start broken

Each pack task is intentionally committed in an unsolved state. A benchmark is
meaningful only if the agent must change code to satisfy the task contract.

The tests are visible. These packs therefore measure bounded software-engineering
execution, not hidden-test generalization.

That tradeoff is deliberate: the built-in packs are designed to make AgentBench
itself reproducible, inspectable, demonstrable, and easy to extend.

## Extending the corpus

New built-in tasks should:

1. have a narrow, reviewable engineering contract
2. start from a deterministic failing state
3. use standard-library tests when practical
4. avoid network access
5. avoid secrets or external services
6. finish quickly enough for repeated trials
7. represent a distinct engineering behavior
8. include category, difficulty, and tags
9. preserve V1 execution-integrity invariants
10. add deterministic materialization tests

Large external corpora should be integrated as separate pack providers rather
than hard-coded into the execution service.
