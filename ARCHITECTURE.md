# AgentBench V2 Architecture

AgentBench is organized around one invariant:

> **A ranking is only as credible as the corpus identity, execution evidence, and
> measurement semantics underneath it.**

V2 therefore adds corpus and statistical layers **above** the hardened V1
execution core rather than replacing that core.

## End-to-end product flow

```text
Built-in pack / custom suite
          │
          ├── materialize deterministic Git fixtures
          ▼
   schema-v1/v2 manifest
          │
          ├── canonical manifest hash
          ├── provenance resolution
          ▼
      suite lock ───────────────► verify / replay gate
          │
          ▼
      SuiteService
          ▼
   ExperimentService
          │
          ├── tasks × agents × repetitions
          ├── frozen definitions
          ▼
    BenchmarkService
          │
          ├── detached worktree
          ├── bounded setup
          ├── bounded agent
          ├── pre-test Git evidence
          ├── bounded tests
          └── immutable run bundle
          ▼
    BenchmarkRun rows
          │
          ▼
     statistics.py
          │
          ├── Wilson success intervals
          ├── Student-t numeric summaries
          ├── conservative ranking
          └── pairwise task outcomes
          ▼
 JSON / Markdown / API / local UI
```

## 1. Benchmark corpus

**Path:** `src/agentbench/packs.py`

Owns:

- built-in pack catalog
- task fixture source definitions
- deterministic Git materialization
- generated schema-v2 suite manifests
- pack-specific corpus metadata
- CLI agent-definition parsing

It does not execute agents or write database rows.

The current built-in packs are:

- `smoke-v2`
- `core-v2`

Task repositories are committed with fixed content, identity, timestamps, and
message so corpus commits can be reproduced across workspaces.

## 2. Manifest layer

**Path:** `src/agentbench/manifests.py`

Owns:

- schema-v1/v2 YAML/JSON validation
- corpus metadata
- task category/difficulty/tags
- task/agent selection
- relative repository-path resolution
- canonical manifest SHA-256

It does not touch persistence or execute processes.

## 3. Provenance and replay

**Path:** `src/agentbench/provenance.py`

Owns bounded reproducibility identity:

- suite schema and manifest digest
- benchmark-pack identity
- exact resolved task commits
- prompt digests
- execution commands/timeouts
- task corpus metadata
- selected matrix/repetitions
- agent command template
- resolved executable/version/binary SHA-256
- AgentBench/Python/platform/Git identity

The lock excludes secrets and indiscriminate environment snapshots.

Replay fails closed on material drift.

## 4. Suite workflow

**Path:** `src/agentbench/services/suite.py`

Owns:

- stable resource identities
- idempotent task/agent imports
- manifest-to-database binding
- experiment creation through `ExperimentService`
- suite execution composition
- schema-v2 report envelope construction

It does not bypass the experiment or benchmark service.

## 5. Experiment orchestration

**Path:** `src/agentbench/services/experiment.py`

Owns:

- deterministic `tasks × agents × repetitions` planning
- persisted `ExperimentTrial` cells
- frozen task/agent snapshots
- definition-drift rejection
- idempotent terminal states
- orchestration-error separation
- persisted-data aggregation
- delegation of one cell to `BenchmarkService`

V2 aggregation additionally feeds observed measurements into the statistics
layer.

## 6. Statistical analysis

**Path:** `src/agentbench/statistics.py`

Owns presentation-independent analysis:

- 95% Wilson score intervals for binomial success
- numeric measurement summaries
- Student-t mean intervals
- conservative agent ranking
- pairwise task comparison

The ranking algorithm is deterministic and self-described in result data.

It does not execute benchmarks or mutate persisted measurements.

## 7. Benchmark execution

**Path:** `src/agentbench/services/benchmark.py`

Owns exactly one trial lifecycle:

1. validate task/agent state
2. verify source repository
3. allocate write-once artifact storage
4. capture bounded provenance
5. create detached worktree at the exact task commit
6. execute optional bounded setup
7. execute the coding agent
8. capture Git evidence before tests
9. execute bounded tests
10. force-clean worktree
11. persist one `BenchmarkRun`

V2 also persists structured token usage emitted by the adapter.

## 8. Agent adapters

**Paths:** `src/agentbench/adapters/`

The current shell adapter:

- parses command templates with `shlex`
- inserts prompts as argv values
- delegates lifecycle to bounded process execution
- records process metadata
- detects common agent families
- invokes structured usage extraction

Future native adapters belong here.

## 9. Structured usage

**Path:** `src/agentbench/usage.py`

Owns conservative telemetry extraction from complete JSON/JSONL output events.

Recognized semantics include input/prompt tokens, output/completion tokens, total
tokens, cached input, and reported USD cost.

Arbitrary prose numbers are ignored.

## 10. Execution, Git, evidence, artifacts

**Paths:**

- `src/agentbench/execution/`
- `src/agentbench/utils/git.py`
- `src/agentbench/evidence.py`
- `src/agentbench/artifacts.py`

These V1 layers remain intentionally stable.

They own process groups/timeouts, worktree lifecycle, pre-test evidence capture,
untracked-file preservation, and immutable run storage.

## 11. Persistence

**Paths:** `src/agentbench/models/`, `src/agentbench/schemas/`

Core entities remain:

```text
AgentConfig
BenchmarkTask
BenchmarkRun
Experiment
ExperimentTrial
```

Token columns on `BenchmarkRun` now receive structured measurements when
available.

Statistical summaries are derived from canonical persisted trials/runs and are
not stored as competing source-of-truth rows.

## 12. Reporting

**Path:** `src/agentbench/reporting.py`

Owns Markdown presentation only.

V2 reports display:

- corpus identity
- success uncertainty
- runtime/token measurements
- reliability leaderboard
- pairwise task outcomes
- methodology and interpretation limits
- reproducibility identity

## 13. API / local UI

**Path:** `src/agentbench/api/`

The local application exposes:

- run-level evidence
- experiment lists
- experiment leaderboard views
- built-in pack metadata
- JSON experiment results
- JSON leaderboard results
- OpenAPI documentation

It does not implement benchmark semantics independently.

## 14. CLI

**Path:** `src/agentbench/cli.py`

V2 product commands:

```text
pack list
pack show
pack materialize
validate
doctor
serve
lock
verify
import
run
replay
results
leaderboard
```

## Integrity invariants

V2 is incomplete if any of these fail:

1. Source repositories remain unchanged by benchmark execution.
2. Agents execute only in isolated worktrees.
3. Worktrees resolve to the intended base commit.
4. Tests cannot overwrite captured agent evidence.
5. Non-ignored untracked agent files survive cleanup.
6. Setup/agent/test processes remain bounded.
7. Timeout cleanup terminates the normal child process tree.
8. Artifact directories remain unique and write-once.
9. Dirty worktrees are removed and stale registrations are pruned.
10. Experiment execution still calls `BenchmarkService`.
11. Benchmark failure remains data, not an orchestration error.
12. Terminal trials are not silently rerun.
13. Historical aggregation uses frozen definitions.
14. Definition drift is rejected before trial execution.
15. Parallel duplicate execution is blocked.
16. Suite imports remain stable/idempotent.
17. Lock identity remains canonical and tamper-evident.
18. Replay detects changed manifest/commit/executable/bounded environment.
19. Every new run persists bounded provenance.
20. Pack task commits are deterministic for a given pack version.
21. Missing token telemetry is not counted as zero.
22. Statistical analysis derives only from canonical observed trial data.
23. Ranking rules are deterministic and disclosed.
24. Pairwise quality ties remain ties.
25. Reporting remains presentation-only.

## V2 completion boundary

V2 is a release when:

- package version is 2.0.0
- built-in packs materialize deterministically
- schema-v1 and schema-v2 manifests both validate
- pack metadata participates in provenance
- repeated-trial summaries expose uncertainty
- leaderboard and pairwise results are available through CLI/API/UI
- structured usage can populate canonical token columns
- Markdown reports explain methodology and limitations
- CI exercises pack → validate → lock → verify
- full QA passes on supported Python versions

Post-V2 development should expand corpus scale and comparison sophistication
without weakening these invariants.
