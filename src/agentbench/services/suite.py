"""Suite manifest import, planning, execution, and report composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..manifests import LoadedSuiteManifest
from ..models.database import AgentConfig, BenchmarkTask, Experiment
from .experiment import ExperimentService


@dataclass(frozen=True)
class SuiteImportResult:
    """Stable database bindings produced by a suite import."""

    suite_id: str
    manifest_sha256: str
    task_ids: dict[str, int]
    agent_config_ids: dict[str, int]
    selected_task_ids: list[int]
    selected_agent_config_ids: list[int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "manifest_sha256": self.manifest_sha256,
            "task_ids": dict(self.task_ids),
            "agent_config_ids": dict(self.agent_config_ids),
            "selected_task_ids": list(self.selected_task_ids),
            "selected_agent_config_ids": list(self.selected_agent_config_ids),
        }


class SuiteService:
    """Translate versioned suite files into existing AgentBench services."""

    def __init__(
        self,
        db: Session,
        artifact_root: Optional[Path] = None,
        setup_timeout: int = 300,
        test_timeout: Optional[int] = None,
    ):
        self.db = db
        self.experiments = ExperimentService(
            db,
            artifact_root=artifact_root,
            setup_timeout=setup_timeout,
            test_timeout=test_timeout,
        )

    @staticmethod
    def stable_resource_name(suite_id: str, resource_id: str) -> str:
        """Return the stable persisted identity used for repeated imports."""

        value = f"{suite_id}/{resource_id}"
        if len(value) > 255:
            raise ValueError(
                "Qualified suite resource ID exceeds 255 characters: "
                f"{suite_id}/{resource_id}"
            )
        return value

    def _upsert_agent(
        self,
        loaded: LoadedSuiteManifest,
        resource_id: str,
    ) -> AgentConfig:
        definition = next(
            item for item in loaded.manifest.agents if item.id == resource_id
        )
        stable_name = self.stable_resource_name(loaded.manifest.id, definition.id)
        row = (
            self.db.query(AgentConfig)
            .filter(AgentConfig.name == stable_name)
            .one_or_none()
        )
        if row is None:
            row = AgentConfig(name=stable_name)
            self.db.add(row)

        row.description = definition.description
        row.command_template = definition.command_template
        row.enabled = definition.enabled
        self.db.flush()
        return row

    def _upsert_task(
        self,
        loaded: LoadedSuiteManifest,
        resource_id: str,
    ) -> BenchmarkTask:
        definition = next(
            item for item in loaded.manifest.tasks if item.id == resource_id
        )
        stable_name = self.stable_resource_name(loaded.manifest.id, definition.id)
        matches = (
            self.db.query(BenchmarkTask)
            .filter(BenchmarkTask.name == stable_name)
            .all()
        )
        if len(matches) > 1:
            raise ValueError(
                "Multiple benchmark tasks use the stable suite resource name "
                f"{stable_name!r}; refusing an ambiguous import"
            )
        if matches:
            row = matches[0]
        else:
            row = BenchmarkTask(
                name=stable_name,
                description=definition.description,
                repository_path="",
                base_commit=definition.base_commit,
                agent_prompt=definition.agent_prompt,
                test_command=definition.test_command,
            )
            self.db.add(row)

        row.description = definition.description
        row.repository_path = str(loaded.resolve_repository_path(definition))
        row.base_commit = definition.base_commit.lower()
        row.agent_prompt = definition.agent_prompt
        row.setup_command = definition.setup_command
        row.test_command = definition.test_command
        row.timeout = definition.timeout
        row.enabled = definition.enabled
        row.agent_config_id = None
        self.db.flush()
        return row

    def import_suite(self, loaded: LoadedSuiteManifest) -> SuiteImportResult:
        """Idempotently upsert manifest resources and return stable bindings."""

        agent_ids: dict[str, int] = {}
        task_ids: dict[str, int] = {}
        try:
            for definition in loaded.manifest.agents:
                row = self._upsert_agent(loaded, definition.id)
                agent_ids[definition.id] = int(row.id)

            for definition in loaded.manifest.tasks:
                row = self._upsert_task(loaded, definition.id)
                task_ids[definition.id] = int(row.id)

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        selected_agent_ids = [
            agent_ids[resource_id]
            for resource_id in loaded.manifest.selected_agent_ids()
        ]
        selected_task_ids = [
            task_ids[resource_id]
            for resource_id in loaded.manifest.selected_task_ids()
        ]
        return SuiteImportResult(
            suite_id=loaded.manifest.id,
            manifest_sha256=loaded.sha256,
            task_ids=task_ids,
            agent_config_ids=agent_ids,
            selected_task_ids=selected_task_ids,
            selected_agent_config_ids=selected_agent_ids,
        )

    def create_experiment(
        self,
        loaded: LoadedSuiteManifest,
        imported: Optional[SuiteImportResult] = None,
    ) -> Experiment:
        """Create a deterministic matrix using manifest order and selections."""

        bindings = imported or self.import_suite(loaded)
        definition = loaded.manifest.experiment
        experiment_name = (
            definition.name
            or loaded.manifest.name
            or loaded.manifest.id
        )
        experiment_description = (
            definition.description
            if definition.description is not None
            else loaded.manifest.description
        )
        return self.experiments.create_experiment(
            name=experiment_name,
            description=experiment_description,
            task_ids=bindings.selected_task_ids,
            agent_config_ids=bindings.selected_agent_config_ids,
            repetitions=definition.repetitions,
            stop_on_error=definition.stop_on_error,
        )

    def execute_suite(
        self,
        loaded: LoadedSuiteManifest,
    ) -> tuple[SuiteImportResult, Experiment, dict[str, Any]]:
        """Import, plan, execute, and aggregate a complete suite."""

        imported = self.import_suite(loaded)
        experiment = self.create_experiment(loaded, imported)
        experiment = self.experiments.execute_experiment(experiment.id)
        summary = self.experiments.aggregate_experiment(experiment.id)
        return imported, experiment, summary

    def build_report(
        self,
        loaded: LoadedSuiteManifest,
        imported: SuiteImportResult,
        experiment: Experiment,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the stable machine-readable suite result envelope."""

        tasks_by_id = {item.id: item for item in loaded.manifest.tasks}
        agents_by_id = {item.id: item for item in loaded.manifest.agents}
        return {
            "report_schema_version": 3,
            "suite": {
                "id": loaded.manifest.id,
                "name": loaded.manifest.name,
                "description": loaded.manifest.description,
                "manifest_path": str(loaded.path),
                "manifest_sha256": loaded.sha256,
                "schema_version": loaded.manifest.schema_version,
                "benchmark_pack": (
                    loaded.manifest.benchmark_pack.model_dump(mode="json")
                    if loaded.manifest.benchmark_pack is not None
                    else None
                ),
            },
            "experiment": {
                "id": int(experiment.id),
                "name": experiment.name,
                "status": experiment.status,
                "repetitions": experiment.repetitions,
                "stop_on_error": experiment.stop_on_error,
                "planned_runs": experiment.planned_runs,
            },
            "resources": {
                "tasks": [
                    {
                        "id": resource_id,
                        "database_id": imported.task_ids[resource_id],
                        "description": tasks_by_id[resource_id].description,
                        "repository_path": str(
                            loaded.resolve_repository_path(tasks_by_id[resource_id])
                        ),
                        "base_commit": tasks_by_id[resource_id].base_commit.lower(),
                        "category": tasks_by_id[resource_id].category,
                        "difficulty": tasks_by_id[resource_id].difficulty,
                        "tags": list(tasks_by_id[resource_id].tags),
                    }
                    for resource_id in loaded.manifest.selected_task_ids()
                ],
                "agents": [
                    {
                        "id": resource_id,
                        "database_id": imported.agent_config_ids[resource_id],
                        "description": agents_by_id[resource_id].description,
                        "adapter_family": (
                            agents_by_id[resource_id].command_template.split()[0]
                            if agents_by_id[resource_id].command_template
                            else None
                        ),
                    }
                    for resource_id in loaded.manifest.selected_agent_ids()
                ],
            },
            "summary": summary,
        }


__all__ = ["SuiteImportResult", "SuiteService"]
