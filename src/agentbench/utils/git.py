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


def create_temp_git_repository() -> Tuple[Path, str]:
    """Create a temporary Git repository for testing.
    
    Returns:
        Tuple of (path, commit_hash)
    """
    import tempfile
    import os
    
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
