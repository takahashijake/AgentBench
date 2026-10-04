# Five-minute AgentBench demo

This walkthrough is designed to show the product to a reviewer without explaining
the implementation first.

## 1. Install

```bash
python -m pip install -e ".[dev]"
agentbench doctor
```

`doctor` prints the bounded environment identity that participates in replay
verification.

## 2. Inspect the suite

```bash
cat examples/qwen-vs-codex.yaml
agentbench validate examples/qwen-vs-codex.yaml
```

The example compares Qwen and Codex against the same pinned historical AgentBench
commit, prompt, tests, timeout, and repetition count.

## 3. Lock the experiment

```bash
agentbench lock examples/qwen-vs-codex.yaml \
  --output results/qwen-vs-codex.lock.json
```

The lock resolves the exact Git commit and fingerprints the concrete agent
executables, AgentBench version, Python version, OS/machine identity, and Git
version. Its SHA-256 is the experiment's reproducibility identity.

## 4. Verify before spending compute

```bash
agentbench verify \
  examples/qwen-vs-codex.yaml \
  results/qwen-vs-codex.lock.json
```

Exit code 0 means the current environment matches the lock. Exit code 3 means
material drift was found and the JSON output identifies each changed field.

## 5. Run and export

```bash
agentbench replay \
  examples/qwen-vs-codex.yaml \
  results/qwen-vs-codex.lock.json \
  --output results/qwen-vs-codex.json \
  --markdown results/qwen-vs-codex.md
```

Each matrix cell is executed through the same hardened benchmark path:

```text
suite -> experiment -> isolated worktree -> agent -> evidence -> tests -> result
```

The JSON report is intended for machines and later analysis. The Markdown report
is intended for a portfolio, README attachment, experiment review, or pull request.

## 6. Inspect evidence

Run:

```bash
agentbench results 1 --markdown results/experiment-1.md
```

Per-run artifacts are stored outside the benchmark repository by default under:

```text
~/.local/share/agentbench/runs/
```

A run bundle includes the task definition, provenance, agent logs, setup/test
logs when applicable, pre-test Git evidence, copied untracked files, cleanup
status, and a final manifest.
