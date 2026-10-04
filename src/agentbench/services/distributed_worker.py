"""Durable cross-process trial ownership and worker execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import socket
import threading
import uuid
from typing import Any

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from ..models.database import (
    Experiment,
    ExperimentExecution,
    ExperimentTrial,
    ExperimentWorkerAttempt,
)
from ..timeutils import utc_now
from .benchmark import BenchmarkService
from .experiment import ExperimentService, TrialExecutionOutcome


@dataclass(frozen=True)
class WorkerClaim:
    attempt_id: int
    experiment_id: int
    trial_id: int
    owner_id: str
    lease_token: str
    lease_seconds: int
    expires_at: Any


class DistributedWorkerService:
    """Claim and execute trials using durable database-backed leases."""

    MIN_LEASE_SECONDS = 10
    MAX_LEASE_SECONDS = 3600

    def __init__(
        self,
        db: Session,
        *,
        experiment_service: ExperimentService | None = None,
    ):
        self.db = db
        self.experiments = experiment_service or ExperimentService(db)
        if self.experiments.db is not db:
            raise ValueError("Injected ExperimentService must use the same session")
        bind = db.get_bind()
        if bind is None:
            raise ValueError("Worker leases require a bound database engine")
        self.engine: Engine = bind.engine if isinstance(bind, Connection) else bind
        if self.engine.dialect.name == "sqlite" and self.engine.url.database in {
            None,
            "",
            ":memory:",
        }:
            raise ValueError(
                "Distributed workers require file-backed SQLite or another "
                "multi-connection database"
            )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    def validate_lease_seconds(cls, lease_seconds: int) -> int:
        value = int(lease_seconds)
        if value < cls.MIN_LEASE_SECONDS or value > cls.MAX_LEASE_SECONDS:
            raise ValueError(
                f"lease_seconds must be between {cls.MIN_LEASE_SECONDS} "
                f"and {cls.MAX_LEASE_SECONDS}"
            )
        return value

    @staticmethod
    def default_owner_id() -> str:
        return f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"

    def claim_next(
        self,
        experiment_id: int,
        *,
        owner_id: str,
        lease_seconds: int = 60,
    ) -> WorkerClaim | None:
        owner = owner_id.strip()
        if not owner:
            raise ValueError("owner_id must not be empty")
        lease_seconds = self.validate_lease_seconds(lease_seconds)
        experiment = self.experiments.get_experiment(experiment_id)
        if experiment.status == "completed":
            return None
        if experiment.stop_on_error:
            has_error = (
                self.db.query(ExperimentTrial)
                .filter(
                    ExperimentTrial.experiment_id == experiment.id,
                    ExperimentTrial.status == "error",
                )
                .count()
            )
            if has_error:
                return None

        while True:
            row = (
                self.db.query(ExperimentTrial.id)
                .filter(
                    ExperimentTrial.experiment_id == experiment.id,
                    ExperimentTrial.status == "planned",
                )
                .order_by(ExperimentTrial.ordinal.asc())
                .first()
            )
            if row is None:
                return None

            trial_id = int(row[0])
            now = utc_now()
            claimed = (
                self.db.query(ExperimentTrial)
                .filter(
                    ExperimentTrial.id == trial_id,
                    ExperimentTrial.status == "planned",
                )
                .update(
                    {
                        ExperimentTrial.status: "running",
                        ExperimentTrial.started_at: now,
                        ExperimentTrial.completed_at: None,
                        ExperimentTrial.error: None,
                    },
                    synchronize_session=False,
                )
            )
            if claimed != 1:
                self.db.rollback()
                continue

            token = uuid.uuid4().hex
            expires_at = now + timedelta(seconds=lease_seconds)
            attempt = ExperimentWorkerAttempt(
                experiment_id=int(experiment.id),
                trial_id=trial_id,
                owner_id=owner,
                lease_token=token,
                status="active",
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
                details={"lease_seconds": lease_seconds},
            )
            self.db.add(attempt)
            (
                self.db.query(Experiment)
                .filter(Experiment.id == int(experiment.id))
                .update(
                    {
                        Experiment.status: "running",
                        Experiment.completed_at: None,
                    },
                    synchronize_session=False,
                )
            )
            self.db.commit()
            self.db.refresh(attempt)
            return WorkerClaim(
                attempt_id=int(attempt.id),
                experiment_id=int(experiment.id),
                trial_id=trial_id,
                owner_id=owner,
                lease_token=token,
                lease_seconds=lease_seconds,
                expires_at=expires_at,
            )

    def heartbeat(self, claim: WorkerClaim) -> bool:
        now = utc_now()
        updated = (
            self.db.query(ExperimentWorkerAttempt)
            .filter(
                ExperimentWorkerAttempt.id == claim.attempt_id,
                ExperimentWorkerAttempt.lease_token == claim.lease_token,
                ExperimentWorkerAttempt.owner_id == claim.owner_id,
                ExperimentWorkerAttempt.status == "active",
            )
            .update(
                {
                    ExperimentWorkerAttempt.heartbeat_at: now,
                    ExperimentWorkerAttempt.expires_at: now
                    + timedelta(seconds=claim.lease_seconds),
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return updated == 1

    def _heartbeat_loop(
        self,
        claim: WorkerClaim,
        stop: threading.Event,
    ) -> None:
        interval = max(1.0, min(30.0, claim.lease_seconds / 3))
        while not stop.wait(interval):
            db = self.session_factory()
            try:
                service = DistributedWorkerService(db)
                if not service.heartbeat(claim):
                    return
            except Exception:
                # Recovery is explicit. A transient heartbeat failure never
                # silently requeues work while the original process may live.
                return
            finally:
                db.close()

    def _finish_claim(
        self,
        claim: WorkerClaim,
        outcome: TrialExecutionOutcome,
    ) -> None:
        now = utc_now()
        attempt = (
            self.db.query(ExperimentWorkerAttempt)
            .filter(
                ExperimentWorkerAttempt.id == claim.attempt_id,
                ExperimentWorkerAttempt.lease_token == claim.lease_token,
                ExperimentWorkerAttempt.owner_id == claim.owner_id,
            )
            .one()
        )
        attempt.status = outcome.status
        attempt.completed_at = now
        attempt.heartbeat_at = now
        attempt.expires_at = now
        details = dict(attempt.details or {})
        details["benchmark_run_id"] = outcome.benchmark_run_id
        details["error"] = outcome.error
        attempt.details = details

        experiment = self.experiments.get_experiment(claim.experiment_id)
        active_or_planned = (
            self.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == experiment.id,
                ExperimentTrial.status.in_(("planned", "running")),
            )
            .count()
        )
        if experiment.stop_on_error and outcome.status == "error":
            experiment.status = "failed"
            experiment.completed_at = utc_now()
        elif active_or_planned == 0:
            self.experiments._finalize_status(experiment)
        self.db.commit()

    def execute_claim(self, claim: WorkerClaim) -> TrialExecutionOutcome:
        attempt = (
            self.db.query(ExperimentWorkerAttempt)
            .filter(
                ExperimentWorkerAttempt.id == claim.attempt_id,
                ExperimentWorkerAttempt.lease_token == claim.lease_token,
                ExperimentWorkerAttempt.owner_id == claim.owner_id,
                ExperimentWorkerAttempt.status == "active",
            )
            .one_or_none()
        )
        if attempt is None:
            raise ValueError("Worker claim is no longer active or owned by this worker")

        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(claim, stop),
            name=f"agentbench-heartbeat-{claim.attempt_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            outcome = self.experiments.execute_claimed_trial(claim.trial_id)
        finally:
            stop.set()
            heartbeat.join(timeout=max(1.0, claim.lease_seconds / 3 + 1))
        self._finish_claim(claim, outcome)
        return outcome

    def run_worker(
        self,
        experiment_id: int,
        *,
        owner_id: str | None = None,
        lease_seconds: int = 60,
        max_trials: int | None = None,
    ) -> dict[str, Any]:
        owner = (owner_id or self.default_owner_id()).strip()
        if max_trials is not None and max_trials < 1:
            raise ValueError("max_trials must be greater than 0 when provided")
        lease_seconds = self.validate_lease_seconds(lease_seconds)
        execution = self.experiments._start_execution_attempt(
            experiment_id,
            mode="distributed_worker",
            max_workers=1,
            details={
                "owner_id": owner,
                "lease_seconds": lease_seconds,
                "max_trials": max_trials,
            },
        )
        outcomes: list[TrialExecutionOutcome] = []
        try:
            while max_trials is None or len(outcomes) < max_trials:
                claim = self.claim_next(
                    experiment_id,
                    owner_id=owner,
                    lease_seconds=lease_seconds,
                )
                if claim is None:
                    break
                outcomes.append(self.execute_claim(claim))
        except BaseException:
            self.experiments._finish_execution_attempt(
                int(execution.id),
                status="interrupted",
                details={"completed_claims": len(outcomes)},
            )
            raise

        status = "failed" if any(item.status == "error" for item in outcomes) else "completed"
        self.experiments._finish_execution_attempt(
            int(execution.id),
            status=status,
            details={"completed_claims": len(outcomes)},
        )
        return {
            "experiment_id": experiment_id,
            "owner_id": owner,
            "execution_id": int(execution.id),
            "status": status,
            "completed_claims": len(outcomes),
            "outcomes": [
                {
                    "trial_id": item.trial_id,
                    "status": item.status,
                    "benchmark_run_id": item.benchmark_run_id,
                    "error": item.error,
                }
                for item in outcomes
            ],
        }

    def recover_expired(
        self,
        experiment_id: int,
        *,
        grace_seconds: int = 0,
    ) -> dict[str, Any]:
        if grace_seconds < 0 or grace_seconds > 86400:
            raise ValueError("grace_seconds must be between 0 and 86400")
        now = utc_now()
        threshold = now - timedelta(seconds=grace_seconds)
        attempts = (
            self.db.query(ExperimentWorkerAttempt)
            .filter(
                ExperimentWorkerAttempt.experiment_id == experiment_id,
                ExperimentWorkerAttempt.status == "active",
                ExperimentWorkerAttempt.expires_at <= threshold,
            )
            .order_by(ExperimentWorkerAttempt.id.asc())
            .all()
        )
        recovered: list[int] = []
        for attempt in attempts:
            trial = (
                self.db.query(ExperimentTrial)
                .filter(ExperimentTrial.id == attempt.trial_id)
                .one_or_none()
            )
            if trial is None or trial.status != "running":
                attempt.status = "orphaned"
                attempt.completed_at = now
                continue
            trial.status = "planned"
            trial.started_at = None
            trial.completed_at = None
            trial.error = None
            attempt.status = "expired"
            attempt.completed_at = now
            recovered.append(int(trial.id))

        experiment = self.experiments.get_experiment(experiment_id)
        if recovered and experiment.status == "running":
            active = (
                self.db.query(ExperimentWorkerAttempt)
                .filter(
                    ExperimentWorkerAttempt.experiment_id == experiment_id,
                    ExperimentWorkerAttempt.status == "active",
                )
                .count()
            )
            if active == 0:
                experiment.status = "pending"
                experiment.completed_at = None
        self.db.commit()
        return {
            "experiment_id": experiment_id,
            "recovered_trial_ids": recovered,
            "recovered_count": len(recovered),
        }

    def status(self, experiment_id: int) -> dict[str, Any]:
        self.experiments.get_experiment(experiment_id)
        rows = (
            self.db.query(ExperimentWorkerAttempt)
            .filter(ExperimentWorkerAttempt.experiment_id == experiment_id)
            .order_by(ExperimentWorkerAttempt.id.asc())
            .all()
        )
        now = utc_now()
        return {
            "experiment_id": experiment_id,
            "attempt_count": len(rows),
            "active_count": sum(row.status == "active" for row in rows),
            "expired_active_count": sum(
                row.status == "active" and row.expires_at <= now for row in rows
            ),
            "attempts": [
                {
                    "id": int(row.id),
                    "trial_id": int(row.trial_id),
                    "owner_id": row.owner_id,
                    "status": row.status,
                    "acquired_at": row.acquired_at.isoformat(),
                    "heartbeat_at": row.heartbeat_at.isoformat(),
                    "expires_at": row.expires_at.isoformat(),
                    "completed_at": (
                        row.completed_at.isoformat()
                        if row.completed_at is not None
                        else None
                    ),
                    "details": dict(row.details or {}),
                }
                for row in rows
            ],
        }


__all__ = ["DistributedWorkerService", "WorkerClaim"]
