from __future__ import annotations

from agentbench.resources import HostResourceInspector, TaskRequirements


def test_task_requirements_normalize_platforms_and_round_trip():
    requirements = TaskRequirements(
        min_cpu_count=2,
        min_memory_mb=512,
        supported_platforms=("Linux", "DARWIN"),
        required_commands=("python", "git"),
    )

    assert requirements.supported_platforms == ("linux", "darwin")
    assert TaskRequirements.from_mapping(requirements.as_dict()) == requirements


def test_host_resource_inspector_reports_missing_command():
    result = HostResourceInspector().evaluate(
        TaskRequirements(required_commands=("agentbench-command-that-does-not-exist",))
    )

    assert result.eligible is False
    assert "required commands are unavailable" in result.reasons[0]
    assert (
        result.observed["commands"]["agentbench-command-that-does-not-exist"] is None
    )
