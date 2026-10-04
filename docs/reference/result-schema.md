# Result and Schema Reference

AgentBench intentionally versions persisted/public formats independently.

Current V4 writers use:

- suite manifest schema: 4
- analysis schema: 4
- suite report schema: 4
- suite-lock schema: 3
- result-bundle schema: 1

Readers retain older formats where compatibility is explicit and safe. A schema version changes when compatibility expectations change; it is not mechanically tied to the package version.

Portable result bundles contain canonical report data, portable experiment metadata, immutable run artifacts, and a content-addressed bundle manifest. Verification checks declared paths, sizes, SHA-256 digests, duplicate names, traversal attempts, undeclared payloads, and archive size bounds before extraction.

## V4 eligibility semantics

Manifest schema 4 adds declarative per-task CPU, memory, platform, and required-command constraints.
Analysis schema 4 separates planned, eligible, skipped, benchmark, and orchestration-error counts.
Resource-incompatible trials are terminal `skipped` observations and are excluded from the agent success-rate denominator.
Suite-lock schema 3 includes normalized task requirements, so requirement changes are reproducibility drift.
Result-bundle schema remains 1 because the content-addressed envelope did not change; V4 report and experiment documents are carried inside it.
