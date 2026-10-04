# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's security reporting features when available rather than opening a public issue with exploit details.

Include enough information to reproduce the problem without including credentials, API keys, private repository contents, or personal data.

## Scope

Security-sensitive areas include:

- subprocess/argument construction;
- benchmark repository and worktree isolation;
- path handling and artifact extraction;
- result-bundle verification;
- optional plugin/provider loading;
- accidental credential capture in provenance or logs.

AgentBench intentionally avoids shell interpolation for prompts and verifies portable bundle paths/digests before extraction. External coding agents remain separate programs with their own security models.
