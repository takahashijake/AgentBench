"""Built-in adapter profiles.

Known coding-agent families remain shell-backed in V4 unless a native provider
explicitly replaces them in a custom registry. The capability catalog therefore
never labels these profiles as native integrations.
"""

from __future__ import annotations

from typing import Any

from .provider import AdapterCapabilities, AdapterProfile
from .shell import ShellAgentAdapter


def _shell_factory(config: dict[str, Any]) -> ShellAgentAdapter:
    return ShellAgentAdapter(config)


class BuiltinAdapterProvider:
    provider_id = "agentbench.builtin"

    def adapters(self) -> tuple[AdapterProfile, ...]:
        shell = AdapterCapabilities(
            execution_protocol="shell",
            native_protocol=False,
            structured_usage=True,
            cost_reporting=True,
            model_reporting=False,
        )
        return (
            AdapterProfile(
                id="shell",
                family="shell",
                description="Generic argv-safe shell adapter.",
                implementation="agentbench.adapters.shell.ShellAgentAdapter",
                factory=_shell_factory,
                capabilities=shell,
            ),
            *tuple(
                AdapterProfile(
                    id=family,
                    family=family,
                    description=(
                        f"Shell-backed {family} CLI profile; not a native protocol adapter."
                    ),
                    implementation="agentbench.adapters.shell.ShellAgentAdapter",
                    factory=_shell_factory,
                    capabilities=shell,
                )
                for family in ("codex", "qwen", "claude", "gemini")
            ),
        )


__all__ = ["BuiltinAdapterProvider"]
