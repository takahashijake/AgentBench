# Quick Start

Check the V4 corpus against the current host:

```bash
agentbench pack preflight engineering-v4
```

For a no-model-credit pipeline check:

```bash
agentbench pack materialize smoke-v2 \
  -o ./benchmarks/smoke-v2 \
  --agent 'fixture=python -c "print(1)" {prompt}' \
  --repetitions 1
agentbench validate ./benchmarks/smoke-v2/suite.yaml
agentbench preflight ./benchmarks/smoke-v2/suite.yaml
agentbench lock ./benchmarks/smoke-v2/suite.yaml -o ./benchmarks/smoke-v2/suite.lock.json
agentbench verify ./benchmarks/smoke-v2/suite.yaml ./benchmarks/smoke-v2/suite.lock.json
```

Pack preflight checks declarative resource requirements. Suite preflight additionally checks pinned repositories and selected agent executables.
