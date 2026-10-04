# Continuous Evaluation and Regression Gates

AgentBench V9 lets a verified result bundle become a durable baseline for later
agent/model changes.

## Compare two runs

```bash
agentbench regression compare \
  baseline.zip \
  candidate.zip \
  --output comparison.json
```

Both bundles are fully verified before comparison.

AgentBench then checks that they represent the same benchmark:

- identical portable task definitions
- identical repetition count
- identical logical agent-name set

Task IDs and experiment IDs do not need to match because those are local
database identifiers.

## Metrics

For each logical agent, the comparison reports baseline, candidate, and delta for:

- eligible success rate
- reliability score: lower bound of the 95% Wilson interval
- orchestration error rate over eligible planned cells
- median benchmark runtime
- median runtime ratio

The output also includes the baseline/candidate bundle identities and a SHA-256
fingerprint of the portable task definition set.

## Enforce a gate

```bash
agentbench regression gate \
  baseline.zip \
  candidate.zip \
  --max-success-drop 0.02 \
  --max-reliability-drop 0.03 \
  --max-error-rate-increase 0.01 \
  --max-runtime-increase-ratio 0.20
```

Thresholds are fractions. A runtime increase ratio of `0.20` allows the
candidate median runtime to be at most 1.20× the baseline.

Defaults for success, reliability, and orchestration-error deltas are strict
(`0.0`). Runtime is not gated unless explicitly configured.

## Exit codes

- `0` — comparison succeeded or gate passed
- `2` — invalid input, invalid bundle, or incompatible benchmark definitions
- `4` — evidence was valid/compatible but a regression policy was violated

This distinction is useful in CI because a quality regression is not the same
kind of failure as corrupted evidence or a changed benchmark.

## CI example

```yaml
- name: AgentBench regression gate
  run: |
    agentbench regression gate \
      artifacts/baseline.zip \
      artifacts/candidate.zip \
      --max-success-drop 0.03 \
      --max-reliability-drop 0.05
```

Store the JSON output as a CI artifact when a gate fails so reviewers can see
which agent/metric crossed the threshold.

## Interpretation

Regression gates are operational policy, not statistical significance tests.
Wilson lower-bound changes provide an uncertainty-aware reliability signal, but
AgentBench does not claim repeated trials or benchmark tasks are independent.
