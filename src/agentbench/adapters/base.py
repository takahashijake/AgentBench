"""Abstract adapter interface for coding agents."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..defaults import DEFAULT_AGENT_COMMAND_TEMPLATE
from ..execution import ProcessResult


class AgentAdapter(ABC):
    """Common interface for coding-agent adapters."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", "agent")
        self.model = config.get("model", "unknown")
        self.command_template = config.get("command_template", DEFAULT_AGENT_COMMAND_TEMPLATE)
        self.stdout_path: Optional[Path] = None
        self.stderr_path: Optional[Path] = None
        self.workspace_path: Optional[Path] = None

    @abstractmethod
    def prepare(self, repository_path: Path, base_commit: str) -> Path:
        """Prepare the adapter to run inside an already-isolated workspace."""
        raise NotImplementedError

    @abstractmethod
    def run_task(
        self,
        prompt: str,
        timeout: int,
        cwd: Optional[Path] = None,
    ) -> Tuple[int, str, str]:
        """Execute the coding agent and return exit code, stdout, and stderr."""
        raise NotImplementedError

    @abstractmethod
    def terminate(self) -> None:
        """Terminate an active adapter process when supported."""
        raise NotImplementedError

    @abstractmethod
    def collect_metadata(self) -> Dict[str, Any]:
        """Return execution metadata suitable for persistent benchmark results."""
        raise NotImplementedError

    def process_result(self) -> Optional[ProcessResult]:
        """Return the bounded process result when the adapter exposes one."""
        return None

    def set_output_paths(self, stdout_path: Path, stderr_path: Path) -> None:
        """Compatibility hook for adapters that stream directly to files."""
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path

    def cleanup(self) -> None:
        """Release adapter-owned temporary resources."""
        return None
