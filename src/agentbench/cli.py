"""Command-line workflows for versioned AgentBench suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from pydantic import ValidationError

from .manifests import LoadedSuiteManifest, load_suite_manifest
from .models.session import close_session, get_session, init_db
from .services.experiment import ExperimentBusyError, ExperimentNotFoundError
from .services.suite import SuiteService


def _write_json(payload: dict[str, Any], output: Optional[str] = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbench",
        description="Validate, import, run, and export AgentBench benchmark suites.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="Validate a suite manifest without mutating the database.",
    )
    validate.add_argument("manifest")

    import_cmd = subparsers.add_parser(
        "import",
        help="Idempotently import suite tasks and agents into AgentBench.",
    )
    import_cmd.add_argument("manifest")

    run = subparsers.add_parser(
        "run",
        help="Import, create an experiment, execute it, and emit JSON results.",
    )
    run.add_argument("manifest")
    run.add_argument(
        "--output",
        "-o",
        help="Optional file path for the machine-readable JSON report.",
    )

    results = subparsers.add_parser(
        "results",
        help="Export aggregate results for an existing experiment ID.",
    )
    results.add_argument("experiment_id", type=int)
    results.add_argument(
        "--output",
        "-o",
        help="Optional file path for the JSON result export.",
    )
    return parser


def _run_database_command(args: argparse.Namespace) -> int:
    init_db()
    db = get_session()
    try:
        service = SuiteService(db)

        if args.command == "import":
            loaded = load_suite_manifest(args.manifest)
            imported = service.import_suite(loaded)
            _write_json(
                {
                    "imported": True,
                    **imported.as_dict(),
                }
            )
            return 0

        if args.command == "run":
            loaded = load_suite_manifest(args.manifest)
            imported, experiment, summary = service.execute_suite(loaded)
            report = service.build_report(
                loaded,
                imported,
                experiment,
                summary,
            )
            _write_json(report, args.output)
            return 0

        if args.command == "results":
            experiment = service.experiments.get_experiment(args.experiment_id)
            summary = service.experiments.aggregate_experiment(args.experiment_id)
            _write_json(
                {
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
                },
                args.output,
            )
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
