"""Filesystem materialization for provider-defined benchmark packs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

import yaml

from .models import PackTaskSpec
from .provider import PackRegistry


_PACK_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "AgentBench Fixtures",
    "GIT_AUTHOR_EMAIL": "fixtures@agentbench.local",
    "GIT_COMMITTER_NAME": "AgentBench Fixtures",
    "GIT_COMMITTER_EMAIL": "fixtures@agentbench.local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class PackMaterializationResult:
    pack_id: str
    pack_version: str
    provider_id: str
    output_directory: str
    manifest_path: str
    task_count: int
    agent_count: int
    repetitions: int
    max_workers: int
    planned_runs: int
    commits: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "provider_id": self.provider_id,
            "output_directory": self.output_directory,
            "manifest_path": self.manifest_path,
            "task_count": self.task_count,
            "agent_count": self.agent_count,
            "repetitions": self.repetitions,
            "max_workers": self.max_workers,
            "planned_runs": self.planned_runs,
            "commits": dict(self.commits),
        }


def parse_agent_spec(value: str) -> dict[str, str]:
    if "=" not in value:
        raise ValueError("Agent must use '<id>=<command template>' syntax")
    agent_id, command = value.split("=", 1)
    agent_id = agent_id.strip()
    command = command.strip()
    if not _RESOURCE_ID_RE.fullmatch(agent_id):
        raise ValueError(f"Invalid agent ID: {agent_id!r}")
    if not command:
        raise ValueError("Agent command template must not be empty")
    if "{prompt}" not in command:
        raise ValueError("Agent command template must contain {prompt}")
    return {
        "id": agent_id,
        "description": f"Agent supplied when materializing benchmark pack: {agent_id}",
        "command_template": command,
    }


def _run_git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"Git command failed ({' '.join(args)}): {detail}")
    return result.stdout.strip()


def _materialize_repository(root: Path, task: PackTaskSpec) -> str:
    root.mkdir(parents=True, exist_ok=False)
    _run_git(root, "init", "-q")
    _run_git(root, "config", "core.autocrlf", "false")
    _run_git(root, "config", "core.filemode", "false")

    for relative_path, contents in sorted(task.files.items()):
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8", newline="\n")

    _run_git(root, "add", "-A")
    _run_git(
        root,
        "commit",
        "-q",
        "-m",
        f"AgentBench {task.id} fixture",
        env=_PACK_COMMIT_ENV,
    )
    return _run_git(root, "rev-parse", "HEAD").lower()


class PackMaterializer:
    """Materialize immutable provider definitions into runnable Git fixtures."""

    def __init__(self, registry: PackRegistry):
        self.registry = registry

    def materialize(
        self,
        pack_id: str,
        output_dir: str | Path,
        *,
        agents: Iterable[dict[str, str]],
        repetitions: int = 5,
        max_workers: int = 1,
    ) -> PackMaterializationResult:
        resolved = self.registry.get(pack_id)
        pack = resolved.pack
        destination = Path(output_dir).expanduser().resolve()
        if destination.exists() and any(destination.iterdir()):
            raise ValueError(f"Output directory is not empty: {destination}")
        destination.mkdir(parents=True, exist_ok=True)

        normalized_agents = list(agents)
        if not normalized_agents:
            raise ValueError(
                "At least one agent is required to materialize a benchmark pack"
            )
        ids = [agent["id"] for agent in normalized_agents]
        if len(ids) != len(set(ids)):
            raise ValueError("Agent IDs must be unique")
        if repetitions < 1 or repetitions > 100:
            raise ValueError("repetitions must be between 1 and 100")
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers must be between 1 and 32")

        repo_root = destination / "repositories"
        repo_root.mkdir()
        tasks: list[dict[str, Any]] = []
        commits: dict[str, str] = {}

        for task in pack.tasks:
            repository = repo_root / task.id
            commit = _materialize_repository(repository, task)
            commits[task.id] = commit
            tasks.append(
                {
                    "id": task.id,
                    "description": task.description,
                    "repository_path": f"repositories/{task.id}",
                    "base_commit": commit,
                    "agent_prompt": task.prompt,
                    "setup_command": task.setup_command,
                    "test_command": task.test_command,
                    "timeout": task.timeout,
                    "category": task.category,
                    "difficulty": task.difficulty,
                    "tags": list(task.tags),
                    "requirements": task.requirements.as_dict(),
                }
            )

        manifest = {
            "schema_version": 6,
            "id": f"agentbench-{pack.id}",
            "name": pack.name,
            "description": pack.description,
            "benchmark_pack": {
                "id": pack.id,
                "version": pack.version,
                "provider": resolved.provider_id,
                "description": pack.description,
            },
            "agents": normalized_agents,
            "tasks": tasks,
            "experiment": {
                "tasks": [task.id for task in pack.tasks],
                "agents": ids,
                "repetitions": repetitions,
                "stop_on_error": False,
                "max_workers": max_workers,
            },
        }
        manifest_path = destination / "suite.yaml"
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
            newline="\n",
        )

        return PackMaterializationResult(
            pack_id=pack.id,
            pack_version=pack.version,
            provider_id=resolved.provider_id,
            output_directory=str(destination),
            manifest_path=str(manifest_path),
            task_count=len(pack.tasks),
            agent_count=len(normalized_agents),
            repetitions=repetitions,
            max_workers=max_workers,
            planned_runs=len(pack.tasks) * len(normalized_agents) * repetitions,
            commits=commits,
        )


__all__ = [
    "PackMaterializationResult",
    "PackMaterializer",
    "parse_agent_spec",
]
