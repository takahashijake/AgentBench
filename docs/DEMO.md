# AgentBench V3 portfolio demo

This walkthrough is designed for a technical reviewer: corpus → reproducibility → execution → statistics → portable evidence.

## 1. Install and inspect

```bash
python -m pip install -e ".[dev]"
agentbench --version
agentbench doctor
agentbench pack list
agentbench pack show core-v3
```

For a repository-health review, `make qa` runs the local lint, format, type, test, docs, build, and smoke gates used by CI.

## 2. Materialize the V3 corpus

```bash
agentbench pack materialize core-v3 \
  --output ./benchmarks/core-v3 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5

agentbench validate ./benchmarks/core-v3/suite.yaml
```

The built-in V3 pack contains eight deterministic software-engineering tasks and emits a schema-3 suite manifest with pack provider identity.

## 3. Lock and verify the exact experiment

```bash
agentbench lock ./benchmarks/core-v3/suite.yaml \
  --output ./benchmarks/core-v3/suite.lock.json

agentbench verify \
  ./benchmarks/core-v3/suite.yaml \
  ./benchmarks/core-v3/suite.lock.json
```

The lock records material experiment inputs and execution provenance. Verification fails closed when the suite, task commits, executable identity, or other locked material inputs drift.

## 4. Execute repeated trials

```bash
mkdir -p results
agentbench replay \
  ./benchmarks/core-v3/suite.yaml \
  ./benchmarks/core-v3/suite.lock.json \
  --output results/core-v3.json \
  --markdown results/core-v3.md
```

With eight tasks, two agents, and five repetitions, the planned matrix contains 80 isolated trials.

## 5. Inspect aggregate and task-level evidence

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md
```

Review observed success rate, Wilson intervals, lower-Wilson reliability ranking, runtime summaries, telemetry coverage, task wins/losses/ties, paired success-rate differences, and the descriptive exact sign test.

Then inspect individual run artifacts to see the setup/agent/test process logs, pre-test Git evidence, provenance, cleanup report, and canonical run manifest.

## 6. Export a portable result bundle

```bash
agentbench bundle export 1 -o results/experiment-1.zip
agentbench bundle verify results/experiment-1.zip
agentbench bundle inspect results/experiment-1.zip
```

The ZIP is deterministic and content-addressed. Verification rejects traversal, duplicate members, undeclared payloads, size mismatches, digest mismatches, and unsupported schema versions before extraction.

## 7. Inspect the local UI

```bash
agentbench serve
```

Open `http://127.0.0.1:8000` to inspect experiments, aggregate results, and canonical runs through the application-factory FastAPI surface.

## What the demo proves

AgentBench is not presented as a claim that eight tasks universally rank coding models. The portfolio contribution is the evaluation system: deterministic corpus materialization, exact-input locking, isolated execution, evidence integrity, explicit uncertainty, extension contracts, portable verified artifacts, and reproducible developer tooling.
