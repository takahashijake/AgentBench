from __future__ import annotations

from agentbench.benchmark_packs import BenchmarkPack, PackTaskSpec
from agentbench.benchmark_packs.provider import PackRegistry
from agentbench.packs import preflight_pack
from agentbench.resources import (
    HostResourceInspector,
    ResourceEligibility,
    TaskRequirements,
)


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
    assert result.observed["commands"]["agentbench-command-that-does-not-exist"] is None


class FixedInspector:
    def __init__(self, eligible: bool):
        self.eligible = eligible

    def evaluate(self, requirements):
        return ResourceEligibility(
            eligible=self.eligible,
            reasons=() if self.eligible else ("fixture incompatibility",),
            observed={"fixture": True},
        )


class RequirementProvider:
    provider_id = "requirements.fixture"

    def packs(self):
        return (
            BenchmarkPack(
                id="requirements-pack",
                version="1.0.0",
                name="Requirements",
                description="fixture",
                tasks=(
                    PackTaskSpec(
                        id="task",
                        description="fixture",
                        category="feature",
                        difficulty="easy",
                        tags=("fixture",),
                        prompt="fix it",
                        files={"x.py": "x = 1\n"},
                        requirements=TaskRequirements(min_cpu_count=8),
                    ),
                ),
            ),
        )


def test_pack_preflight_reports_ineligible_tasks_without_executing_them():
    registry = PackRegistry()
    registry.register(RequirementProvider())

    result = preflight_pack(
        "requirements-pack",
        registry=registry,
        inspector=FixedInspector(False),
    )

    assert result["eligible"] is False
    assert result["eligible_task_count"] == 0
    assert result["ineligible_task_count"] == 1
    assert result["tasks"][0]["reasons"] == ["fixture incompatibility"]
