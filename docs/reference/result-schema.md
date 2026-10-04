# Result and Schema Reference

AgentBench versions persisted/public formats independently.

Current V6 writers use:

- suite manifest schema: **5**
- analysis schema: **6**
- suite report schema: **6**
- suite-lock schema: **4**
- result-bundle schema: **1**

Readers retain older formats where compatibility is explicit and safe.

## V5 execution evidence

Manifest schema 5 adds `experiment.max_workers` (1–32). Worker count is part of
canonical manifest identity and lock schema 4, because local concurrency can
materially affect resource contention and runtime.

Analysis schema 5 adds:

- `execution_history`
- `latest_execution`

Each execution attempt records mode, worker count, status, timestamps, and bounded
details. Sequential runs use mode `sequential`; bounded local parallel runs use
`local_parallel`.

Suite report schema 5 carries the locked worker policy and analysis execution
history.

Result-bundle schema remains 1 because the verified ZIP envelope did not change.
Portable experiment metadata now includes persisted execution attempts.

## V4 eligibility semantics retained

Task CPU/memory/platform/command requirements remain schema data. Resource-
incompatible trials are terminal `skipped` observations and are excluded from
agent-success denominators.

Portable result bundles remain content-addressed and verify declared paths, sizes,
SHA-256 digests, duplicate names, traversal attempts, undeclared payloads, and
archive size bounds before extraction.


## V6 worker evidence

Analysis schema 6 adds `worker_attempts` and `worker_summary`.

Portable worker-attempt fields include trial ID, owner ID, status, acquisition,
heartbeat, expiry, completion timestamps, and bounded details. The opaque lease
token is intentionally excluded from reports and result bundles.

Worker-attempt statuses may include:

- `active`
- `completed`
- `error`
- `skipped`
- `expired`
- `orphaned`

A stale worker may internally observe `lease_lost`; canonical attempt history
continues to reflect the recovered/expired ownership record rather than allowing
the stale process to overwrite it.
