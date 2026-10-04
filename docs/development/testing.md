# Testing and QA

AgentBench uses layered verification.

```bash
make lint
make format-check
make typecheck
pytest
pytest --cov=agentbench --cov-report=term-missing
mkdocs build --strict
python -m build
python -m twine check dist/*
make smoke
```

CI runs static quality, coverage, documentation, and package-build gates on Python 3.11, then runs the installed product and integration suite on Python 3.11 and 3.13.

Regression rule: when a defect is fixed, first add a focused test that demonstrates the incorrect behavior, then fix the implementation. Prefer deterministic in-process fakes and temporary Git repositories to tests that spend model credits.
