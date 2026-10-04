from pathlib import Path

import pytest

from agentbench.artifacts import RunArtifactStore


def test_run_artifacts_are_unique_and_write_once(tmp_path: Path):
    root = tmp_path / "runs"
    first = RunArtifactStore.create(root, task_id=7)
    second = RunArtifactStore.create(root, task_id=7)

    assert first.root != second.root

    path = first.write_text("agent/stdout.log", "hello")
    assert path.read_text(encoding="utf-8") == "hello"

    with pytest.raises(FileExistsError):
        first.write_text("agent/stdout.log", "overwrite")


def test_artifact_paths_cannot_escape_run_directory(tmp_path: Path):
    store = RunArtifactStore.create(tmp_path / "runs", task_id=1)

    with pytest.raises(ValueError):
        store.write_text("../escape.txt", "nope")
