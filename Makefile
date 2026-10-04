PYTHON ?= python

.PHONY: install test coverage lint format format-check typecheck docs build smoke docker-build docker-smoke qa clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	pytest

coverage:
	pytest --cov=agentbench --cov-report=term-missing --cov-report=html

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m ruff format src tests

format-check:
	$(PYTHON) -m ruff format --check src tests

typecheck:
	$(PYTHON) -m mypy src/agentbench/manifests.py src/agentbench/statistics.py src/agentbench/benchmark_packs/models.py src/agentbench/adapters/base.py src/agentbench/resources.py src/agentbench/services/local_executor.py src/agentbench/services/distributed_worker.py

docs:
	mkdocs build --strict

build:
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

smoke:
	agentbench --version
	agentbench doctor
	agentbench pack list
	agentbench pack show smoke-v2
	agentbench pack preflight engineering-v4

docker-build:
	docker build --tag agentbench-local .

docker-smoke: docker-build
	docker run --rm agentbench-local --version
	docker run --rm agentbench-local doctor

qa: lint format-check typecheck test docs build smoke

clean:
	rm -rf build dist site htmlcov .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache
