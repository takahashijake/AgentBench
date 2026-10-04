# Development Workflow

```bash
python -m pip install -e ".[dev]"
make qa
```

Implement on a branch, add regression tests for fixes, update docs when contracts change, and open a PR. CI separately reports static quality, coverage/docs/build checks, and cross-version integration results.
