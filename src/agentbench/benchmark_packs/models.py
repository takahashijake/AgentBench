"""Immutable domain models for benchmark packs.

Providers describe benchmark content. They do not perform filesystem I/O or
execute benchmarks; materialization is owned by PackMaterializer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class PackTaskSpec:
    id: str
    description: str
    category: str
    difficulty: str
    tags: tuple[str, ...]
    prompt: str
    files: dict[str, str]
    test_command: str = "python -m unittest -q"
    timeout: int = 600
    setup_command: str | None = None

    def __post_init__(self) -> None:
        if not _RESOURCE_ID_RE.fullmatch(self.id):
            raise ValueError(f"Invalid benchmark task ID: {self.id!r}")
        if not self.description.strip():
            raise ValueError(f"Task {self.id!r} must have a description")
        if not self.prompt.strip():
            raise ValueError(f"Task {self.id!r} must have a prompt")
        if not self.files:
            raise ValueError(f"Task {self.id!r} must define at least one file")
        if self.timeout < 1 or self.timeout > 3600:
            raise ValueError(f"Task {self.id!r} timeout must be between 1 and 3600")
        for path in self.files:
            if not path or path.startswith("/") or ".." in path.split("/"):
                raise ValueError(
                    f"Task {self.id!r} contains unsafe relative file path: {path!r}"
                )


@dataclass(frozen=True)
class BenchmarkPack:
    id: str
    version: str
    name: str
    description: str
    tasks: tuple[PackTaskSpec, ...]

    def __post_init__(self) -> None:
        if not _RESOURCE_ID_RE.fullmatch(self.id):
            raise ValueError(f"Invalid benchmark pack ID: {self.id!r}")
        if not self.version.strip():
            raise ValueError(f"Pack {self.id!r} must have a version")
        if not self.name.strip():
            raise ValueError(f"Pack {self.id!r} must have a name")
        if not self.tasks:
            raise ValueError(f"Pack {self.id!r} must contain at least one task")
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError(f"Pack {self.id!r} contains duplicate task IDs")


__all__ = ["BenchmarkPack", "PackTaskSpec"]
