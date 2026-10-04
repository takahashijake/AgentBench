from __future__ import annotations

from dataclasses import replace

from agentbench.benchmark_packs import (
    CORE_V2,
    CORE_V3,
    BenchmarkPack,
    PackTaskSpec,
    compare_resolved_packs,
    pack_content_sha256,
    task_content_sha256,
)
from agentbench.benchmark_packs.provider import ResolvedPack
from agentbench.packs import compare_packs, create_pack_registry


def test_core_v2_to_v3_has_shared_lineage_and_explicit_partial_comparability():
    comparison = compare_packs(
        "core-v2",
        "core-v3",
        create_pack_registry(discover_plugins=False),
    )

    assert comparison["status"] == "partially-comparable"
    assert comparison["same_provider"] is True
    assert comparison["same_lineage"] is True
    assert comparison["whole_pack_results_comparable"] is False
    assert comparison["shared_task_results_comparable"] == [
        "bugfix-duration-parser",
        "feature-slug-normalizer",
        "refactor-lazy-batching",
        "regression-ttl-cache",
    ]
    assert comparison["changed_tasks"] == []
    assert comparison["removed_tasks"] == []
    assert len(comparison["added_tasks"]) == 4


def test_non_execution_metadata_does_not_change_task_content_identity():
    task = CORE_V2.tasks[0]
    renamed = replace(
        task,
        description="Different prose only",
        category="documentation-only-change",
        difficulty="reworded",
        tags=("different",),
    )

    assert task_content_sha256(task) == task_content_sha256(renamed)


def test_execution_affecting_task_change_breaks_shared_task_comparability():
    original = CORE_V2.tasks[0]
    changed = replace(original, prompt=original.prompt + "\nDo one extra thing.")
    revised = BenchmarkPack(
        id="core-v2-revised",
        version="2.1.0",
        name="Core revised",
        description="fixture",
        tasks=(changed, *CORE_V2.tasks[1:]),
        compatibility_id=CORE_V2.effective_compatibility_id,
    )

    comparison = compare_resolved_packs(
        ResolvedPack("agentbench.builtin", CORE_V2),
        ResolvedPack("agentbench.builtin", revised),
    )

    assert comparison["status"] == "partially-comparable"
    assert comparison["whole_pack_results_comparable"] is False
    assert comparison["changed_tasks"] == ["bugfix-duration-parser"]
    assert "bugfix-duration-parser" not in comparison[
        "shared_task_results_comparable"
    ]


def test_identical_semantics_are_comparable_across_version_labels():
    relabeled = replace(CORE_V2, id="core-v2.1", version="2.1.0")
    comparison = compare_resolved_packs(
        ResolvedPack("agentbench.builtin", CORE_V2),
        ResolvedPack("agentbench.builtin", relabeled),
    )

    assert comparison["status"] == "identical-semantics"
    assert comparison["whole_pack_results_comparable"] is True
    assert pack_content_sha256(CORE_V2) == pack_content_sha256(relabeled)


def test_provider_or_lineage_change_is_incompatible_even_if_tasks_match():
    different_lineage = replace(
        CORE_V2,
        id="other",
        compatibility_id="unrelated-corpus",
    )

    provider_mismatch = compare_resolved_packs(
        ResolvedPack("one.provider", CORE_V2),
        ResolvedPack("two.provider", CORE_V2),
    )
    lineage_mismatch = compare_resolved_packs(
        ResolvedPack("agentbench.builtin", CORE_V2),
        ResolvedPack("agentbench.builtin", different_lineage),
    )

    assert provider_mismatch["status"] == "incompatible"
    assert provider_mismatch["shared_task_results_comparable"] == []
    assert lineage_mismatch["status"] == "incompatible"
    assert lineage_mismatch["shared_task_results_comparable"] == []
