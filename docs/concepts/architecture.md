# Architecture

AgentBench is organized around explicit dependency boundaries. The root `ARCHITECTURE.md` contains the complete design rationale and invariant list; this page is the documentation-site summary.

```text
CLI / FastAPI
      |
      v
 SuiteService
      |
      v
ExperimentService
      |
      v
BenchmarkService ---> AdapterRegistry ---> AgentAdapter
      |
      +----> isolated Git worktree ---> evidence ---> bounded tests
      |
      v
 persistence ---> statistics / reporting / verified result bundles

BenchmarkPackProvider ---> PackRegistry ---> PackMaterializer ---> suite manifest
```

The principal rule is dependency direction: transports compose services; services own workflow semantics; adapters and providers enter through explicit contracts; reporting and statistics do not execute benchmarks.

Architecture tests enforce several of these boundaries so the diagram is not merely aspirational documentation.
