"""Portable, integrity-checked experiment result bundles.

Bundle creation is deliberately separated from CLI/API transport. The bundle is a
deterministic ZIP container whose manifest authenticates every included payload.
Extraction never delegates to ZipFile.extractall; paths are validated and written
explicitly to avoid traversal surprises.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

from sqlalchemy.orm import Session

from . import __version__
from .reporting import render_markdown_report
from .services.experiment import ExperimentService


BUNDLE_SCHEMA_VERSION = 1
_MAX_BUNDLE_FILES = 10_000
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BundleValidationError(ValueError):
    """Raised when a result bundle violates the portable bundle contract."""


@dataclass(frozen=True)
class VerifiedResultBundle:
    path: Path
    manifest: dict[str, Any]
    report: dict[str, Any]

    @property
    def identity_sha256(self) -> str:
        return str(self.manifest["identity_sha256"])


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _safe_member_name(name: str) -> str:
    if "\\" in name:
        raise BundleValidationError(f"Bundle member uses backslashes: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts:
        raise BundleValidationError(f"Unsafe bundle member path: {name!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise BundleValidationError(f"Unsafe bundle member path: {name!r}")
    return path.as_posix()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


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
            portable_adapter["command_template_sha256"] = _sha256_bytes(
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
            key: value for key, value in cleanup.items() if "path" not in key.lower()
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
            _sha256_bytes(prompt.encode("utf-8")) if isinstance(prompt, str) else None
        ),
        "setup_command": snapshot.get("setup_command"),
        "test_command": snapshot.get("test_command"),
        "timeout": snapshot.get("timeout"),
        "enabled": snapshot.get("enabled"),
        "requirements": snapshot.get("requirements") or {},
    }


def _portable_agent_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    command = snapshot.get("command_template")
    return {
        "id": snapshot.get("id"),
        "name": snapshot.get("name"),
        "description": snapshot.get("description"),
        "command_template_sha256": (
            _sha256_bytes(command.encode("utf-8")) if isinstance(command, str) else None
        ),
        "enabled": snapshot.get("enabled"),
    }


class ResultBundleService:
    """Export canonical experiment state and immutable artifacts."""

    def __init__(self, db: Session):
        self.db = db
        self.experiments = ExperimentService(db)

    def _report(self, experiment: Any, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "report_schema_version": 5,
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
            "agent_config_ids": [int(value) for value in experiment.agent_config_ids],
            "task_snapshots": [
                _portable_task_snapshot(snapshot)
                for snapshot in experiment.task_snapshots
            ],
            "agent_snapshots": [
                _portable_agent_snapshot(snapshot)
                for snapshot in experiment.agent_snapshots
            ],
            "executions": [
                {
                    "id": int(item.id),
                    "mode": item.mode,
                    "max_workers": int(item.max_workers),
                    "status": item.status,
                    "details": dict(item.details or {}),
                    "started_at": (
                        item.started_at.isoformat()
                        if item.started_at is not None
                        else None
                    ),
                    "completed_at": (
                        item.completed_at.isoformat()
                        if item.completed_at is not None
                        else None
                    ),
                }
                for item in experiment.executions
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
                archive_name = _safe_member_name(
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
            "report.json": _canonical_json_bytes(report),
            "report.md": render_markdown_report(report).encode("utf-8"),
            "experiment.json": _canonical_json_bytes(
                self._experiment_document(experiment)
            ),
        }
        payloads.update(self._artifact_files(experiment))

        files = [
            {
                "path": name,
                "sha256": _sha256_bytes(payloads[name]),
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
            "identity_sha256": _sha256_bytes(_canonical_json_bytes(manifest_core)),
        }

        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"Result bundle already exists: {target}")

        with zipfile.ZipFile(target, "x") as archive:
            archive.writestr(
                _zip_info("bundle.json"),
                _canonical_json_bytes(manifest),
            )
            for name in sorted(payloads):
                archive.writestr(_zip_info(name), payloads[name])

        return {
            "exported": True,
            "path": str(target),
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "identity_sha256": manifest["identity_sha256"],
            "experiment_id": int(experiment.id),
            "file_count": len(files),
        }


def verify_result_bundle(path: str | Path) -> VerifiedResultBundle:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise BundleValidationError(f"Result bundle does not exist: {source}")

    try:
        archive = zipfile.ZipFile(source, "r")
    except zipfile.BadZipFile as exc:
        raise BundleValidationError(f"Invalid ZIP result bundle: {source}") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_BUNDLE_FILES + 1:
            raise BundleValidationError("Result bundle contains too many files")

        names = [_safe_member_name(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise BundleValidationError("Result bundle contains duplicate member names")
        if "bundle.json" not in names:
            raise BundleValidationError("Result bundle is missing bundle.json")

        total_size = sum(int(info.file_size) for info in infos)
        if total_size > _MAX_UNCOMPRESSED_BYTES:
            raise BundleValidationError("Result bundle is too large to verify safely")

        try:
            manifest = json.loads(archive.read("bundle.json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError("bundle.json is not valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict):
            raise BundleValidationError("bundle.json root must be an object")
        if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
            raise BundleValidationError(
                "Unsupported result bundle schema version: "
                f"{manifest.get('bundle_schema_version')!r}"
            )

        identity = manifest.get("identity_sha256")
        core = dict(manifest)
        core.pop("identity_sha256", None)
        expected_identity = _sha256_bytes(_canonical_json_bytes(core))
        if identity != expected_identity:
            raise BundleValidationError("Result bundle identity digest does not match")

        declared = manifest.get("files")
        if not isinstance(declared, list):
            raise BundleValidationError("Result bundle files must be a list")

        declared_names: list[str] = []
        for item in declared:
            if not isinstance(item, dict):
                raise BundleValidationError("Invalid file entry in bundle manifest")
            name = _safe_member_name(str(item.get("path") or ""))
            declared_names.append(name)
            if name == "bundle.json":
                raise BundleValidationError("bundle.json must not declare itself")
            if name not in names:
                raise BundleValidationError(f"Declared bundle file is missing: {name}")
            data = archive.read(name)
            if len(data) != int(item.get("size", -1)):
                raise BundleValidationError(f"Size mismatch for bundle file: {name}")
            if _sha256_bytes(data) != item.get("sha256"):
                raise BundleValidationError(f"Digest mismatch for bundle file: {name}")

        if len(declared_names) != len(set(declared_names)):
            raise BundleValidationError("Bundle manifest declares duplicate files")
        actual_payloads = sorted(name for name in names if name != "bundle.json")
        if sorted(declared_names) != actual_payloads:
            raise BundleValidationError(
                "Bundle contains undeclared payload files or omits declared files"
            )

        try:
            report = json.loads(archive.read("report.json"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError(
                "Result bundle lacks a valid report.json"
            ) from exc
        if not isinstance(report, dict):
            raise BundleValidationError("report.json root must be an object")

    return VerifiedResultBundle(path=source, manifest=manifest, report=report)


def inspect_result_bundle(path: str | Path) -> dict[str, Any]:
    verified = verify_result_bundle(path)
    return {
        "valid": True,
        "path": str(verified.path),
        "identity_sha256": verified.identity_sha256,
        "manifest": verified.manifest,
        "report": verified.report,
    }


def extract_result_bundle(
    path: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    verified = verify_result_bundle(path)
    target = Path(destination).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise BundleValidationError(
            f"Bundle extraction directory is not empty: {target}"
        )
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(verified.path, "r") as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = _safe_member_name(info.filename)
            output = (target / Path(*PurePosixPath(name).parts)).resolve()
            try:
                output.relative_to(target)
            except ValueError as exc:
                raise BundleValidationError(
                    f"Bundle extraction escaped destination: {name}"
                ) from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(info))

    return {
        "extracted": True,
        "source": str(verified.path),
        "destination": str(target),
        "identity_sha256": verified.identity_sha256,
        "file_count": len(verified.manifest["files"]) + 1,
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
