"""Optional entry-point discovery for adapter providers."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from .provider import AgentAdapterProvider
from .registry import AdapterRegistry


ADAPTER_PROVIDER_ENTRYPOINT_GROUP = "agentbench.adapter_providers"


def _instantiate(candidate: Any) -> AgentAdapterProvider:
    if isinstance(candidate, type):
        candidate = candidate()
    elif callable(candidate) and not hasattr(candidate, "adapters"):
        candidate = candidate()
    if not isinstance(candidate, AgentAdapterProvider):
        raise TypeError(
            "entry point must resolve to an object implementing "
            "provider_id and adapters()"
        )
    return candidate


def discover_adapter_providers(registry: AdapterRegistry) -> list[str]:
    """Load optional providers while isolating third-party failures."""

    errors: list[str] = []
    try:
        entry_points = metadata.entry_points(group=ADAPTER_PROVIDER_ENTRYPOINT_GROUP)
    except TypeError:  # pragma: no cover - compatibility with older metadata API
        entry_points = metadata.entry_points().select(
            group=ADAPTER_PROVIDER_ENTRYPOINT_GROUP
        )

    for entry_point in sorted(entry_points, key=lambda item: item.name):
        try:
            registry.register_provider(_instantiate(entry_point.load()))
        except Exception as exc:  # third-party boundary
            errors.append(f"{entry_point.name}: {type(exc).__name__}: {exc}")

    registry.discovery_errors.extend(errors)
    return errors


__all__ = [
    "ADAPTER_PROVIDER_ENTRYPOINT_GROUP",
    "discover_adapter_providers",
]
