# AgentBench multi-session objective

Continue developing the current repository into a trustworthy local coding-agent benchmarking platform.

Immediate priorities:
- make benchmark runs isolated, reproducible, and trustworthy
- create immutable per-run artifacts
- capture tracked and untracked agent changes
- preserve setup, agent, test, and Git evidence
- fix prompt quoting, process timeout, and Git worktree lifecycle issues
- add deterministic integration tests
- clean repository hygiene and generated artifacts

Once benchmark-run integrity is complete and validated, move to the next major milestone:

Build an experiment matrix / agent comparison engine capable of running:

tasks × agents × repetitions

and aggregating metrics such as:
- success rate
- tests passed
- runtime
- token usage when available
- files changed
- insertions/deletions

Do not prioritize dashboards, cloud deployment, authentication, distributed workers, or LLM-as-a-judge before the benchmark and experiment foundations are reliable.

Each fresh session should:
1. inspect the current repository state
2. determine the highest-value unfinished implementation slice
3. implement it
4. run relevant tests
5. fix regressions when feasible
6. leave a concise handoff for the next fresh session

Do not commit or push.
