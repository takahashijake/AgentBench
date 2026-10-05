from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from agentbench.cli import _run_suite, main
from agentbench.manifests import load_suite_manifest
from agentbench.packs import materialize_pack
from agentbench.preflight import preflight_suite


def _agent(command: str) -> dict[str, str]:
    return {
        "id": "fixture",
        "description": "fixture",
        "command_template": command,
    }


def test_suite_preflight_accepts_ready_materialized_suite(tmp_path: Path):
    command = f'"{sys.executable}" -c "print(1)" {{prompt}}'
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "suite",
        agents=[_agent(command)],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    payload = preflight_suite(loaded)

    assert payload["ready"] is True
    assert payload["ready_task_count"] == 2
    assert payload["ready_agent_count"] == 1
    assert all(row["resolved_commit"] == row["base_commit"] for row in payload["tasks"])


def test_suite_preflight_reports_missing_agent_executable(tmp_path: Path):
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "missing-agent",
        agents=[_agent("agentbench-executable-that-does-not-exist {prompt}")],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])

    payload = preflight_suite(loaded)

    assert payload["ready"] is False
    assert payload["ready_task_count"] == 2
    assert payload["ready_agent_count"] == 0
    assert "not available on PATH" in payload["agents"][0]["reasons"][0]


@pytest.mark.parametrize(
    ("command", "expected_ready", "reason_fragment"),
    [
        (
            'qwen -p "{prompt}"',
            False,
            "does not explicitly enable unattended editing",
        ),
        (
            'qwen -p "{prompt}" --approval-mode auto-edit',
            True,
            None,
        ),
        (
            'codex exec "{prompt}"',
            False,
            "does not explicitly enable unattended workspace writes",
        ),
        (
            'codex exec --full-auto "{prompt}"',
            True,
            None,
        ),
    ],
)
def test_suite_preflight_checks_known_agent_automation_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    expected_ready: bool,
    reason_fragment: str | None,
):
    slug = command.split()[0] + ("-ready" if expected_ready else "-blocked")
    result = materialize_pack(
        "smoke-v2",
        tmp_path / slug,
        agents=[_agent(command)],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])
    monkeypatch.setattr(
        "agentbench.preflight.executable_identity",
        lambda _command: {
            "command": command.split()[0],
            "resolved_name": command.split()[0],
            "version": "fixture",
            "binary_sha256": "0" * 64,
        },
    )

    payload = preflight_suite(loaded)

    assert payload["ready"] is expected_ready
    assert payload["ready_agent_count"] == (1 if expected_ready else 0)
    if reason_fragment is None:
        assert payload["agents"][0]["reasons"] == []
    else:
        assert reason_fragment in payload["agents"][0]["reasons"][0]


def test_suite_preflight_cli_returns_machine_readable_status(tmp_path: Path, capsys):
    command = f'"{sys.executable}" -c "print(1)" {{prompt}}'
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "cli-suite",
        agents=[_agent(command)],
        repetitions=1,
    )

    assert main(["preflight", result["manifest_path"]]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is True
    assert payload["suite_id"] == "agentbench-smoke-v2"


def test_suite_preflight_reports_missing_task_repository(tmp_path: Path):
    command = f'"{sys.executable}" -c "print(1)" {{prompt}}'
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "missing-repo",
        agents=[_agent(command)],
        repetitions=1,
    )
    loaded = load_suite_manifest(result["manifest_path"])
    first_repo = loaded.resolve_repository_path(loaded.manifest.tasks[0])
    for candidate in sorted(first_repo.rglob("*"), reverse=True):
        if candidate.is_file() or candidate.is_symlink():
            candidate.unlink()
        elif candidate.is_dir():
            candidate.rmdir()
    first_repo.rmdir()

    payload = preflight_suite(loaded)

    assert payload["ready"] is False
    failed = next(
        row for row in payload["tasks"] if row["id"] == loaded.manifest.tasks[0].id
    )
    assert failed["ready"] is False
    assert "repository readiness failed" in failed["reasons"][0]


def test_run_suite_blocks_failed_agent_preflight_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    result = materialize_pack(
        "smoke-v2",
        tmp_path / "blocked-run",
        agents=[_agent('qwen -p "{prompt}"')],
        repetitions=1,
    )
    monkeypatch.setattr(
        "agentbench.preflight.executable_identity",
        lambda _command: {
            "command": "qwen",
            "resolved_name": "qwen",
            "version": "fixture",
            "binary_sha256": "0" * 64,
        },
    )

    class MustNotExecute:
        def execute_suite(self, _loaded):
            raise AssertionError(
                "suite execution must not start after failed preflight"
            )

    args = argparse.Namespace(
        manifest=result["manifest_path"],
        lock=None,
        write_lock=None,
        output=None,
        markdown=None,
    )

    assert _run_suite(args, MustNotExecute()) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_blocked"] is True
    assert payload["reason"] == "agent_preflight_failed"
    assert payload["preflight"]["agents"][0]["ready"] is False
    assert "unattended editing" in payload["preflight"]["agents"][0]["reasons"][0]
