"""Benchmark orchestration.

This module coordinates the major AgentBench boundaries:
1. isolated Git workspace creation
2. setup and agent execution
3. evidence capture before tests can mutate the workspace
4. bounded test execution
5. worktree cleanup
6. database persistence
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from ..adapters.base import AgentAdapter
from ..adapters.registry import AdapterRegistry, create_default_adapter_registry
from ..artifacts import RunArtifactStore
from ..evidence import capture_git_evidence
from ..execution import ProcessResult, run_shell_command
from ..models.database import AgentConfig, BenchmarkRun, BenchmarkTask
from ..provenance import capture_run_provenance
from ..timeutils import utc_now
from ..utils.git import (
    cleanup_git_worktree,
    create_git_worktree,
    get_git_commit,
    get_git_diff_stats,
    is_git_repository,
)


@dataclass(frozen=True)
class TestExecution:
    process: ProcessResult
    passed_count: int
    failed_count: int
    error: Optional[str]

    @property
    def passed(self) -> bool:
        return self.process.returncode == 0 and not self.process.timed_out


class BenchmarkService:
    """Execute benchmark tasks and persist reproducible evidence."""

    def __init__(
        self,
        db: Session,
        artifact_root: Optional[Path] = None,
        setup_timeout: int = 300,
        test_timeout: Optional[int] = None,
        adapter_registry: Optional[AdapterRegistry] = None,
    ):
        self.db = db
        self.artifact_root = artifact_root
        self.setup_timeout = setup_timeout
        self.test_timeout = test_timeout
        self.adapter_registry = adapter_registry or create_default_adapter_registry()

    def _resolve_agent_config_id(
        self,
        agent_config_id: Optional[int],
    ) -> Optional[int]:
        if agent_config_id is not None:
            agent_config = (
                self.db.query(AgentConfig)
                .filter(AgentConfig.id == agent_config_id)
                .first()
            )
            if agent_config is None:
                raise ValueError(f"Agent configuration not found: {agent_config_id}")
            if not agent_config.enabled:
                raise ValueError(f"Agent configuration is disabled: {agent_config_id}")
            return agent_config.id

        default_config = (
            self.db.query(AgentConfig)
            .filter(AgentConfig.enabled.is_(True))
            .order_by(AgentConfig.id.asc())
            .first()
        )
        return default_config.id if default_config is not None else None

    def create_agent_adapter(self, agent_config_id: Optional[int] = None) -> AgentAdapter:
        resolved_id = self._resolve_agent_config_id(agent_config_id)
        if resolved_id is None:
            config = {
                "name": "qwen",
                "model": "default",
                "command_template": "qwen -p {prompt}",
            }
        else:
            agent_config = (
                self.db.query(AgentConfig)
                .filter(AgentConfig.id == resolved_id)
                .one()
            )
            config = {
                "name": agent_config.name,
                "model": "default",
                "command_template": agent_config.command_template,
            }
        return self.adapter_registry.create(config)

    def verify_repository(self, repo_path: Path) -> str:
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not is_git_repository(repo_path):
            raise ValueError(f"Directory is not a git repository: {repo_path}")

        commit = get_git_commit(repo_path)
        if commit is None:
            raise ValueError(f"Unable to resolve repository HEAD: {repo_path}")
        return commit

    def get_diff_stats(
        self,
        repo_path: Path,
        base_commit: str,
    ) -> Tuple[int, int, int, str]:
        stats = get_git_diff_stats(repo_path, base_commit)
        return (
            int(stats.get("files_changed", 0)),
            int(stats.get("insertions", 0)),
            int(stats.get("deletions", 0)),
            str(stats.get("diffstat", "")),
        )

    def _run_setup(self, workspace_path: Path, setup_command: str) -> ProcessResult:
        return run_shell_command(
            setup_command,
            cwd=workspace_path,
            timeout=self.setup_timeout,
        )

    def execute_setup_command(
        self,
        workspace_path: Path,
        setup_command: str,
    ) -> Tuple[bool, str, str]:
        """Compatibility wrapper around bounded setup execution."""
        if not setup_command:
            return True, "", ""
        result = self._run_setup(workspace_path, setup_command)
        return (
            result.returncode == 0 and not result.timed_out,
            result.stdout,
            result.stderr,
        )

    @staticmethod
    def _parse_test_counts(stdout: str, stderr: str) -> tuple[int, int]:
        output = f"{stdout}\n{stderr}"
        passed_matches = re.findall(r"(\d+)\s+passed", output)
        failed_matches = re.findall(r"(\d+)\s+failed", output)
        if passed_matches or failed_matches:
            passed = int(passed_matches[-1]) if passed_matches else 0
            failed = int(failed_matches[-1]) if failed_matches else 0
            return passed, failed

        # Python unittest reports "Ran N tests" rather than pytest-style counts.
        ran_matches = re.findall(r"Ran\s+(\d+)\s+tests?", output)
        if not ran_matches:
            return 0, 0
        total = int(ran_matches[-1])
        failures = re.findall(r"failures=(\d+)", output)
        errors = re.findall(r"errors=(\d+)", output)
        failed = (
            (int(failures[-1]) if failures else 0)
            + (int(errors[-1]) if errors else 0)
        )
        if "OK" in output:
            failed = 0
        return max(total - failed, 0), failed

    def _run_tests_detailed(
        self,
        repo_path: Path,
        test_command: str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> TestExecution:
        working_dir = cwd or repo_path
        bounded_timeout = timeout or self.test_timeout or 300
        result = run_shell_command(
            test_command,
            cwd=working_dir,
            timeout=bounded_timeout,
        )
        passed_count, failed_count = self._parse_test_counts(
            result.stdout,
            result.stderr,
        )

        error: Optional[str] = None
        if result.timed_out:
            error = f"Test command timed out after {bounded_timeout} seconds"
        elif result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            error = detail[-8000:] if detail else f"Test command exited {result.returncode}"

        return TestExecution(
            process=result,
            passed_count=passed_count,
            failed_count=failed_count,
            error=error,
        )

    def run_tests(
        self,
        repo_path: Path,
        test_command: str,
        cwd: Optional[Path] = None,
    ) -> Tuple[bool, int, int, Optional[str]]:
        """Compatibility wrapper returning the historical four-value tuple."""
        execution = self._run_tests_detailed(
            repo_path,
            test_command,
            cwd=cwd,
            timeout=self.test_timeout,
        )
        return (
            execution.passed,
            execution.passed_count,
            execution.failed_count,
            execution.error,
        )

    @staticmethod
    def _write_phase_git_snapshot(
        artifact_store: RunArtifactStore,
        phase: str,
        workspace_path: Path,
        base_commit: str,
    ) -> None:
        status = subprocess.run(
            ["git", "status", "--short", "-uall"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
        )
        diff = subprocess.run(
            ["git", "diff", "--binary", base_commit, "--"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            check=False,
        )
        artifact_store.write_text(f"{phase}/git-status.txt", status.stdout)
        artifact_store.write_text(f"{phase}/diff.patch", diff.stdout)

    def execute_benchmark(
        self,
        task: BenchmarkTask,
        agent_config_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> BenchmarkRun:
        if not task.enabled:
            raise ValueError(f"Benchmark task is disabled: {task.id}")

        started_at = utc_now()
        requested_agent_config_id = (
            agent_config_id if agent_config_id is not None else task.agent_config_id
        )
        resolved_agent_config_id = self._resolve_agent_config_id(
            requested_agent_config_id
        )
        adapter = self.create_agent_adapter(resolved_agent_config_id)
        if agent_name:
            adapter.name = agent_name
        if model_name:
            adapter.model = model_name

        repo_path = Path(task.repository_path).resolve()
        original_commit = self.verify_repository(repo_path)
        artifact_store = RunArtifactStore.create(self.artifact_root, task_id=task.id)

        artifact_store.write_json(
            "task.json",
            {
                "task_id": task.id,
                "task_name": task.name,
                "repository_path": str(repo_path),
                "repository_head_at_start": original_commit,
                "base_commit": task.base_commit,
                "agent_prompt": task.agent_prompt,
                "setup_command": task.setup_command,
                "test_command": task.test_command,
                "agent_timeout_seconds": task.timeout,
                "setup_timeout_seconds": self.setup_timeout,
                "test_timeout_seconds": self.test_timeout or task.timeout,
                "agent_config_id": resolved_agent_config_id,
                "agent_name": adapter.name,
                "model_name": adapter.model,
                "adapter_type": str(adapter.config.get("adapter") or "shell"),
            },
        )

        worktree_path: Optional[Path] = None
        setup_result: Optional[ProcessResult] = None
        agent_result: Optional[ProcessResult] = None
        test_execution: Optional[TestExecution] = None
        evidence: Optional[dict[str, Any]] = None
        run_provenance: Optional[dict[str, Any]] = None
        evidence_attempted = False
        internal_error: Optional[str] = None
        cleanup_report: dict[str, Any] = {
            "success": True,
            "worktree_path": None,
            "errors": [],
        }

        try:
            run_provenance = capture_run_provenance(adapter.command_template)
            artifact_store.write_json("provenance.json", run_provenance)

            worktree_path = create_git_worktree(repo_path, task.base_commit)
            adapter.prepare(worktree_path, task.base_commit)

            setup_ok = True
            if task.setup_command:
                setup_result = self._run_setup(worktree_path, task.setup_command)
                artifact_store.write_text("setup/stdout.log", setup_result.stdout)
                artifact_store.write_text("setup/stderr.log", setup_result.stderr)
                self._write_phase_git_snapshot(
                    artifact_store,
                    "setup",
                    worktree_path,
                    task.base_commit,
                )
                setup_ok = setup_result.returncode == 0 and not setup_result.timed_out

            if setup_ok:
                exit_code, stdout, stderr = adapter.run_task(
                    task.agent_prompt,
                    task.timeout,
                )
                bounded_result = adapter.process_result()
                if bounded_result is not None:
                    agent_result = bounded_result
                else:
                    agent_result = ProcessResult(
                        returncode=exit_code,
                        stdout=stdout,
                        stderr=stderr,
                        timed_out=False,
                        duration_seconds=0.0,
                    )

                artifact_store.write_text("agent/stdout.log", stdout)
                artifact_store.write_text("agent/stderr.log", stderr)

                # Capture the agent workspace before tests can mutate it.
                evidence_attempted = True
                evidence = capture_git_evidence(
                    worktree_path,
                    task.base_commit,
                    artifact_store,
                )

                if task.test_command:
                    test_execution = self._run_tests_detailed(
                        repo_path,
                        task.test_command,
                        cwd=worktree_path,
                        timeout=self.test_timeout or task.timeout,
                    )
                    artifact_store.write_text(
                        "test/stdout.log",
                        test_execution.process.stdout,
                    )
                    artifact_store.write_text(
                        "test/stderr.log",
                        test_execution.process.stderr,
                    )
                    self._write_phase_git_snapshot(
                        artifact_store,
                        "test",
                        worktree_path,
                        task.base_commit,
                    )
            else:
                # Setup failures are benchmark evidence too.
                evidence_attempted = True
                evidence = capture_git_evidence(
                    worktree_path,
                    task.base_commit,
                    artifact_store,
                )

        except Exception as exc:
            internal_error = f"{type(exc).__name__}: {exc}"
            if worktree_path is not None and not evidence_attempted:
                evidence_attempted = True
                try:
                    evidence = capture_git_evidence(
                        worktree_path,
                        task.base_commit,
                        artifact_store,
                    )
                except Exception as evidence_exc:
                    internal_error += (
                        f"; evidence capture failed: "
                        f"{type(evidence_exc).__name__}: {evidence_exc}"
                    )
        finally:
            try:
                adapter.cleanup()
            except Exception as cleanup_exc:
                cleanup_report["errors"].append(
                    f"adapter cleanup failed: {type(cleanup_exc).__name__}: {cleanup_exc}"
                )

            if worktree_path is not None:
                worktree_cleanup = cleanup_git_worktree(worktree_path, repo_path)
                cleanup_report = {
                    "success": bool(worktree_cleanup.get("success"))
                    and not cleanup_report["errors"],
                    "worktree_path": worktree_cleanup.get("worktree_path"),
                    "errors": cleanup_report["errors"]
                    + list(worktree_cleanup.get("errors", [])),
                }

            artifact_store.write_json("cleanup.json", cleanup_report)

        ended_at = utc_now()
        duration = (ended_at - started_at).total_seconds()

        setup_failed = (
            setup_result is not None
            and (setup_result.returncode != 0 or setup_result.timed_out)
        )
        tests_requirement_met = (
            test_execution.passed if test_execution is not None else not bool(task.test_command)
        )
        agent_succeeded = (
            agent_result is not None
            and agent_result.returncode == 0
            and not agent_result.timed_out
        )

        success = (
            internal_error is None
            and not setup_failed
            and agent_succeeded
            and tests_requirement_met
            and bool(cleanup_report.get("success"))
        )

        if agent_result is not None:
            exit_code = agent_result.returncode
        elif setup_result is not None and setup_failed:
            exit_code = setup_result.returncode
        else:
            exit_code = -2 if internal_error else 1

        diff_metrics = (
            evidence.get("diff_stats", {})
            if evidence is not None
            else {
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "diffstat": "",
            }
        )

        stdout_path = (
            str(artifact_store.path_for("agent/stdout.log"))
            if artifact_store.path_for("agent/stdout.log").exists()
            else None
        )
        stderr_path = (
            str(artifact_store.path_for("agent/stderr.log"))
            if artifact_store.path_for("agent/stderr.log").exists()
            else None
        )

        adapter_metadata = adapter.collect_metadata()
        usage_metadata = adapter_metadata.get("usage", {}) or {}

        result_payload: Dict[str, Any] = {
            "artifact_directory": str(artifact_store.root),
            "adapter_metadata": adapter_metadata,
            "provenance": run_provenance,
            "repository_head_at_start": original_commit,
            "base_commit": task.base_commit,
            "final_commit": evidence.get("head_commit") if evidence else None,
            "workspace_status": evidence.get("status") if evidence else None,
            "workspace_diff_stats": diff_metrics,
            "git_evidence": evidence.get("paths") if evidence else None,
            "setup": {
                "command": task.setup_command,
                "returncode": setup_result.returncode if setup_result else None,
                "timed_out": setup_result.timed_out if setup_result else False,
                "stdout_path": (
                    str(artifact_store.path_for("setup/stdout.log"))
                    if artifact_store.path_for("setup/stdout.log").exists()
                    else None
                ),
                "stderr_path": (
                    str(artifact_store.path_for("setup/stderr.log"))
                    if artifact_store.path_for("setup/stderr.log").exists()
                    else None
                ),
            },
            "test": {
                "command": task.test_command,
                "returncode": (
                    test_execution.process.returncode if test_execution else None
                ),
                "timed_out": (
                    test_execution.process.timed_out if test_execution else False
                ),
                "stdout_path": (
                    str(artifact_store.path_for("test/stdout.log"))
                    if artifact_store.path_for("test/stdout.log").exists()
                    else None
                ),
                "stderr_path": (
                    str(artifact_store.path_for("test/stderr.log"))
                    if artifact_store.path_for("test/stderr.log").exists()
                    else None
                ),
            },
            "cleanup": cleanup_report,
            "internal_error": internal_error,
        }

        artifact_store.write_json(
            "manifest.json",
            {
                "success": success,
                "started_at": started_at.isoformat() + "Z",
                "ended_at": ended_at.isoformat() + "Z",
                "duration_seconds": duration,
                "exit_code": exit_code,
                "files_changed": int(diff_metrics.get("files_changed", 0)),
                "insertions": int(diff_metrics.get("insertions", 0)),
                "deletions": int(diff_metrics.get("deletions", 0)),
                "results": result_payload,
            },
        )

        run = BenchmarkRun(
            task_id=task.id,
            agent_config_id=resolved_agent_config_id,
            agent_name=adapter.name,
            model_name=adapter.model,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            exit_code=exit_code,
            success=success,
            test_command=task.test_command,
            test_passed=test_execution.passed_count if test_execution else 0,
            test_failed=test_execution.failed_count if test_execution else 0,
            test_error=test_execution.error if test_execution else None,
            tests_passed=test_execution.passed if test_execution else None,
            files_changed=int(diff_metrics.get("files_changed", 0)),
            insertions=int(diff_metrics.get("insertions", 0)),
            deletions=int(diff_metrics.get("deletions", 0)),
            diff_stats=str(diff_metrics.get("diffstat", "")),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            results=result_payload,
            prompt_tokens=usage_metadata.get("prompt_tokens"),
            completion_tokens=usage_metadata.get("completion_tokens"),
            total_tokens=usage_metadata.get("total_tokens"),
        )

        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run
