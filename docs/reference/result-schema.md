# Result and Schema Reference

AgentBench intentionally versions persisted/public formats independently.

Current V3 writers use:

- suite manifest schema: 3
- analysis schema: 3
- suite report schema: 3
- suite-lock schema: 2
- result-bundle schema: 1

Readers retain older formats where compatibility is explicit and safe. A schema version changes when compatibility expectations change; it is not mechanically tied to the package version.

Portable result bundles contain canonical report data, portable experiment metadata, immutable run artifacts, and a content-addressed bundle manifest. Verification checks declared paths, sizes, SHA-256 digests, duplicate names, traversal attempts, undeclared payloads, and archive size bounds before extraction.
