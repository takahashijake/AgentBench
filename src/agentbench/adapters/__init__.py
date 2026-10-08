"""Coding-agent adapter interfaces and registries."""

from .base import AgentAdapter
from .codex import CodexAgentAdapter
from .registry import (
    AdapterFactory,
    AdapterRegistry,
    AgentAdapterFactory,
    create_default_adapter_registry,
    executable_key,
)
from .shell import ShellAgentAdapter

__all__ = [
    "AdapterFactory",
    "AdapterRegistry",
    "AgentAdapter",
    "CodexAgentAdapter",
    "AgentAdapterFactory",
    "ShellAgentAdapter",
    "create_default_adapter_registry",
    "executable_key",
]
