"""Pre-execution readiness checks for materialized benchmark suites."""

from __future__ import annotations

import shlex
from typing import Any

from .manifests import LoadedSuiteManifest
from .provenance import executable_identity, resolve_commit
from .resources import HostResourceInspector, TaskRequirements
from .usage import detect_agent_family


def _option_value(tokens: list[str], option: str) -> str | None:
    prefix = option + "="
    for index, token in enumerate(tokens):
        if token.startswith(prefix):
            return token[len(prefix) :].strip().lower()
        if token == option and index + 1 < len(tokens):
            return tokens[index + 1].strip().lower()
    return None


def _automation_readiness_reasons(command_template: str) -> list[str]:
    """Return reproducibility failures for known coding-agent automation modes.

    AgentBench captures the command template in suite identity, so write capability
    should be explicit there rather than depending on mutable per-user CLI config.
    This check is intentionally conservative and never executes the external agent.
    """

    try:
        tokens = shlex.split(command_template)
    except ValueError:
        # executable_identity reports malformed templates with the canonical error.
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


def preflight_suite(
    loaded: LoadedSuiteManifest,
    *,
    resource_inspector: HostResourceInspector | None = None,
) -> dict[str, Any]:
    """Check selected tasks and agents without executing benchmark work."""

    inspector = resource_inspector or HostResourceInspector()
    tasks_by_id = {task.id: task for task in loaded.manifest.tasks}
    agents_by_id = {agent.id: agent for agent in loaded.manifest.agents}

    task_rows: list[dict[str, Any]] = []
    for task_id in loaded.manifest.selected_task_ids():
        task = tasks_by_id[task_id]
        requirements = TaskRequirements.from_mapping(
            task.requirements.model_dump(mode="json")
        )
        eligibility = inspector.evaluate(requirements)
        reasons = list(eligibility.reasons)
        repository = loaded.resolve_repository_path(task)
        resolved_commit = None
        try:
            resolved_commit = resolve_commit(repository, task.base_commit)
            if resolved_commit != task.base_commit.lower():
                reasons.append(
                    "resolved repository commit does not match manifest base_commit"
                )
        except ValueError as exc:
            reasons.append(f"repository readiness failed: {exc}")

        task_rows.append(
            {
                "id": task.id,
                "ready": not reasons,
                "repository_path": str(repository),
                "base_commit": task.base_commit.lower(),
                "resolved_commit": resolved_commit,
                "requirements": requirements.as_dict(),
                "observed": eligibility.observed,
                "reasons": reasons,
            }
        )

    agent_rows: list[dict[str, Any]] = []
    for agent_id in loaded.manifest.selected_agent_ids():
        agent = agents_by_id[agent_id]
        reasons: list[str] = []
        identity = None
        try:
            identity = executable_identity(agent.command_template)
        except ValueError as exc:
            reasons.append(f"agent executable readiness failed: {exc}")
        reasons.extend(_automation_readiness_reasons(agent.command_template))
        agent_rows.append(
            {
                "id": agent.id,
                "ready": not reasons,
                "executable": identity,
                "reasons": reasons,
            }
        )

    ready_tasks = sum(bool(row["ready"]) for row in task_rows)
    ready_agents = sum(bool(row["ready"]) for row in agent_rows)
    ready = ready_tasks == len(task_rows) and ready_agents == len(agent_rows)
    return {
        "ready": ready,
        "suite_id": loaded.manifest.id,
        "manifest_sha256": loaded.sha256,
        "task_count": len(task_rows),
        "ready_task_count": ready_tasks,
        "agent_count": len(agent_rows),
        "ready_agent_count": ready_agents,
        "tasks": task_rows,
        "agents": agent_rows,
    }


__all__ = ["preflight_suite"]
