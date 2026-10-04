# Running Benchmarks

The reliable workflow is **preflight → materialize → validate → lock → verify → replay → report**.

Use `agentbench pack list` to discover corpora, `agentbench pack show <id>` to inspect one, and `agentbench pack preflight <id>` to check host eligibility before materialization.

For a real comparison:

```bash
agentbench pack materialize core-v3 \
  --output ./benchmarks/core-v3 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5

agentbench validate ./benchmarks/core-v3/suite.yaml
agentbench lock ./benchmarks/core-v3/suite.yaml -o ./benchmarks/core-v3/suite.lock.json
agentbench verify ./benchmarks/core-v3/suite.yaml ./benchmarks/core-v3/suite.lock.json
agentbench replay ./benchmarks/core-v3/suite.yaml ./benchmarks/core-v3/suite.lock.json \
  --output results/core-v3.json \
  --markdown results/core-v3.md
```

Do not edit a locked suite and continue as though it is the same experiment. Verification is designed to fail closed when material inputs drift.
