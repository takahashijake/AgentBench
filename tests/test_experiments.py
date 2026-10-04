from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.models.database import (
    AgentConfig,
    Base,
    BenchmarkRun,
    BenchmarkTask,
    ExperimentTrial,
)
from agentbench.services.experiment import ExperimentBusyError, ExperimentService

from helpers import init_git_repo


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def add_agent(db, name: str, code: str, enabled: bool = True) -> AgentConfig:
    agent = AgentConfig(
        name=name,
        enabled=enabled,
        command_template=shlex.join([sys.executable, "-c", code]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def add_task(
    db,
    *,
    name: str,
    repo: Path,
    base_commit: str,
    test_command: str = "",
) -> BenchmarkTask:
    task = BenchmarkTask(
        name=name,
        description=f"{name} fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt=f"solve {name}",
        test_command=test_command,
        timeout=5,
        enabled=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_matrix_planning_is_deterministic_and_deduplicates_ids(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent_a = add_agent(db, "agent-a", "pass")
    agent_b = add_agent(db, "agent-b", "pass")
    task_a = add_task(db, name="task-a", repo=repo, base_commit=base_commit)
    task_b = add_task(db, name="task-b", repo=repo, base_commit=base_commit)

    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="matrix",
        task_ids=[task_a.id, task_b.id, task_a.id],
        agent_config_ids=[agent_a.id, agent_b.id, agent_a.id],
        repetitions=2,
    )

    assert experiment.task_ids == [task_a.id, task_b.id]
    assert experiment.agent_config_ids == [agent_a.id, agent_b.id]
    assert experiment.planned_runs == 8
    assert experiment.status == "pending"

    trials = (
        db.query(ExperimentTrial)
        .filter(ExperimentTrial.experiment_id == experiment.id)
        .order_by(ExperimentTrial.ordinal.asc())
        .all()
    )
    assert [trial.ordinal for trial in trials] == list(range(1, 9))
    assert [
        (trial.task_id, trial.agent_config_id, trial.repetition)
        for trial in trials
    ] == [
        (task_a.id, agent_a.id, 1),
        (task_a.id, agent_a.id, 2),
        (task_a.id, agent_b.id, 1),
        (task_a.id, agent_b.id, 2),
        (task_b.id, agent_a.id, 1),
        (task_b.id, agent_a.id, 2),
        (task_b.id, agent_b.id, 1),
        (task_b.id, agent_b.id, 2),
    ]

    summary = service.aggregate_experiment(experiment.id)
    assert summary["overall"]["planned_runs"] == 8
    assert summary["overall"]["terminal_trials"] == 0
    assert summary["overall"]["completion_rate"] == 0
    assert summary["overall"]["benchmark_runs"] == 0


def test_matrix_executes_two_by_two_by_two_and_is_idempotent(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent_a = add_agent(
        db,
        "agent-a",
        "from pathlib import Path; Path('result.txt').write_text('a')",
    )
    agent_b = add_agent(
        db,
        "agent-b",
        "from pathlib import Path; Path('result.txt').write_text('b')",
    )
    test_command = shlex.join(
        [sys.executable, "-c", "print('2 passed'); raise SystemExit(0)"]
    )
    task_a = add_task(
        db,
        name="task-a",
        repo=repo,
        base_commit=base_commit,
        test_command=test_command,
    )
    task_b = add_task(
        db,
        name="task-b",
        repo=repo,
        base_commit=base_commit,
        test_command=test_command,
    )

    service = ExperimentService(
        db,
        artifact_root=tmp_path / "artifacts",
        setup_timeout=2,
        test_timeout=2,
    )
    experiment = service.create_experiment(
        name="2x2x2",
        task_ids=[task_a.id, task_b.id],
        agent_config_ids=[agent_a.id, agent_b.id],
        repetitions=2,
    )

    completed = service.execute_experiment(experiment.id)

    assert completed.status == "completed"
    assert completed.started_at is not None
    assert completed.completed_at is not None
    assert db.query(BenchmarkRun).count() == 8
    assert all(trial.status == "completed" for trial in completed.trials)
    assert all(trial.benchmark_run_id is not None for trial in completed.trials)

    summary = service.aggregate_experiment(experiment.id)
    assert summary["overall"]["planned_runs"] == 8
    assert summary["overall"]["benchmark_runs"] == 8
    assert summary["overall"]["successful_runs"] == 8
    assert summary["overall"]["failed_runs"] == 0
    assert summary["overall"]["orchestration_errors"] == 0
    assert summary["overall"]["completion_rate"] == 1
    assert summary["overall"]["success_rate"] == 1
    assert summary["overall"]["tests_passed"] == 16
    assert summary["overall"]["changes"]["files_changed_total"] == 8
    assert len(summary["by_agent"]) == 2
    assert len(summary["by_task"]) == 2
    assert len(summary["by_cell"]) == 4
    assert all(row["metrics"]["planned_runs"] == 4 for row in summary["by_agent"])
    assert all(row["metrics"]["success_rate"] == 1 for row in summary["by_agent"])
    assert all(row["metrics"]["planned_runs"] == 4 for row in summary["by_task"])
    assert all(row["metrics"]["planned_runs"] == 2 for row in summary["by_cell"])
    assert all(row["metrics"]["success_rate"] == 1 for row in summary["by_cell"])

    first_completed_at = completed.completed_at
    service.execute_experiment(experiment.id)
    assert db.query(BenchmarkRun).count() == 8
    db.refresh(completed)
    assert completed.completed_at == first_completed_at


def test_benchmark_failure_is_a_measurement_not_orchestration_error(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    good = add_agent(db, "good", "pass")
    bad = add_agent(db, "bad", "raise SystemExit(4)")
    task = add_task(db, name="task", repo=repo, base_commit=base_commit)

    service = ExperimentService(
        db,
        artifact_root=tmp_path / "artifacts",
        test_timeout=2,
    )
    experiment = service.create_experiment(
        name="agent comparison",
        task_ids=[task.id],
        agent_config_ids=[good.id, bad.id],
        repetitions=1,
    )

    completed = service.execute_experiment(experiment.id)
    summary = service.aggregate_experiment(experiment.id)

    assert completed.status == "completed"
    assert summary["overall"]["benchmark_runs"] == 2
    assert summary["overall"]["successful_runs"] == 1
    assert summary["overall"]["failed_runs"] == 1
    assert summary["overall"]["orchestration_errors"] == 0
    assert summary["overall"]["success_rate"] == pytest.approx(0.5)


def test_orchestration_error_is_recorded_and_historical_results_still_aggregate(
    tmp_path: Path,
):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent = add_agent(db, "later-disabled", "pass")
    task = add_task(db, name="task", repo=repo, base_commit=base_commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="disabled after planning",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
        repetitions=1,
    )

    agent.enabled = False
    db.commit()

    completed = service.execute_experiment(experiment.id)
    summary = service.aggregate_experiment(experiment.id)

    assert completed.status == "completed_with_errors"
    assert completed.trials[0].status == "error"
    assert "disabled" in completed.trials[0].error
    assert summary["overall"]["planned_runs"] == 1
    assert summary["overall"]["benchmark_runs"] == 0
    assert summary["overall"]["orchestration_errors"] == 1
    assert summary["overall"]["completion_rate"] == 1
    assert summary["by_agent"][0]["agent_name"] == "later-disabled"


def test_experiment_rejects_missing_or_disabled_dimensions(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent = add_agent(db, "disabled", "pass", enabled=False)
    task = add_task(db, name="task", repo=repo, base_commit=base_commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")

    with pytest.raises(ValueError, match="disabled"):
        service.create_experiment(
            name="bad",
            task_ids=[task.id],
            agent_config_ids=[agent.id],
        )

    with pytest.raises(ValueError, match="not found"):
        service.create_experiment(
            name="missing",
            task_ids=[task.id],
            agent_config_ids=[99999],
        )


def test_definition_drift_becomes_an_orchestration_error(tmp_path: Path):
    repo = tmp_path / "target-drift"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent = add_agent(db, "stable-agent", "pass")
    task = add_task(db, name="stable-task", repo=repo, base_commit=base_commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="frozen definitions",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
    )

    task.agent_prompt = "mutated after planning"
    db.commit()

    completed = service.execute_experiment(experiment.id)
    summary = service.aggregate_experiment(experiment.id)

    assert completed.status == "completed_with_errors"
    assert "definition drifted" in completed.trials[0].error
    assert summary["overall"]["orchestration_errors"] == 1
    assert summary["by_task"][0]["task_name"] == "stable-task"


def test_running_trial_blocks_parallel_matrix_execution(tmp_path: Path):
    repo = tmp_path / "target-busy"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent = add_agent(db, "agent", "pass")
    task = add_task(db, name="task", repo=repo, base_commit=base_commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="busy",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
    )

    experiment.trials[0].status = "running"
    db.commit()

    with pytest.raises(ExperimentBusyError, match="running trials"):
        service.execute_experiment(experiment.id)

    assert db.query(BenchmarkRun).count() == 0
