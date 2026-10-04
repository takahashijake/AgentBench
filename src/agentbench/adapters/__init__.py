"""Coding-agent adapter interfaces, providers, and registries."""

from .base import AgentAdapter
from .builtin import BuiltinAdapterProvider
from .discovery import ADAPTER_PROVIDER_ENTRYPOINT_GROUP, discover_adapter_providers
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
from .registry import (
    AdapterRegistry,
    AgentAdapterFactory,
    create_adapter_registry,
    create_default_adapter_registry,
    executable_key,
)
from .shell import ShellAgentAdapter

__all__ = [
    "ADAPTER_PROVIDER_ENTRYPOINT_GROUP",
    "AdapterCapabilities",
    "AdapterFactory",
    "AdapterNotFoundError",
    "AdapterProfile",
    "AdapterProviderError",
    "AdapterRegistry",
    "AgentAdapter",
    "AgentAdapterFactory",
    "AgentAdapterProvider",
    "BuiltinAdapterProvider",
    "DuplicateAdapterError",
    "ResolvedAdapter",
    "ShellAgentAdapter",
    "create_adapter_registry",
    "create_default_adapter_registry",
    "discover_adapter_providers",
    "executable_key",
]
