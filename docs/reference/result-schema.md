# Result and Schema Reference

AgentBench versions persisted/public formats independently.

Current V7 writers use:

- suite manifest schema: **5**
- analysis schema: **7**
- suite report schema: **7**
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

Portable worker-attempt fields include trial ID, a SHA-256 projection of the
owner ID, status, acquisition, heartbeat, expiry, completion timestamps, and
bounded details. The opaque lease token and raw host-derived owner ID are
intentionally excluded from result bundles.

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


## V7 worker capability evidence

Analysis schema 7 adds `worker_registrations` containing active local worker
capabilities. Durable lease attempts retain the capability snapshot that
justified scheduling.

Portable result bundles do not copy raw worker owner IDs. Worker attempts,
execution details, and worker summaries use SHA-256 owner projections so shared
evidence can correlate records without disclosing a hostname-derived identifier.
Live worker registrations are omitted from portable reports because registration
heartbeat/capability state can change after an experiment; durable worker attempts
already retain the capability snapshot that justified scheduling. Local analysis
may still show the active registration set.
