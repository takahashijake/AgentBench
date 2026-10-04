# Configuration

AgentBench configuration is intentionally explicit and local.

## Suite manifests

A suite defines agents, tasks, experiment selection, repetitions, and optional benchmark-pack metadata. Manifests are validated before persistence or execution. Unknown fields are rejected so misspellings do not silently change benchmark behavior.

Important constraints include:

- agent and task IDs must be unique;
- selected resources must exist and be enabled;
- task commits are exact Git object IDs;
- task timeouts are bounded;
- repetitions are bounded;
- experiments exceeding the maximum planned-run count are rejected.

Relative repository paths are resolved from the manifest location.

## Environment

AgentBench keeps local state and artifacts outside benchmark source repositories. The `.env` file is ignored, but AgentBench does not require secrets of its own. External agent credentials should be managed by the corresponding provider/agent tooling.

Run `agentbench doctor` before a long experiment to verify the local product prerequisites.
