"""Dependency-inverted adapter construction for benchmark execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import shlex
from typing import Any, Protocol

from .base import AgentAdapter
from .codex import CodexAgentAdapter
from .shell import ShellAgentAdapter
from ..usage import detect_agent_family


AdapterFactory = Callable[[dict[str, Any]], AgentAdapter]


class AgentAdapterFactory(Protocol):
    """Minimal factory contract consumed by BenchmarkService."""

    def create(self, config: Mapping[str, Any]) -> AgentAdapter: ...


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


@dataclass
class AdapterRegistry:
    """Explicit registry so orchestration never imports concrete adapters."""

    _factories: dict[str, AdapterFactory] = field(default_factory=dict)

    def register(self, name: str, factory: AdapterFactory) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError("Adapter name must not be empty")
        if key in self._factories:
            raise ValueError(f"Adapter already registered: {key}")
        self._factories[key] = factory

    def create(self, config: Mapping[str, Any]) -> AgentAdapter:
        normalized = dict(config)
        explicit = str(normalized.get("adapter") or "").strip().lower()
        executable = executable_key(str(normalized.get("command_template") or ""))
        key = explicit or executable
        if key not in self._factories:
            key = "shell"
        normalized["adapter"] = key
        normalized.setdefault(
            "agent_family",
            detect_agent_family(str(normalized.get("command_template") or ""))
            if key == "shell"
            else key,
        )
        return self._factories[key](normalized)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def _shell_factory(config: dict[str, Any]) -> AgentAdapter:
    return ShellAgentAdapter(config)


def create_default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register("shell", _shell_factory)
    registry.register("codex", lambda config: CodexAgentAdapter(config))
    for family in ("qwen", "claude", "gemini"):
        registry.register(family, _shell_factory)
    return registry


__all__ = [
    "AdapterFactory",
    "AdapterRegistry",
    "AgentAdapterFactory",
    "create_default_adapter_registry",
    "executable_key",
]
