# AgentBench Architecture

AgentBench V1 is structured around one principle: **comparison is only useful when
execution integrity and reproducibility are first-class constraints**.

The layers below are intentionally narrow. New features should compose these
layers instead of bypassing them.

## Product flow

```text
Versioned suite manifest
        │
        ├── validate
        │
        ├── resolve provenance ──► suite.lock.json
        │                           │
        │                           └── verify / replay gate
        ▼
    SuiteService
        ▼
  ExperimentService
        ▼
   BenchmarkService
        ▼
 isolated worktree
        ▼
      agent
        ▼
 pre-test evidence
        ▼
      tests
        ▼
 persisted BenchmarkRun + immutable artifacts
        ▼
 comparison aggregation
        ▼
 JSON / Markdown report
```

## 1. Manifest layer

**Path:** `src/agentbench/manifests.py`

Owns:

- schema-versioned YAML/JSON loading
- deterministic validation
- task/agent resource IDs
- experiment selections
- relative repository-path resolution
- canonical manifest SHA-256

It does not touch the database or execute processes.

## 2. Provenance and replay layer

**Path:** `src/agentbench/provenance.py`

Owns bounded reproducibility identity:

- exact resolved task commits
- task prompt digest
- setup/test commands and timeout
- selected matrix/repetition policy
- agent command template
- resolved executable name
- executable version output when available
- executable binary SHA-256
- AgentBench version
- Python implementation/version
- OS release/machine architecture
- Git version
- canonical lock identity SHA-256

The lock intentionally excludes environment-variable dumps, credentials, and
other high-volume or secret state.

`verify_suite_lock` compares a fresh resolution against a saved lock. A replay
must fail closed when material drift is detected.

## 3. Suite workflow layer

**Path:** `src/agentbench/services/suite.py`

Owns:

- stable imported identities using `<suite-id>/<resource-id>`
- idempotent task/agent upserts
- manifest selection → database ID translation
- experiment creation through `ExperimentService`
- suite execution composition
- machine-readable report envelope construction

It must never create `BenchmarkRun` rows directly.

## 4. Experiment orchestration

**Path:** `src/agentbench/services/experiment.py`

Owns:

- deterministic `tasks × agents × repetitions` matrices
- persisted `ExperimentTrial` cells
- frozen task/agent snapshots
- definition-drift rejection
- trial state transitions
- orchestration-error handling
- idempotence for terminal trials
- overall/per-agent/per-task/per-cell aggregation
- delegation of each trial to `BenchmarkService`

A benchmark failure is data. An orchestration failure means AgentBench could not
produce the benchmark measurement.

## 5. Benchmark orchestration

**Path:** `src/agentbench/services/benchmark.py`

Owns exactly one benchmark lifecycle:

1. validate task/agent state
2. verify source repository
3. allocate a unique write-once artifact directory
4. capture bounded run provenance
5. create a detached worktree at the requested commit
6. run optional bounded setup
7. run the coding agent
8. capture Git evidence **before tests**
9. run bounded tests
10. force-clean the worktree
11. persist one `BenchmarkRun`

No other layer should reimplement this lifecycle.

## 6. Agent adapters

**Path:** `src/agentbench/adapters/`

Adapters translate a common prompt into a concrete agent invocation.

The current `ShellAgentAdapter`:

- parses `command_template` using `shlex.split`
- substitutes `{prompt}` as an argv value
- does not shell-interpolate the prompt
- delegates process lifecycle to the execution layer
- exposes execution metadata to the benchmark result

Future native Codex/Qwen/Claude/Gemini/API adapters belong here.

## 7. Process execution

**Path:** `src/agentbench/execution/`

Owns:

- subprocess creation
- stdout/stderr capture
- wall-clock timeouts
- process-group/tree termination
- explicit trusted-shell execution for setup/test commands

The agent prompt path is argv-based; setup/test commands are user-authored trusted
benchmark configuration.

## 8. Git workspace lifecycle

**Path:** `src/agentbench/utils/git.py`

Owns:

- Git repository recognition
- commit resolution
- detached temporary worktree creation
- forced dirty-worktree removal
- stale worktree metadata pruning
- basic Git helpers

A benchmark worktree is disposable. Anything needed after cleanup must already
be persisted.

## 9. Evidence capture

**Path:** `src/agentbench/evidence.py`

Evidence is captured immediately after the agent exits and before test execution.

It preserves:

- HEAD
- status
- tracked binary diff
- numstat
- commits produced by the agent
- non-ignored untracked file copies/hashes
- aggregate change metrics

This ordering is an integrity invariant: test commands are allowed to modify the
worktree, but those modifications must not become agent evidence.

## 10. Artifact storage

**Path:** `src/agentbench/artifacts.py`

Each benchmark receives a unique write-once directory, outside the target
repository by default.

Artifact writes use exclusive creation so a later phase cannot silently overwrite
earlier evidence.

## 11. Persistence

**Paths:** `src/agentbench/models/`, `src/agentbench/schemas/`

Core entities:

```text
AgentConfig
BenchmarkTask
BenchmarkRun
Experiment
ExperimentTrial
```

`ExperimentTrial.benchmark_run_id` links matrix planning to the canonical
single-run result without polluting `BenchmarkRun` with experiment-only semantics.

## 12. Reporting

**Path:** `src/agentbench/reporting.py`

Reporting is presentation-only. It receives persisted aggregate data and emits a
reviewer-friendly Markdown representation.

It must not calculate new benchmark semantics or change stored results.

## 13. API / dashboard

**Path:** `src/agentbench/api/`

The FastAPI surface is transport and local inspection only:

- HTTP validation
- ORM loading
- service invocation
- persisted run/experiment retrieval
- local HTML dashboard

The API does not own benchmark logic.

## 14. CLI

**Path:** `src/agentbench/cli.py`

The installed `agentbench` command composes the layers above.

Product commands:

```text
validate
doctor
serve
lock
verify
import
run
replay
results
```

## Integrity invariants

A change is incomplete unless all of these remain true:

1. Source repositories are unchanged by benchmark execution.
2. Agents execute only in isolated worktrees.
3. Worktrees resolve to the intended base commit.
4. Tests cannot overwrite captured agent evidence.
5. Non-ignored untracked agent files survive cleanup.
6. Setup/agent/test processes are bounded.
7. Timed-out processes do not leave the normal child process tree running.
8. Artifact directories are unique and write-once.
9. Dirty worktrees are removed and stale registrations are pruned.
10. Experiment execution calls `BenchmarkService`.
11. Benchmark failure remains a measurement rather than an orchestration error.
12. Terminal experiment trials are not silently rerun.
13. Historical aggregation uses frozen snapshots.
14. Definition drift is rejected before trial execution.
15. Parallel duplicate execution is blocked by running-trial state.
16. Suite imports are stable/idempotent.
17. Lock identity is canonical and tamper-evident.
18. Replay detects changed manifest, commit, executable, or bounded environment identity.
19. Every new run persists bounded provenance.
20. Reporting remains presentation-only.

## V1 completion boundary

V1 is complete when:

- the package installs cleanly
- the CLI smoke-tests after installation
- suite lock/verify/replay is covered
- benchmark provenance is persisted
- JSON and Markdown reports are available
- the local UI loads from packaged templates
- the complete QA suite passes on supported Python versions

Post-V1 work should expand **benchmark depth and analysis**, not weaken these
integrity boundaries. High-value next areas are curated benchmark packs, native
agent metadata/token accounting, statistical confidence across repetitions, and
richer comparison/ranking reports.
