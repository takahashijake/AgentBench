# Resource-aware benchmark execution

AgentBench V4 makes host eligibility part of the benchmark contract rather than treating host limitations as agent failures.

## Supported requirements

Tasks may declare minimum logical CPU count, optional physical memory in MiB, a platform allowlist, and required executable names.

```yaml
requirements:
  min_cpu_count: 2
  min_memory_mb: 4096
  supported_platforms: [linux, darwin]
  required_commands: [python, git]
```

AgentBench intentionally does not claim GPU, network, credential, or container-runtime detection yet; those should only be added with reliable probes.

## Preflight

```bash
agentbench pack preflight engineering-v4
```

The command returns machine-readable per-task requirements, observed host capabilities, eligibility, and incompatibility reasons.

Exit code `0` means every task is eligible. Exit code `3` means at least one task is incompatible. Exit code `2` is reserved for invalid input/runtime errors.

## Execution semantics

Requirements are frozen into the experiment task snapshot. Immediately before a planned trial, the experiment service evaluates them. Ineligible cells become terminal `skipped` trials without invoking the agent.

Analysis schema 4 reports `planned_runs`, `eligible_planned_runs`, `skipped_runs`, `benchmark_runs`, and `orchestration_errors` separately. Agent success rate uses eligible planned runs as its denominator.

V4 remains deterministic and sequential. This is an eligibility layer, not a claim of unsafe in-process parallel scheduling or a distributed worker system.
