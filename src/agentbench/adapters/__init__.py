"""Agent adapters package."""

from .base import AgentAdapter
from .shell import ShellAgentAdapter

__all__ = ["AgentAdapter", "ShellAgentAdapter"]
