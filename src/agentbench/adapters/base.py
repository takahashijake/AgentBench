"""Abstract adapter interface for coding agents."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from pathlib import Path


class AgentAdapter(ABC):
    """Abstract interface for agent adapters.

    This interface allows AgentBench to support multiple coding agents
    through a common abstraction.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the adapter with configuration.

        Args:
            config: Configuration dictionary for the agent.
        """
        self.config = config
        self.name = config.get("name", "agent")
        self.model = config.get("model", "unknown")
        self.command_template = config.get("command_template", "qwen -p \"{prompt}\"")
        self.stdout_path: Optional[Path] = None
        self.stderr_path: Optional[Path] = None
        self.workspace_path: Optional[Path] = None

    @abstractmethod
    def prepare(self, repository_path: Path, base_commit: str) -> Path:
        """Prepare the agent for a benchmark task.

        Args:
            repository_path: Path to the target repository.
            base_commit: The starting commit hash.

        Returns:
            Path to the workspace directory (worktree or original repo).
        """
        pass

    @abstractmethod
    def run_task(self, prompt: str, timeout: int, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """Execute the agent against a task prompt.

        Args:
            prompt: The task prompt to execute.
            timeout: Timeout in seconds.
            cwd: Working directory for command execution (optional).

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        pass

    @abstractmethod
    def terminate(self) -> None:
        """Terminate any running agent processes."""
        pass

    @abstractmethod
    def collect_metadata(self) -> Dict[str, Any]:
        """Collect agent execution metadata.

        Returns:
            Dictionary containing metadata like token usage, timing, etc.
        """
        pass

    def set_output_paths(self, stdout_path: Path, stderr_path: Path) -> None:
        """Set paths for stdout and stderr log files.

        Args:
            stdout_path: Path to write stdout.
            stderr_path: Path to write stderr.
        """
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
