# Configuration

Suite manifests define agents, tasks, selection, repetitions, timeouts, optional pack provenance, and—under schema 4—task host requirements.

Unknown keys are rejected. IDs are unique, task commits are exact, selections cannot reference disabled resources, and planned-run counts are bounded.

V4 task requirements may declare minimum CPU count, optional physical memory, supported platforms, and required executables.

Use `agentbench validate <suite>` for structural validation, `agentbench preflight <suite>` for current-host readiness, and create a suite lock for any comparison intended to be reproducible.
