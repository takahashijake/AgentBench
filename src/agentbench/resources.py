"""Host capability contracts for resource-aware benchmark execution.

Resource requirements are declarative benchmark metadata. They are evaluated
before a trial starts so an incompatible host produces an explicit skipped trial
rather than an opaque subprocess failure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import platform
import shutil
from typing import Any, Mapping


@dataclass(frozen=True)
class TaskRequirements:
    """Minimum host capabilities required to execute one benchmark task."""

    min_cpu_count: int = 1
    min_memory_mb: int | None = None
    supported_platforms: tuple[str, ...] = ()
    required_commands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.min_cpu_count < 1:
            raise ValueError("min_cpu_count must be greater than 0")
        if self.min_memory_mb is not None and self.min_memory_mb < 1:
            raise ValueError("min_memory_mb must be greater than 0 when provided")
        normalized_platforms = tuple(
            platform_name.strip().lower() for platform_name in self.supported_platforms
        )
        normalized_commands = tuple(
            command.strip() for command in self.required_commands
        )
        if any(not value for value in normalized_platforms):
            raise ValueError("supported_platforms must not contain empty values")
        if any(not value for value in normalized_commands):
            raise ValueError("required_commands must not contain empty values")
        if len(normalized_platforms) != len(set(normalized_platforms)):
            raise ValueError("supported_platforms must not contain duplicates")
        if len(normalized_commands) != len(set(normalized_commands)):
            raise ValueError("required_commands must not contain duplicates")
        object.__setattr__(self, "supported_platforms", normalized_platforms)
        object.__setattr__(self, "required_commands", normalized_commands)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "TaskRequirements":
        if not value:
            return cls()
        return cls(
            min_cpu_count=int(value.get("min_cpu_count", 1)),
            min_memory_mb=(
                int(value["min_memory_mb"])
                if value.get("min_memory_mb") is not None
                else None
            ),
            supported_platforms=tuple(value.get("supported_platforms") or ()),
            required_commands=tuple(value.get("required_commands") or ()),
        )


@dataclass(frozen=True)
class ResourceEligibility:
    eligible: bool
    reasons: tuple[str, ...]
    observed: dict[str, Any]


def _memory_mb() -> int | None:
    """Return physical memory in MiB when the platform exposes it safely."""

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    if not isinstance(page_size, int) or not isinstance(page_count, int):
        return None
    if page_size <= 0 or page_count <= 0:
        return None
    return int((page_size * page_count) / (1024 * 1024))


class HostResourceInspector:
    """Evaluate declarative requirements against the current local host."""

    def evaluate(self, requirements: TaskRequirements) -> ResourceEligibility:
        system = platform.system().lower()
        cpu_count = os.cpu_count() or 1
        memory_mb = _memory_mb()
        command_paths = {
            command: shutil.which(command) for command in requirements.required_commands
        }

        reasons: list[str] = []
        if (
            requirements.supported_platforms
            and system not in requirements.supported_platforms
        ):
            reasons.append(
                "platform "
                f"{system!r} is not in supported_platforms="
                f"{list(requirements.supported_platforms)!r}"
            )
        if cpu_count < requirements.min_cpu_count:
            reasons.append(
                f"cpu_count={cpu_count} is below min_cpu_count="
                f"{requirements.min_cpu_count}"
            )
        if requirements.min_memory_mb is not None:
            if memory_mb is None:
                reasons.append(
                    "physical memory could not be detected for a task that "
                    "declares min_memory_mb"
                )
            elif memory_mb < requirements.min_memory_mb:
                reasons.append(
                    f"memory_mb={memory_mb} is below min_memory_mb="
                    f"{requirements.min_memory_mb}"
                )
        missing_commands = [
            command for command, path in command_paths.items() if path is None
        ]
        if missing_commands:
            reasons.append(f"required commands are unavailable: {missing_commands}")

        return ResourceEligibility(
            eligible=not reasons,
            reasons=tuple(reasons),
            observed={
                "platform": system,
                "cpu_count": cpu_count,
                "memory_mb": memory_mb,
                "commands": command_paths,
            },
        )


__all__ = [
    "HostResourceInspector",
    "ResourceEligibility",
    "TaskRequirements",
]
