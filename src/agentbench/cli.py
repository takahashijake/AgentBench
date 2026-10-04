"""Command-line product surface for AgentBench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from pydantic import ValidationError

from . import __version__

from .manifests import LoadedSuiteManifest, load_suite_manifest
from .models.session import close_session, get_session, init_db
from .provenance import (
    build_suite_lock,
    environment_identity,
    load_suite_lock,
    verify_suite_lock,
    write_suite_lock,
)
from .reporting import render_markdown_report
from .services.experiment import ExperimentBusyError, ExperimentNotFoundError
from .services.suite import SuiteService


def _write_json(payload: dict[str, Any], output: Optional[str] = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _write_markdown(report: dict[str, Any], output: Optional[str]) -> None:
    if not output:
        return
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown_report(report), encoding="utf-8")


def _validation_payload(loaded: LoadedSuiteManifest) -> dict[str, Any]:
    tasks_by_id = {item.id: item for item in loaded.manifest.tasks}
    return {
        "valid": True,
        "schema_version": loaded.manifest.schema_version,
        "suite_id": loaded.manifest.id,
        "manifest_path": str(loaded.path),
        "manifest_sha256": loaded.sha256,
        "selected_tasks": [
            {
                "id": resource_id,
                "repository_path": str(
                    loaded.resolve_repository_path(tasks_by_id[resource_id])
                ),
                "base_commit": tasks_by_id[resource_id].base_commit.lower(),
            }
            for resource_id in loaded.manifest.selected_task_ids()
        ],
        "selected_agents": loaded.manifest.selected_agent_ids(),
        "repetitions": loaded.manifest.experiment.repetitions,
        "planned_runs": (
            len(loaded.manifest.selected_task_ids())
            * len(loaded.manifest.selected_agent_ids())
            * loaded.manifest.experiment.repetitions
        ),
        "stop_on_error": loaded.manifest.experiment.stop_on_error,
    }


def _default_lock_path(manifest_path: str) -> str:
    path = Path(manifest_path).expanduser().resolve()
    return str(path.with_suffix(".lock.json"))


def _add_report_outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        "-o",
        help="Optional file path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--markdown",
        help="Optional file path for a human-readable Markdown report.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbench",
        description=(
            "Reproducible local benchmarking and comparison for coding agents."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="Validate a suite manifest without mutating local state.",
    )
    validate.add_argument("manifest")

    doctor = subparsers.add_parser(
        "doctor",
        help="Show the bounded environment identity used for reproducibility.",
    )

    lock = subparsers.add_parser(
        "lock",
        help="Resolve a suite into a deterministic reproducibility lock.",
    )
    lock.add_argument("manifest")
    lock.add_argument(
        "--output",
        "-o",
        help="Lock path. Defaults to <manifest>.lock.json.",
    )

    verify = subparsers.add_parser(
        "verify",
        help="Verify the current suite/toolchain against a saved lock.",
    )
    verify.add_argument("manifest")
    verify.add_argument("lock")

    import_cmd = subparsers.add_parser(
        "import",
        help="Idempotently import suite tasks and agents into AgentBench.",
    )
    import_cmd.add_argument("manifest")

    run = subparsers.add_parser(
        "run",
        help="Resolve provenance, execute a suite, and export results.",
    )
    run.add_argument("manifest")
    run.add_argument(
        "--lock",
        help="Optional existing lock that must verify before execution.",
    )
    run.add_argument(
        "--write-lock",
        help="Optional path to persist the resolved lock used by this run.",
    )
    _add_report_outputs(run)

    replay = subparsers.add_parser(
        "replay",
        help="Verify a saved lock, then execute the locked suite.",
    )
    replay.add_argument("manifest")
    replay.add_argument("lock")
    replay.add_argument(
        "--write-lock",
        help="Optional path to persist the newly verified current lock.",
    )
    _add_report_outputs(replay)

    results = subparsers.add_parser(
        "results",
        help="Export aggregate results for an existing experiment ID.",
    )
    results.add_argument("experiment_id", type=int)
    _add_report_outputs(results)
    return parser


def _verify_or_raise(
    loaded: LoadedSuiteManifest,
    lock_path: str,
) -> dict[str, Any]:
    expected = load_suite_lock(lock_path)
    verification = verify_suite_lock(loaded, expected)
    if not verification["valid"]:
        drift = verification["drift"]
        preview = "; ".join(
            f"{item['path']}: {item['expected']!r} -> {item['actual']!r}"
            for item in drift[:8]
        )
        suffix = "" if len(drift) <= 8 else f"; +{len(drift) - 8} more"
        raise ValueError(f"Suite lock verification failed: {preview}{suffix}")
    return verification["current_lock"]


def _run_suite(
    args: argparse.Namespace,
    service: SuiteService,
) -> int:
    loaded = load_suite_manifest(args.manifest)
    expected_lock_path = (
        args.lock if args.command == "run" else args.lock
    )
    if expected_lock_path:
        current_lock = _verify_or_raise(loaded, expected_lock_path)
    else:
        current_lock = build_suite_lock(loaded)

    if args.write_lock:
        write_suite_lock(args.write_lock, current_lock)

    imported, experiment, summary = service.execute_suite(loaded)
    report = service.build_report(loaded, imported, experiment, summary)
    report["lock"] = current_lock
    _write_markdown(report, args.markdown)
    _write_json(report, args.output)
    return 0


def _run_database_command(args: argparse.Namespace) -> int:
    init_db()
    db = get_session()
    try:
        service = SuiteService(db)

        if args.command == "import":
            loaded = load_suite_manifest(args.manifest)
            imported = service.import_suite(loaded)
            _write_json({"imported": True, **imported.as_dict()})
            return 0

        if args.command in {"run", "replay"}:
            return _run_suite(args, service)

        if args.command == "results":
            experiment = service.experiments.get_experiment(args.experiment_id)
            summary = service.experiments.aggregate_experiment(args.experiment_id)
            report = {
                "report_schema_version": 1,
                "experiment": {
                    "id": int(experiment.id),
                    "name": experiment.name,
                    "status": experiment.status,
                    "repetitions": experiment.repetitions,
                    "stop_on_error": experiment.stop_on_error,
                    "planned_runs": experiment.planned_runs,
                },
                "summary": summary,
            }
            _write_markdown(report, args.markdown)
            _write_json(report, args.output)
            return 0

        raise ValueError(f"Unsupported database command: {args.command}")
    finally:
        close_session()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            loaded = load_suite_manifest(args.manifest)
            _write_json(_validation_payload(loaded))
            return 0

        if args.command == "doctor":
            _write_json(
                {
                    "status": "ok",
                    "environment": environment_identity(),
                }
            )
            return 0

        if args.command == "lock":
            loaded = load_suite_manifest(args.manifest)
            payload = build_suite_lock(loaded)
            output = args.output or _default_lock_path(args.manifest)
            write_suite_lock(output, payload)
            _write_json(
                {
                    "locked": True,
                    "lock_path": str(Path(output).expanduser().resolve()),
                    "identity_sha256": payload["identity_sha256"],
                }
            )
            return 0

        if args.command == "verify":
            loaded = load_suite_manifest(args.manifest)
            expected = load_suite_lock(args.lock)
            verification = verify_suite_lock(loaded, expected)
            response = {
                key: value
                for key, value in verification.items()
                if key != "current_lock"
            }
            _write_json(response)
            return 0 if verification["valid"] else 3

        return _run_database_command(args)
    except (
        OSError,
        ValueError,
        ValidationError,
        ExperimentBusyError,
        ExperimentNotFoundError,
    ) as exc:
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "detail": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
