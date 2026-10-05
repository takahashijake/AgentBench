from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.api.routers.runs import create_run
from agentbench.models.database import AgentConfig, Base, BenchmarkRun, BenchmarkTask
from agentbench.schemas import BenchmarkRunCreate
from agentbench.services.benchmark import BenchmarkService

from helpers import init_git_repo


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def worktree_count(repo: Path) -> int:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return sum(1 for line in result.stdout.splitlines() if line.startswith("worktree "))


def test_full_benchmark_isolated_preserves_agent_file_and_cleans_worktree(
    tmp_path: Path,
):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent_code = "from pathlib import Path; Path('created.txt').write_text('hello')"
    agent = AgentConfig(
        name="fixture-agent",
        command_template=shlex.join([sys.executable, "-c", agent_code]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    test_code = (
        "from pathlib import Path; "
        "raise SystemExit(0 if Path('created.txt').read_text() == 'hello' else 1)"
    )
    task = BenchmarkTask(
        name="create file",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="create the fixture file",
        test_command=shlex.join([sys.executable, "-c", test_code]),
        timeout=5,
        agent_config_id=agent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    service = BenchmarkService(
        db,
        artifact_root=tmp_path / "artifacts",
        setup_timeout=2,
        test_timeout=2,
    )
    run = service.execute_benchmark(task)

    assert run.success is True
    assert run.agent_config_id == agent.id
    assert run.tests_passed is True
    assert run.files_changed == 1
    assert run.insertions == 1
    assert run.results["cleanup"]["success"] is True

    artifact_dir = Path(run.results["artifact_directory"])
    assert (artifact_dir / "manifest.json").is_file()
    assert (artifact_dir / "agent" / "stdout.log").is_file()
    assert (artifact_dir / "provenance.json").is_file()
    assert run.results["provenance"]["environment"]["agentbench_version"] == "10.0.0"
    assert run.results["provenance"]["agent_executable"]["binary_sha256"]
    assert (artifact_dir / "git" / "untracked" / "created.txt").read_text(
        encoding="utf-8"
    ) == "hello"

    assert not (repo / "created.txt").exists()
    assert not (repo / "runs").exists()
    status = subprocess.run(
        ["git", "status", "--short", "-uall"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip() == ""
    assert worktree_count(repo) == 1


def test_setup_failure_is_preserved_and_agent_does_not_run(tmp_path: Path):
    repo = tmp_path / "target"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent_code = "from pathlib import Path; Path('should-not-exist').write_text('bad')"
    agent = AgentConfig(
        name="fixture-agent",
        command_template=shlex.join([sys.executable, "-c", agent_code]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    setup_code = "import sys; print('setup failed'); sys.exit(7)"
    task = BenchmarkTask(
        name="setup failure",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="this must not run",
        setup_command=shlex.join([sys.executable, "-c", setup_code]),
        test_command="pytest -q",
        timeout=5,
        agent_config_id=agent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    service = BenchmarkService(
        db,
        artifact_root=tmp_path / "artifacts",
        setup_timeout=2,
        test_timeout=2,
    )
    run = service.execute_benchmark(task, agent_config_id=agent.id)

    assert run.success is False
    assert run.exit_code == 7
    artifact_dir = Path(run.results["artifact_directory"])
    assert "setup failed" in (artifact_dir / "setup" / "stdout.log").read_text(
        encoding="utf-8"
    )
    assert not (artifact_dir / "agent" / "stdout.log").exists()
    assert not (repo / "should-not-exist").exists()
    assert worktree_count(repo) == 1


def test_disabled_task_and_agent_are_rejected(tmp_path: Path):
    import pytest

    repo = tmp_path / "target-disabled"
    base_commit = init_git_repo(repo)
    db = make_session()

    agent = AgentConfig(
        name="disabled-agent",
        enabled=False,
        command_template=shlex.join([sys.executable, "-c", "print('no')"]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    disabled_task = BenchmarkTask(
        name="disabled task",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="do not run",
        test_command="",
        timeout=5,
        enabled=False,
    )
    db.add(disabled_task)
    db.commit()
    db.refresh(disabled_task)

    service = BenchmarkService(db, artifact_root=tmp_path / "artifacts")

    with pytest.raises(ValueError, match="task is disabled"):
        service.execute_benchmark(disabled_task)

    enabled_task = BenchmarkTask(
        name="enabled task",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="do not run",
        test_command="",
        timeout=5,
        enabled=True,
        agent_config_id=agent.id,
    )
    db.add(enabled_task)
    db.commit()
    db.refresh(enabled_task)

    with pytest.raises(ValueError, match="configuration is disabled"):
        service.execute_benchmark(enabled_task)


def test_structured_agent_usage_is_persisted_on_run(tmp_path: Path):
    repo = tmp_path / "target-usage"
    base_commit = init_git_repo(repo)
    db = make_session()

    usage_line = '{"usage":{"input_tokens":42,"output_tokens":17,"total_tokens":59}}'
    agent = AgentConfig(
        name="usage-agent",
        command_template=shlex.join([sys.executable, "-c", f"print({usage_line!r})"]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    task = BenchmarkTask(
        name="usage task",
        description="fixture",
        repository_path=str(repo),
        base_commit=base_commit,
        agent_prompt="report structured usage",
        test_command="",
        timeout=5,
        agent_config_id=agent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    run = BenchmarkService(
        db,
        artifact_root=tmp_path / "artifacts",
    ).execute_benchmark(task)

    assert run.success is True
    assert run.prompt_tokens == 42
    assert run.completion_tokens == 17
    assert run.total_tokens == 59
    metadata = run.results["adapter_metadata"]
    assert metadata["agent_family"] == "shell"
    assert metadata["usage"]["source"] == "structured_json_output"


def test_unittest_output_counts_are_parsed():
    stdout = ""
    stderr = "Ran 5 tests in 0.001s\n\nFAILED (failures=1, errors=1)"
    passed, failed = BenchmarkService._parse_test_counts(stdout, stderr)

    assert passed == 3
    assert failed == 2


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("1 passed, 2 errors in 0.10s", (1, 2)),
        ("2 passed, 1 failed, 3 errors in 0.10s", (2, 4)),
        ("1 error in 0.10s", (0, 1)),
    ],
)
def test_pytest_error_counts_are_included_in_failed_metrics(
    output: str,
    expected: tuple[int, int],
):
    assert BenchmarkService._parse_test_counts(output, "") == expected


def test_direct_benchmark_rejects_known_agent_without_unattended_mode(tmp_path: Path):
    db = make_session()
    agent = AgentConfig(
        name="unsafe-qwen",
        command_template='qwen -p "{prompt}"',
    )
    db.add(agent)
    db.flush()
    task = BenchmarkTask(
        name="unsafe direct run",
        description="fixture",
        repository_path=str(tmp_path / "must-not-be-touched"),
        base_commit="0" * 40,
        agent_prompt="edit the repository",
        test_command="",
        timeout=5,
        agent_config_id=agent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    service = BenchmarkService(db, artifact_root=tmp_path / "artifacts")

    with pytest.raises(ValueError, match="not automation-ready"):
        service.execute_benchmark(task, agent_config_id=agent.id)

    assert db.query(BenchmarkRun).count() == 0
    assert not (tmp_path / "must-not-be-touched").exists()


def test_known_agent_explicit_automation_mode_is_accepted_by_adapter_boundary():
    db = make_session()
    agent = AgentConfig(
        name="automation-qwen",
        command_template='qwen -p "{prompt}" --approval-mode auto-edit',
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    adapter = BenchmarkService(db).create_agent_adapter(agent.id)

    assert adapter.command_template == agent.command_template


def test_api_run_returns_400_for_non_automation_ready_known_agent(tmp_path: Path):
    db = make_session()
    agent = AgentConfig(
        name="unsafe-codex",
        command_template='codex exec "{prompt}"',
    )
    db.add(agent)
    db.flush()
    task = BenchmarkTask(
        name="unsafe api run",
        description="fixture",
        repository_path=str(tmp_path / "must-not-be-touched"),
        base_commit="0" * 40,
        agent_prompt="edit the repository",
        test_command="",
        timeout=5,
        agent_config_id=agent.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    with pytest.raises(HTTPException) as caught:
        create_run(
            BenchmarkRunCreate(
                task_id=int(task.id),
                agent_config_id=int(agent.id),
            ),
            db,
        )

    assert caught.value.status_code == 400
    assert "not automation-ready" in str(caught.value.detail)
    assert db.query(BenchmarkRun).count() == 0
