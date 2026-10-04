# Configuration

Suite manifests define agents, tasks, selection, repetitions, timeouts, and optional pack provenance. Unknown keys are rejected. IDs are unique, task commits are exact, selections cannot reference disabled resources, and planned-run counts are bounded.

Use `agentbench validate <suite>` before import/run and create a suite lock for any comparison intended to be reproducible.
