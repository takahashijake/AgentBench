"""Git workspace lifecycle helpers for AgentBench."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def is_git_repository(path: Path) -> bool:
    if not path.exists():
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_git_commit(path: Path) -> Optional[str]:
    if not is_git_repository(path):
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def get_git_status(path: Path) -> str:
    if not is_git_repository(path):
        return "Not a Git repository"
    result = subprocess.run(
        ["git", "status", "--short", "-uall"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "Error getting status"


def get_git_diff_stats(path: Path, base_commit: str) -> dict:
    """Return diff metrics including untracked files."""
    from ..evidence import collect_diff_stats

    if not is_git_repository(path):
        return {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "diffstat": "",
        }
    try:
        return collect_diff_stats(path, base_commit)
    except subprocess.CalledProcessError:
        return {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "diffstat": "",
        }


def create_git_worktree(repo_path: Path, commit: str = "HEAD") -> Path:
    """Create a detached worktree at an exact commit/ref for benchmark isolation."""
    repo_path = Path(repo_path).resolve()
    if not is_git_repository(repo_path):
        raise ValueError(f"Not a Git repository: {repo_path}")

    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        raise ValueError(f"Base commit does not resolve to a commit: {commit}")
    resolved_commit = verify.stdout.strip()

    worktree_path = Path(tempfile.mkdtemp(prefix="agentbench_worktree_"))
    shutil.rmtree(worktree_path)

    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), resolved_commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.rmtree(worktree_path, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune", "--expire", "now"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        raise RuntimeError(f"Failed to create git worktree: {result.stderr.strip()}")

    return worktree_path


def cleanup_git_worktree(worktree_path: Path, repo_path: Path) -> dict:
    """Force-remove a benchmark worktree and prune stale Git metadata."""
    worktree_path = Path(worktree_path)
    repo_path = Path(repo_path)
    errors: list[str] = []

    remove_result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if remove_result.returncode != 0 and remove_result.stderr.strip():
        errors.append(remove_result.stderr.strip())

    if worktree_path.exists():
        try:
            shutil.rmtree(worktree_path)
        except OSError as exc:
            errors.append(str(exc))

    prune_result = subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if prune_result.returncode != 0 and prune_result.stderr.strip():
        errors.append(prune_result.stderr.strip())

    return {
        "success": not worktree_path.exists(),
        "worktree_path": str(worktree_path),
        "errors": errors,
    }


def create_temp_git_repository() -> Tuple[Path, str]:
    """Create a minimal committed repository for deterministic tests."""
    repo_path = Path(tempfile.mkdtemp(prefix="agentbench_repo_"))

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    (repo_path / "README.md").write_text(
        "# Test Repository\n\nThis is a test repository for AgentBench.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    commit_hash = get_git_commit(repo_path)
    if commit_hash is None:
        raise RuntimeError("Failed to resolve test repository commit")
    return repo_path, commit_hash


def cleanup_temp_repository(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
