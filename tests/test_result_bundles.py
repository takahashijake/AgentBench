from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.cli import main
from agentbench.models.database import (
    AgentConfig,
    Base,
    BenchmarkRun,
    BenchmarkTask,
    Experiment,
    ExperimentExecution,
    ExperimentTrial,
)
from agentbench.publication import (
    PublicationValidationError,
    publish_bundle,
    publish_experiment,
    verify_publication,
)
from agentbench.result_bundles import (
    BundleValidationError,
    ResultBundleService,
    extract_result_bundle,
    inspect_result_bundle,
    verify_result_bundle,
)


def make_bundle_session(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    agent = AgentConfig(
        name="bundle-agent", command_template="python agent.py {prompt}"
    )
    db.add(agent)
    db.flush()

    task = BenchmarkTask(
        name="bundle-task",
        description="fixture",
        repository_path=str(tmp_path),
        base_commit="a" * 40,
        agent_prompt="fix it",
        test_command="pytest",
        timeout=60,
    )
    db.add(task)
    db.flush()

    artifact_dir = tmp_path / "run-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "manifest.json").write_text(
        json.dumps({"success": True}),
        encoding="utf-8",
    )
    nested = artifact_dir / "git"
    nested.mkdir()
    (nested / "diff.patch").write_text("+fixed\n", encoding="utf-8")

    run = BenchmarkRun(
        task_id=task.id,
        agent_config_id=agent.id,
        agent_name="bundle-agent",
        duration_seconds=1.5,
        exit_code=0,
        success=True,
        test_passed=2,
        test_failed=0,
        tests_passed=True,
        files_changed=1,
        insertions=1,
        deletions=0,
        total_tokens=100,
        results={
            "artifact_directory": str(artifact_dir),
            "base_commit": "a" * 40,
            "workspace_diff_stats": {
                "files_changed": 1,
                "insertions": 1,
                "deletions": 0,
            },
        },
    )
    db.add(run)
    db.flush()

    experiment = Experiment(
        name="bundle experiment",
        description="portable evidence fixture",
        repetitions=1,
        stop_on_error=False,
        status="completed",
        task_ids=[task.id],
        agent_config_ids=[agent.id],
        task_snapshots=[
            {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "repository_path": task.repository_path,
                "base_commit": task.base_commit,
                "agent_prompt": task.agent_prompt,
                "setup_command": task.setup_command,
                "test_command": task.test_command,
                "timeout": task.timeout,
                "enabled": True,
            }
        ],
        agent_snapshots=[
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "command_template": agent.command_template,
                "enabled": True,
            }
        ],
        planned_runs=1,
    )
    db.add(experiment)
    db.flush()

    execution = ExperimentExecution(
        experiment_id=experiment.id,
        mode="local_parallel",
        max_workers=4,
        status="completed",
        details={"planned_for_attempt": 1},
    )
    db.add(execution)
    db.flush()

    trial = ExperimentTrial(
        experiment_id=experiment.id,
        task_id=task.id,
        agent_config_id=agent.id,
        repetition=1,
        ordinal=1,
        status="completed",
        benchmark_run_id=run.id,
    )
    db.add(trial)
    db.commit()
    db.refresh(experiment)
    return db, experiment


def test_result_bundle_is_deterministic_and_verifiable(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    service = ResultBundleService(db)

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    one = service.export(experiment.id, first)
    two = service.export(experiment.id, second)

    assert one["identity_sha256"] == two["identity_sha256"]
    assert first.read_bytes() == second.read_bytes()

    verified = verify_result_bundle(first)
    assert verified.identity_sha256 == one["identity_sha256"]
    assert verified.report["report_schema_version"] == 7
    assert verified.report["experiment"]["id"] == experiment.id
    with zipfile.ZipFile(first, "r") as archive:
        experiment_doc = json.loads(archive.read("experiment.json"))
    serialized = json.dumps(experiment_doc)
    assert str(tmp_path) not in serialized
    run_results = experiment_doc["trials"][0]["benchmark_run"]["results"]
    assert run_results["artifact_bundle_prefix"] == "artifacts/run-1/"
    assert run_results["git_evidence"]["patch"] == "artifacts/run-1/git/diff.patch"
    assert "repository_path" not in experiment_doc["task_snapshots"][0]
    assert "command_template" not in experiment_doc["agent_snapshots"][0]
    assert experiment_doc["executions"][0]["mode"] == "local_parallel"
    assert experiment_doc["executions"][0]["max_workers"] == 4
    assert experiment_doc["executions"][0]["details"]["planned_for_attempt"] == 1

    inspected = inspect_result_bundle(first)
    assert inspected["valid"] is True
    assert inspected["manifest"]["experiment"]["name"] == "bundle experiment"


def test_bundle_extract_verifies_before_writing(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "bundle.zip"
    ResultBundleService(db).export(experiment.id, bundle)

    destination = tmp_path / "imported"
    result = extract_result_bundle(bundle, destination)

    assert result["extracted"] is True
    assert (destination / "bundle.json").is_file()
    assert (destination / "report.json").is_file()
    assert (destination / "artifacts" / "run-1" / "git" / "diff.patch").read_text(
        encoding="utf-8"
    ) == "+fixed\n"


def test_bundle_verifier_rejects_duplicate_or_tampered_payload(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "bundle.zip"
    ResultBundleService(db).export(experiment.id, bundle)

    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("report.json", b'{"tampered":true}')

    with pytest.raises(BundleValidationError, match="duplicate"):
        verify_result_bundle(bundle)


def test_bundle_verifier_rejects_path_traversal_before_extraction(tmp_path: Path):
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.txt", "bad")
        archive.writestr("bundle.json", "{}")

    with pytest.raises(BundleValidationError, match="Unsafe"):
        verify_result_bundle(bundle)


def test_bundle_cli_verify_and_inspect(tmp_path: Path, capsys):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "bundle.zip"
    ResultBundleService(db).export(experiment.id, bundle)

    assert main(["bundle", "verify", str(bundle)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True

    assert main(["bundle", "inspect", str(bundle)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["report"]["experiment"]["name"] == "bundle experiment"


def test_static_publication_is_deterministic_and_verifiable(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "source.zip"
    ResultBundleService(db).export(experiment.id, bundle)

    first = tmp_path / "site-a"
    second = tmp_path / "site-b"
    one = publish_bundle(bundle, first)
    two = publish_bundle(bundle, second)

    assert one["identity_sha256"] == two["identity_sha256"]
    for name in ("index.html", "report.json", "publication.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    verified = verify_publication(first)
    assert verified.identity_sha256 == one["identity_sha256"]
    assert (
        verified.manifest["source_bundle_identity_sha256"]
        == verify_result_bundle(bundle).identity_sha256
    )
    assert verified.report["experiment"]["name"] == "bundle experiment"

    rendered = (first / "index.html").read_text(encoding="utf-8")
    assert "bundle experiment" in rendered
    assert "external JavaScript" in rendered
    assert str(tmp_path) not in rendered


def test_static_publication_from_experiment_uses_bundle_semantics(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    site = tmp_path / "experiment-site"

    published = publish_experiment(db, experiment.id, site)
    verified = verify_publication(site)

    assert published["published"] is True
    assert published["source_bundle_identity_sha256"]
    assert verified.report["experiment"]["id"] == experiment.id
    assert (site / "report.json").is_file()


def test_publication_verifier_rejects_tampering_and_undeclared_files(tmp_path: Path):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "publication-source.zip"
    ResultBundleService(db).export(experiment.id, bundle)

    tampered = tmp_path / "tampered-site"
    publish_bundle(bundle, tampered)
    (tampered / "index.html").write_text("tampered", encoding="utf-8")
    with pytest.raises(PublicationValidationError, match="(?:Size|Digest) mismatch"):
        verify_publication(tampered)

    extra = tmp_path / "extra-site"
    publish_bundle(bundle, extra)
    (extra / "secret.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(PublicationValidationError, match="undeclared"):
        verify_publication(extra)

    nested = tmp_path / "nested-site"
    publish_bundle(bundle, nested)
    assets = nested / "assets"
    assets.mkdir()
    (assets / "script.js").write_text("unexpected", encoding="utf-8")
    with pytest.raises(PublicationValidationError, match="undeclared"):
        verify_publication(nested)


def test_publication_cli_bundle_and_verify(tmp_path: Path, capsys):
    db, experiment = make_bundle_session(tmp_path)
    bundle = tmp_path / "cli-publication.zip"
    ResultBundleService(db).export(experiment.id, bundle)
    site = tmp_path / "cli-site"

    assert main(["publish", "bundle", str(bundle), "--output", str(site)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["published"] is True

    assert main(["publish", "verify", str(site)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["experiment"]["name"] == "bundle experiment"
