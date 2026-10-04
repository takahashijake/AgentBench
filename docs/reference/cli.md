# CLI Reference

Run `agentbench --help` and subcommand help for the installed version.

## Discovery and readiness

```text
agentbench doctor
agentbench pack list
agentbench pack show <pack>
agentbench pack preflight <pack>
agentbench preflight <suite>
```

## Materialize a locked execution policy

```text
agentbench pack materialize <pack> -o <dir> \
  --agent <id=command>... \
  --repetitions <n> \
  --workers <1-32>
```

The generated schema-5 manifest stores `experiment.max_workers`. Suite
`run`/`replay` always use that locked value.

## Reproducible suite workflow

```text
agentbench validate <suite>
agentbench lock <suite>
agentbench verify <suite> <lock>
agentbench import <suite>
agentbench run <suite>
agentbench replay <suite> <lock>
agentbench results <experiment-id>
agentbench leaderboard <experiment-id>
```

## Persisted experiment execution and recovery

```text
agentbench execute <experiment-id> --workers <1-32>
agentbench recover <experiment-id> --confirm-inactive
```

`execute` is for an already-persisted experiment and records the chosen worker
count in execution history. It is not a substitute for locked suite replay.

`recover` is deliberately explicit. Use it only after confirming the prior
worker process is gone; otherwise resetting a live claim could duplicate work.

## Portable results and local UI

```text
agentbench bundle export <experiment-id> -o <file.zip>
agentbench bundle verify <file.zip>
agentbench bundle inspect <file.zip>
agentbench bundle extract <file.zip> -o <directory>
agentbench serve
```

Readiness mismatch uses exit code `3`; invalid input/runtime errors use exit
code `2`.


## Durable cross-process workers

```text
agentbench worker run <experiment-id> [--owner <id>] [--lease-seconds 60] [--max-trials N]
agentbench worker status <experiment-id>
agentbench worker recover-expired <experiment-id> --confirm-expired [--grace-seconds N]
```

`worker run` claims planned cells one at a time through durable database state.
Each worker invocation records a `distributed_worker` execution attempt. The
default owner is generated from the hostname plus a random suffix; production
automation should normally provide an explicit stable worker identity.

Lease duration is bounded to 10–3600 seconds. A heartbeat thread renews an active
claim approximately every third of the lease interval.

`worker recover-expired` is intentionally gated by `--confirm-expired`.
Expiry alone does not prove the old worker process stopped. Recovery requeues only
claims whose persisted expiry is older than the optional grace period.

Use `worker status` before recovery to inspect owners, expiry times, and claim
state. Lease tokens are internal fencing credentials and are never printed.
