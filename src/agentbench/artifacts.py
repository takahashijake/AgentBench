"""Immutable per-run artifact storage for AgentBench."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def default_artifact_root() -> Path:
    """Return the default artifact root outside benchmark repositories."""
    configured = os.getenv("AGENTBENCH_RUNS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".local" / "share" / "agentbench" / "runs").resolve()


def _safe_relative_path(relative_path: str | Path) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            f"Artifact path must stay within the run directory: {relative_path}"
        )
    return relative


@dataclass(frozen=True)
class RunArtifactStore:
    """Write-once storage for one benchmark run."""

    root: Path

    @classmethod
    def create(
        cls,
        artifact_root: Optional[Path] = None,
        task_id: Optional[int] = None,
    ) -> "RunArtifactStore":
        base = (
            Path(artifact_root).expanduser().resolve()
            if artifact_root
            else default_artifact_root()
        )
        base.mkdir(parents=True, exist_ok=True)

        task_component = f"task-{task_id}" if task_id is not None else "task-unknown"
        for _ in range(20):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            run_name = f"{stamp}_{task_component}_{uuid.uuid4().hex[:12]}"
            run_dir = base / run_name
            try:
                run_dir.mkdir(parents=False, exist_ok=False)
                return cls(run_dir)
            except FileExistsError:
                continue

        raise RuntimeError("Unable to allocate a unique benchmark artifact directory")

    def path_for(self, relative_path: str | Path) -> Path:
        relative = _safe_relative_path(relative_path)
        return self.root / relative

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        target = self.path_for(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return target

    def write_bytes(self, relative_path: str | Path, content: bytes) -> Path:
        target = self.path_for(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
        return target

    def write_json(self, relative_path: str | Path, payload: Any) -> Path:
        return self.write_text(
            relative_path,
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        )
