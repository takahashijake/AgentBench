# Durable worker execution

AgentBench V6 supports multiple worker processes sharing one experiment through
database-backed leases.

## Starting workers

Workers require access to the same AgentBench database, benchmark repositories,
agent executables, and artifact storage paths.

```bash
agentbench worker run 42 --owner worker-a --lease-seconds 60
agentbench worker run 42 --owner worker-b --lease-seconds 60
```

Use `--max-trials` to bound one worker invocation, which is useful for batch
systems and job arrays.

## Claim lifecycle

1. select the lowest-ordinal planned trial
2. atomically transition `planned → running`
3. persist an active worker attempt with an opaque fencing token
4. periodically heartbeat the lease
5. execute through the canonical BenchmarkService
6. verify ownership before terminal trial mutation
7. persist worker-attempt completion

Workers never share SQLAlchemy sessions.

## Expiry and recovery

Heartbeat loss alone does not requeue work. Inspect:

```bash
agentbench worker status 42
```

After confirming an expired owner is no longer trustworthy:

```bash
agentbench worker recover-expired 42 \
  --grace-seconds 30 \
  --confirm-expired
```

The trial returns to `planned` and the prior attempt becomes `expired`.

If the old process later finishes, its lease token no longer authorizes terminal
trial mutation. It receives an internal `lease_lost` result.

## Delivery semantics

The durable worker layer provides at-least-once execution with fenced canonical
AgentBench trial state. It does not make arbitrary external side effects from an
agent command exactly-once.

If an agent mutates external services, users should design those operations to be
idempotent or independently transactional.
