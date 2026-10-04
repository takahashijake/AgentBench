from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest
import yaml

from agentbench.manifests import load_suite_manifest
from agentbench.provenance import (
    build_suite_lock,
    load_suite_lock,
    verify_suite_lock,
    write_suite_lock,
)

from helpers import init_git_repo


def write_manifest(path: Path, repo: Path, commit: str) -> Path:
    payload = {
        "schema_version": 1,
        "id": "provenance-suite",
        "agents": [
            {
                "id": "python-agent",
                "command_template": shlex.join(
                    [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('answer.txt').write_text('ok')",
                    ]
                ),
            }
        ],
        "tasks": [
            {
                "id": "task",
                "description": "provenance fixture",
                "repository_path": repo.name,
                "base_commit": commit,
                "agent_prompt": "produce answer.txt",
                "test_command": "",
                "timeout": 5,
            }
        ],
        "experiment": {"repetitions": 1},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_suite_lock_is_deterministic_and_resolves_exact_inputs(tmp_path: Path):
    repo = tmp_path / "target"
    commit = init_git_repo(repo)
    manifest_path = write_manifest(tmp_path / "suite.yaml", repo, commit)
    loaded = load_suite_manifest(manifest_path)

    first = build_suite_lock(loaded)
    second = build_suite_lock(loaded)

    assert first["identity_sha256"] == second["identity_sha256"]
    assert first["tasks"][0]["resolved_base_commit"] == commit
    assert first["agents"][0]["executable"]["command"]
    assert first["agents"][0]["executable"]["binary_sha256"]
    assert first["environment"]["agentbench_version"] == "9.0.0"


def test_lock_round_trip_and_tamper_detection(tmp_path: Path):
    repo = tmp_path / "target"
    commit = init_git_repo(repo)
    loaded = load_suite_manifest(write_manifest(tmp_path / "suite.yaml", repo, commit))
    payload = build_suite_lock(loaded)
    lock_path = write_suite_lock(tmp_path / "suite.lock.json", payload)

    restored = load_suite_lock(lock_path)
    assert restored == payload

    tampered = json.loads(lock_path.read_text(encoding="utf-8"))
    tampered["experiment"]["repetitions"] = 99
    lock_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="identity is invalid"):
        load_suite_lock(lock_path)


def test_verify_reports_manifest_drift(tmp_path: Path):
    repo = tmp_path / "target"
    commit = init_git_repo(repo)
    manifest_path = write_manifest(tmp_path / "suite.yaml", repo, commit)
    loaded = load_suite_manifest(manifest_path)
    expected = build_suite_lock(loaded)

    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["tasks"][0]["agent_prompt"] = "changed prompt"
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    changed = load_suite_manifest(manifest_path)

    verification = verify_suite_lock(changed, expected)

    assert verification["valid"] is False
    assert verification["expected_identity_sha256"] == expected["identity_sha256"]
    assert any(row["path"] == "suite.manifest_sha256" for row in verification["drift"])
    assert any(row["path"] == "tasks" for row in verification["drift"])


def test_cli_lock_and_verify(tmp_path: Path, capsys):
    from agentbench.cli import main

    repo = tmp_path / "target"
    commit = init_git_repo(repo)
    manifest_path = write_manifest(tmp_path / "suite.yaml", repo, commit)
    lock_path = tmp_path / "suite.lock.json"

    assert main(["lock", str(manifest_path), "-o", str(lock_path)]) == 0
    lock_output = json.loads(capsys.readouterr().out)
    assert lock_output["locked"] is True
    assert lock_path.is_file()

    assert main(["verify", str(manifest_path), str(lock_path)]) == 0
    verify_output = json.loads(capsys.readouterr().out)
    assert verify_output["valid"] is True
    assert verify_output["drift"] == []


def test_worker_count_is_locked_and_reported_as_replay_drift(tmp_path: Path):
    repo = tmp_path / "parallel-target"
    commit = init_git_repo(repo)
    manifest_path = write_manifest(tmp_path / "parallel-suite.yaml", repo, commit)

    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 5
    payload["experiment"]["max_workers"] = 2
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    loaded = load_suite_manifest(manifest_path)
    expected = build_suite_lock(loaded)
    assert expected["lock_schema_version"] == 4
    assert expected["experiment"]["max_workers"] == 2

    payload["experiment"]["max_workers"] = 3
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    changed = load_suite_manifest(manifest_path)
    verification = verify_suite_lock(changed, expected)

    assert verification["valid"] is False
    assert any(row["path"] == "experiment.max_workers" for row in verification["drift"])
