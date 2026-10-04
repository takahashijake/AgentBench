# Quick Start

```bash
agentbench pack materialize smoke-v2 \
  -o ./benchmarks/smoke-v2 \
  --agent 'fixture=python -c "print(1)" {prompt}' \
  --repetitions 1
agentbench validate ./benchmarks/smoke-v2/suite.yaml
agentbench lock ./benchmarks/smoke-v2/suite.yaml -o ./benchmarks/smoke-v2/suite.lock.json
agentbench verify ./benchmarks/smoke-v2/suite.yaml ./benchmarks/smoke-v2/suite.lock.json
```

This validates the deterministic corpus/materialization/locking path without paid model access.
