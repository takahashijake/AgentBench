from __future__ import annotations

from pathlib import Path

from agentbench.artifacts import RunArtifactStore
from agentbench.evidence import capture_git_evidence

from helpers import init_git_repo


def test_git_evidence_preserves_tracked_and_untracked_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    base_commit = init_git_repo(repo)

    (repo / "tracked.txt").write_text("base\nchanged\n", encoding="utf-8")
    nested = repo / "nested"
    nested.mkdir()
    (nested / "new.txt").write_text("one\ntwo\n", encoding="utf-8")

    store = RunArtifactStore.create(tmp_path / "artifacts", task_id=3)
    evidence = capture_git_evidence(repo, base_commit, store)

    assert "tracked.txt" in evidence["status"]
    assert "nested/new.txt" in evidence["status"]
    assert evidence["diff_stats"]["files_changed"] == 2
    assert evidence["diff_stats"]["insertions"] >= 3

    preserved = store.path_for("git/untracked/nested/new.txt")
    assert preserved.read_text(encoding="utf-8") == "one\ntwo\n"
    assert "+changed" in store.path_for("git/diff.patch").read_text(encoding="utf-8")
