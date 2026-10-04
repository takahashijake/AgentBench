# Results and Metrics

Use `agentbench leaderboard <experiment-id>` for aggregate reliability and
`agentbench results <experiment-id>` for experiment output.

V5 retains planned/eligible/skipped/benchmark/orchestration counts and adds
`execution_history` plus `latest_execution`. Each attempt records execution
mode, worker count, status, timestamps, and bounded details.

Agent success rates use eligible planned runs as the denominator. Missing
telemetry remains missing. Pairwise differences and exact sign tests are
descriptive.

Portable result bundles include execution history so shared evidence retains the
conditions under which the experiment was actually executed.
