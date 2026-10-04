from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.adapters import AdapterRegistry, AgentAdapter
from agentbench.adapters.registry import create_default_adapter_registry
from agentbench.benchmark_packs import (
    BenchmarkPack,
    BuiltinPackProvider,
    DuplicatePackError,
    PackMaterializer,
    PackRegistry,
    PackTaskSpec,
)
from agentbench.benchmark_packs.discovery import discover_pack_providers
from agentbench.manifests import load_suite_manifest
from agentbench.models.database import AgentConfig, Base, BenchmarkTask
from agentbench.services.benchmark import BenchmarkService
from agentbench.services.experiment import ExperimentService
from agentbench.services.suite import SuiteService
from helpers import init_git_repo


class TinyProvider:
    provider_id = "example.provider"

    def packs(self):
        return (
            BenchmarkPack(
                id="example-pack",
                version="1.0.0",
                name="Example",
                description="third-party fixture",
                tasks=(
                    PackTaskSpec(
                        id="example-task",
                        description="fixture",
                        category="feature",
                        difficulty="easy",
                        tags=("plugin",),
                        prompt="Implement value() so the tests pass.",
                        files={
                            "value.py": "def value():\n    return 0\n",
                            "test_value.py": (
                                "import unittest\n"
                                "from value import value\n"
                                "class T(unittest.TestCase):\n"
                                "    def test_value(self): self.assertEqual(value(), 1)\n"
                            ),
                        },
                    ),
                ),
            ),
        )


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_pack_registry_supports_external_provider_without_core_changes(tmp_path: Path):
    registry = PackRegistry()
    registry.register(BuiltinPackProvider())
    registry.register(TinyProvider())

    assert "example.provider" in registry.provider_ids
    assert registry.get("example-pack").provider_id == "example.provider"

    result = PackMaterializer(registry).materialize(
        "example-pack",
        tmp_path / "plugin-pack",
        agents=[
            {
                "id": "fixture",
                "description": "fixture",
                "command_template": 'python -c "print(1)" {prompt}',
            }
        ],
        repetitions=2,
    )
    loaded = load_suite_manifest(result.manifest_path)

    assert loaded.manifest.schema_version == 4
    assert loaded.manifest.benchmark_pack.provider == "example.provider"
    assert result.planned_runs == 2


def test_pack_registry_rejects_global_pack_id_collisions():
    registry = PackRegistry()
    registry.register(TinyProvider())

    class CollidingProvider:
        provider_id = "collision.provider"

        def packs(self):
            return TinyProvider().packs()

    with pytest.raises(DuplicatePackError, match="already registered"):
        registry.register(CollidingProvider())


def test_optional_provider_discovery_is_failure_isolated(monkeypatch):
    class BrokenEntryPoint:
        name = "broken-provider"

        def load(self):
            raise RuntimeError("plugin import exploded")

    registry = PackRegistry()
    registry.register(BuiltinPackProvider())
    monkeypatch.setattr(
        "agentbench.benchmark_packs.discovery.metadata.entry_points",
        lambda **kwargs: [BrokenEntryPoint()],
    )

    errors = discover_pack_providers(registry)

    assert len(errors) == 1
    assert "plugin import exploded" in errors[0]
    assert registry.get("core-v3").provider_id == "agentbench.builtin"


class FakeAdapter(AgentAdapter):
    def prepare(self, repository_path: Path, base_commit: str) -> Path:
        self.workspace_path = Path(repository_path)
        return self.workspace_path

    def run_task(self, prompt: str, timeout: int, cwd=None):
        return 0, "fake", ""

    def terminate(self) -> None:
        return None

    def collect_metadata(self):
        return {"adapter": "fake"}


def test_benchmark_service_accepts_injected_adapter_registry():
    registry = AdapterRegistry()
    registry.register("python", lambda config: FakeAdapter(dict(config)))
    db = make_session()
    agent = AgentConfig(name="custom", command_template="python tool.py {prompt}")
    db.add(agent)
    db.commit()
    db.refresh(agent)

    adapter = BenchmarkService(db, adapter_registry=registry).create_agent_adapter(
        agent.id
    )

    assert isinstance(adapter, FakeAdapter)
    assert adapter.config["adapter"] == "python"


def test_default_adapter_registry_profiles_known_agents_and_falls_back_to_shell():
    registry = create_default_adapter_registry()

    codex = registry.create(
        {"name": "codex", "command_template": 'codex exec "{prompt}"'}
    )
    generic = registry.create(
        {"name": "custom", "command_template": 'python runner.py "{prompt}"'}
    )

    assert codex.config["adapter"] == "codex"
    assert codex.config["agent_family"] == "codex"
    assert generic.config["adapter"] == "shell"
    assert generic.config["agent_family"] == "shell"


def test_adapter_registry_rejects_duplicate_registration():
    registry = AdapterRegistry()
    registry.register("x", lambda config: FakeAdapter(dict(config)))

    with pytest.raises(ValueError, match="already registered"):
        registry.register("x", lambda config: FakeAdapter(dict(config)))


def test_injected_adapter_flows_through_experiment_and_suite_services(tmp_path: Path):
    registry = AdapterRegistry()
    registry.register("python", lambda config: FakeAdapter(dict(config)))
    db = make_session()

    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    agent = AgentConfig(name="custom-flow", command_template="python tool.py {prompt}")
    db.add(agent)
    db.flush()
    task = BenchmarkTask(
        name="custom-flow-task",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="exercise injected adapter",
        test_command="",
        timeout=5,
    )
    db.add(task)
    db.commit()
    db.refresh(agent)
    db.refresh(task)

    benchmark_service = BenchmarkService(
        db,
        artifact_root=tmp_path / "artifacts",
        adapter_registry=registry,
    )
    experiment_service = ExperimentService(
        db,
        benchmark_service=benchmark_service,
    )
    suite_service = SuiteService(
        db,
        experiment_service=experiment_service,
    )

    experiment = suite_service.experiments.create_experiment(
        name="injected-flow",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
        repetitions=1,
    )
    completed = suite_service.experiments.execute_experiment(experiment.id)
    summary = suite_service.experiments.aggregate_experiment(experiment.id)

    assert completed.status == "completed"
    assert summary["overall"]["successful_runs"] == 1
    run = completed.trials[0].benchmark_run
    assert run.results["adapter_metadata"]["adapter"] == "fake"


def test_service_injection_rejects_cross_session_dependencies(tmp_path: Path):
    left = make_session()
    right = make_session()
    foreign = BenchmarkService(right, artifact_root=tmp_path / "foreign")

    with pytest.raises(ValueError, match="same database session"):
        ExperimentService(left, benchmark_service=foreign)
