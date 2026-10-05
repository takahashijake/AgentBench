"""Canonical product defaults shared across persistence, API, and execution."""

DEFAULT_AGENT_COMMAND_TEMPLATE = (
    "qwen -p {prompt} --approval-mode auto-edit"
)

__all__ = ["DEFAULT_AGENT_COMMAND_TEMPLATE"]
