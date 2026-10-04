"""Database-backed export service for portable AgentBench result bundles.

Portable format verification/extraction lives in :mod:`agentbench.bundle_format`
so consumers can inspect and publish bundles without importing persistence or
orchestration services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import zipfile

from sqlalchemy.orm import Session

from . import __version__
from .bundle_format import (
    BUNDLE_SCHEMA_VERSION,
    BundleValidationError,
    VerifiedResultBundle,
    canonical_json_bytes,
    deterministic_zip_info,
    extract_result_bundle,
    inspect_result_bundle,
    safe_member_name,
    sha256_bytes,
    verify_result_bundle,
)
from .reporting import render_markdown_report
from .services.experiment import ExperimentService


def _portable_results(run: Any) -> dict[str, Any]:
    """Project run results onto portable semantics, excluding host-local paths."""

    results = run.results if isinstance(run.results, dict) else {}
    adapter = results.get("adapter_metadata")
    portable_adapter: dict[str, Any] | None = None
    if isinstance(adapter, dict):
        command_template = adapter.get("command_template")
        portable_adapter = {
            key: value
            for key, value in adapter.items()
            if key not in {"workspace_path", "command_template"}
        }
        if isinstance(command_template, str):
            portable_adapter["command_template_sha256"] = sha256_bytes(
                command_template.encode("utf-8")
            )

    stages: dict[str, Any] = {}
    for name in ("setup", "test"):
        stage = results.get(name)
        if isinstance(stage, dict):
            stages[name] = {
                key: value
                for key, value in stage.items()
                if key not in {"stdout_path", "stderr_path", "cwd"}
            }

    cleanup = results.get("cleanup")
    portable_cleanup = None
    if isinstance(cleanup, dict):
        portable_cleanup = {
            key: value
            for key, value in cleanup.items()
            if "path" not in key.lower()
        }

    artifact_prefix = f"artifacts/run-{int(run.id)}/"
    return {
        "artifact_bundle_prefix": artifact_prefix,
        "adapter_metadata": portable_adapter,
        "provenance": results.get("provenance"),
        "base_commit": results.get("base_commit"),
        "repository_head_at_start": results.get("repository_head_at_start"),
        "final_commit": results.get("final_commit"),
        "workspace_status": results.get("workspace_status"),
        "workspace_diff_stats": results.get("workspace_diff_stats"),
        "git_evidence": {
            "head": artifact_prefix + "git/head.txt",
            "status": artifact_prefix + "git/status.txt",
            "patch": artifact_prefix + "git/diff.patch",
            "numstat": artifact_prefix + "git/numstat.txt",
            "commits": artifact_prefix + "git/commits.txt",
            "untracked_manifest": artifact_prefix + "git/untracked-manifest.json",
            "untracked_root": artifact_prefix + "git/untracked/",
        },
        "stages": stages,
        "cleanup": portable_cleanup,
        "internal_error": results.get("internal_error"),
    }


def _run_payload(run: Any) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "task_id": int(run.task_id),
        "agent_config_id": (
            int(run.agent_config_id) if run.agent_config_id is not None else None
        ),
        "agent_name": run.agent_name,
        "model_name": run.model_name,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "duration_seconds": run.duration_seconds,
        "exit_code": run.exit_code,
        "success": run.success,
        "test_passed": int(run.test_passed or 0),
        "test_failed": int(run.test_failed or 0),
        "tests_passed": run.tests_passed,
        "files_changed": int(run.files_changed or 0),
        "insertions": int(run.insertions or 0),
        "deletions": int(run.deletions or 0),
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "total_tokens": run.total_tokens,
        "results": _portable_results(run),
    }


def _portable_task_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    prompt = snapshot.get("agent_prompt")
    return {
        "id": snapshot.get("id"),
        "name": snapshot.get("name"),
        "description": snapshot.get("description"),
        "base_commit": snapshot.get("base_commit"),
        "agent_prompt_sha256": (
            sha256_bytes(prompt.encode("utf-8"))
            if isinstance(prompt, str)
            else None
        ),
        "setup_command": snapshot.get("setup_command"),
        "test_command": snapshot.get("test_command"),
        "timeout": snapshot.get("timeout"),
        "enabled": snapshot.get("enabled"),
    }


def _portable_agent_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    command = snapshot.get("command_template")
    return {
        "id": snapshot.get("id"),
        "name": snapshot.get("name"),
        "description": snapshot.get("description"),
        "command_template_sha256": (
            sha256_bytes(command.encode("utf-8"))
            if isinstance(command, str)
            else None
        ),
        "enabled": snapshot.get("enabled"),
    }


class ResultBundleService:
    """Export canonical persisted experiment state and immutable artifacts."""

    def __init__(self, db: Session):
        self.db = db
        self.experiments = ExperimentService(db)

    def _report(self, experiment: Any, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "report_schema_version": 3,
            "experiment": {
                "id": int(experiment.id),
                "name": experiment.name,
                "description": experiment.description,
                "status": experiment.status,
                "repetitions": int(experiment.repetitions),
                "stop_on_error": bool(experiment.stop_on_error),
                "planned_runs": int(experiment.planned_runs),
            },
            "summary": summary,
        }

    def _experiment_document(self, experiment: Any) -> dict[str, Any]:
        trials = []
        for trial in experiment.trials:
            trials.append(
                {
                    "id": int(trial.id),
                    "task_id": int(trial.task_id),
                    "agent_config_id": int(trial.agent_config_id),
                    "repetition": int(trial.repetition),
                    "ordinal": int(trial.ordinal),
                    "status": trial.status,
                    "error": trial.error,
                    "benchmark_run": (
                        _run_payload(trial.benchmark_run)
                        if trial.benchmark_run is not None
                        else None
                    ),
                }
            )
        return {
            "id": int(experiment.id),
            "name": experiment.name,
            "description": experiment.description,
            "status": experiment.status,
            "repetitions": int(experiment.repetitions),
            "stop_on_error": bool(experiment.stop_on_error),
            "planned_runs": int(experiment.planned_runs),
            "task_ids": [int(value) for value in experiment.task_ids],
            "agent_config_ids": [
                int(value) for value in experiment.agent_config_ids
            ],
            "task_snapshots": [
                _portable_task_snapshot(snapshot)
                for snapshot in experiment.task_snapshots
            ],
            "agent_snapshots": [
                _portable_agent_snapshot(snapshot)
                for snapshot in experiment.agent_snapshots
            ],
            "trials": trials,
        }

    @staticmethod
    def _artifact_files(experiment: Any) -> dict[str, bytes]:
        payloads: dict[str, bytes] = {}
        for trial in experiment.trials:
            run = trial.benchmark_run
            if run is None or not isinstance(run.results, dict):
                continue
            artifact_directory = run.results.get("artifact_directory")
            if not artifact_directory:
                continue
            root = Path(str(artifact_directory)).expanduser().resolve()
            if not root.is_dir():
                continue

            for candidate in sorted(root.rglob("*")):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                try:
                    relative = resolved.relative_to(root)
                except ValueError as exc:
                    raise BundleValidationError(
                        f"Artifact escaped run directory: {candidate}"
                    ) from exc
                archive_name = safe_member_name(
                    f"artifacts/run-{int(run.id)}/{relative.as_posix()}"
                )
                if archive_name in payloads:
                    raise BundleValidationError(
                        f"Duplicate artifact bundle path: {archive_name}"
                    )
                payloads[archive_name] = resolved.read_bytes()
        return payloads

    def export(self, experiment_id: int, destination: str | Path) -> dict[str, Any]:
        experiment = self.experiments.get_experiment(experiment_id)
        summary = self.experiments.aggregate_experiment(experiment_id)
        report = self._report(experiment, summary)

        payloads: dict[str, bytes] = {
            "report.json": canonical_json_bytes(report),
            "report.md": render_markdown_report(report).encode("utf-8"),
            "experiment.json": canonical_json_bytes(
                self._experiment_document(experiment)
            ),
        }
        payloads.update(self._artifact_files(experiment))

        files = [
            {
                "path": name,
                "sha256": sha256_bytes(payloads[name]),
                "size": len(payloads[name]),
            }
            for name in sorted(payloads)
        ]
        manifest_core: dict[str, Any] = {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "agentbench_version": __version__,
            "experiment": {
                "id": int(experiment.id),
                "name": experiment.name,
                "status": experiment.status,
            },
            "files": files,
        }
        manifest = {
            **manifest_core,
            "identity_sha256": sha256_bytes(canonical_json_bytes(manifest_core)),
        }

        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"Result bundle already exists: {target}")

        with zipfile.ZipFile(target, "x") as archive:
            archive.writestr(
                deterministic_zip_info("bundle.json"),
                canonical_json_bytes(manifest),
            )
            for name in sorted(payloads):
                archive.writestr(
                    deterministic_zip_info(name),
                    payloads[name],
                )

        return {
            "exported": True,
            "path": str(target),
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "identity_sha256": manifest["identity_sha256"],
            "experiment_id": int(experiment.id),
            "file_count": len(files),
        }


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BundleValidationError",
    "ResultBundleService",
    "VerifiedResultBundle",
    "extract_result_bundle",
    "inspect_result_bundle",
    "verify_result_bundle",
]
