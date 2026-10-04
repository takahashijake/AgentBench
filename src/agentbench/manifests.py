"""Versioned benchmark-suite manifest loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml


_RESOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
_RESOURCE_ID_RE = re.compile(_RESOURCE_ID_PATTERN)


class ManifestAgent(BaseModel):
    """One coding-agent definition in a suite manifest."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID_PATTERN)
    description: Optional[str] = None
    command_template: str = Field(..., min_length=1)
    enabled: bool = True


class ManifestBenchmarkPack(BaseModel):
    """Optional provenance for a curated benchmark corpus."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID_PATTERN)
    version: str = Field(..., min_length=1, max_length=64)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class ManifestTask(BaseModel):
    """One benchmark task definition in a suite manifest."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID_PATTERN)
    description: str = Field(..., min_length=1)
    repository_path: str = Field(..., min_length=1)
    base_commit: str = Field(
        ...,
        min_length=40,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{40,64}$",
    )
    agent_prompt: str = Field(..., min_length=1)
    setup_command: Optional[str] = None
    test_command: str = Field(default="pytest")
    timeout: int = Field(default=300, ge=1, le=3600)
    enabled: bool = True
    category: Optional[str] = Field(default=None, min_length=1, max_length=64)
    difficulty: Optional[str] = Field(default=None, min_length=1, max_length=64)
    tags: list[str] = Field(default_factory=list)


class ManifestExperiment(BaseModel):
    """Experiment dimensions selected from the manifest resources."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    tasks: Optional[list[str]] = Field(default=None, min_length=1)
    agents: Optional[list[str]] = Field(default=None, min_length=1)
    repetitions: int = Field(default=1, ge=1, le=100)
    stop_on_error: bool = False


class SuiteManifest(BaseModel):
    """Top-level versioned suite manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1)
    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID_PATTERN)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    benchmark_pack: Optional[ManifestBenchmarkPack] = None
    agents: list[ManifestAgent] = Field(..., min_length=1)
    tasks: list[ManifestTask] = Field(..., min_length=1)
    experiment: ManifestExperiment = Field(default_factory=ManifestExperiment)

    @model_validator(mode="after")
    def validate_manifest(self) -> "SuiteManifest":
        if self.schema_version not in {1, 2, 3}:
            raise ValueError(
                f"Unsupported suite manifest schema_version: {self.schema_version}"
            )

        agent_ids = [agent.id for agent in self.agents]
        task_ids = [task.id for task in self.tasks]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("Agent IDs must be unique within a suite manifest")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique within a suite manifest")

        selected_agents = self.experiment.agents or [
            agent.id for agent in self.agents if agent.enabled
        ]
        selected_tasks = self.experiment.tasks or [
            task.id for task in self.tasks if task.enabled
        ]

        if not selected_agents:
            raise ValueError("Experiment must select at least one enabled agent")
        if not selected_tasks:
            raise ValueError("Experiment must select at least one enabled task")

        unknown_agents = [item for item in selected_agents if item not in set(agent_ids)]
        unknown_tasks = [item for item in selected_tasks if item not in set(task_ids)]
        if unknown_agents:
            raise ValueError(f"Experiment references unknown agent IDs: {unknown_agents}")
        if unknown_tasks:
            raise ValueError(f"Experiment references unknown task IDs: {unknown_tasks}")

        if len(selected_agents) != len(set(selected_agents)):
            raise ValueError("Experiment agent references must not contain duplicates")
        if len(selected_tasks) != len(set(selected_tasks)):
            raise ValueError("Experiment task references must not contain duplicates")

        agents_by_id = {agent.id: agent for agent in self.agents}
        tasks_by_id = {task.id: task for task in self.tasks}
        disabled_agents = [
            item for item in selected_agents if not agents_by_id[item].enabled
        ]
        disabled_tasks = [
            item for item in selected_tasks if not tasks_by_id[item].enabled
        ]
        if disabled_agents:
            raise ValueError(
                f"Experiment references disabled agent IDs: {disabled_agents}"
            )
        if disabled_tasks:
            raise ValueError(
                f"Experiment references disabled task IDs: {disabled_tasks}"
            )

        planned_runs = (
            len(selected_agents) * len(selected_tasks) * self.experiment.repetitions
        )
        if planned_runs > 10_000:
            raise ValueError(
                f"Experiment plans {planned_runs} runs; maximum is 10000"
            )
        return self

    def selected_agent_ids(self) -> list[str]:
        return list(
            self.experiment.agents
            or [agent.id for agent in self.agents if agent.enabled]
        )

    def selected_task_ids(self) -> list[str]:
        return list(
            self.experiment.tasks
            or [task.id for task in self.tasks if task.enabled]
        )


@dataclass(frozen=True)
class LoadedSuiteManifest:
    """A parsed manifest plus source path and canonical digest."""

    path: Path
    manifest: SuiteManifest
    sha256: str

    def resolve_repository_path(self, task: ManifestTask) -> Path:
        path = Path(task.repository_path).expanduser()
        if not path.is_absolute():
            path = self.path.parent / path
        return path.resolve()


def _canonical_manifest_bytes(manifest: SuiteManifest) -> bytes:
    payload = manifest.model_dump(mode="json")
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_suite_manifest(path: str | Path) -> LoadedSuiteManifest:
    """Load YAML/JSON, validate it, and compute a deterministic content digest."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Suite manifest does not exist: {source}")

    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML/JSON suite manifest: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Suite manifest root must be a mapping/object")

    manifest = SuiteManifest.model_validate(raw)
    digest = sha256(_canonical_manifest_bytes(manifest)).hexdigest()
    return LoadedSuiteManifest(path=source, manifest=manifest, sha256=digest)


__all__ = [
    "LoadedSuiteManifest",
    "ManifestAgent",
    "ManifestBenchmarkPack",
    "ManifestExperiment",
    "ManifestTask",
    "SuiteManifest",
    "load_suite_manifest",
]
