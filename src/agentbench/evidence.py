"""Git evidence capture for benchmark runs."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import RunArtifactStore


def _git(
    path: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=check,
    )


def list_untracked_files(path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    decoded = result.stdout.decode("utf-8", errors="surrogateescape")
    return [item for item in decoded.split("\0") if item]


def _safe_git_relative_path(relative_path: str) -> tuple[str, ...]:
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe path returned by Git: {relative_path!r}")
    return parts


def _line_count_for_untracked(path: Path) -> int:
    data = path.read_bytes()
    if not data or b"\x00" in data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def collect_diff_stats(path: Path, base_commit: str) -> dict[str, int | str]:
    """Collect tracked diff stats plus untracked files."""
    numstat_result = _git(path, "diff", "--numstat", base_commit, "--", check=True)
    insertions = 0
    deletions = 0
    tracked_files = 0

    for line in numstat_result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tracked_files += 1
        if parts[0].isdigit():
            insertions += int(parts[0])
        if parts[1].isdigit():
            deletions += int(parts[1])

    untracked = list_untracked_files(path)
    for relative in untracked:
        source = path.joinpath(*_safe_git_relative_path(relative))
        if source.is_file() and not source.is_symlink():
            try:
                insertions += _line_count_for_untracked(source)
            except OSError:
                pass

    diffstat = _git(
        path, "diff", "--stat", base_commit, "--", check=True
    ).stdout.strip()
    return {
        "files_changed": tracked_files + len(untracked),
        "insertions": insertions,
        "deletions": deletions,
        "diffstat": diffstat,
    }


def capture_git_evidence(
    workspace_path: Path,
    base_commit: str,
    artifact_store: RunArtifactStore,
) -> dict[str, Any]:
    """Persist enough Git evidence to reconstruct the agent result after cleanup."""
    head_commit = _git(workspace_path, "rev-parse", "HEAD").stdout.strip()
    status = _git(workspace_path, "status", "--short", "-uall").stdout
    patch = _git(workspace_path, "diff", "--binary", base_commit, "--").stdout
    numstat = _git(workspace_path, "diff", "--numstat", base_commit, "--").stdout
    log = _git(
        workspace_path,
        "log",
        "--format=%H%x09%an%x09%ad%x09%s",
        "--date=iso-strict",
        f"{base_commit}..HEAD",
        check=False,
    ).stdout

    artifact_store.write_text("git/head.txt", head_commit + "\n")
    artifact_store.write_text("git/status.txt", status)
    artifact_store.write_text("git/diff.patch", patch)
    artifact_store.write_text("git/numstat.txt", numstat)
    artifact_store.write_text("git/commits.txt", log)

    untracked_manifest: list[dict[str, Any]] = []
    for relative in list_untracked_files(workspace_path):
        parts = _safe_git_relative_path(relative)
        source = workspace_path.joinpath(*parts)
        entry: dict[str, Any] = {"path": relative}

        try:
            if source.is_symlink():
                entry.update({"type": "symlink", "target": str(source.readlink())})
            elif source.is_file():
                data = source.read_bytes()
                artifact_store.write_bytes(
                    Path("git") / "untracked" / Path(*parts), data
                )
                entry.update(
                    {
                        "type": "file",
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            else:
                entry.update({"type": "other"})
        except OSError as exc:
            entry.update({"type": "error", "error": str(exc)})

        untracked_manifest.append(entry)

    artifact_store.write_json("git/untracked-manifest.json", untracked_manifest)
    stats = collect_diff_stats(workspace_path, base_commit)

    return {
        "base_commit": base_commit,
        "head_commit": head_commit,
        "status": status.strip(),
        "diff_stats": stats,
        "untracked_files": [entry["path"] for entry in untracked_manifest],
        "paths": {
            "head": str(artifact_store.path_for("git/head.txt")),
            "status": str(artifact_store.path_for("git/status.txt")),
            "patch": str(artifact_store.path_for("git/diff.patch")),
            "numstat": str(artifact_store.path_for("git/numstat.txt")),
            "commits": str(artifact_store.path_for("git/commits.txt")),
            "untracked_manifest": str(
                artifact_store.path_for("git/untracked-manifest.json")
            ),
            "untracked_root": str(artifact_store.path_for("git/untracked")),
        },
    }
