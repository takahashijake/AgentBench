# Quickstart

A safe first run uses the built-in deterministic smoke pack.

```bash
agentbench pack show smoke-v2
agentbench pack preflight engineering-v4

agentbench pack materialize smoke-v2 \
  --output ./benchmarks/smoke-v2 \
  --agent 'fixture=python -c "print(1)" {prompt}' \
  --repetitions 1

agentbench validate ./benchmarks/smoke-v2/suite.yaml
agentbench preflight ./benchmarks/smoke-v2/suite.yaml

agentbench lock ./benchmarks/smoke-v2/suite.yaml \
  --output ./benchmarks/smoke-v2/suite.lock.json

agentbench verify \
  ./benchmarks/smoke-v2/suite.yaml \
  ./benchmarks/smoke-v2/suite.lock.json
```

This proves pack discovery, deterministic materialization, manifest validation, exact-input locking, and drift verification without consuming external model credits.

To benchmark a real coding agent, replace the fixture command with an installed agent command such as the examples in the README, then use `agentbench replay` against the verified lock.
