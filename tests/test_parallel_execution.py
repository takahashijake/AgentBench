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
    ExperimentExecution,
    ExperimentTrial,
)
from agentbench.services.experiment import ExperimentService

from helpers import init_git_repo


def make_file_session(tmp_path: Path):
    database = tmp_path / "parallel.sqlite3"
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def add_agent(db, name: str, code: str) -> AgentConfig:
    agent = AgentConfig(
        name=name,
        enabled=True,
        command_template=shlex.join([sys.executable, "-c", code]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def add_task(db, name: str, repo: Path, base_commit: str) -> BenchmarkTask:
    task = BenchmarkTask(
        name=name,
        description=f"{name} fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt=f"solve {name}",
        test_command="",
        timeout=5,
        enabled=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_parallel_workers_overlap_across_independent_repositories(tmp_path: Path):
    db = make_file_session(tmp_path)
    first_repo = tmp_path / "repo-a"
    second_repo = tmp_path / "repo-b"
    first_commit = init_git_repo(first_repo)
    second_commit = init_git_repo(second_repo)
    barrier = tmp_path / "barrier"

    code = f"""
import time
from pathlib import Path

root = Path({str(barrier)!r})
root.mkdir(parents=True, exist_ok=True)
marker = root / (Path.cwd().name + ".start")
marker.write_text("started", encoding="utf-8")
deadline = time.monotonic() + 2.0
while len(list(root.glob("*.start"))) < 2 and time.monotonic() < deadline:
    time.sleep(0.02)
raise SystemExit(0 if len(list(root.glob("*.start"))) >= 2 else 9)
""".strip()

    agent = add_agent(db, "parallel-agent", code)
    first = add_task(db, "first", first_repo, first_commit)
    second = add_task(db, "second", second_repo, second_commit)
    service = ExperimentService(
        db,
        artifact_root=tmp_path / "artifacts",
        test_timeout=2,
    )
    experiment = service.create_experiment(
        name="parallel-overlap",
        task_ids=[first.id, second.id],
        agent_config_ids=[agent.id],
    )

    completed = service.execute_experiment(experiment.id, max_workers=2)
    summary = service.aggregate_experiment(experiment.id)

    assert completed.status == "completed"
    assert summary["overall"]["benchmark_runs"] == 2
    assert summary["overall"]["successful_runs"] == 2
    assert summary["overall"]["orchestration_errors"] == 0
    assert summary["analysis_schema_version"] == 5
    assert summary["latest_execution"]["mode"] == "local_parallel"
    assert summary["latest_execution"]["max_workers"] == 2
    assert summary["latest_execution"]["status"] == "completed"
    assert len(summary["execution_history"]) == 1
    assert len(list(barrier.glob("*.start"))) == 2

    run_count = db.query(BenchmarkRun).count()
    service.execute_experiment(experiment.id, max_workers=2)
    assert db.query(BenchmarkRun).count() == run_count


def test_parallel_execution_rejects_in_memory_sqlite(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    repo = tmp_path / "repo"
    commit = init_git_repo(repo)
    agent = add_agent(db, "agent", "pass")
    task = add_task(db, "task", repo, commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="memory-db",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
    )

    with pytest.raises(ValueError, match="in-memory SQLite"):
        service.execute_experiment(experiment.id, max_workers=2)


def test_recover_running_trials_requires_explicit_service_action(tmp_path: Path):
    db = make_file_session(tmp_path)
    repo = tmp_path / "repo"
    commit = init_git_repo(repo)
    agent = add_agent(db, "agent", "pass")
    task = add_task(db, "task", repo, commit)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="recover",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
    )

    trial = experiment.trials[0]
    trial.status = "running"
    experiment.status = "running"
    attempt = service._start_execution_attempt(
        experiment.id,
        mode="local_parallel",
        max_workers=2,
    )
    db.commit()

    assert service.recover_running_trials(experiment.id) == 1
    db.refresh(trial)
    assert trial.status == "planned"
    assert trial.started_at is None
    assert trial.completed_at is None
    db.refresh(attempt)
    assert attempt.status == "interrupted"
    assert attempt.completed_at is not None
    assert attempt.details["recovered_running_trials"] == 1

    completed = service.execute_experiment(experiment.id, max_workers=1)
    assert completed.status == "completed"


def test_parallel_stop_on_error_finishes_inflight_but_stops_new_work(tmp_path: Path):
    db = make_file_session(tmp_path)
    repos = [tmp_path / f"repo-{index}" for index in range(3)]
    commits = [init_git_repo(repo) for repo in repos]

    slow_code = "import time; time.sleep(0.5)"
    agent = add_agent(db, "parallel-stop-agent", slow_code)
    tasks = [
        add_task(db, f"task-{index}", repo, commit)
        for index, (repo, commit) in enumerate(zip(repos, commits), start=1)
    ]
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="parallel-stop",
        task_ids=[task.id for task in tasks],
        agent_config_ids=[agent.id],
        stop_on_error=True,
    )

    # Force the first scheduled cell to fail definition validation immediately.
    tasks[0].agent_prompt = "drifted after planning"
    db.commit()

    completed = service.execute_experiment(experiment.id, max_workers=2)
    trials = (
        db.query(ExperimentTrial)
        .filter(ExperimentTrial.experiment_id == experiment.id)
        .order_by(ExperimentTrial.ordinal.asc())
        .all()
    )

    assert completed.status == "failed"
    assert trials[0].status == "error"
    assert trials[1].status == "completed"
    assert trials[2].status == "planned"
    assert db.query(BenchmarkRun).count() == 1
    attempts = (
        db.query(ExperimentExecution)
        .filter(ExperimentExecution.experiment_id == experiment.id)
        .order_by(ExperimentExecution.id.asc())
        .all()
    )
    assert attempts[-1].status == "failed"
    assert attempts[-1].max_workers == 2
