"""Shell-based agent adapter for executing agent commands."""

import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

from .base import AgentAdapter


class ShellAgentAdapter(AgentAdapter):
    """Agent adapter that executes commands via shell.
    
    This adapter runs a configurable shell command with the task prompt
    injected. It's designed for command-line agents like Qwen Code.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the shell adapter.
        
        Args:
            config: Configuration dictionary with:
                - name: Agent name
                - model: Model name
                - command_template: Shell command template with {prompt} placeholder
        """
        super().__init__(config)
        self.process: Optional[subprocess.Popen] = None
        self.temp_files: list = []
    
    def prepare(self, repository_path: Path, base_commit: str) -> None:
        """Prepare for benchmark execution.
        
        Verifies the repository exists and is a git repository.
        
        Args:
            repository_path: Path to the target repository.
            base_commit: The starting commit hash (not used in shell adapter).
        """
        repo_path = Path(repository_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repository_path}")
        
        # Verify it's a git repository
        git_dir = repo_path / ".git"
        if not git_dir.exists() and not (repo_path / ".git").is_file():
            # Check if .git is a file (worktree)
            git_file = repo_path / ".git"
            if not git_file.is_file():
                raise ValueError(f"Directory is not a git repository: {repository_path}")
    
    def run_task(self, prompt: str, timeout: int) -> Tuple[int, str, str]:
        """Execute the agent command with the given prompt.
        
        Args:
            prompt: The task prompt to execute.
            timeout: Timeout in seconds.
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        # Build the command by substituting the prompt
        # Escape the prompt for shell usage
        import shlex
        command = self.command_template.format(prompt=shlex.quote(prompt))
        
        # Create temporary files for output
        stdout_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, prefix="agentbench_stdout_", suffix=".log"
        )
        stderr_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, prefix="agentbench_stderr_", suffix=".log"
        )
        
        self.temp_files.extend([stdout_file.name, stderr_file.name])
        
        try:
            # Execute the command
            self.process = subprocess.Popen(
                command,
                shell=True,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True
            )
            
            try:
                exit_code = self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                exit_code = -1
                
                # Get any output before timeout
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read()
                stderr = stderr_file.read()
                return exit_code, stdout, stderr
            
            # Read output
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read()
            
            return exit_code, stdout, stderr
            
        finally:
            stdout_file.close()
            stderr_file.close()
            # Don't delete temp files yet - we'll read them later
    
    def terminate(self) -> None:
        """Terminate any running agent process."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
    
    def collect_metadata(self) -> Dict[str, Any]:
        """Collect agent execution metadata.
        
        Returns:
            Dictionary containing metadata like token usage.
        """
        metadata = {
            "adapter": "shell",
            "command": self.command_template,
            "temp_files": self.temp_files,
        }
        return metadata
    
    def cleanup(self) -> None:
        """Clean up temporary files."""
        import os
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        self.temp_files = []
