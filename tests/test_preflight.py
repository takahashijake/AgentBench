from __future__ import annotations

import json
import sys
from pathlib import Path

from agentbench.cli import main
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
