from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.cli import main
from agentbench.manifests import load_suite_manifest
from agentbench.models.database import AgentConfig, Base, BenchmarkTask, ExperimentTrial
from agentbench.services.suite import SuiteService

from helpers import init_git_repo


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def write_manifest(
    path: Path,
    *,
    repo: Path,
    base_commit: str,
    agents: list[dict] | None = None,
    tasks: list[dict] | None = None,
    experiment: dict | None = None,
) -> Path:
    agents = agents or [
        {
            "id": "agent-a",
            "description": "fixture agent",
            "command_template": shlex.join(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('answer.txt').write_text('ok')",
                ]
            ),
        }
    ]
    tasks = tasks or [
        {
            "id": "task-a",
            "description": "fixture task",
            "repository_path": repo.name,
            "base_commit": base_commit,
            "agent_prompt": "solve the fixture",
            "test_command": shlex.join(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "assert Path('answer.txt').read_text() == 'ok'; "
                        "print('1 passed')"
                    ),
                ]
            ),
            "timeout": 5,
        }
    ]
    payload = {
        "schema_version": 1,
        "id": "fixture-suite",
        "name": "Fixture Suite",
        "description": "suite manifest test",
        "agents": agents,
        "tasks": tasks,
        "experiment": experiment or {"repetitions": 1},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_manifest_load_is_deterministic_and_resolves_relative_repo(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
    )

    first = load_suite_manifest(manifest_path)
    second = load_suite_manifest(manifest_path)

    assert first.sha256 == second.sha256
    assert first.manifest.selected_task_ids() == ["task-a"]
    assert first.manifest.selected_agent_ids() == ["agent-a"]
    assert first.resolve_repository_path(first.manifest.tasks[0]) == repo.resolve()


def test_manifest_rejects_unknown_experiment_reference(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
        experiment={"tasks": ["missing"], "agents": ["agent-a"]},
    )

    with pytest.raises(ValueError, match="unknown task"):
        load_suite_manifest(manifest_path)


def test_suite_import_is_idempotent_and_updates_existing_bindings(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
    )
    db = make_session()
    service = SuiteService(db, artifact_root=tmp_path / "artifacts")

    first = service.import_suite(load_suite_manifest(manifest_path))
    second = service.import_suite(load_suite_manifest(manifest_path))

    assert first.task_ids == second.task_ids
    assert first.agent_config_ids == second.agent_config_ids
    assert db.query(BenchmarkTask).count() == 1
    assert db.query(AgentConfig).count() == 1

    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["agents"][0]["description"] = "updated agent"
    payload["tasks"][0]["description"] = "updated task"
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    third = service.import_suite(load_suite_manifest(manifest_path))

    assert third.task_ids == first.task_ids
    assert third.agent_config_ids == first.agent_config_ids
    assert db.query(BenchmarkTask).one().description == "updated task"
    assert db.query(AgentConfig).one().description == "updated agent"


def test_suite_planning_preserves_manifest_selection_order(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    agents = [
        {
            "id": "agent-a",
            "command_template": shlex.join([sys.executable, "-c", "pass"]),
        },
        {
            "id": "agent-b",
            "command_template": shlex.join([sys.executable, "-c", "pass"]),
        },
    ]
    tasks = [
        {
            "id": "task-a",
            "description": "A",
            "repository_path": repo.name,
            "base_commit": base_commit,
            "agent_prompt": "A",
            "test_command": "",
            "timeout": 5,
        },
        {
            "id": "task-b",
            "description": "B",
            "repository_path": repo.name,
            "base_commit": base_commit,
            "agent_prompt": "B",
            "test_command": "",
            "timeout": 5,
        },
    ]
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
        agents=agents,
        tasks=tasks,
        experiment={
            "tasks": ["task-b", "task-a"],
            "agents": ["agent-b", "agent-a"],
            "repetitions": 2,
        },
    )
    db = make_session()
    service = SuiteService(db, artifact_root=tmp_path / "artifacts")
    loaded = load_suite_manifest(manifest_path)
    imported = service.import_suite(loaded)
    experiment = service.create_experiment(loaded, imported)

    assert experiment.task_ids == [
        imported.task_ids["task-b"],
        imported.task_ids["task-a"],
    ]
    assert experiment.agent_config_ids == [
        imported.agent_config_ids["agent-b"],
        imported.agent_config_ids["agent-a"],
    ]
    trials = (
        db.query(ExperimentTrial)
        .filter(ExperimentTrial.experiment_id == experiment.id)
        .order_by(ExperimentTrial.ordinal.asc())
        .all()
    )
    assert [
        (trial.task_id, trial.agent_config_id, trial.repetition) for trial in trials[:4]
    ] == [
        (imported.task_ids["task-b"], imported.agent_config_ids["agent-b"], 1),
        (imported.task_ids["task-b"], imported.agent_config_ids["agent-b"], 2),
        (imported.task_ids["task-b"], imported.agent_config_ids["agent-a"], 1),
        (imported.task_ids["task-b"], imported.agent_config_ids["agent-a"], 2),
    ]


def test_suite_executes_through_existing_services_and_builds_report(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
    )
    db = make_session()
    service = SuiteService(
        db,
        artifact_root=tmp_path / "artifacts",
        setup_timeout=2,
        test_timeout=2,
    )
    loaded = load_suite_manifest(manifest_path)

    imported, experiment, summary = service.execute_suite(loaded)
    report = service.build_report(loaded, imported, experiment, summary)

    assert experiment.status == "completed"
    assert summary["overall"]["planned_runs"] == 1
    assert summary["overall"]["successful_runs"] == 1
    assert report["suite"]["id"] == "fixture-suite"
    assert report["suite"]["manifest_sha256"] == loaded.sha256
    assert report["experiment"]["id"] == experiment.id
    assert report["resources"]["tasks"][0]["id"] == "task-a"
    assert report["resources"]["agents"][0]["id"] == "agent-a"


def test_cli_validate_emits_machine_readable_json(tmp_path: Path, capsys):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    manifest_path = write_manifest(
        tmp_path / "suite.yaml",
        repo=repo,
        base_commit=base_commit,
    )

    assert main(["validate", str(manifest_path)]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["valid"] is True
    assert output["suite_id"] == "fixture-suite"
    assert output["planned_runs"] == 1
