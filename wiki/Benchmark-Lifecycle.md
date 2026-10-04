# Benchmark Lifecycle

1. validate manifest and selected resources
2. resolve exact task commit and verified experiment inputs
3. create a unique artifact directory
4. create an isolated Git worktree
5. run bounded setup
6. run the agent through the adapter interface
7. capture agent Git evidence before tests
8. run bounded tests
9. force cleanup
10. persist the run and aggregate later from canonical data

Benchmark failure is data; orchestration failure is a separate diagnostic state.
