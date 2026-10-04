# Results and Metrics

Use `agentbench leaderboard <experiment-id>` for aggregate reliability and `agentbench results <experiment-id>` for experiment output.

V4 distinguishes planned runs, eligible planned runs, resource-skipped runs, benchmark runs, and orchestration errors. Agent success rates use eligible planned runs as the denominator, so a host limitation is not scored as an agent failure.

Interpret missing telemetry as missing. Pairwise differences and exact sign tests are descriptive. For sharing, export a result bundle and verify it before extraction.
