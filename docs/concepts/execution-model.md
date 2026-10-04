# Execution Model

Each benchmark trial is treated as an auditable state transition rather than a best-effort subprocess call.

1. Resolve the task and agent configuration.
2. Verify the source repository and pinned commit.
3. Allocate a unique write-once artifact directory.
4. Capture bounded provenance.
5. Create an isolated detached Git worktree.
6. Run optional setup with a timeout.
7. Execute the selected agent through the adapter contract.
8. Capture Git evidence before tests can mutate the workspace.
9. Run bounded tests.
10. Clean and deregister the worktree.
11. Persist the canonical run result.

Benchmark failures are measurement data; orchestration failures are recorded separately. A failed task should not be reclassified as successful because cleanup, parsing, or reporting encountered a secondary issue.
