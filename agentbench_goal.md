# AgentBench multi-session objective

Continue developing AgentBench into a trustworthy local coding-agent benchmarking and comparison platform.

## Current architecture

Read \`ARCHITECTURE.md\` before editing. The benchmark core is intentionally split into:

- API: HTTP/database boundary only
- services/benchmark.py: lifecycle orchestration
- adapters/: agent-specific invocation
- execution/: bounded process management
- utils/git.py: disposable worktree lifecycle
- evidence.py: post-agent Git/untracked evidence
- artifacts.py: unique write-once run bundles
- models/schemas: persistence contracts

Do not collapse these boundaries without a concrete reason.

## First action in every fresh session

Run the deterministic QA suite:

\`\`\`bash
PYTHONPATH=src pytest -q
\`\`\`

If it fails, fix the benchmark-integrity regression before adding features.

## Integrity invariants

Preserve these behaviors:

- isolated detached worktree at the task's exact base commit
- no run artifacts written into the benchmark worktree
- safe argv-based prompt injection for coding-agent commands
- bounded setup, agent, and test execution
- process-tree termination on timeout
- Git evidence captured before tests
- tracked and non-ignored untracked agent changes preserved before cleanup
- unique write-once artifact bundle per run
- forced dirty-worktree cleanup and Git metadata pruning
- ORM models kept distinct from Pydantic API schemas

## Next major milestone

Once the QA suite is green, build the experiment matrix / agent comparison engine:

\`\`\`text
tasks × agents × repetitions
\`\`\`

Aggregate at least:

- success rate
- tests passed/failed
- runtime
- token usage when available
- files changed
- insertions/deletions

Build this on top of the existing single-run \`BenchmarkService\`; do not duplicate execution logic.

Do not prioritize dashboards, cloud deployment, authentication, distributed workers, or LLM-as-a-judge ahead of the experiment foundation.

Each fresh session should inspect the current state, implement one bounded high-value slice, run the relevant tests, fix regressions, and leave one concise next objective.

Do not commit or push from Qwen sessions.
