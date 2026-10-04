# Troubleshooting

## `agentbench doctor` fails

Run it before debugging a benchmark definition. Confirm Python and Git are available in the same environment where `agentbench` was installed.

## Manifest validation fails

Read the full validation message. Unknown fields are rejected intentionally. Confirm referenced task/agent IDs exist, selected entries are enabled, commits are full Git object IDs, and timeout/repetition values are within bounds.

## Lock verification fails

Treat this as evidence of drift, not an inconvenience to bypass. Re-materialize or deliberately create a new lock after understanding what changed.

## External agent executable is missing

AgentBench does not install Codex, Qwen, Claude, Gemini, or provider credentials. Install/configure the external agent separately and confirm its command works before a long run.

## A trial times out or crashes

Inspect that run's artifact directory and persisted result. Setup, agent, test, evidence, and cleanup phases are recorded separately so a benchmark failure can be distinguished from an orchestration failure.

## Result bundle verification fails

Do not extract an unverified bundle. Re-export from the source experiment or inspect the verification error for digest, path, duplicate-member, or schema issues.
