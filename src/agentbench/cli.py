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
from .packs import (
    get_pack,
    list_packs,
    materialize_pack,
    parse_agent_spec,
    preflight_pack,
)
from .preflight import preflight_suite
from .provenance import (
    build_suite_lock,
    environment_identity,
    load_suite_lock,
    verify_suite_lock,
    write_suite_lock,
)
from .reporting import render_leaderboard_markdown, render_markdown_report
from .result_bundles import (
    BundleValidationError,
    ResultBundleService,
    extract_result_bundle,
    inspect_result_bundle,
    verify_result_bundle,
)
from .services.budget import ExperimentBudgetService
from .services.distributed_worker import DistributedWorkerService
from .services.experiment import ExperimentBusyError, ExperimentNotFoundError
from .services.suite import SuiteService


def _write_json(payload: dict[str, Any], output: Optional[str] = None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _write_markdown_text(rendered: str, output: Optional[str]) -> None:
    if not output:
        return
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")


def _write_markdown(report: dict[str, Any], output: Optional[str]) -> None:
    _write_markdown_text(render_markdown_report(report), output)


def _validation_payload(loaded: LoadedSuiteManifest) -> dict[str, Any]:
    tasks_by_id = {item.id: item for item in loaded.manifest.tasks}
    return {
        "valid": True,
        "schema_version": loaded.manifest.schema_version,
        "suite_id": loaded.manifest.id,
        "benchmark_pack": (
            loaded.manifest.benchmark_pack.model_dump(mode="json")
            if loaded.manifest.benchmark_pack is not None
            else None
        ),
        "manifest_path": str(loaded.path),
        "manifest_sha256": loaded.sha256,
        "selected_tasks": [
            {
                "id": resource_id,
                "repository_path": str(
                    loaded.resolve_repository_path(tasks_by_id[resource_id])
                ),
                "base_commit": tasks_by_id[resource_id].base_commit.lower(),
                "category": tasks_by_id[resource_id].category,
                "difficulty": tasks_by_id[resource_id].difficulty,
                "tags": list(tasks_by_id[resource_id].tags),
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
        help="Optional file path for machine-readable JSON.",
    )
    parser.add_argument(
        "--markdown",
        help="Optional file path for human-readable Markdown.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbench",
        description=(
            "Reproducible local benchmarking, statistical comparison, and "
            "leaderboards for coding agents."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AgentBench {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack = subparsers.add_parser(
        "pack",
        help="Inspect or materialize built-in deterministic benchmark packs.",
    )
    pack_subparsers = pack.add_subparsers(dest="pack_command", required=True)
    pack_subparsers.add_parser("list", help="List built-in benchmark packs.")
    pack_show = pack_subparsers.add_parser(
        "show",
        help="Show one built-in pack and its tasks.",
    )
    pack_show.add_argument("pack_id")
    pack_preflight = pack_subparsers.add_parser(
        "preflight",
        help="Check task host requirements before materializing or running a pack.",
    )
    pack_preflight.add_argument("pack_id")
    pack_materialize = pack_subparsers.add_parser(
        "materialize",
        help="Create deterministic Git fixtures and a runnable suite manifest.",
    )
    pack_materialize.add_argument("pack_id")
    pack_materialize.add_argument(
        "--output",
        "-o",
        required=True,
        help="Empty output directory for the generated pack.",
    )
    pack_materialize.add_argument(
        "--agent",
        action="append",
        default=[],
        help=(
            "Agent definition in '<id>=<command template>' form. Repeat for "
            "multiple agents; command templates must contain {prompt}."
        ),
    )
    pack_materialize.add_argument(
        "--repetitions",
        type=int,
        default=5,
        help="Repeated trials per task/agent cell (default: 5).",
    )
    pack_materialize.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Locked local worker count for suite execution (1-32).",
    )
    pack_materialize.add_argument("--max-started-trials", type=int)
    pack_materialize.add_argument("--max-wall-seconds", type=int)
    pack_materialize.add_argument("--max-total-tokens", type=int)
    pack_materialize.add_argument("--max-orchestration-errors", type=int)

    preflight = subparsers.add_parser(
        "preflight",
        help="Check a materialized suite host, repositories, and agent executables.",
    )
    preflight.add_argument("manifest")

    validate = subparsers.add_parser(
        "validate",
        help="Validate a suite manifest without mutating local state.",
    )
    validate.add_argument("manifest")

    subparsers.add_parser(
        "doctor",
        help="Show the bounded environment identity used for reproducibility.",
    )

    serve = subparsers.add_parser(
        "serve",
        help="Run the local AgentBench dashboard and API.",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

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
        help="Resolve provenance, execute a suite, and export V2 analysis.",
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

    execute = subparsers.add_parser(
        "execute",
        help="Resume/execute a persisted experiment by ID.",
    )
    execute.add_argument("experiment_id", type=int)
    execute.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Bounded local worker count for independent trial execution (1-32).",
    )

    recover = subparsers.add_parser(
        "recover",
        help="Reset interrupted running trial claims to planned for explicit resume.",
    )
    recover.add_argument("experiment_id", type=int)
    recover.add_argument(
        "--confirm-inactive",
        action="store_true",
        help="Required acknowledgement that no worker process is still executing.",
    )

    worker = subparsers.add_parser(
        "worker",
        help="Run or inspect durable cross-process experiment workers.",
    )
    worker_subparsers = worker.add_subparsers(dest="worker_command", required=True)

    worker_register = worker_subparsers.add_parser(
        "register",
        help="Register this host's normalized capabilities for scheduling.",
    )
    worker_register.add_argument("experiment_id", type=int)
    worker_register.add_argument("--owner", required=True)
    worker_register.add_argument(
        "--label",
        action="append",
        default=[],
        help="Optional scheduling label to advertise. Repeat as needed.",
    )

    worker_queue = worker_subparsers.add_parser(
        "queue",
        help="Inspect planned work and capability matches.",
    )
    worker_queue.add_argument("experiment_id", type=int)

    worker_run = worker_subparsers.add_parser(
        "run",
        help="Claim and execute available trials with durable leases.",
    )
    worker_run.add_argument("experiment_id", type=int)
    worker_run.add_argument("--owner")
    worker_run.add_argument("--lease-seconds", type=int, default=60)
    worker_run.add_argument("--max-trials", type=int)

    worker_status = worker_subparsers.add_parser(
        "status",
        help="Inspect durable worker claims and lease state.",
    )
    worker_status.add_argument("experiment_id", type=int)

    worker_recover = worker_subparsers.add_parser(
        "recover-expired",
        help="Explicitly requeue expired durable worker claims.",
    )
    worker_recover.add_argument("experiment_id", type=int)
    worker_recover.add_argument("--grace-seconds", type=int, default=0)
    worker_recover.add_argument(
        "--confirm-expired",
        action="store_true",
        help="Required acknowledgement before requeueing expired worker claims.",
    )

    budget = subparsers.add_parser(
        "budget",
        help="Inspect durable experiment budget state.",
    )
    budget_subparsers = budget.add_subparsers(dest="budget_command", required=True)
    budget_status = budget_subparsers.add_parser(
        "status",
        help="Show budget policy, reservations, and exhaustion state.",
    )
    budget_status.add_argument("experiment_id", type=int)

    results = subparsers.add_parser(
        "results",
        help="Export aggregate results for an existing experiment ID.",
    )
    results.add_argument("experiment_id", type=int)
    _add_report_outputs(results)

    leaderboard = subparsers.add_parser(
        "leaderboard",
        help="Export the conservative ranking and pairwise task comparison.",
    )
    leaderboard.add_argument("experiment_id", type=int)
    _add_report_outputs(leaderboard)

    bundle = subparsers.add_parser(
        "bundle",
        help="Export, verify, inspect, or safely extract portable result bundles.",
    )
    bundle_subparsers = bundle.add_subparsers(dest="bundle_command", required=True)

    bundle_export = bundle_subparsers.add_parser(
        "export",
        help="Export one persisted experiment and its immutable artifacts.",
    )
    bundle_export.add_argument("experiment_id", type=int)
    bundle_export.add_argument("--output", "-o", required=True)

    bundle_verify = bundle_subparsers.add_parser(
        "verify",
        help="Verify bundle identity and every declared payload digest.",
    )
    bundle_verify.add_argument("bundle")

    bundle_inspect = bundle_subparsers.add_parser(
        "inspect",
        help="Verify a bundle and print its portable manifest/report.",
    )
    bundle_inspect.add_argument("bundle")

    bundle_extract = bundle_subparsers.add_parser(
        "extract",
        help="Verify then safely extract a bundle into an empty directory.",
    )
    bundle_extract.add_argument("bundle")
    bundle_extract.add_argument("--output", "-o", required=True)
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
    expected_lock_path = getattr(args, "lock", None)

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


def _experiment_report(
    service: SuiteService,
    experiment_id: int,
) -> dict[str, Any]:
    experiment = service.experiments.get_experiment(experiment_id)
    summary = service.experiments.aggregate_experiment(experiment_id)
    latest_execution = summary.get("latest_execution") or {}
    return {
        "report_schema_version": 8,
        "experiment": {
            "id": int(experiment.id),
            "name": experiment.name,
            "status": experiment.status,
            "repetitions": experiment.repetitions,
            "stop_on_error": experiment.stop_on_error,
            "max_workers": latest_execution.get("max_workers"),
            "execution_mode": latest_execution.get("mode"),
            "planned_runs": experiment.planned_runs,
        },
        "summary": summary,
    }


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

        if args.command == "execute":
            experiment = service.experiments.execute_experiment(
                args.experiment_id,
                max_workers=args.workers,
            )
            summary = service.experiments.aggregate_experiment(experiment.id)
            _write_json(
                {
                    "experiment": {
                        "id": int(experiment.id),
                        "name": experiment.name,
                        "status": experiment.status,
                        "planned_runs": experiment.planned_runs,
                    },
                    "summary": summary,
                }
            )
            return 0

        if args.command == "recover":
            if not args.confirm_inactive:
                raise ValueError(
                    "recover requires --confirm-inactive because resetting a live "
                    "worker claim can duplicate benchmark execution"
                )
            recovered = service.experiments.recover_running_trials(args.experiment_id)
            _write_json(
                {
                    "experiment_id": args.experiment_id,
                    "recovered_trials": recovered,
                }
            )
            return 0

        if args.command == "worker":
            workers = DistributedWorkerService(
                db,
                experiment_service=service.experiments,
            )
            if args.worker_command == "register":
                capabilities = workers.register_worker(
                    args.owner,
                    experiment_id=args.experiment_id,
                    labels=tuple(args.label),
                )
                _write_json(
                    {
                        "experiment_id": args.experiment_id,
                        "owner_id": args.owner,
                        "capabilities": capabilities.as_dict(),
                    }
                )
                return 0
            if args.worker_command == "queue":
                _write_json(workers.queue_status(args.experiment_id))
                return 0
            if args.worker_command == "run":
                _write_json(
                    workers.run_worker(
                        args.experiment_id,
                        owner_id=args.owner,
                        lease_seconds=args.lease_seconds,
                        max_trials=args.max_trials,
                    )
                )
                return 0
            if args.worker_command == "status":
                _write_json(workers.status(args.experiment_id))
                return 0
            if args.worker_command == "recover-expired":
                if not args.confirm_expired:
                    raise ValueError(
                        "worker recover-expired requires --confirm-expired because "
                        "a disconnected worker may still be executing"
                    )
                _write_json(
                    workers.recover_expired(
                        args.experiment_id,
                        grace_seconds=args.grace_seconds,
                    )
                )
                return 0
            raise ValueError(f"Unsupported worker command: {args.worker_command}")

        if args.command == "budget":
            budgets = ExperimentBudgetService(db)
            if args.budget_command == "status":
                _write_json(budgets.status(args.experiment_id))
                return 0
            raise ValueError(f"Unsupported budget command: {args.budget_command}")

        if args.command == "results":
            report = _experiment_report(service, args.experiment_id)
            _write_markdown(report, args.markdown)
            _write_json(report, args.output)
            return 0

        if args.command == "leaderboard":
            report = _experiment_report(service, args.experiment_id)
            summary = report["summary"]
            payload = {
                "analysis_schema_version": summary.get("analysis_schema_version", 8),
                "experiment": report["experiment"],
                "ranking": summary.get("ranking"),
                "pairwise_task_comparison": summary.get(
                    "pairwise_task_comparison",
                    [],
                ),
            }
            _write_markdown_text(
                render_leaderboard_markdown(
                    summary,
                    title=f"{report['experiment']['name']} Leaderboard",
                ),
                args.markdown,
            )
            _write_json(payload, args.output)
            return 0

        if args.command == "bundle" and args.bundle_command == "export":
            payload = ResultBundleService(db).export(
                args.experiment_id,
                args.output,
            )
            _write_json(payload)
            return 0

        raise ValueError(f"Unsupported database command: {args.command}")
    finally:
        close_session()


def _run_pack_command(args: argparse.Namespace) -> int:
    if args.pack_command == "list":
        _write_json({"packs": list_packs()})
        return 0

    if args.pack_command == "show":
        pack = get_pack(args.pack_id)
        payload = next(row for row in list_packs() if row["id"] == pack.id)
        _write_json(payload)
        return 0

    if args.pack_command == "preflight":
        payload = preflight_pack(args.pack_id)
        _write_json(payload)
        return 0 if payload["eligible"] else 3

    if args.pack_command == "materialize":
        agents = [parse_agent_spec(value) for value in args.agent]
        budget = {
            key: value
            for key, value in {
                "max_started_trials": args.max_started_trials,
                "max_wall_seconds": args.max_wall_seconds,
                "max_total_tokens": args.max_total_tokens,
                "max_orchestration_errors": args.max_orchestration_errors,
            }.items()
            if value is not None
        }
        result = materialize_pack(
            args.pack_id,
            args.output,
            agents=agents,
            repetitions=args.repetitions,
            max_workers=args.workers,
            budget=budget or None,
        )
        loaded = load_suite_manifest(result["manifest_path"])
        result["manifest_sha256"] = loaded.sha256
        result["schema_version"] = loaded.manifest.schema_version
        _write_json(result)
        return 0

    raise ValueError(f"Unsupported pack command: {args.pack_command}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "pack":
            return _run_pack_command(args)

        if args.command == "preflight":
            loaded = load_suite_manifest(args.manifest)
            payload = preflight_suite(loaded)
            _write_json(payload)
            return 0 if payload["ready"] else 3

        if args.command == "validate":
            loaded = load_suite_manifest(args.manifest)
            _write_json(_validation_payload(loaded))
            return 0

        if args.command == "doctor":
            _write_json({"status": "ok", "environment": environment_identity()})
            return 0

        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "agentbench.api:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
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

        if args.command == "bundle":
            if args.bundle_command == "verify":
                verified = verify_result_bundle(args.bundle)
                _write_json(
                    {
                        "valid": True,
                        "path": str(verified.path),
                        "identity_sha256": verified.identity_sha256,
                        "experiment": verified.manifest.get("experiment"),
                        "file_count": len(verified.manifest.get("files", [])),
                    }
                )
                return 0
            if args.bundle_command == "inspect":
                _write_json(inspect_result_bundle(args.bundle))
                return 0
            if args.bundle_command == "extract":
                _write_json(extract_result_bundle(args.bundle, args.output))
                return 0

        return _run_database_command(args)
    except (
        OSError,
        ValueError,
        ValidationError,
        ExperimentBusyError,
        ExperimentNotFoundError,
        BundleValidationError,
    ) as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "detail": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
