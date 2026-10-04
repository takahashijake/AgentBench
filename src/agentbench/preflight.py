"""Pre-execution readiness checks for materialized benchmark suites."""

from __future__ import annotations

from typing import Any

from .manifests import LoadedSuiteManifest
from .provenance import executable_identity, resolve_commit
from .resources import HostResourceInspector, TaskRequirements


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
