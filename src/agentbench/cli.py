"""Command-line product surface for AgentBench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

from pydantic import ValidationError

from . import __version__
from .adapters import create_adapter_registry
from .manifests import LoadedSuiteManifest, load_suite_manifest
from .models.session import close_session, get_session, init_db
from .packs import (
    compare_packs,
    get_pack,
    list_packs,
    materialize_pack,
    parse_agent_spec,
)
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
    pack_compare = pack_subparsers.add_parser(
        "compare",
        help="Explain semantic result compatibility between two pack versions.",
    )
    pack_compare.add_argument("left_pack_id")
    pack_compare.add_argument("right_pack_id")
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

    adapter = subparsers.add_parser(
        "adapter",
        help="Inspect registered coding-agent adapter profiles.",
    )
    adapter_subparsers = adapter.add_subparsers(
        dest="adapter_command",
        required=True,
    )
    adapter_subparsers.add_parser(
        "list",
        help="List adapter profiles and declared capabilities.",
    )
    adapter_show = adapter_subparsers.add_parser(
        "show",
        help="Show one adapter profile.",
    )
    adapter_show.add_argument("adapter_id")

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

    results = subparsers.add_parser(
        "results",
        help="Export aggregate V2 results for an existing experiment ID.",
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
    return {
        "report_schema_version": 3,
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
            report = _experiment_report(service, args.experiment_id)
            _write_markdown(report, args.markdown)
            _write_json(report, args.output)
            return 0

        if args.command == "leaderboard":
            report = _experiment_report(service, args.experiment_id)
            summary = report["summary"]
            payload = {
                "analysis_schema_version": summary.get("analysis_schema_version", 3),
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


def _run_adapter_command(args: argparse.Namespace) -> int:
    registry = create_adapter_registry(discover_plugins=True)
    if args.adapter_command == "list":
        _write_json(
            {
                "adapters": registry.catalog(),
                "providers": list(registry.provider_ids),
                "discovery_errors": list(registry.discovery_errors),
            }
        )
        return 0

    if args.adapter_command == "show":
        resolved = registry.get(args.adapter_id)
        row = next(
            item for item in registry.catalog()
            if item["id"] == resolved.profile.id
        )
        _write_json(row)
        return 0

    raise ValueError(f"Unsupported adapter command: {args.adapter_command}")


def _run_pack_command(args: argparse.Namespace) -> int:
    if args.pack_command == "list":
        _write_json({"packs": list_packs()})
        return 0

    if args.pack_command == "show":
        pack = get_pack(args.pack_id)
        payload = next(row for row in list_packs() if row["id"] == pack.id)
        _write_json(payload)
        return 0

    if args.pack_command == "compare":
        _write_json(compare_packs(args.left_pack_id, args.right_pack_id))
        return 0

    if args.pack_command == "materialize":
        agents = [parse_agent_spec(value) for value in args.agent]
        result = materialize_pack(
            args.pack_id,
            args.output,
            agents=agents,
            repetitions=args.repetitions,
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

        if args.command == "adapter":
            return _run_adapter_command(args)

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
