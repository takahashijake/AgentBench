"""Compatibility facade for benchmark-pack discovery and materialization.

V3 moves corpus definitions, provider discovery, and filesystem materialization
behind explicit interfaces in agentbench.benchmark_packs. Existing imports from
agentbench.packs remain supported.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .resources import HostResourceInspector

from .benchmark_packs import (
    BenchmarkPack,
    BuiltinPackProvider,
    CORE_V2,
    CORE_V3,
    CORE_V4,
    PackMaterializer,
    PackRegistry,
    PackTaskSpec,
    SMOKE_V2,
    discover_pack_providers,
    parse_agent_spec,
)


def create_pack_registry(*, discover_plugins: bool = True) -> PackRegistry:
    registry = PackRegistry()
    registry.register(BuiltinPackProvider())
    if discover_plugins:
        discover_pack_providers(registry)
    return registry


@lru_cache(maxsize=1)
def default_pack_registry() -> PackRegistry:
    return create_pack_registry(discover_plugins=True)


def list_packs(registry: PackRegistry | None = None) -> list[dict[str, object]]:
    return (registry or default_pack_registry()).catalog()


def get_pack(pack_id: str, registry: PackRegistry | None = None) -> BenchmarkPack:
    return (registry or default_pack_registry()).get(pack_id).pack


def preflight_pack(
    pack_id: str,
    *,
    registry: PackRegistry | None = None,
    inspector: HostResourceInspector | None = None,
) -> dict[str, Any]:
    """Evaluate whether the current host can execute every task in a pack."""

    active_registry = registry or default_pack_registry()
    resolved = active_registry.get(pack_id)
    active_inspector = inspector or HostResourceInspector()
    tasks: list[dict[str, Any]] = []
    eligible_count = 0

    for task in resolved.pack.tasks:
        evaluation = active_inspector.evaluate(task.requirements)
        if evaluation.eligible:
            eligible_count += 1
        tasks.append(
            {
                "id": task.id,
                "eligible": evaluation.eligible,
                "requirements": task.requirements.as_dict(),
                "reasons": list(evaluation.reasons),
                "observed": evaluation.observed,
            }
        )

    return {
        "pack_id": resolved.pack.id,
        "pack_version": resolved.pack.version,
        "provider_id": resolved.provider_id,
        "eligible": eligible_count == len(tasks),
        "eligible_task_count": eligible_count,
        "ineligible_task_count": len(tasks) - eligible_count,
        "task_count": len(tasks),
        "tasks": tasks,
    }


def materialize_pack(
    pack_id: str,
    output_dir: str | Path,
    *,
    agents: Iterable[dict[str, str]],
    repetitions: int = 5,
    max_workers: int = 1,
    budget: dict[str, int] | None = None,
    registry: PackRegistry | None = None,
) -> dict[str, Any]:
    result = PackMaterializer(registry or default_pack_registry()).materialize(
        pack_id,
        output_dir,
        agents=agents,
        repetitions=repetitions,
        max_workers=max_workers,
        budget=budget,
    )
    return result.as_dict()


__all__ = [
    "BenchmarkPack",
    "BuiltinPackProvider",
    "CORE_V2",
    "CORE_V3",
    "CORE_V4",
    "PackRegistry",
    "PackTaskSpec",
    "SMOKE_V2",
    "create_pack_registry",
    "default_pack_registry",
    "get_pack",
    "list_packs",
    "materialize_pack",
    "parse_agent_spec",
    "preflight_pack",
]
