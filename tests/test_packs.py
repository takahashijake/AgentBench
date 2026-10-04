from __future__ import annotations

import json
from pathlib import Path
import subprocess

from agentbench.cli import main
from agentbench.manifests import load_suite_manifest
from agentbench.packs import list_packs, materialize_pack, parse_agent_spec


AGENT = {
    "id": "fixture-agent",
    "description": "fixture",
    "command_template": 'python -c "print(123)" {prompt}',
}


def test_builtin_pack_catalog_has_portfolio_task_coverage():
    packs = {row["id"]: row for row in list_packs()}

    assert {"smoke-v2", "core-v2"} <= set(packs)
    core = packs["core-v2"]
    assert core["task_count"] == 4
    assert {task["category"] for task in core["tasks"]} == {
        "bugfix",
        "feature",
        "regression",
        "refactor",
    }


def test_pack_materialization_is_deterministic_and_manifest_is_v2(tmp_path: Path):
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
    assert loaded.manifest.schema_version == 2
    assert loaded.manifest.benchmark_pack.id == "smoke-v2"
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


def test_pack_fixtures_begin_unsolved(tmp_path: Path):
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
    assert main(
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
    ) == 0
    generated = json.loads(capsys.readouterr().out)
    assert generated["schema_version"] == 2
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
