"""Durable scheduling budgets for experiment execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from ..models.database import (
    BenchmarkRun,
    Experiment,
    ExperimentBudget,
    ExperimentBudgetReservation,
    ExperimentTrial,
)
from ..timeutils import utc_now


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str | None
    already_reserved: bool
    snapshot: dict[str, Any]


class ExperimentBudgetService:
    """Reserve conservative execution slots and stop new scheduling at limits."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_policy(value: Mapping[str, Any] | None) -> dict[str, int]:
        if not value:
            return {}
        allowed = {
            "max_started_trials",
            "max_wall_seconds",
            "max_total_tokens",
            "max_orchestration_errors",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Unknown budget fields: {unknown}")
        policy: dict[str, int] = {}
        for key in allowed:
            raw = value.get(key)
            if raw is None:
                continue
            number = int(raw)
            if number < 1:
                raise ValueError(f"{key} must be greater than 0")
            policy[key] = number
        if not policy:
            raise ValueError("budget must define at least one limit")
        return policy

    def create(
        self,
        experiment_id: int,
        policy: Mapping[str, Any] | None,
    ) -> ExperimentBudget | None:
        if not policy:
            return None
        normalized = self.normalize_policy(policy)
        existing = (
            self.db.query(ExperimentBudget)
            .filter(ExperimentBudget.experiment_id == int(experiment_id))
            .one_or_none()
        )
        if existing is not None:
            if dict(existing.policy or {}) != normalized:
                raise ValueError("Experiment budget already exists with different policy")
            return existing
        row = ExperimentBudget(
            experiment_id=int(experiment_id),
            policy=normalized,
            status="active",
            reserved_trials=0,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _usage(self, budget: ExperimentBudget) -> dict[str, Any]:
        trials = (
            self.db.query(ExperimentTrial)
            .filter(ExperimentTrial.experiment_id == budget.experiment_id)
            .all()
        )
        run_ids = [
            int(trial.benchmark_run_id)
            for trial in trials
            if trial.benchmark_run_id is not None
        ]
        runs = (
            self.db.query(BenchmarkRun).filter(BenchmarkRun.id.in_(run_ids)).all()
            if run_ids
            else []
        )
        return {
            "reserved_trials": int(budget.reserved_trials or 0),
            "known_total_tokens": sum(
                int(run.total_tokens or 0)
                for run in runs
                if run.total_tokens is not None
            ),
            "orchestration_errors": sum(trial.status == "error" for trial in trials),
            "budgeted_out_trials": sum(
                trial.status == "budgeted_out" for trial in trials
            ),
        }

    def _dynamic_exhaustion(
        self,
        budget: ExperimentBudget,
        *,
        now: datetime,
    ) -> tuple[str | None, dict[str, Any]]:
        policy = dict(budget.policy or {})
        usage = self._usage(budget)
        if budget.started_at is not None:
            elapsed = max(0.0, (now - budget.started_at).total_seconds())
        else:
            elapsed = 0.0
        usage["elapsed_wall_seconds"] = elapsed

        wall_limit = policy.get("max_wall_seconds")
        if wall_limit is not None and elapsed >= int(wall_limit):
            return f"max_wall_seconds={wall_limit} reached", usage
        token_limit = policy.get("max_total_tokens")
        if (
            token_limit is not None
            and int(usage["known_total_tokens"]) >= int(token_limit)
        ):
            return f"max_total_tokens={token_limit} reached", usage
        error_limit = policy.get("max_orchestration_errors")
        if (
            error_limit is not None
            and int(usage["orchestration_errors"]) >= int(error_limit)
        ):
            return f"max_orchestration_errors={error_limit} reached", usage
        return None, usage

    def _mark_exhausted(
        self,
        budget: ExperimentBudget,
        *,
        reason: str,
        now: datetime,
    ) -> None:
        (
            self.db.query(ExperimentBudget)
            .filter(ExperimentBudget.id == int(budget.id))
            .update(
                {
                    ExperimentBudget.status: "exhausted",
                    ExperimentBudget.exhaustion_reason: reason,
                    ExperimentBudget.exhausted_at: now,
                },
                synchronize_session=False,
            )
        )
        (
            self.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == budget.experiment_id,
                ExperimentTrial.status == "planned",
            )
            .update(
                {
                    ExperimentTrial.status: "budgeted_out",
                    ExperimentTrial.completed_at: now,
                    ExperimentTrial.error: f"Experiment budget exhausted: {reason}",
                },
                synchronize_session=False,
            )
        )
        self.db.commit()

    def reserve(self, experiment_id: int, trial_id: int) -> BudgetDecision:
        budget = (
            self.db.query(ExperimentBudget)
            .filter(ExperimentBudget.experiment_id == int(experiment_id))
            .one_or_none()
        )
        if budget is None:
            return BudgetDecision(True, None, False, {"enabled": False})

        existing = (
            self.db.query(ExperimentBudgetReservation)
            .filter(ExperimentBudgetReservation.trial_id == int(trial_id))
            .one_or_none()
        )
        if existing is not None:
            return BudgetDecision(
                True,
                None,
                True,
                {
                    "enabled": True,
                    "policy": dict(budget.policy or {}),
                    **self._usage(budget),
                },
            )

        now = utc_now()
        reason, usage = self._dynamic_exhaustion(budget, now=now)
        if budget.status == "exhausted":
            reason = budget.exhaustion_reason or "budget already exhausted"
        if reason is not None:
            self._mark_exhausted(budget, reason=reason, now=now)
            return BudgetDecision(
                False,
                reason,
                False,
                {"enabled": True, "policy": dict(budget.policy or {}), **usage},
            )

        policy = dict(budget.policy or {})
        max_started = policy.get("max_started_trials")
        query = self.db.query(ExperimentBudget).filter(
            ExperimentBudget.id == int(budget.id),
            ExperimentBudget.status == "active",
        )
        if max_started is not None:
            query = query.filter(ExperimentBudget.reserved_trials < int(max_started))
        updated = query.update(
            {
                ExperimentBudget.reserved_trials: ExperimentBudget.reserved_trials + 1,
                ExperimentBudget.started_at: budget.started_at or now,
            },
            synchronize_session=False,
        )
        if updated != 1:
            self.db.rollback()
            budget = (
                self.db.query(ExperimentBudget)
                .filter(ExperimentBudget.id == int(budget.id))
                .one()
            )
            reason = (
                f"max_started_trials={max_started} reached"
                if max_started is not None
                else "budget is no longer active"
            )
            self._mark_exhausted(budget, reason=reason, now=now)
            return BudgetDecision(
                False,
                reason,
                False,
                {"enabled": True, "policy": dict(budget.policy or {}), **usage},
            )

        self.db.add(
            ExperimentBudgetReservation(
                budget_id=int(budget.id),
                trial_id=int(trial_id),
                reserved_at=now,
                details={"policy": policy},
            )
        )
        self.db.commit()
        budget = (
            self.db.query(ExperimentBudget)
            .filter(ExperimentBudget.id == int(budget.id))
            .one()
        )
        return BudgetDecision(
            True,
            None,
            False,
            {
                "enabled": True,
                "policy": policy,
                **self._usage(budget),
            },
        )

    def status(self, experiment_id: int) -> dict[str, Any]:
        budget = (
            self.db.query(ExperimentBudget)
            .filter(ExperimentBudget.experiment_id == int(experiment_id))
            .one_or_none()
        )
        if budget is None:
            return {"experiment_id": experiment_id, "enabled": False}
        reason, usage = self._dynamic_exhaustion(budget, now=utc_now())
        return {
            "experiment_id": experiment_id,
            "enabled": True,
            "status": budget.status,
            "policy": dict(budget.policy or {}),
            "exhaustion_reason": budget.exhaustion_reason or reason,
            "started_at": (
                budget.started_at.isoformat() if budget.started_at is not None else None
            ),
            "exhausted_at": (
                budget.exhausted_at.isoformat()
                if budget.exhausted_at is not None
                else None
            ),
            **usage,
        }


__all__ = ["BudgetDecision", "ExperimentBudgetService"]
