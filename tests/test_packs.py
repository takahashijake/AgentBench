from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.cli import main
from agentbench.manifests import load_suite_manifest
from agentbench.models.database import Base
from agentbench.packs import (
    list_packs,
    materialize_pack,
    parse_agent_spec,
    preflight_pack,
)
from agentbench.provenance import build_suite_lock
from agentbench.services.suite import SuiteService


AGENT = {
    "id": "fixture-agent",
    "description": "fixture",
    "command_template": 'python -c "print(123)" {prompt}',
}


def test_builtin_pack_catalog_has_portfolio_task_coverage():
    packs = {row["id"]: row for row in list_packs()}

    assert {"smoke-v2", "core-v2", "core-v3", "engineering-v4"} <= set(packs)
    core = packs["core-v2"]
    assert core["task_count"] == 4
    assert core["provider"] == "agentbench.builtin"
    assert packs["core-v3"]["task_count"] == 8
    assert packs["core-v3"]["provider"] == "agentbench.builtin"
    assert packs["engineering-v4"]["task_count"] == 12
    assert packs["engineering-v4"]["provider"] == "agentbench.builtin"
    assert all("requirements" in task for task in packs["engineering-v4"]["tasks"])
    assert {task["category"] for task in core["tasks"]} == {
        "bugfix",
        "feature",
        "regression",
        "refactor",
    }


def test_pack_materialization_is_deterministic_and_manifest_is_v5(tmp_path: Path):
    first = materialize_pack(
        "smoke-v2",
        tmp_path / "first",
        agents=[AGENT],
        repetitions=3,
    )
    second = materialize_pack(
        "smoke-v2",
        tmp_path / "second",
        agents=[AGENT],
        repetitions=3,
    )

    assert first["commits"] == second["commits"]
    assert first["planned_runs"] == 6

    loaded = load_suite_manifest(first["manifest_path"])
    assert loaded.manifest.schema_version == 5
    assert loaded.manifest.benchmark_pack.id == "smoke-v2"
    assert loaded.manifest.benchmark_pack.provider == "agentbench.builtin"
    assert loaded.manifest.experiment.repetitions == 3
    assert {task.category for task in loaded.manifest.tasks} == {"bugfix", "feature"}

    for task in loaded.manifest.tasks:
        repo = loaded.resolve_repository_path(task)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert head == task.base_commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert status == ""


def test_smoke_pack_fixtures_begin_unsolved(tmp_path: Path):
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "pack",
        agents=[AGENT],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    returncodes = []
    for task in loaded.manifest.tasks:
        completed = subprocess.run(
            ["python", "-m", "unittest", "-q"],
            cwd=loaded.resolve_repository_path(task),
            capture_output=True,
            text=True,
            check=False,
        )
        returncodes.append(completed.returncode)

    assert all(code != 0 for code in returncodes)


def test_pack_cli_lists_and_materializes(tmp_path: Path, capsys):
    assert main(["pack", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(pack["id"] == "core-v2" for pack in listed["packs"])

    output = tmp_path / "generated"
    assert (
        main(
            [
                "pack",
                "materialize",
                "smoke-v2",
                "--output",
                str(output),
                "--agent",
                'fixture=python -c "print(1)" {prompt}',
                "--repetitions",
                "2",
            ]
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    assert generated["schema_version"] == 5
    assert generated["planned_runs"] == 4
    assert (output / "suite.yaml").is_file()


def test_agent_spec_requires_prompt_placeholder():
    parsed = parse_agent_spec('qwen=qwen -p "{prompt}"')
    assert parsed["id"] == "qwen"

    try:
        parse_agent_spec("bad=qwen -p fixed")
    except ValueError as exc:
        assert "{prompt}" in str(exc)
    else:
        raise AssertionError("missing prompt placeholder was accepted")


def test_pack_metadata_flows_into_lock_and_suite_report(tmp_path: Path):
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "pack-metadata",
        agents=[AGENT],
        repetitions=2,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    lock = build_suite_lock(loaded)
    assert lock["suite"]["schema_version"] == 5
    assert lock["suite"]["benchmark_pack"]["id"] == "smoke-v2"
    assert lock["suite"]["benchmark_pack"]["version"] == "2.0.0"
    assert lock["suite"]["benchmark_pack"]["provider"] == "agentbench.builtin"
    assert {task["category"] for task in lock["tasks"]} == {"bugfix", "feature"}
    assert all(task["tags"] for task in lock["tasks"])

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    service = SuiteService(db, artifact_root=tmp_path / "artifacts")
    imported = service.import_suite(loaded)
    experiment = service.create_experiment(loaded, imported)
    report = service.build_report(
        loaded,
        imported,
        experiment,
        {"analysis_schema_version": 3, "overall": {}},
    )

    assert report["report_schema_version"] == 5
    assert report["suite"]["benchmark_pack"]["id"] == "smoke-v2"
    assert report["suite"]["schema_version"] == 5
    assert {task["category"] for task in report["resources"]["tasks"]} == {
        "bugfix",
        "feature",
    }


def test_smoke_pack_executes_end_to_end_through_canonical_services(tmp_path: Path):
    solver_code = """
from pathlib import Path
duration = Path("duration.py")
if duration.exists():
    duration.write_text(
        duration.read_text(encoding="utf-8").replace('"ms": 1.0', '"ms": 0.001'),
        encoding="utf-8",
    )
else:
    Path("slug.py").write_text(
        'import re\\n\\ndef slugify(text: str) -> str:\\n'
        '    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")\\n',
        encoding="utf-8",
    )
""".strip()
    solver = {
        "id": "deterministic-solver",
        "description": "test-only fixture agent",
        "command_template": (
            shlex.join([sys.executable, "-c", solver_code]) + " {prompt}"
        ),
    }
    materialized = materialize_pack(
        "smoke-v2",
        tmp_path / "executable-pack",
        agents=[solver],
        repetitions=1,
    )
    loaded = load_suite_manifest(materialized["manifest_path"])

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    service = SuiteService(
        db,
        artifact_root=tmp_path / "execution-artifacts",
        setup_timeout=2,
        test_timeout=5,
    )

    imported, experiment, summary = service.execute_suite(loaded)

    assert experiment.status == "completed"
    assert summary["overall"]["planned_runs"] == 2
    assert summary["overall"]["successful_runs"] == 2
    assert summary["overall"]["tests_passed"] == 10
    assert summary["overall"]["orchestration_errors"] == 0
    assert summary["ranking"]["entries"][0]["agent_name"].endswith(
        "/deterministic-solver"
    )
    assert summary["ranking"]["entries"][0]["success_rate"] == 1.0
    assert len(imported.task_ids) == 2


def test_engineering_v4_preflight_and_materialization_include_requirements(
    tmp_path: Path,
):
    preflight = preflight_pack("engineering-v4")

    assert preflight["eligible"] is True
    assert preflight["task_count"] == 12
    assert preflight["ineligible_task_count"] == 0

    result = materialize_pack(
        "engineering-v4",
        tmp_path / "engineering-v4",
        agents=[AGENT],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    assert loaded.manifest.schema_version == 5
    assert loaded.manifest.benchmark_pack.id == "engineering-v4"
    assert len(loaded.manifest.tasks) == 12
    by_id = {task.id: task for task in loaded.manifest.tasks}
    assert by_id["feature-bounded-retry"].requirements.required_commands == ["python"]
    assert by_id["feature-bounded-retry"].requirements.min_memory_mb == 64


def test_pack_preflight_cli_is_machine_readable(capsys):
    assert main(["pack", "preflight", "engineering-v4"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["pack_id"] == "engineering-v4"
    assert payload["eligible"] is True
    assert payload["task_count"] == 12


def test_engineering_v4_fixtures_begin_unsolved(tmp_path: Path):
    result = materialize_pack(
        "engineering-v4",
        tmp_path / "engineering-unsolved",
        agents=[AGENT],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    returncodes = {}
    for task in loaded.manifest.tasks:
        completed = subprocess.run(
            ["python", "-m", "unittest", "-q"],
            cwd=loaded.resolve_repository_path(task),
            capture_output=True,
            text=True,
            check=False,
        )
        returncodes[task.id] = completed.returncode

    assert len(returncodes) == 12
    assert all(code != 0 for code in returncodes.values())
