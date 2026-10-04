# Architecture

Core dependency direction:

```text
CLI/API -> SuiteService -> ExperimentService -> BenchmarkService -> AgentAdapter
providers -> PackRegistry -> PackMaterializer -> manifest -> SuiteService
persistence -> statistics/reporting/result bundles
```

Transports should not own benchmark semantics. Providers describe corpora without filesystem execution. Adapters encapsulate agent execution. Statistics remains presentation-independent.
