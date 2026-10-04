# Benchmark Lifecycle

1. validate the manifest and selected resources
2. preflight frozen host requirements, repositories, and agent executables
3. resolve exact task commits and verified experiment inputs
4. create a unique artifact directory
5. create an isolated Git worktree
6. run bounded setup
7. run the agent through the adapter interface
8. capture agent Git evidence before tests
9. run bounded tests
10. force cleanup
11. persist the run and aggregate from canonical data

A resource-incompatible matrix cell becomes `skipped` before agent execution. Benchmark failure remains measurement data; orchestration failure remains a separate diagnostic state.
