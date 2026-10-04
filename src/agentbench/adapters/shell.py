"""Shell-style command adapter executed safely without shell interpolation."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .base import AgentAdapter
from ..execution import ProcessResult, run_process
from ..usage import detect_agent_family, extract_usage_metadata


class ShellAgentAdapter(AgentAdapter):
    """Execute a configurable coding-agent command in an isolated workspace."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.last_result: Optional[ProcessResult] = None

    def prepare(self, repository_path: Path, base_commit: str) -> Path:
        repo_path = Path(repository_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repository_path}")

        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise ValueError(f"Directory is not a git repository: {repository_path}")

        self.workspace_path = repo_path
        return repo_path

    def build_argv(self, prompt: str) -> list[str]:
        """Parse the configured command and inject the prompt as one argv value."""
        try:
            tokens = shlex.split(self.command_template)
        except ValueError as exc:
            raise ValueError(f"Invalid agent command template: {exc}") from exc

        if not tokens:
            raise ValueError("Agent command template is empty")

        return [token.replace("{prompt}", prompt) for token in tokens]

    def run_task(
        self,
        prompt: str,
        timeout: int,
        cwd: Optional[Path] = None,
    ) -> Tuple[int, str, str]:
        working_dir = Path(cwd) if cwd is not None else self.workspace_path
        if working_dir is None:
            raise RuntimeError(
                "No working directory specified and adapter is not prepared"
            )

        argv = self.build_argv(prompt)
        self.last_result = run_process(argv, cwd=working_dir, timeout=timeout)
        return (
            self.last_result.returncode,
            self.last_result.stdout,
            self.last_result.stderr,
        )

    def process_result(self) -> Optional[ProcessResult]:
        return self.last_result

    def terminate(self) -> None:
        # run_process owns and tears down the complete process group on timeout.
        return None

    def collect_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "adapter": str(self.config.get("adapter") or "shell"),
            "agent_family": str(
                self.config.get("agent_family")
                or detect_agent_family(self.command_template)
            ),
            "command_template": self.command_template,
            "workspace_path": str(self.workspace_path) if self.workspace_path else None,
        }
        if self.last_result is not None:
            metadata.update(
                {
                    "timed_out": self.last_result.timed_out,
                    "process_duration_seconds": self.last_result.duration_seconds,
                    "returncode": self.last_result.returncode,
                    "usage": extract_usage_metadata(
                        self.last_result.stdout,
                        self.last_result.stderr,
                    ),
                }
            )
        return metadata
