# CLI Reference

Run `agentbench --help` and subcommand help for the installed version.

## Readiness and discovery

```text
agentbench doctor
agentbench pack list
agentbench pack show <pack>
agentbench pack preflight <pack>
agentbench preflight <suite>
```

`pack preflight` checks a pack's declarative host requirements before materialization. `preflight <suite>` additionally verifies selected task repositories/base commits and selected agent executable availability. Both return exit code `3` when the input is valid but the current host is not ready.

## Benchmark workflow

```text
agentbench pack materialize <pack> -o <dir> --agent <id=command>...
agentbench validate <suite>
agentbench lock <suite>
agentbench verify <suite> <lock>
agentbench import <suite>
agentbench run <suite>
agentbench replay <suite> <lock>
agentbench results <experiment-id>
agentbench leaderboard <experiment-id>
```

## Portable results and local UI

```text
agentbench bundle export <experiment-id> -o <file.zip>
agentbench bundle verify <file.zip>
agentbench bundle inspect <file.zip>
agentbench bundle extract <file.zip> -o <directory>
agentbench serve
```

Human-readable output is the default for reports; machine-readable JSON is used for validation/readiness/discovery surfaces and reusable report outputs. Invalid input/runtime errors return a non-zero status with an actionable JSON error. Resource/readiness mismatch is distinct from invalid input and uses exit code `3`.
