# Architecture

The authoritative detailed design is maintained in [ARCHITECTURE.md](../../ARCHITECTURE.md).

At a high level:

```mermaid
flowchart LR
    CLI[CLI / FastAPI] --> Suite[SuiteService]
    Suite --> Exp[ExperimentService]
    Exp --> Bench[BenchmarkService]
    Bench --> Adapter[Adapter registry / AgentAdapter]
    Bench --> Worktree[Isolated Git worktree]
    Worktree --> Evidence[Pre-test evidence]
    Evidence --> Tests[Bounded tests]
    Exp --> Stats[Statistics]
    Exp --> Persist[(SQLAlchemy persistence)]
    Persist --> Report[Reporting]
    Persist --> Bundle[Verified result bundle]
    Provider[Benchmark pack provider] --> Materializer[Pack materializer]
    Materializer --> Manifest[Suite manifest]
    Manifest --> Suite
```

The principal rule is dependency direction: transports compose services; services own workflow semantics; adapters and providers enter through explicit contracts; reporting and statistics do not execute benchmarks.
