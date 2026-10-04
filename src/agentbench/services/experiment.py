"""Experiment matrix planning, execution, and aggregation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from ..models.database import (
    AgentConfig,
    BenchmarkTask,
    Experiment,
    ExperimentTrial,
)
from ..statistics import (
    build_agent_ranking,
    build_pairwise_task_comparison,
    numeric_summary,
    wilson_interval,
)
from ..timeutils import utc_now
from .benchmark import BenchmarkService


class ExperimentNotFoundError(ValueError):
    pass


class ExperimentBusyError(RuntimeError):
    pass


class ExperimentService:
    """Execute tasks × agents × repetitions using BenchmarkService."""

    TERMINAL_TRIAL_STATUSES = {"completed", "error"}
    MAX_PLANNED_RUNS = 10_000

    def __init__(
        self,
        db: Session,
        artifact_root: Optional[Path] = None,
        setup_timeout: int = 300,
        test_timeout: Optional[int] = None,
        benchmark_service: Optional[BenchmarkService] = None,
    ):
        self.db = db
        if benchmark_service is not None and benchmark_service.db is not db:
            raise ValueError(
                "Injected BenchmarkService must use the same database session"
            )
        self.benchmark_service = benchmark_service or BenchmarkService(
            db,
            artifact_root=artifact_root,
            setup_timeout=setup_timeout,
            test_timeout=test_timeout,
        )

    @staticmethod
    def _dedupe_ids(values: Iterable[int], label: str) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for raw in values:
            value = int(raw)
            if value <= 0:
                raise ValueError(f"{label} IDs must be positive integers")
            if value not in seen:
                seen.add(value)
                result.append(value)
        if not result:
            raise ValueError(f"At least one {label} ID is required")
        return result

    def _load_tasks(self, task_ids: list[int]) -> list[BenchmarkTask]:
        rows = self.db.query(BenchmarkTask).filter(BenchmarkTask.id.in_(task_ids)).all()
        by_id = {row.id: row for row in rows}
        missing = [task_id for task_id in task_ids if task_id not in by_id]
        if missing:
            raise ValueError(f"Benchmark task IDs not found: {missing}")
        disabled = [task_id for task_id in task_ids if not by_id[task_id].enabled]
        if disabled:
            raise ValueError(f"Benchmark task IDs are disabled: {disabled}")
        return [by_id[task_id] for task_id in task_ids]

    def _load_agents(self, agent_ids: list[int]) -> list[AgentConfig]:
        rows = self.db.query(AgentConfig).filter(AgentConfig.id.in_(agent_ids)).all()
        by_id = {row.id: row for row in rows}
        missing = [agent_id for agent_id in agent_ids if agent_id not in by_id]
        if missing:
            raise ValueError(f"Agent configuration IDs not found: {missing}")
        disabled = [agent_id for agent_id in agent_ids if not by_id[agent_id].enabled]
        if disabled:
            raise ValueError(f"Agent configuration IDs are disabled: {disabled}")
        return [by_id[agent_id] for agent_id in agent_ids]

    @staticmethod
    def _task_snapshot(task: BenchmarkTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "repository_path": task.repository_path,
            "base_commit": task.base_commit,
            "agent_prompt": task.agent_prompt,
            "setup_command": task.setup_command,
            "test_command": task.test_command,
            "timeout": task.timeout,
            "enabled": task.enabled,
        }

    @staticmethod
    def _agent_snapshot(agent: AgentConfig) -> dict[str, Any]:
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "command_template": agent.command_template,
            "enabled": agent.enabled,
        }

    @staticmethod
    def _snapshots_by_id(snapshots: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        return {int(snapshot["id"]): snapshot for snapshot in snapshots}

    def _validate_trial_definition(
        self,
        experiment: Experiment,
        task: BenchmarkTask,
        agent: AgentConfig,
    ) -> None:
        if not task.enabled:
            raise ValueError(f"Benchmark task is disabled: {task.id}")
        if not agent.enabled:
            raise ValueError(f"Agent configuration is disabled: {agent.id}")

        task_snapshots = self._snapshots_by_id(list(experiment.task_snapshots))
        agent_snapshots = self._snapshots_by_id(list(experiment.agent_snapshots))
        expected_task = task_snapshots.get(task.id)
        expected_agent = agent_snapshots.get(agent.id)

        if expected_task is None or self._task_snapshot(task) != expected_task:
            raise ValueError(
                f"Benchmark task definition drifted after experiment planning: {task.id}"
            )
        if expected_agent is None or self._agent_snapshot(agent) != expected_agent:
            raise ValueError(
                f"Agent configuration drifted after experiment planning: {agent.id}"
            )

    def create_experiment(
        self,
        *,
        name: str,
        task_ids: Iterable[int],
        agent_config_ids: Iterable[int],
        repetitions: int = 1,
        description: Optional[str] = None,
        stop_on_error: bool = False,
    ) -> Experiment:
        name = name.strip()
        if not name:
            raise ValueError("Experiment name must not be empty")
        if repetitions < 1 or repetitions > 100:
            raise ValueError("repetitions must be between 1 and 100")

        normalized_tasks = self._dedupe_ids(task_ids, "task")
        normalized_agents = self._dedupe_ids(agent_config_ids, "agent")
        tasks = self._load_tasks(normalized_tasks)
        agents = self._load_agents(normalized_agents)

        planned_runs = len(normalized_tasks) * len(normalized_agents) * repetitions
        if planned_runs > self.MAX_PLANNED_RUNS:
            raise ValueError(
                f"Experiment plans {planned_runs} runs; "
                f"maximum is {self.MAX_PLANNED_RUNS}"
            )
        experiment = Experiment(
            name=name,
            description=description,
            repetitions=repetitions,
            stop_on_error=stop_on_error,
            status="pending",
            task_ids=normalized_tasks,
            agent_config_ids=normalized_agents,
            task_snapshots=[self._task_snapshot(task) for task in tasks],
            agent_snapshots=[self._agent_snapshot(agent) for agent in agents],
            planned_runs=planned_runs,
        )
        self.db.add(experiment)
        self.db.flush()

        ordinal = 0
        for task_id in normalized_tasks:
            for agent_id in normalized_agents:
                for repetition in range(1, repetitions + 1):
                    ordinal += 1
                    self.db.add(
                        ExperimentTrial(
                            experiment_id=experiment.id,
                            task_id=task_id,
                            agent_config_id=agent_id,
                            repetition=repetition,
                            ordinal=ordinal,
                            status="planned",
                        )
                    )

        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def get_experiment(self, experiment_id: int) -> Experiment:
        experiment = (
            self.db.query(Experiment)
            .filter(Experiment.id == experiment_id)
            .first()
        )
        if experiment is None:
            raise ExperimentNotFoundError(f"Experiment not found: {experiment_id}")
        return experiment

    def execute_experiment(self, experiment_id: int) -> Experiment:
        """Run all still-planned trials without re-running terminal trials."""
        experiment = self.get_experiment(experiment_id)
        running_trials = (
            self.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == experiment.id,
                ExperimentTrial.status == "running",
            )
            .count()
        )
        if running_trials:
            raise ExperimentBusyError(
                f"Experiment {experiment.id} already has running trials"
            )

        pending = (
            self.db.query(ExperimentTrial)
            .filter(
                ExperimentTrial.experiment_id == experiment.id,
                ExperimentTrial.status == "planned",
            )
            .order_by(ExperimentTrial.ordinal.asc())
            .all()
        )
        if not pending:
            self._finalize_status(experiment)
            self.db.commit()
            self.db.refresh(experiment)
            return experiment

        if experiment.started_at is None:
            experiment.started_at = utc_now()
        if experiment.status == "failed":
            experiment.completed_at = None
        experiment.status = "running"
        self.db.commit()

        stopped_early = False
        for trial in pending:
            trial.status = "running"
            trial.started_at = utc_now()
            trial.error = None
            self.db.commit()

            try:
                task = (
                    self.db.query(BenchmarkTask)
                    .filter(BenchmarkTask.id == trial.task_id)
                    .one()
                )
                agent = (
                    self.db.query(AgentConfig)
                    .filter(AgentConfig.id == trial.agent_config_id)
                    .one()
                )
                self._validate_trial_definition(experiment, task, agent)
                run = self.benchmark_service.execute_benchmark(
                    task,
                    agent_config_id=trial.agent_config_id,
                )
                trial.benchmark_run_id = run.id
                trial.status = "completed"
            except Exception as exc:
                trial.status = "error"
                trial.error = f"{type(exc).__name__}: {exc}"
                if experiment.stop_on_error:
                    stopped_early = True
            finally:
                trial.completed_at = utc_now()
                self.db.commit()

            if stopped_early:
                break

        if stopped_early:
            remaining = (
                self.db.query(ExperimentTrial)
                .filter(
                    ExperimentTrial.experiment_id == experiment.id,
                    ExperimentTrial.status == "planned",
                )
                .count()
            )
            if remaining:
                experiment.status = "failed"
                experiment.completed_at = utc_now()
            else:
                self._finalize_status(experiment)
        else:
            self._finalize_status(experiment)

        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def _finalize_status(self, experiment: Experiment) -> None:
        trials = (
            self.db.query(ExperimentTrial)
            .filter(ExperimentTrial.experiment_id == experiment.id)
            .all()
        )
        if not trials:
            experiment.status = "pending"
            return

        terminal = all(
            trial.status in self.TERMINAL_TRIAL_STATUSES for trial in trials
        )
        errors = any(trial.status == "error" for trial in trials)

        if terminal:
            experiment.status = "completed_with_errors" if errors else "completed"
            if experiment.completed_at is None:
                experiment.completed_at = utc_now()
        else:
            experiment.status = "running"

    @staticmethod
    def _aggregate_trials(trials: list[ExperimentTrial]) -> dict[str, Any]:
        planned = len(trials)
        benchmark_runs = [trial.benchmark_run for trial in trials if trial.benchmark_run]
        successful = [run for run in benchmark_runs if run.success is True]
        failed = [run for run in benchmark_runs if run.success is False]
        errors = [trial for trial in trials if trial.status == "error"]
        terminal_trials = sum(
            trial.status in ExperimentService.TERMINAL_TRIAL_STATUSES
            for trial in trials
        )

        durations = [
            float(run.duration_seconds)
            for run in benchmark_runs
            if run.duration_seconds is not None
        ]
        measured_tokens = [
            int(run.total_tokens)
            for run in benchmark_runs
            if run.total_tokens is not None
        ]
        files_changed = [int(run.files_changed or 0) for run in benchmark_runs]
        insertions = [int(run.insertions or 0) for run in benchmark_runs]
        deletions = [int(run.deletions or 0) for run in benchmark_runs]

        runtime_summary = numeric_summary(durations)
        token_summary = numeric_summary(measured_tokens)
        file_summary = numeric_summary(files_changed)
        insertion_summary = numeric_summary(insertions)
        deletion_summary = numeric_summary(deletions)

        success_rate = (len(successful) / planned) if planned else None
        benchmark_success_rate = (
            len(successful) / len(benchmark_runs) if benchmark_runs else None
        )

        return {
            "planned_runs": planned,
            "terminal_trials": terminal_trials,
            "completion_rate": (terminal_trials / planned) if planned else None,
            "benchmark_runs": len(benchmark_runs),
            "orchestration_errors": len(errors),
            "successful_runs": len(successful),
            "failed_runs": len(failed),
            "success_rate": success_rate,
            "benchmark_success_rate": benchmark_success_rate,
            "tests_passed": sum(int(run.test_passed or 0) for run in benchmark_runs),
            "tests_failed": sum(int(run.test_failed or 0) for run in benchmark_runs),
            "runtime_seconds": runtime_summary,
            "tokens": {
                **token_summary,
                "prompt_total": sum(
                    int(run.prompt_tokens or 0) for run in benchmark_runs
                ),
                "completion_total": sum(
                    int(run.completion_tokens or 0) for run in benchmark_runs
                ),
                "coverage_rate": (
                    len(measured_tokens) / len(benchmark_runs)
                    if benchmark_runs
                    else None
                ),
            },
            "changes": {
                "files_changed_total": sum(files_changed),
                "files_changed_average": file_summary["average"],
                "insertions_total": sum(insertions),
                "insertions_average": insertion_summary["average"],
                "deletions_total": sum(deletions),
                "deletions_average": deletion_summary["average"],
                "files_changed": file_summary,
                "insertions": insertion_summary,
                "deletions": deletion_summary,
            },
            "statistics": {
                "success_rate_confidence_interval_95": wilson_interval(
                    len(successful),
                    planned,
                ),
                "benchmark_success_rate_confidence_interval_95": wilson_interval(
                    len(successful),
                    len(benchmark_runs),
                ),
                "note": (
                    "Proportion intervals use Wilson score. Runtime/token/change "
                    "mean intervals use Student-t when at least two measurements "
                    "exist. These are descriptive uncertainty estimates, not "
                    "independence or significance claims."
                ),
            },
        }

    def aggregate_experiment(self, experiment_id: int) -> dict[str, Any]:
        experiment = self.get_experiment(experiment_id)
        trials = (
            self.db.query(ExperimentTrial)
            .filter(ExperimentTrial.experiment_id == experiment.id)
            .order_by(ExperimentTrial.ordinal.asc())
            .all()
        )

        by_agent: dict[int, list[ExperimentTrial]] = defaultdict(list)
        by_task: dict[int, list[ExperimentTrial]] = defaultdict(list)
        by_cell: dict[tuple[int, int], list[ExperimentTrial]] = defaultdict(list)
        for trial in trials:
            by_agent[trial.agent_config_id].append(trial)
            by_task[trial.task_id].append(trial)
            by_cell[(trial.task_id, trial.agent_config_id)].append(trial)

        agents = self._snapshots_by_id(list(experiment.agent_snapshots))
        tasks = self._snapshots_by_id(list(experiment.task_snapshots))

        by_agent_rows = [
            {
                "agent_config_id": agent_id,
                "agent_name": (
                    agents[agent_id]["name"]
                    if agent_id in agents
                    else f"agent-{agent_id}"
                ),
                "metrics": self._aggregate_trials(by_agent[agent_id]),
            }
            for agent_id in experiment.agent_config_ids
        ]
        by_task_rows = [
            {
                "task_id": task_id,
                "task_name": (
                    tasks[task_id]["name"]
                    if task_id in tasks
                    else f"task-{task_id}"
                ),
                "metrics": self._aggregate_trials(by_task[task_id]),
            }
            for task_id in experiment.task_ids
        ]
        by_cell_rows = [
            {
                "task_id": task_id,
                "task_name": (
                    tasks[task_id]["name"]
                    if task_id in tasks
                    else f"task-{task_id}"
                ),
                "agent_config_id": agent_id,
                "agent_name": (
                    agents[agent_id]["name"]
                    if agent_id in agents
                    else f"agent-{agent_id}"
                ),
                "metrics": self._aggregate_trials(by_cell[(task_id, agent_id)]),
            }
            for task_id in experiment.task_ids
            for agent_id in experiment.agent_config_ids
        ]

        return {
            "analysis_schema_version": 3,
            "experiment_id": experiment.id,
            "name": experiment.name,
            "status": experiment.status,
            "repetitions": experiment.repetitions,
            "overall": self._aggregate_trials(trials),
            "by_agent": by_agent_rows,
            "by_task": by_task_rows,
            "by_cell": by_cell_rows,
            "ranking": build_agent_ranking(by_agent_rows),
            "pairwise_task_comparison": build_pairwise_task_comparison(
                by_cell_rows,
                [int(agent_id) for agent_id in experiment.agent_config_ids],
            ),
        }

