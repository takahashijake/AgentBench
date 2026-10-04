"""Benchmark execution service."""

import subprocess
import shutil
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session

from ..adapters.base import AgentAdapter, ShellAgentAdapter
from ..models.database import BenchmarkRun, BenchmarkTask, AgentConfig
from ..utils.git import (
    get_git_commit,
    get_git_status,
    get_git_diff_stats,
    create_git_worktree,
    cleanup_git_worktree,
)


class BenchmarkService:
    """Service for executing benchmark tasks."""
    
    def __init__(self, db: Session):
        """Initialize the benchmark service.
        
        Args:
            db: Database session.
        """
        self.db = db
    
    def create_agent_adapter(self, agent_config_id: Optional[int] = None) -> AgentAdapter:
        """Create an agent adapter from configuration.
        
        Args:
            agent_config_id: ID of the agent configuration, or None for default.
            
        Returns:
            Configured agent adapter instance.
        """
        if agent_config_id:
            agent_config = self.db.query(AgentConfig).filter(
                AgentConfig.id == agent_config_id
            ).first()
        else:
            agent_config = self.db.query(AgentConfig).first()
        
        if not agent_config:
            # Default to shell adapter with qwen
            return ShellAgentAdapter({
                "name": "qwen",
                "model": "default",
                "command_template": "qwen -p \"{prompt}\""
            })
        
        return ShellAgentAdapter({
            "name": agent_config.name,
            "model": "default",
            "command_template": agent_config.command_template
        })
    
    def verify_repository(self, repo_path: Path) -> str:
        """Verify a directory is a valid Git repository and get current commit.
        
        Args:
            repo_path: Path to the repository.
            
        Returns:
            Current commit hash.
            
        Raises:
            ValueError: If not a valid git repository.
        """
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        if not (repo_path / ".git").exists() and not (repo_path / ".git").is_file():
            raise ValueError(f"Directory is not a git repository: {repo_path}")
        
        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    
    def get_diff_stats(self, repo_path: Path, base_commit: str) -> Tuple[int, int, int, str]:
        """Get git diff statistics between base commit and current state.
        
        Args:
            repo_path: Path to the repository.
            base_commit: The starting commit hash.
            
        Returns:
            Tuple of (files_changed, insertions, deletions, diff_stats_output)
        """
        # Get diff stats
        result = subprocess.run(
            ["git", "diff", "--stat", base_commit],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return 0, 0, 0, ""
        
        diff_stats = result.stdout.strip()
        
        # Parse the stats line
        lines = diff_stats.split("\n")
        if not lines:
            return 0, 0, 0, ""
        
        # Last line has the summary: "X files changed, Y insertions(+), Z deletions(-)"
        summary = lines[-1] if lines else ""
        
        files_changed = 0
        insertions = 0
        deletions = 0
        
        # Try to parse the summary
        files_match = re.search(r"(\d+)\s+files?\s+changed", summary)
        ins_match = re.search(r"(\d+)\s+insertions?\(\+\)", summary)
        del_match = re.search(r"(\d+)\s+deletions?\(-\)", summary)
        
        if files_match:
            files_changed = int(files_match.group(1))
        if ins_match:
            insertions = int(ins_match.group(1))
        if del_match:
            deletions = int(del_match.group(1))
        
        return files_changed, insertions, deletions, diff_stats

    def execute_setup_command(self, workspace_path: Path, setup_command: str) -> Tuple[bool, str, str]:
        """Execute the task's setup command in the workspace.

        Args:
            workspace_path: Path to the isolated workspace.
            setup_command: The setup command to execute.

        Returns:
            Tuple of (success, stdout, stderr)
        """
        if not setup_command:
            return True, "", ""

        try:
            result = subprocess.run(
                setup_command,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                shell=True,
                timeout=300  # 5 minute timeout for setup
            )

            success = result.returncode == 0
            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            return False, "", "Setup command timed out after 300 seconds"

    def run_tests(self, repo_path: Path, test_command: str, cwd: Optional[Path] = None) -> Tuple[bool, int, int, Optional[str]]:
        """Run tests on the repository.
        
        Args:
            repo_path: Path to the repository (used for getting test framework config).
            test_command: The test command to execute.
            cwd: Working directory to run tests in. Defaults to repo_path.
            
        Returns:
            Tuple of (passed, passed_count, failed_count, error_message)
        """
        try:
            result = subprocess.run(
                test_command,
                cwd=cwd or repo_path,
                capture_output=True,
                text=True,
                shell=True
            )
            
            passed = result.returncode == 0
            passed_count = 0
            failed_count = 0
            error = None
            
            if passed:
                # Try to extract test counts from output
                passed_match = re.search(r"(\d+)\s+passed", result.stdout)
                failed_match = re.search(r"(\d+)\s+failed", result.stdout)
                
                if passed_match:
                    passed_count = int(passed_match.group(1))
                if failed_match:
                    failed_count = int(failed_match.group(1))
            else:
                error = result.stderr or result.stdout
            
            return passed, passed_count, failed_count, error
            
        except Exception as e:
            return False, 0, 0, str(e)
    
    def execute_benchmark(
        self,
        task: BenchmarkTask,
        agent_config_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> BenchmarkRun:
        """Execute a benchmark task and record results.

        Args:
            task: The benchmark task to execute.
            agent_config_id: ID of the agent configuration to use.
            agent_name: Name of the agent (optional override).
            model_name: Name of the model (optional).

        Returns:
            The completed benchmark run record.
        """
        started_at = datetime.utcnow()

        # Create agent adapter
        adapter = self.create_agent_adapter(agent_config_id)
        if agent_name:
            adapter.name = agent_name
        if model_name:
            adapter.model = model_name

        # Verify repository
        repo_path = Path(task.repository_path)
        current_commit = self.verify_repository(repo_path)

        # Create isolated workspace using git worktree
        worktree_path = create_git_worktree(repo_path, task.base_commit)

        try:
            # Prepare adapter with workspace path
            adapter.prepare(worktree_path, task.base_commit)

            # Create run directory for persistent logs
            runs_dir = repo_path / "runs" / str(task.id)
            runs_dir.mkdir(parents=True, exist_ok=True)

            stdout_path = runs_dir / "agent.stdout.log"
            stderr_path = runs_dir / "agent.stderr.log"

            adapter.set_output_paths(stdout_path, stderr_path)

            # Execute setup command before agent execution
            if task.setup_command:
                setup_success, setup_stdout, setup_stderr = self.execute_setup_command(
                    worktree_path,
                    task.setup_command
                )

                # Write setup logs
                with open(runs_dir / "setup.stdout.log", "w") as f:
                    f.write(setup_stdout)
                with open(runs_dir / "setup.stderr.log", "w") as f:
                    f.write(setup_stderr)

                if not setup_success:
                    # Setup failed, create a failed run record
                    ended_at = datetime.utcnow()
                    duration = (ended_at - started_at).total_seconds()

                    run = BenchmarkRun(
                        task_id=task.id,
                        agent_config_id=agent_config_id,
                        agent_name=adapter.name,
                        model_name=adapter.model,
                        started_at=started_at,
                        ended_at=ended_at,
                        duration_seconds=duration,
                        exit_code=1,
                        success=False,
                        test_command=task.test_command,
                        test_passed=0,
                        test_failed=0,
                        test_error="Setup command failed",
                        tests_passed=False,
                        files_changed=0,
                        insertions=0,
                        deletions=0,
                        diff_stats="",
                        stdout_path=str(stdout_path),
                        stderr_path=str(stderr_path),
                        results={
                            "adapter_metadata": adapter.collect_metadata(),
                            "original_commit": current_commit,
                            "final_commit": task.base_commit,
                            "setup_error": "Setup command failed",
                            "setup_stdout_path": str(runs_dir / "setup.stdout.log"),
                            "setup_stderr_path": str(runs_dir / "setup.stderr.log"),
                        }
                    )

                    self.db.add(run)
                    self.db.commit()
                    self.db.refresh(run)

                    return run

            # Run the agent in workspace
            exit_code, stdout, stderr = adapter.run_task(
                task.agent_prompt,
                task.timeout
            )

            ended_at = datetime.utcnow()
            duration = (ended_at - started_at).total_seconds()

            # Run tests in workspace
            tests_passed = False
            test_passed_count = 0
            test_failed_count = 0
            test_error = None

            if task.test_command:
                tests_passed, test_passed_count, test_failed_count, test_error = self.run_tests(
                    repo_path,
                    task.test_command,
                    cwd=worktree_path
                )

            # Collect git evidence from workspace
            workspace_head = get_git_commit(worktree_path)
            workspace_status = get_git_status(worktree_path)
            workspace_diff_stats = get_git_diff_stats(worktree_path, task.base_commit)

            files_changed = workspace_diff_stats["files_changed"]
            insertions = workspace_diff_stats["insertions"]
            deletions = workspace_diff_stats["deletions"]
            diff_stats = workspace_diff_stats.get("diffstat", "")

            # Determine overall success
            success = exit_code == 0 and tests_passed

            # Write outputs to files
            with open(stdout_path, "w") as f:
                f.write(stdout)
            with open(stderr_path, "w") as f:
                f.write(stderr)

            # Create run record
            run = BenchmarkRun(
                task_id=task.id,
                agent_config_id=agent_config_id,
                agent_name=adapter.name,
                model_name=adapter.model,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration,
                exit_code=exit_code,
                success=success,
                test_command=task.test_command,
                test_passed=test_passed_count,
                test_failed=test_failed_count,
                test_error=test_error,
                tests_passed=tests_passed,
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
                diff_stats=diff_stats,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                results={
                    "adapter_metadata": adapter.collect_metadata(),
                    "original_commit": current_commit,
                    "final_commit": workspace_head,
                    "workspace_status": workspace_status,
                    "workspace_diff_stats": diff_stats,
                    "setup_command": task.setup_command,
                    "logs_directory": str(runs_dir),
                }
            )

            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)

            return run

        finally:
            # Cleanup worktree but keep logs in runs/ directory
            cleanup_git_worktree(worktree_path, repo_path)
