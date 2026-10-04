# AgentBench V4 portfolio demo

This walkthrough is designed for a technical reviewer: **preflight → corpus → reproducibility → execution → statistics → portable evidence**.

## 1. Install and inspect

```bash
python -m pip install -e ".[dev]"
agentbench --version
agentbench doctor
agentbench pack list
agentbench pack show engineering-v4
agentbench pack preflight engineering-v4
```

For repository health, `make qa` runs the local lint, format, type, test, docs, package-build, and smoke gates enforced by CI.

## 2. Materialize the V4 corpus

```bash
agentbench pack materialize engineering-v4 \
  --output ./benchmarks/engineering-v4 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5

agentbench validate ./benchmarks/engineering-v4/suite.yaml
agentbench preflight ./benchmarks/engineering-v4/suite.yaml
```

The built-in V4 pack contains 12 deterministic software-engineering tasks. Schema-4 manifests carry provider identity plus per-task host requirements. Suite preflight verifies requirements, pinned task repositories, and selected agent executable availability before model work begins.

## 3. Lock and verify exact inputs

```bash
agentbench lock ./benchmarks/engineering-v4/suite.yaml \
  --output ./benchmarks/engineering-v4/suite.lock.json

agentbench verify \
  ./benchmarks/engineering-v4/suite.yaml \
  ./benchmarks/engineering-v4/suite.lock.json
```

Lock schema 3 includes normalized task requirements. Changing a requirement, task input, agent executable identity, or other material input becomes reproducibility drift.

## 4. Execute repeated trials

```bash
mkdir -p results
agentbench replay \
  ./benchmarks/engineering-v4/suite.yaml \
  ./benchmarks/engineering-v4/suite.lock.json \
  --output results/engineering-v4.json \
  --markdown results/engineering-v4.md
```

With 12 tasks, two agents, and five repetitions, the planned matrix contains 120 cells. Resource-incompatible cells are recorded as `skipped` before agent execution and are excluded from agent-success denominators.

## 5. Inspect evidence and comparisons

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md
```

Review planned versus eligible/skipped cells, observed success rate, Wilson intervals, lower-Wilson reliability ranking, runtime summaries, telemetry coverage, task wins/losses/ties, paired success-rate differences, and the descriptive exact sign test.

Individual run artifacts retain setup/agent/test logs, pre-test Git evidence, bounded provenance, cleanup state, and the canonical run manifest.

## 6. Export portable evidence

```bash
agentbench bundle export 1 -o results/experiment-1.zip
agentbench bundle verify results/experiment-1.zip
agentbench bundle inspect results/experiment-1.zip
```

The deterministic ZIP is content-addressed and carries frozen task requirements in portable snapshots. Verification rejects traversal, duplicate members, undeclared payloads, size/digest mismatches, and unsupported envelope versions before extraction.

## 7. Inspect the local UI

```bash
agentbench serve
```

Open `http://127.0.0.1:8000`.

## What the demo proves

AgentBench does not claim 12 tasks universally rank coding models. The portfolio contribution is the evaluation system: extensible deterministic corpora, host/readiness preflight, exact-input locking, isolated execution, evidence integrity, honest skipped/error/failure semantics, explicit statistical uncertainty, and verified portable artifacts.
