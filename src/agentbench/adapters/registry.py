"""Collision-safe adapter registry and factory composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import shlex
from typing import Any, Protocol

from .base import AgentAdapter
from .builtin import BuiltinAdapterProvider
from .provider import (
    AdapterCapabilities,
    AdapterFactory,
    AdapterNotFoundError,
    AdapterProfile,
    AdapterProviderError,
    AgentAdapterProvider,
    DuplicateAdapterError,
    ResolvedAdapter,
)


class AgentAdapterFactory(Protocol):
    """Minimal factory contract consumed by BenchmarkService."""

    def create(self, config: Mapping[str, Any]) -> AgentAdapter:
        ...


def executable_key(command_template: str) -> str:
    """Return the normalized executable basename without expanding the prompt."""

    try:
        tokens = shlex.split(command_template)
    except ValueError as exc:
        raise ValueError(f"Invalid agent command template: {exc}") from exc
    if not tokens:
        raise ValueError("Agent command template is empty")
    executable = tokens[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    return executable[:-4] if executable.endswith(".exe") else executable


def _factory_identity(factory: AdapterFactory) -> str:
    module = getattr(factory, "__module__", None)
    qualname = getattr(factory, "__qualname__", None)
    if module and qualname:
        return f"{module}.{qualname}"
    return type(factory).__name__


@dataclass
class AdapterRegistry:
    """Resolve adapter profiles while keeping provider discovery out of services."""

    _adapters: dict[str, ResolvedAdapter] = field(default_factory=dict)
    _providers: dict[str, AgentAdapterProvider] = field(default_factory=dict)
    _manual_ids: set[str] = field(default_factory=set)
    discovery_errors: list[str] = field(default_factory=list)

    def register(self, name: str, factory: AdapterFactory) -> None:
        """Backward-compatible explicit registration for application/test code."""

        key = name.strip().lower()
        if not key:
            raise ValueError("Adapter name must not be empty")
        if key in self._adapters:
            raise DuplicateAdapterError(f"Adapter already registered: {key}")

        profile = AdapterProfile(
            id=key,
            family=key,
            description=f"Explicitly registered adapter: {key}",
            implementation=_factory_identity(factory),
            factory=factory,
            capabilities=AdapterCapabilities(execution_protocol="custom"),
        )
        self._adapters[key] = ResolvedAdapter(
            provider_id="agentbench.manual",
            profile=profile,
        )
        self._manual_ids.add(key)

    def register_provider(self, provider: AgentAdapterProvider) -> None:
        provider_id = str(provider.provider_id).strip()
        if not provider_id:
            raise AdapterProviderError("Adapter provider_id must not be empty")
        if provider_id in self._providers:
            raise AdapterProviderError(
                f"Adapter provider already registered: {provider_id}"
            )

        profiles = tuple(provider.adapters())
        local_ids = [profile.id.lower() for profile in profiles]
        if len(local_ids) != len(set(local_ids)):
            raise DuplicateAdapterError(
                f"Provider {provider_id!r} returned duplicate adapter IDs"
            )

        collisions = sorted(
            adapter_id for adapter_id in local_ids if adapter_id in self._adapters
        )
        if collisions:
            owners = {
                adapter_id: self._adapters[adapter_id].provider_id
                for adapter_id in collisions
            }
            raise DuplicateAdapterError(
                f"Adapter IDs already registered: {owners}; provider={provider_id!r}"
            )

        self._providers[provider_id] = provider
        for profile in profiles:
            key = profile.id.lower()
            self._adapters[key] = ResolvedAdapter(
                provider_id=provider_id,
                profile=profile,
            )

    def get(self, adapter_id: str) -> ResolvedAdapter:
        key = adapter_id.strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._adapters)) or "<none>"
            raise AdapterNotFoundError(
                f"Unknown adapter {adapter_id!r}; available: {available}"
            ) from exc

    def create(self, config: Mapping[str, Any]) -> AgentAdapter:
        normalized = dict(config)
        explicit = str(normalized.get("adapter") or "").strip().lower()
        executable = executable_key(str(normalized.get("command_template") or ""))
        key = explicit or executable
        if key not in self._adapters:
            key = "shell"

        resolved = self.get(key)
        profile = resolved.profile
        normalized["adapter"] = profile.id
        normalized.setdefault("agent_family", profile.family)
        normalized["adapter_provider"] = resolved.provider_id
        normalized["adapter_implementation"] = profile.implementation
        normalized["adapter_capabilities"] = profile.capabilities.as_dict()
        return profile.factory(normalized)

    def catalog(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for adapter_id in sorted(self._adapters):
            resolved = self._adapters[adapter_id]
            profile = resolved.profile
            rows.append(
                {
                    "id": profile.id,
                    "family": profile.family,
                    "provider": resolved.provider_id,
                    "description": profile.description,
                    "implementation": profile.implementation,
                    "capabilities": profile.capabilities.as_dict(),
                }
            )
        return rows

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    @property
    def provider_ids(self) -> tuple[str, ...]:
        provider_ids = set(self._providers)
        if self._manual_ids:
            provider_ids.add("agentbench.manual")
        return tuple(sorted(provider_ids))


def create_adapter_registry(*, discover_plugins: bool = True) -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register_provider(BuiltinAdapterProvider())
    if discover_plugins:
        # Local import prevents discovery -> registry from becoming an import cycle.
        from .discovery import discover_adapter_providers

        discover_adapter_providers(registry)
    return registry


def create_default_adapter_registry() -> AdapterRegistry:
    """Compatibility alias for the normal provider-aware registry."""

    return create_adapter_registry(discover_plugins=True)


__all__ = [
    "AdapterFactory",
    "AdapterRegistry",
    "AgentAdapterFactory",
    "create_adapter_registry",
    "create_default_adapter_registry",
    "executable_key",
]
