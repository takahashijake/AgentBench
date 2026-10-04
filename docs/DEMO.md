# AgentBench V2 portfolio demo

This walkthrough demonstrates the product in the order a reviewer can understand
it: corpus → reproducibility → execution → statistics → evidence.

## 1. Install and inspect the product

```bash
python -m pip install -e ".[dev]"

agentbench --version
agentbench doctor
agentbench pack list
agentbench pack show core-v2
```

## 2. Materialize a real benchmark corpus

Use coding-agent commands installed on the machine:

```bash
agentbench pack materialize core-v2 \
  --output ./benchmarks/core-v2 \
  --agent 'qwen=qwen -p "{prompt}"' \
  --agent 'codex=codex exec "{prompt}"' \
  --repetitions 5
```

AgentBench creates four standalone Git repositories and a schema-v2 suite
manifest. The task repositories start in deliberately unsolved states.

Review:

```bash
find ./benchmarks/core-v2 -maxdepth 2 -type f
cat ./benchmarks/core-v2/suite.yaml
agentbench validate ./benchmarks/core-v2/suite.yaml
```

## 3. Lock the experiment

```bash
agentbench lock ./benchmarks/core-v2/suite.yaml \
  --output ./benchmarks/core-v2/suite.lock.json
```

The lock resolves exact task commits and fingerprints the agent executables,
AgentBench/Python/platform/Git identity, matrix policy, and corpus metadata.

Verify before running:

```bash
agentbench verify \
  ./benchmarks/core-v2/suite.yaml \
  ./benchmarks/core-v2/suite.lock.json
```

A mismatch fails closed and identifies the drift.

## 4. Execute repeated trials

```bash
mkdir -p results

agentbench replay \
  ./benchmarks/core-v2/suite.yaml \
  ./benchmarks/core-v2/suite.lock.json \
  --output results/core-v2.json \
  --markdown results/core-v2.md
```

With four tasks, two agents, and five repetitions this produces 40 planned trial
cells through the same hardened path.

## 5. Read the leaderboard

```bash
agentbench leaderboard 1 \
  --output results/leaderboard.json \
  --markdown results/leaderboard.md

cat results/leaderboard.md
```

Point out:

- observed success rate
- 95% Wilson success interval
- lower-Wilson reliability score
- median runtime
- token coverage when available
- pairwise task wins/losses/ties

The ranking methodology is printed in the report rather than hidden in code.

## 6. Inspect the dashboard

```bash
agentbench serve
```

Open:

```text
http://127.0.0.1:8000
```

The experiment view shows aggregate reliability and pairwise outcomes. The run
view drills down to canonical execution evidence and provenance.

## 7. Inspect one run bundle

Run artifacts are stored under:

```text
~/.local/share/agentbench/runs/
```

unless `AGENTBENCH_RUNS_DIR` is overridden.

A bundle preserves the exact task definition, environment/executable provenance,
agent stdout/stderr, pre-test Git evidence, test logs, cleanup evidence, and final
manifest.

## 8. Explain what the demo proves

A strong concise explanation is:

> AgentBench makes coding-agent comparisons reproducible at three levels. The
> corpus is deterministic and Git-pinned; execution is isolated and evidence is
> captured before tests; repeated results are summarized with explicit
> uncertainty and a transparent conservative leaderboard.

Do not present the built-in four-task corpus as a universal model benchmark. The
portfolio contribution is the evaluation system and its integrity guarantees.
