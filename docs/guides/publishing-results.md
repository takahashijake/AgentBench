# Publishing Verifiable Static Results

AgentBench V8 can turn an experiment into a standalone static report without
running a web server.

## Recommended workflow

Export the archival evidence object first:

```bash
agentbench bundle export 42 -o results/experiment-42.zip
agentbench bundle verify results/experiment-42.zip
```

Then publish the verified bundle:

```bash
agentbench publish bundle results/experiment-42.zip \
  --output public/experiment-42
```

Verify the static publication independently:

```bash
agentbench publish verify public/experiment-42
```

A direct convenience path is also available:

```bash
agentbench publish experiment 42 --output public/experiment-42
```

Internally, the direct path first creates the same deterministic result bundle,
verifies it, then derives the static site.

## Publication contract

A publication directory contains exactly:

- `index.html`
- `report.json`
- `publication.json`

`publication.json` stores publication schema version, AgentBench version,
source result-bundle identity, experiment summary, and SHA-256/size for every
declared static payload.

The verifier rejects:

- changed HTML or report bytes
- missing declared files
- undeclared extra files
- invalid publication identity
- unsupported publication schema versions

## Hosting

The directory is pure static content. It can be committed to a GitHub Pages
branch, copied into an object-storage website bucket, or served by any ordinary
static host.

There is no generated JavaScript dependency and no server-side runtime.

## Privacy boundary

Static publication consumes portable result-bundle data. Raw local repository
paths and raw command templates are already projected out before publication.

The HTML also avoids analytics, remote fonts, CDNs, and other automatic network
requests.

## Evidence model

Use the result bundle as the archival evidence object and the static publication
as its human-facing view.

```text
canonical experiment
       │
       ▼
verified result bundle
       │
       ├── archival evidence
       │
       ▼
static publication
       │
       └── portfolio / review surface
```

This preserves a single evidence authority while still making results easy to
share.
