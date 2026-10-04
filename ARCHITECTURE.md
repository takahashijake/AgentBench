# AgentBench Architecture

AgentBench is organized around benchmark integrity. The boundaries below are intentional: future coding-agent passes should extend the appropriate layer instead of adding benchmark behavior directly to the API or dashboard.

## 1. API layer

**Path:** \`src/agentbench/api/\`

Responsibilities:

- validate HTTP inputs
- load ORM records
- invoke \`BenchmarkService\`
- render/read persisted results

The API must not implement Git worktree logic, process management, evidence capture, or metric calculation.

## 2. Benchmark orchestration

**Path:** \`src/agentbench/services/benchmark.py\`

\`BenchmarkService\` owns the benchmark lifecycle:

1. verify the source repository
2. allocate a unique artifact bundle
3. create an isolated worktree at \`base_commit\`
4. run optional setup
5. run the coding agent
6. capture Git evidence **before tests**
7. run bounded tests
8. clean up the worktree
9. persist the run record

This module coordinates the lower layers but should avoid reimplementing them.

## 3. Agent adapters

**Path:** \`src/agentbench/adapters/\`

Adapters translate a common benchmark prompt into a concrete agent invocation.

\`ShellAgentAdapter\` parses \`command_template\` with \`shlex.split\`, replaces \`{prompt}\` as an argv value, and delegates process execution to the execution layer. It deliberately does not use \`shell=True\` for agent prompts.

Future Codex, Claude Code, Gemini CLI, or API-backed adapters belong here.

## 4. Process execution

**Path:** \`src/agentbench/execution/\`

Responsibilities:

- spawn commands
- enforce wall-clock timeouts
- capture stdout/stderr
- terminate process groups/trees on timeout
- provide explicit shell execution only for trusted benchmark setup/test commands

No Git or database logic belongs here.

## 5. Git workspace lifecycle

**Path:** \`src/agentbench/utils/git.py\`

Responsibilities:

- recognize repositories
- resolve commits
- create detached temporary worktrees
- force-remove dirty worktrees
- prune stale worktree metadata
- expose basic status/diff helpers

Worktrees are disposable. Anything needed after cleanup must already be in the artifact bundle.

## 6. Evidence capture

**Path:** \`src/agentbench/evidence.py\`

Evidence is captured immediately after the agent exits and before tests run.

The bundle preserves:

- HEAD
- \`git status --short -uall\`
- binary-capable tracked diff from the task base commit
- numstat
- commits made relative to the task base
- copies of non-ignored untracked files
- hashes/sizes for copied untracked files
- aggregate files/insertions/deletions metrics

Tests may mutate a repository, so test-phase status/diff are stored separately and do not replace the agent evidence.

## 7. Artifact storage

**Path:** \`src/agentbench/artifacts.py\`

Every run gets a unique directory. Files are opened in exclusive-create mode so AgentBench does not accidentally overwrite an earlier artifact.

The default root is outside benchmark repositories:

\`\`\`text
~/.local/share/agentbench/runs
\`\`\`

A typical bundle looks like:

\`\`\`text
<run>/
  task.json
  setup/
    stdout.log
    stderr.log
    git-status.txt
    diff.patch
  agent/
    stdout.log
    stderr.log
  git/
    head.txt
    status.txt
    diff.patch
    numstat.txt
    commits.txt
    untracked-manifest.json
    untracked/...
  test/
    stdout.log
    stderr.log
    git-status.txt
    diff.patch
  cleanup.json
  manifest.json
\`\`\`

## 8. Persistence

**Paths:** \`src/agentbench/models/\`, \`src/agentbench/schemas/\`

The database stores searchable summary fields and absolute references to durable artifacts. Large evidence stays in the artifact bundle instead of being duplicated into database columns.

## Integrity rules

A benchmark change is not complete unless these remain true:

1. The source repository is unchanged by the benchmark run.
2. The agent executes only in the isolated worktree.
3. Test execution cannot overwrite the captured agent evidence.
4. Untracked agent files survive worktree deletion in the artifact bundle.
5. Timeouts cannot leave the normal child process tree running.
6. Two executions of the same task never reuse an artifact directory.
7. Dirty worktrees are removable without stale registrations.
8. API ORM queries use ORM models, not Pydantic schemas.
9. Core failure paths are deterministic and tested.

## Next major milestone

Only after the integrity suite is green should AgentBench add the experiment matrix:

\`\`\`text
tasks × agents × repetitions
\`\`\`

That layer should consume the existing single-run service instead of duplicating benchmark execution.
