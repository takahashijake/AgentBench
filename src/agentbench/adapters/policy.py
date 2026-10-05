"""Reproducible automation policy for known coding-agent CLIs."""

from __future__ import annotations

import shlex

from ..usage import detect_agent_family


def _option_value(tokens: list[str], option: str) -> str | None:
    prefix = option + "="
    for index, token in enumerate(tokens):
        if token.startswith(prefix):
            return token[len(prefix) :].strip().lower()
        if token == option and index + 1 < len(tokens):
            return tokens[index + 1].strip().lower()
    return None


def automation_readiness_reasons(command_template: str) -> list[str]:
    """Return reproducibility failures for known coding-agent automation modes.

    AgentBench runs subprocesses non-interactively and captures command templates
    as evidence. Known coding-agent write/approval policy therefore must be
    explicit in the command rather than inherited from mutable user configuration.
    """

    try:
        tokens = shlex.split(command_template)
    except ValueError:
        return []
    if not tokens:
        return []

    family = detect_agent_family(command_template)
    lowered = {token.lower() for token in tokens}

    if family == "qwen":
        approval_mode = _option_value(tokens, "--approval-mode")
        edit_modes = {"auto-edit", "auto", "yolo"}
        if (
            "--yolo" not in lowered
            and "-y" not in lowered
            and approval_mode not in edit_modes
        ):
            return [
                "qwen command does not explicitly enable unattended editing; "
                "add --approval-mode auto-edit/auto/yolo (or --yolo in a trusted "
                "sandbox) so benchmark write capability is reproducible"
            ]

    if family == "codex":
        automation_flags = {
            "--full-auto",
            "--approve-for-me",
            "--dangerously-bypass-approvals-and-sandbox",
            "--yolo",
        }
        if not lowered.intersection(automation_flags):
            return [
                "codex command does not explicitly enable unattended workspace "
                "writes; add --full-auto (recommended) or another explicit "
                "automation mode so benchmark write capability is reproducible"
            ]

    return []


def require_automation_ready(command_template: str) -> None:
    """Reject a known coding-agent command that cannot run unattended."""

    reasons = automation_readiness_reasons(command_template)
    if reasons:
        raise ValueError("Agent command is not automation-ready: " + "; ".join(reasons))


__all__ = ["automation_readiness_reasons", "require_automation_ready"]
