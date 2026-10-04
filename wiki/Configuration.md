# Configuration

Suite manifests define agents, tasks, selection, repetitions, timeouts, optional
pack provenance, task host requirements, and—under schema 5—bounded local
concurrency.

```yaml
experiment:
  repetitions: 5
  stop_on_error: false
  max_workers: 4
```

`max_workers` is limited to 1–32 and participates in manifest/lock identity.
Suite run/replay uses the locked value; there is no unrecorded worker override.

Use `agentbench validate <suite>` for structural validation,
`agentbench preflight <suite>` for current-host readiness, and create a suite
lock for any comparison intended to be reproducible.
