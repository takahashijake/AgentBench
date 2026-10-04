from __future__ import annotations

from datetime import timedelta
import shlex
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.models.database import (
    AgentConfig,
    Base,
    BenchmarkRun,
    BenchmarkTask,
    ExperimentTrial,
    ExperimentWorkerAttempt,
    WorkerRegistration,
)
from agentbench.resources import WorkerCapabilities
from agentbench.services.distributed_worker import DistributedWorkerService
from agentbench.services.experiment import ExperimentService
from agentbench.timeutils import utc_now

from helpers import init_git_repo


def make_factory(tmp_path: Path):
    database = tmp_path / "workers.sqlite3"
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def add_agent(db, name: str, code: str = "pass") -> AgentConfig:
    agent = AgentConfig(
        name=name,
        enabled=True,
        command_template=shlex.join([sys.executable, "-c", code]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def add_task(db, name: str, repo: Path, commit: str) -> BenchmarkTask:
    task = BenchmarkTask(
        name=name,
        description=f"{name} fixture",
        repository_path=str(repo),
        base_commit=commit,
        agent_prompt=f"solve {name}",
        test_command="",
        timeout=5,
        enabled=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def build_two_task_experiment(tmp_path: Path):
    factory = make_factory(tmp_path)
    db = factory()
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    commit_a = init_git_repo(repo_a)
    commit_b = init_git_repo(repo_b)
    agent = add_agent(db, "worker-agent")
    task_a = add_task(db, "task-a", repo_a, commit_a)
    task_b = add_task(db, "task-b", repo_b, commit_b)
    service = ExperimentService(db, artifact_root=tmp_path / "artifacts")
    experiment = service.create_experiment(
        name="distributed",
        task_ids=[task_a.id, task_b.id],
        agent_config_ids=[agent.id],
    )
    return factory, db, experiment


def test_independent_worker_sessions_claim_different_trials(tmp_path: Path):
    factory, db1, experiment = build_two_task_experiment(tmp_path)
    db2 = factory()
    try:
        worker1 = DistributedWorkerService(db1)
        worker2 = DistributedWorkerService(db2)

        first = worker1.claim_next(experiment.id, owner_id="worker-a", lease_seconds=30)
        second = worker2.claim_next(
            experiment.id, owner_id="worker-b", lease_seconds=30
        )

        assert first is not None
        assert second is not None
        assert first.trial_id != second.trial_id
        assert first.lease_token != second.lease_token

        db1.expire_all()
        attempts = (
            db1.query(ExperimentWorkerAttempt)
            .filter(ExperimentWorkerAttempt.experiment_id == experiment.id)
            .order_by(ExperimentWorkerAttempt.id.asc())
            .all()
        )
        assert [row.owner_id for row in attempts] == ["worker-a", "worker-b"]
        assert all(row.status == "active" for row in attempts)
    finally:
        db2.close()
        db1.close()


def test_heartbeat_extends_durable_lease(tmp_path: Path):
    factory, db, experiment = build_two_task_experiment(tmp_path)
    try:
        worker = DistributedWorkerService(db)
        claim = worker.claim_next(
            experiment.id,
            owner_id="heartbeat-worker",
            lease_seconds=30,
        )
        assert claim is not None
        before = claim.expires_at

        assert worker.heartbeat(claim) is True
        db.expire_all()
        attempt = db.get(ExperimentWorkerAttempt, claim.attempt_id)

        assert attempt is not None
        assert attempt.heartbeat_at >= claim.expires_at - timedelta(seconds=30)
        assert attempt.expires_at >= before
    finally:
        db.close()


def test_expired_claim_recovery_requeues_trial_explicitly(tmp_path: Path):
    factory, db, experiment = build_two_task_experiment(tmp_path)
    try:
        worker = DistributedWorkerService(db)
        claim = worker.claim_next(
            experiment.id,
            owner_id="expired-worker",
            lease_seconds=30,
        )
        assert claim is not None
        attempt = db.get(ExperimentWorkerAttempt, claim.attempt_id)
        assert attempt is not None
        attempt.expires_at = utc_now() - timedelta(seconds=5)
        db.commit()

        recovered = worker.recover_expired(experiment.id)

        assert recovered["recovered_count"] == 1
        assert recovered["recovered_trial_ids"] == [claim.trial_id]
        db.expire_all()
        trial = db.get(ExperimentTrial, claim.trial_id)
        attempt = db.get(ExperimentWorkerAttempt, claim.attempt_id)
        assert trial is not None and trial.status == "planned"
        assert trial.started_at is None
        assert attempt is not None and attempt.status == "expired"
    finally:
        db.close()


def test_recovered_stale_worker_is_fenced_from_terminal_mutation(tmp_path: Path):
    factory = make_factory(tmp_path)
    owner_db = factory()
    recovery_db = factory()
    try:
        repo = tmp_path / "repo"
        commit = init_git_repo(repo)
        code = (
            "from pathlib import Path; "
            "Path('agent-output.txt').write_text('done', encoding='utf-8')"
        )
        agent = add_agent(owner_db, "stale-agent", code)
        task = add_task(owner_db, "stale-task", repo, commit)
        service = ExperimentService(owner_db, artifact_root=tmp_path / "artifacts")
        experiment = service.create_experiment(
            name="stale-fencing",
            task_ids=[task.id],
            agent_config_ids=[agent.id],
        )
        owner = DistributedWorkerService(owner_db, experiment_service=service)
        claim = owner.claim_next(
            experiment.id,
            owner_id="stale-owner",
            lease_seconds=30,
        )
        assert claim is not None

        attempt = owner_db.get(ExperimentWorkerAttempt, claim.attempt_id)
        assert attempt is not None
        attempt.expires_at = utc_now() - timedelta(seconds=5)
        owner_db.commit()

        recovery = DistributedWorkerService(recovery_db)
        assert recovery.recover_expired(experiment.id)["recovered_count"] == 1

        outcome = service.execute_claimed_trial(
            claim.trial_id,
            ownership_check=lambda: owner._claim_is_active(claim),
        )

        assert outcome.status == "lease_lost"
        owner_db.expire_all()
        trial = owner_db.get(ExperimentTrial, claim.trial_id)
        assert trial is not None
        assert trial.status == "planned"
        assert trial.benchmark_run_id is None
    finally:
        recovery_db.close()
        owner_db.close()


def test_worker_run_persists_attempts_and_completes_experiment(tmp_path: Path):
    factory = make_factory(tmp_path)
    db = factory()
    try:
        repo = tmp_path / "repo"
        commit = init_git_repo(repo)
        agent = add_agent(db, "run-agent")
        task = add_task(db, "run-task", repo, commit)
        experiment = ExperimentService(
            db,
            artifact_root=tmp_path / "artifacts",
        ).create_experiment(
            name="worker-run",
            task_ids=[task.id],
            agent_config_ids=[agent.id],
        )

        worker = DistributedWorkerService(db)
        result = worker.run_worker(
            experiment.id,
            owner_id="worker-runner",
            lease_seconds=30,
        )

        assert result["status"] == "completed"
        assert result["completed_claims"] == 1
        assert result["outcomes"][0]["status"] == "completed"
        summary = worker.experiments.aggregate_experiment(experiment.id)
        assert summary["analysis_schema_version"] == 7
        assert summary["worker_summary"]["attempt_count"] == 1
        assert summary["worker_summary"]["active_count"] == 0
        assert summary["worker_attempts"][0]["owner_id"] == "worker-runner"
        assert summary["worker_attempts"][0]["status"] == "completed"
        assert db.query(BenchmarkRun).count() == 1
    finally:
        db.close()


def test_capability_aware_workers_skip_incompatible_earlier_trials(tmp_path: Path):
    factory = make_factory(tmp_path)
    db_low = factory()
    db_high = factory()
    try:
        repo_high = tmp_path / "repo-high"
        repo_low = tmp_path / "repo-low"
        commit_high = init_git_repo(repo_high)
        commit_low = init_git_repo(repo_low)
        agent = add_agent(db_low, "capability-agent")
        high = add_task(db_low, "high-resource", repo_high, commit_high)
        low = add_task(db_low, "low-resource", repo_low, commit_low)
        service = ExperimentService(db_low, artifact_root=tmp_path / "artifacts")
        experiment = service.create_experiment(
            name="capability-routing",
            task_ids=[high.id, low.id],
            agent_config_ids=[agent.id],
            task_requirements={
                high.id: {
                    "min_cpu_count": 8,
                    "required_commands": ["special-accelerator"],
                },
                low.id: {"min_cpu_count": 1},
            },
        )

        low_worker = DistributedWorkerService(db_low, experiment_service=service)
        low_worker.register_worker(
            "small-worker",
            capabilities=WorkerCapabilities(
                platform="linux",
                cpu_count=2,
                memory_mb=2048,
                commands=(),
                labels=("cpu",),
            ),
        )

        queue = low_worker.queue_status(experiment.id)
        assert queue["planned_count"] == 2
        assert queue["unmatched_planned_count"] == 1
        high_row = next(row for row in queue["trials"] if row["task_id"] == high.id)
        low_row = next(row for row in queue["trials"] if row["task_id"] == low.id)
        assert high_row["eligible_owners"] == []
        assert low_row["eligible_owners"] == ["small-worker"]

        low_claim = low_worker.claim_next(
            experiment.id,
            owner_id="small-worker",
            lease_seconds=30,
        )
        assert low_claim is not None
        assert low_claim.trial_id == low_row["trial_id"]

        high_worker = DistributedWorkerService(db_high)
        high_worker.register_worker(
            "large-worker",
            capabilities=WorkerCapabilities(
                platform="linux",
                cpu_count=16,
                memory_mb=32768,
                commands=("special-accelerator",),
                labels=("accelerator",),
            ),
        )
        high_claim = high_worker.claim_next(
            experiment.id,
            owner_id="large-worker",
            lease_seconds=30,
        )
        assert high_claim is not None
        assert high_claim.trial_id == high_row["trial_id"]
    finally:
        db_high.close()
        db_low.close()


def test_worker_registration_is_durable_and_normalized(tmp_path: Path):
    factory, db, experiment = build_two_task_experiment(tmp_path)
    try:
        worker = DistributedWorkerService(db)
        capabilities = worker.register_worker(
            "registered-worker",
            experiment_id=experiment.id,
            capabilities=WorkerCapabilities(
                platform="LINUX",
                cpu_count=4,
                memory_mb=8192,
                commands=("git", "python", "git"),
                labels=("general", "general"),
            ),
            metadata={"pool": "test"},
        )

        assert capabilities.platform == "linux"
        assert capabilities.commands == ("git", "python")
        assert capabilities.labels == ("general",)
        registration = (
            db.query(WorkerRegistration)
            .filter(WorkerRegistration.owner_id == "registered-worker")
            .one()
        )
        assert registration.capabilities["cpu_count"] == 4
        assert registration.metadata_json == {"pool": "test"}
        assert worker.worker_heartbeat("registered-worker") is True
    finally:
        db.close()
