# Contributing

AgentBench values reproducibility, explicit contracts, deterministic tests, and small dependency surfaces.

## Workflow

1. Create a focused branch.
2. Make the implementation change.
3. Add or update tests.
4. Update documentation for user-visible behavior.
5. Run `make qa`.
6. Open a pull request and let CI complete.
7. Address review/CI failures before merge.

## Design expectations

- Keep CLI/API transport thin.
- Add new corpora through the benchmark-pack provider boundary.
- Add new agent behavior through adapter factories/contracts.
- Do not bypass the canonical benchmark lifecycle.
- Preserve exact-commit worktree isolation and pre-test evidence capture.
- Keep benchmark failures separate from orchestration failures.
- Never silently convert missing telemetry to zero.
- Prefer actionable validation errors over fallback behavior.

## Tests

Use deterministic test doubles and temporary repositories whenever possible. Tests should exercise production pathways, not only mocks. External model access must never be required for the default test suite.

## Security

Do not include API keys, private prompts, credentials, or secret-bearing logs in issues, pull requests, fixtures, or committed benchmark artifacts.
