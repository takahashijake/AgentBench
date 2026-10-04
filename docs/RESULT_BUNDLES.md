# Portable result bundles

AgentBench V3 can export a completed or partially completed persisted experiment
into a deterministic, integrity-checked ZIP artifact.

The bundle layer is intentionally independent of CLI and HTTP transport.

## Commands

```bash
agentbench bundle export 12 -o results/experiment-12.zip
agentbench bundle verify results/experiment-12.zip
agentbench bundle inspect results/experiment-12.zip
agentbench bundle extract results/experiment-12.zip -o results/experiment-12
```

Export refuses to overwrite an existing bundle.

Extraction requires an empty/nonexistent destination.

## Bundle contents

A typical bundle contains:

```text
bundle.json
report.json
report.md
experiment.json
artifacts/
  run-101/
    manifest.json
    provenance.json
    agent/
    setup/
    test/
    git/
  run-102/
    ...
```

`bundle.json` includes:

- result-bundle schema version
- AgentBench package version
- experiment identity/status
- sorted payload list
- byte size for every payload
- SHA-256 for every payload
- canonical bundle `identity_sha256`

The identity digest authenticates the manifest structure. Individual payload
digests authenticate the files.

## Deterministic serialization

AgentBench fixes ZIP metadata that would otherwise introduce non-semantic
differences:

- sorted member order
- fixed archive timestamps
- fixed regular-file mode
- canonical compact JSON for machine payloads

Exporting unchanged canonical experiment/artifact data twice in one environment
produces identical bundle bytes.

## Portable metadata

`experiment.json` intentionally does not duplicate machine-local paths.

Task snapshots omit the local source repository path and store the agent prompt
digest rather than copying the full prompt into the portable snapshot.

Agent snapshots store a command-template digest rather than the raw command
template.

Per-run portable results:

- omit worktree/artifact-store filesystem paths
- convert Git evidence references to logical bundle paths
- preserve bounded executable/environment provenance
- preserve success/test/change/token measurements
- preserve stage outcomes without log filesystem paths
- point to the run artifact prefix inside the ZIP

The actual immutable evidence files remain inside `artifacts/run-<id>/...`.

## Verification

Verification is mandatory before extraction and checks:

1. the input is a readable ZIP
2. member count is bounded
3. total uncompressed size is bounded
4. every member path is safe
5. member names are unique
6. `bundle.json` exists and is valid
7. bundle schema is supported
8. canonical identity digest matches
9. every declared payload exists
10. every size matches
11. every SHA-256 matches
12. no undeclared payload exists
13. `report.json` is valid JSON

## Extraction safety

AgentBench never uses `ZipFile.extractall`.

Each member is validated as a POSIX-style relative path. Extraction rejects:

- absolute paths
- `..` traversal
- empty/dot components
- backslashes
- duplicate ZIP members

The resolved output path must remain under the requested destination before bytes
are written.

## Threat model

Result bundles protect integrity and path safety. They are **not encrypted** and
are not a secret-storage format.

AgentBench avoids copying obvious machine-local paths and raw adapter command
templates into portable metadata, but benchmark prompts, logs, diffs, untracked
agent files, and test outputs can contain project information. Review a bundle
before publishing it.

## Why bundle export is not an HTTP file endpoint

AgentBench is local-first. Export chooses an explicit local destination and may
include many immutable artifacts.

V3 keeps that filesystem authority in the local service/CLI boundary instead of
adding an HTTP route that writes arbitrary server-side paths. A future remote
artifact service should define its own authorization/storage contract rather than
reusing local filesystem semantics.
