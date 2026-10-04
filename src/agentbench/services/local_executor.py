"""Bounded local parallel execution with one SQLAlchemy session per worker."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Lock
from typing import Any, cast

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import sessionmaker

from ..models.database import ExperimentTrial
from ..timeutils import utc_now
from .benchmark import BenchmarkService
from .experiment import ExperimentBusyError, ExperimentService, TrialExecutionOutcome


class LocalParallelExperimentExecutor:
    """Execute independent experiment cells without sharing ORM sessions."""

    def __init__(self, coordinator: ExperimentService):
        self.coordinator = coordinator
        if type(coordinator.benchmark_service) is not BenchmarkService:
            raise ValueError(
                "Parallel execution currently requires the standard BenchmarkService; "
                "custom benchmark services must provide an explicit worker factory"
            )

        bind = coordinator.db.get_bind()
        if bind is None:
            raise ValueError("Parallel execution requires a bound database engine")
        self.engine: Engine = (
            bind.engine if isinstance(bind, Connection) else cast(Engine, bind)
        )
        if self.engine.dialect.name == "sqlite":
            database = self.engine.url.database
            if database in {None, "", ":memory:"}:
                raise ValueError(
                    "Parallel execution requires a file-backed SQLite database or "
                    "another multi-connection database; in-memory SQLite is unsupported"
                )

        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        benchmark = coordinator.benchmark_service
        self.artifact_root = benchmark.artifact_root
        self.setup_timeout = benchmark.setup_timeout
        self.test_timeout = benchmark.test_timeout
        self.adapter_registry = benchmark.adapter_registry
        self.resource_inspector = coordinator.resource_inspector
        self._repository_locks: dict[str, Lock] = {}
        self._repository_locks_guard = Lock()

    def _repository_lock(self, repository_path: str) -> Lock:
        key = str(Path(repository_path).expanduser().resolve())
        with self._repository_locks_guard:
            return self._repository_locks.setdefault(key, Lock())

    def _worker(self, trial_id: int, repository_path: str) -> TrialExecutionOutcome:
        """Run one trial with a fresh persistence unit of work."""

        db = self.session_factory()
        try:
            benchmark = BenchmarkService(
                db,
                artifact_root=self.artifact_root,
                setup_timeout=self.setup_timeout,
                test_timeout=self.test_timeout,
                adapter_registry=self.adapter_registry,
            )
            service = ExperimentService(
                db,
                benchmark_service=benchmark,
                resource_inspector=self.resource_inspector,
            )
            # Git worktree metadata is shared by every task backed by the same
            # source repository. Keep one active lifecycle per repository while
            # still allowing different repositories to execute concurrently.
            with self._repository_lock(repository_path):
                return service.execute_trial(trial_id)
        finally:
            db.close()

    def _mark_worker_failure(self, trial_id: int, exc: BaseException) -> None:
        db = self.session_factory()
        try:
            trial = (
                db.query(ExperimentTrial)
                .filter(ExperimentTrial.id == int(trial_id))
                .one_or_none()
            )
            if trial is not None and trial.status in {"planned", "running"}:
                now = utc_now()
                values: dict[Any, Any] = {
                    ExperimentTrial.status: "error",
                    ExperimentTrial.error: f"{type(exc).__name__}: {exc}",
                    ExperimentTrial.completed_at: now,
                }
                if trial.started_at is None:
                    values[ExperimentTrial.started_at] = now
                (
                    db.query(ExperimentTrial)
                    .filter(ExperimentTrial.id == int(trial_id))
                    .update(values, synchronize_session=False)
                )
                db.commit()
        finally:
            db.close()

    def execute(self, experiment_id: int, *, max_workers: int):
        experiment = self.coordinator.get_experiment(experiment_id)
        running = (
            self.coordinator.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == experiment.id,
                ExperimentTrial.status == "running",
            )
            .count()
        )
        if running:
            raise ExperimentBusyError(
                f"Experiment {experiment.id} already has running trials"
            )

        pending: list[tuple[int, int]] = [
            (int(trial_id), int(task_id))
            for trial_id, task_id in (
                self.coordinator.db.query(
                    ExperimentTrial.id,
                    ExperimentTrial.task_id,
                )
                .filter(
                    ExperimentTrial.experiment_id == experiment.id,
                    ExperimentTrial.status == "planned",
                )
                .order_by(ExperimentTrial.ordinal.asc())
                .all()
            )
        ]
        if not pending:
            self.coordinator._finalize_status(experiment)
            self.coordinator.db.commit()
            self.coordinator.db.refresh(experiment)
            return experiment

        task_snapshots = self.coordinator._snapshots_by_id(
            list(experiment.task_snapshots)
        )
        work_items = [
            (
                int(trial_id),
                str(task_snapshots[int(task_id)]["repository_path"]),
            )
            for trial_id, task_id in pending
        ]

        experiment = self.coordinator._claim_experiment_for_execution(experiment)
        attempt = self.coordinator._start_execution_attempt(
            experiment.id,
            mode="local_parallel",
            max_workers=max_workers,
            details={"planned_for_attempt": len(work_items)},
        )

        next_index = 0
        stop_scheduling = False
        futures: dict[Future[TrialExecutionOutcome], int] = {}

        def submit_available(pool: ThreadPoolExecutor) -> None:
            nonlocal next_index
            while (
                not stop_scheduling
                and next_index < len(work_items)
                and len(futures) < max_workers
            ):
                trial_id, repository_path = work_items[next_index]
                next_index += 1
                future = pool.submit(self._worker, trial_id, repository_path)
                futures[future] = trial_id

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="agentbench-trial",
        ) as pool:
            submit_available(pool)
            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    trial_id = futures.pop(future)
                    try:
                        outcome = future.result()
                    except BaseException as exc:
                        self._mark_worker_failure(trial_id, exc)
                        outcome = TrialExecutionOutcome(
                            trial_id=trial_id,
                            status="error",
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    if outcome.status == "error" and experiment.stop_on_error:
                        stop_scheduling = True
                submit_available(pool)

        self.coordinator.db.expire_all()
        experiment = self.coordinator.get_experiment(experiment_id)
        remaining = (
            self.coordinator.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == experiment.id,
                ExperimentTrial.status == "planned",
            )
            .count()
        )
        if stop_scheduling and remaining:
            experiment.status = "failed"
            experiment.completed_at = utc_now()
        else:
            self.coordinator._finalize_status(experiment)

        self.coordinator.db.commit()
        self.coordinator.db.refresh(experiment)
        self.coordinator._finish_execution_attempt(
            attempt.id,
            status=str(experiment.status),
            details={
                "stop_scheduling_triggered": bool(stop_scheduling),
                "remaining_planned_trials": int(remaining),
            },
        )
        return experiment


__all__ = ["LocalParallelExperimentExecutor"]
