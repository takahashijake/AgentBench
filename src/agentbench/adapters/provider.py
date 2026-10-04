"""Typed adapter provider contracts.

Adapter providers describe available implementations and capabilities. They do not
own benchmark orchestration, persistence, or workspace lifecycle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any, Protocol, runtime_checkable

from .base import AgentAdapter


_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
AdapterFactory = Callable[[dict[str, Any]], AgentAdapter]


class AdapterProviderError(ValueError):
    """Base error for adapter-provider registration failures."""


class AdapterNotFoundError(AdapterProviderError):
    """Raised when an adapter profile cannot be resolved."""


class DuplicateAdapterError(AdapterProviderError):
    """Raised when two providers claim the same stable adapter ID."""


@dataclass(frozen=True)
class AdapterCapabilities:
    """Small, explicit capability surface used for discovery and QA."""

    execution_protocol: str = "shell"
    native_protocol: bool = False
    structured_usage: bool = False
    cost_reporting: bool = False
    model_reporting: bool = False

    def __post_init__(self) -> None:
        if not self.execution_protocol.strip():
            raise ValueError("execution_protocol must not be empty")

    def as_dict(self) -> dict[str, object]:
        return {
            "execution_protocol": self.execution_protocol,
            "native_protocol": self.native_protocol,
            "structured_usage": self.structured_usage,
            "cost_reporting": self.cost_reporting,
            "model_reporting": self.model_reporting,
        }


@dataclass(frozen=True)
class AdapterProfile:
    """Provider-owned adapter descriptor and factory."""

    id: str
    family: str
    description: str
    implementation: str
    factory: AdapterFactory
    capabilities: AdapterCapabilities = AdapterCapabilities()

    def __post_init__(self) -> None:
        if not _RESOURCE_ID_RE.fullmatch(self.id):
            raise ValueError(f"Invalid adapter ID: {self.id!r}")
        if not self.family.strip():
            raise ValueError(f"Adapter {self.id!r} must define a family")
        if not self.description.strip():
            raise ValueError(f"Adapter {self.id!r} must define a description")
        if not self.implementation.strip():
            raise ValueError(f"Adapter {self.id!r} must define an implementation")


@runtime_checkable
class AgentAdapterProvider(Protocol):
    """Structural SPI implemented by built-in and third-party adapter providers."""

    @property
    def provider_id(self) -> str:
        ...

    def adapters(self) -> tuple[AdapterProfile, ...]:
        ...


@dataclass(frozen=True)
class ResolvedAdapter:
    provider_id: str
    profile: AdapterProfile


__all__ = [
    "AdapterCapabilities",
    "AdapterFactory",
    "AdapterNotFoundError",
    "AdapterProfile",
    "AdapterProviderError",
    "AgentAdapterProvider",
    "DuplicateAdapterError",
    "ResolvedAdapter",
]
