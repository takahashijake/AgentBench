# Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install
```

The preferred local entry point is:

```bash
make qa
```

Individual checks are available as `make lint`, `make format-check`, `make typecheck`, `make test`, `make docs`, `make build`, and `make smoke`.

Repository structure:

- `src/agentbench/benchmark_packs/` — immutable pack descriptions and provider SPI
- `src/agentbench/adapters/` — agent execution contract and registry
- `src/agentbench/services/` — benchmark/experiment/suite workflows
- `src/agentbench/api/` — FastAPI composition and routers
- `src/agentbench/statistics.py` — pure analysis
- `src/agentbench/result_bundles.py` — portable result boundary
- `tests/` — unit, integration, architecture, and regression tests
