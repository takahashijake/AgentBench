# Benchmark Lifecycle

1. validate the manifest and selected resources
2. preflight frozen host requirements, repositories, and agent executables
3. verify the suite lock, including `max_workers`
4. atomically acquire the experiment coordinator lease
5. persist an execution-attempt record
6. atomically claim planned trials
7. assign each worker an independent SQLAlchemy session
8. serialize Git lifecycle per source repository
9. create an isolated detached worktree
10. run bounded setup and agent execution
11. capture agent Git evidence before tests
12. run bounded tests
13. force cleanup
14. persist the run, complete the trial, and aggregate from canonical data
15. persist execution-attempt terminal status

Resource-incompatible cells become `skipped`. Benchmark failure remains
measurement data. Orchestration failure remains a separate diagnostic state.

With parallel `stop_on_error`, AgentBench stops scheduling new cells after the
first orchestration error but allows already in-flight work to finish.

If a process crashes, explicit recovery can reset stale running claims and mark
the abandoned execution attempt `interrupted`.
