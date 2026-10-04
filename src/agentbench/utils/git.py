"""Utility functions for AgentBench."""

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def is_git_repository(path: Path) -> bool:
    """Check if a directory is a Git repository.

    Args:
        path: Path to check.

    Returns:
        True if the directory is a Git repository.
    """
    if not path.exists():
        return False
    return (path / ".git").exists() or (path / ".git").is_file()


def get_git_commit(path: Path) -> Optional[str]:
    """Get the current Git commit hash.

    Args:
        path: Path to the Git repository.

    Returns:
        The commit hash, or None if not a Git repository.
    """
    if not is_git_repository(path):
        return None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_git_status(path: Path) -> str:
    """Get the Git status of a repository.

    Args:
        path: Path to the Git repository.

    Returns:
        The git status output.
    """
    if not is_git_repository(path):
        return "Not a Git repository"

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=path,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "Error getting status"


def get_git_diff_stats(path: Path, base_commit: str) -> dict:
    """Get git diff statistics between base commit and current HEAD.

    Args:
        path: Path to the Git repository.
        base_commit: The base commit hash to compare against.

    Returns:
        Dictionary with diff statistics including files_changed, insertions, deletions.
    """
    if not is_git_repository(path):
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    try:
        # Get diffstat
        result = subprocess.run(
            ["git", "diff", "--stat", base_commit],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )
        diffstat = result.stdout.strip()
        
        # Count files changed
        files_changed = len([line for line in diffstat.split('\n') if line and 'file' not in line.lower()]) if diffstat else 0
        
        # Get detailed stats
        stats_result = subprocess.run(
            ["git", "diff", "--numstat", base_commit],
            cwd=path,
            capture_output=True,
            text=True,
            check=True
        )
        
        insertions = 0
        deletions = 0
        for line in stats_result.stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 2:
                    ins = parts[0]
                    dels = parts[1]
                    if ins != '-':
                        insertions += int(ins)
                    if dels != '-':
                        deletions += int(dels)
        
        return {
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
            "diffstat": diffstat
        }
    except subprocess.CalledProcessError:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "diffstat": ""}


def create_git_worktree(repo_path: Path, commit: str = "HEAD") -> Path:
    """Create a git worktree for isolated benchmark execution.

    Args:
        repo_path: Path to the main Git repository.
        commit: Commit hash or ref to check out in the worktree.

    Returns:
        Path to the created worktree directory.

    Raises:
        RuntimeError: If worktree creation fails.
    """
    import tempfile
    
    # Create worktree in a temporary location
    worktree_dir = tempfile.mkdtemp(prefix="agentbench_worktree_")
    worktree_path = Path(worktree_dir)
    
    try:
        # Create the worktree
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), commit],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return worktree_path
    except subprocess.CalledProcessError as e:
        # Clean up on failure
        if worktree_path.exists():
            import shutil
            shutil.rmtree(worktree_path, ignore_errors=True)
        raise RuntimeError(
            f"Failed to create git worktree: {e.stderr}"
        ) from e


def cleanup_git_worktree(worktree_path: Path, repo_path: Path) -> None:
    """Remove a git worktree and clean up its directory.

    Args:
        worktree_path: Path to the worktree directory.
        repo_path: Path to the main Git repository.
    """
    if not worktree_path.exists():
        return

    try:
        # First remove the worktree using git worktree remove (proper removal)
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            cwd=repo_path,
            capture_output=True,
            check=True
        )
    except subprocess.CalledProcessError:
        # If worktree remove fails, try prune as fallback
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError:
            pass  # Git may not know about this worktree

    # Remove the directory and all contents
    import shutil
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


def create_temp_git_repository() -> Tuple[Path, str]:
    """Create a temporary Git repository for testing.

    Returns:
        Tuple of (path, commit_hash)
    """
    import tempfile

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="agentbench_repo_")
    repo_path = Path(temp_dir)

    # Initialize Git repository
    subprocess.run(
        ["git", "init"],
        cwd=repo_path,
        capture_output=True,
        check=True
    )

    # Configure Git
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True,
        check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True
    )

    # Create an initial file and commit
    test_file = repo_path / "README.md"
    test_file.write_text("# Test Repository\n\nThis is a test repository for AgentBench.\n")

    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        capture_output=True,
        check=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True
    )

    commit_hash = get_git_commit(repo_path)

    return repo_path, commit_hash


def cleanup_temp_repository(path: Path) -> None:
    """Clean up a temporary Git repository.

    Args:
        path: Path to the temporary repository.
    """
    import shutil
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
