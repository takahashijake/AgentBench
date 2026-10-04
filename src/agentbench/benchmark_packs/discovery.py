"""Optional entry-point discovery for third-party benchmark packs."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from .provider import BenchmarkPackProvider, PackRegistry


PACK_PROVIDER_ENTRYPOINT_GROUP = "agentbench.pack_providers"


def _instantiate(candidate: Any) -> BenchmarkPackProvider:
    if isinstance(candidate, type):
        candidate = candidate()
    elif callable(candidate) and not hasattr(candidate, "packs"):
        candidate = candidate()
    if not isinstance(candidate, BenchmarkPackProvider):
        raise TypeError(
            "entry point must resolve to an object implementing "
            "provider_id and packs()"
        )
    return candidate


def discover_pack_providers(registry: PackRegistry) -> list[str]:
    """Load optional providers without making plugin failures fatal."""

    errors: list[str] = []
    try:
        entry_points = metadata.entry_points(group=PACK_PROVIDER_ENTRYPOINT_GROUP)
    except TypeError:  # pragma: no cover
        entry_points = metadata.entry_points().select(
            group=PACK_PROVIDER_ENTRYPOINT_GROUP
        )

    for entry_point in sorted(entry_points, key=lambda item: item.name):
        try:
            provider = _instantiate(entry_point.load())
            registry.register(provider)
        except Exception as exc:
            errors.append(f"{entry_point.name}: {type(exc).__name__}: {exc}")

    registry.discovery_errors.extend(errors)
    return errors


__all__ = ["PACK_PROVIDER_ENTRYPOINT_GROUP", "discover_pack_providers"]
