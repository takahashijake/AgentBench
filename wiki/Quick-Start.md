# Quick Start

Check the engineering corpus against the current host:

```bash
agentbench pack preflight engineering-v4
```

For a no-model-credit pipeline check with locked local concurrency:

```bash
agentbench pack materialize smoke-v2 \
  -o ./benchmarks/smoke-v2 \
  --agent 'fixture=python -c "print(1)" {prompt}' \
  --repetitions 1 \
  --workers 2
agentbench validate ./benchmarks/smoke-v2/suite.yaml
agentbench preflight ./benchmarks/smoke-v2/suite.yaml
agentbench lock ./benchmarks/smoke-v2/suite.yaml -o ./benchmarks/smoke-v2/suite.lock.json
agentbench verify ./benchmarks/smoke-v2/suite.yaml ./benchmarks/smoke-v2/suite.lock.json
agentbench replay ./benchmarks/smoke-v2/suite.yaml ./benchmarks/smoke-v2/suite.lock.json
```

Schema 5 locks `max_workers`; replay uses that exact value.
