# Adding a New Agent

Use the adapter extension boundary instead of adding provider-specific branches to benchmark orchestration.

A custom adapter factory should satisfy the public `AgentAdapter` contract and be registered through `AdapterRegistry`. Keep process execution bounded and return structured metadata without leaking credentials.
