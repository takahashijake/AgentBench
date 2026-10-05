from __future__ import annotations

import json
from pathlib import Path

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
    ExperimentTrial,
)
from agentbench.regression import (
    RegressionComparisonError,
    RegressionPolicy,
    compare_bundles,
    gate_bundles,
)
from agentbench.result_bundles import ResultBundleService


def build_regression_fixture(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    agent = AgentConfig(
        name="candidate-agent",
        command_template="python agent.py {prompt}",
        enabled=True,
    )
    db.add(agent)
    db.flush()

    task = BenchmarkTask(
        name="stable-task",
        description="stable benchmark task",
        repository_path=str(tmp_path),
        base_commit="a" * 40,
        agent_prompt="fix the stable task",
        test_command="pytest",
        timeout=60,
        enabled=True,
    )
    db.add(task)
    db.flush()

    artifact_dir = tmp_path / "regression-artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "manifest.json").write_text(
        '{"success": true}\n',
        encoding="utf-8",
    )

    run = BenchmarkRun(
        task_id=task.id,
        agent_config_id=agent.id,
        agent_name=agent.name,
        duration_seconds=1.0,
        exit_code=0,
        success=True,
        tests_passed=True,
        test_passed=1,
        test_failed=0,
        files_changed=1,
        insertions=1,
        deletions=0,
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
        name="regression fixture",
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
                "setup_command": None,
                "test_command": task.test_command,
                "timeout": task.timeout,
                "enabled": True,
                "requirements": {},
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
    return db, experiment, run


def export_baseline_and_degraded_candidate(tmp_path: Path):
    db, experiment, run = build_regression_fixture(tmp_path)
    service = ResultBundleService(db)
    baseline = tmp_path / "baseline.zip"
    candidate = tmp_path / "candidate.zip"

    service.export(experiment.id, baseline)

    run.success = False
    run.tests_passed = False
    run.test_passed = 0
    run.test_failed = 1
    run.duration_seconds = 2.0
    db.commit()

    service.export(experiment.id, candidate)
    return db, experiment, baseline, candidate


def test_compare_bundles_reports_agent_regressions(tmp_path: Path):
    _, _, baseline, candidate = export_baseline_and_degraded_candidate(tmp_path)

    comparison = compare_bundles(baseline, candidate)
    row = comparison["agents"][0]

    assert comparison["compatible"] is True
    assert comparison["task_fingerprint_sha256"]
    assert row["agent_name"] == "candidate-agent"
    assert row["baseline"]["success_rate"] == 1.0
    assert row["candidate"]["success_rate"] == 0.0
    assert row["deltas"]["success_rate"] == -1.0
    assert row["deltas"]["reliability_score"] < 0
    assert row["deltas"]["median_runtime_ratio"] == 2.0


def test_regression_gate_strict_fails_and_relaxed_policy_passes(tmp_path: Path):
    _, _, baseline, candidate = export_baseline_and_degraded_candidate(tmp_path)

    strict = gate_bundles(
        baseline,
        candidate,
        policy=RegressionPolicy(max_median_runtime_increase_ratio=0.25),
    )
    assert strict["passed"] is False
    assert {item["metric"] for item in strict["violations"]} == {
        "success_rate",
        "reliability_score",
        "median_runtime_seconds",
    }

    relaxed = gate_bundles(
        baseline,
        candidate,
        policy=RegressionPolicy(
            max_success_rate_drop=1.0,
            max_reliability_drop=1.0,
            max_median_runtime_increase_ratio=1.0,
        ),
    )
    assert relaxed["passed"] is True
    assert relaxed["violations"] == []


def test_regression_cli_uses_distinct_gate_exit_code(tmp_path: Path, capsys):
    _, _, baseline, candidate = export_baseline_and_degraded_candidate(tmp_path)

    assert main(["regression", "compare", str(baseline), str(candidate)]) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["compatible"] is True

    assert (
        main(
            [
                "regression",
                "gate",
                str(baseline),
                str(candidate),
                "--max-runtime-increase-ratio",
                "0.25",
            ]
        )
        == 4
    )
    gated = json.loads(capsys.readouterr().out)
    assert gated["passed"] is False


def test_regression_comparison_rejects_task_definition_drift(tmp_path: Path):
    db, experiment, _ = build_regression_fixture(tmp_path)
    # Export the baseline, then alter the frozen portable task definition.
    service = ResultBundleService(db)
    baseline_path = tmp_path / "stable.zip"
    service.export(experiment.id, baseline_path)

    snapshots = [dict(item) for item in experiment.task_snapshots]
    snapshots[0]["base_commit"] = "b" * 40
    experiment.task_snapshots = snapshots
    db.commit()
    changed_path = tmp_path / "changed.zip"
    service.export(experiment.id, changed_path)

    with pytest.raises(RegressionComparisonError, match="task definitions"):
        compare_bundles(baseline_path, changed_path)


def test_regression_comparison_rejects_mismatched_eligible_coverage(
    tmp_path: Path,
):
    db, experiment, _ = build_regression_fixture(tmp_path)
    service = ResultBundleService(db)
    baseline_path = tmp_path / "coverage-baseline.zip"
    candidate_path = tmp_path / "coverage-candidate.zip"
    service.export(experiment.id, baseline_path)

    trial = (
        db.query(ExperimentTrial)
        .filter(ExperimentTrial.experiment_id == experiment.id)
        .one()
    )
    trial.status = "skipped"
    trial.error = "resource requirements not satisfied"
    trial.benchmark_run_id = None
    db.commit()
    service.export(experiment.id, candidate_path)

    with pytest.raises(RegressionComparisonError, match="eligible-run coverage"):
        compare_bundles(baseline_path, candidate_path)
