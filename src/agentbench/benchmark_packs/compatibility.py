"""Semantic compatibility analysis for benchmark-pack evolution.

Version labels are provenance. Comparability is derived from provider/lineage
identity plus hashes of execution-affecting task semantics.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import TYPE_CHECKING, Any

from .models import BenchmarkPack, PackTaskSpec

if TYPE_CHECKING:
    from .provider import ResolvedPack


COMPATIBILITY_SCHEMA_VERSION = 1


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def task_semantic_payload(task: PackTaskSpec) -> dict[str, Any]:
    """Return only semantics that can materially change benchmark execution."""

    return {
        "id": task.id,
        "prompt": task.prompt,
        "files": {path: task.files[path] for path in sorted(task.files)},
        "setup_command": task.setup_command,
        "test_command": task.test_command,
        "timeout": task.timeout,
    }


def task_content_sha256(task: PackTaskSpec) -> str:
    return _sha256(task_semantic_payload(task))


def pack_content_sha256(pack: BenchmarkPack) -> str:
    """Hash task semantics and lineage while intentionally excluding version text."""

    return _sha256(
        {
            "compatibility_id": pack.effective_compatibility_id,
            "tasks": [
                {
                    "id": task.id,
                    "content_sha256": task_content_sha256(task),
                }
                for task in pack.tasks
            ],
        }
    )


def compare_resolved_packs(
    left: "ResolvedPack",
    right: "ResolvedPack",
) -> dict[str, Any]:
    """Explain whether whole-pack or shared-task result comparisons are valid."""

    left_hashes = {
        task.id: task_content_sha256(task)
        for task in left.pack.tasks
    }
    right_hashes = {
        task.id: task_content_sha256(task)
        for task in right.pack.tasks
    }
    shared = sorted(set(left_hashes) & set(right_hashes))
    unchanged = [
        task_id for task_id in shared
        if left_hashes[task_id] == right_hashes[task_id]
    ]
    changed = [
        task_id for task_id in shared
        if left_hashes[task_id] != right_hashes[task_id]
    ]
    added = sorted(set(right_hashes) - set(left_hashes))
    removed = sorted(set(left_hashes) - set(right_hashes))

    same_provider = left.provider_id == right.provider_id
    same_lineage = (
        left.pack.effective_compatibility_id
        == right.pack.effective_compatibility_id
    )
    lineage_match = same_provider and same_lineage
    fully_comparable = (
        lineage_match
        and not changed
        and not added
        and not removed
    )
    comparable_shared = unchanged if lineage_match else []

    if fully_comparable:
        status = "identical-semantics"
    elif lineage_match and comparable_shared:
        status = "partially-comparable"
    else:
        status = "incompatible"

    reasons: list[str] = []
    if not same_provider:
        reasons.append("provider identity differs")
    if not same_lineage:
        reasons.append("compatibility lineage differs")
    if changed:
        reasons.append("shared task semantics changed")
    if added:
        reasons.append("right pack adds tasks")
    if removed:
        reasons.append("right pack removes tasks")
    if not reasons:
        reasons.append("execution-affecting task semantics are identical")

    return {
        "compatibility_schema_version": COMPATIBILITY_SCHEMA_VERSION,
        "status": status,
        "left": {
            "provider": left.provider_id,
            "id": left.pack.id,
            "version": left.pack.version,
            "compatibility_id": left.pack.effective_compatibility_id,
            "content_sha256": pack_content_sha256(left.pack),
        },
        "right": {
            "provider": right.provider_id,
            "id": right.pack.id,
            "version": right.pack.version,
            "compatibility_id": right.pack.effective_compatibility_id,
            "content_sha256": pack_content_sha256(right.pack),
        },
        "same_provider": same_provider,
        "same_lineage": same_lineage,
        "whole_pack_results_comparable": fully_comparable,
        "shared_task_results_comparable": comparable_shared,
        "unchanged_tasks": unchanged,
        "changed_tasks": changed,
        "added_tasks": added,
        "removed_tasks": removed,
        "reasons": reasons,
    }


__all__ = [
    "COMPATIBILITY_SCHEMA_VERSION",
    "compare_resolved_packs",
    "pack_content_sha256",
    "task_content_sha256",
    "task_semantic_payload",
]
