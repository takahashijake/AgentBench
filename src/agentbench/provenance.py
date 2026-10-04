"""Reproducibility provenance and suite lock files.

The lock captures bounded, non-secret inputs that materially affect a benchmark:
resolved task commits, agent command definitions/executable identities, AgentBench and
Python versions, platform identity, and Git version. The resulting lock has a
canonical SHA-256 identity and can be verified before replay.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import platform
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .manifests import LoadedSuiteManifest


LOCK_SCHEMA_VERSION = 2
SUPPORTED_LOCK_SCHEMA_VERSIONS = frozenset({1, 2})
_VERSION_TIMEOUT_SECONDS = 3
_MAX_VERSION_OUTPUT = 1000


class SuiteLock(BaseModel):
    """Validated persisted lock envelope."""

    model_config = ConfigDict(extra="forbid")

    lock_schema_version: int = Field(default=LOCK_SCHEMA_VERSION)
    suite: dict[str, Any]
    tasks: list[dict[str, Any]]
    agents: list[dict[str, Any]]
    experiment: dict[str, Any]
    environment: dict[str, Any]
    identity_sha256: str = Field(..., min_length=64, max_length=64)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return sha256(_canonical_bytes(payload)).hexdigest()


def _run_probe(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 127, "", f"{type(exc).__name__}: {exc}")


def _bounded_version_text(result: subprocess.CompletedProcess[str]) -> str | None:
    combined = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    ).strip()
    if not combined:
        return None
    return combined[:_MAX_VERSION_OUTPUT]


def _hash_file(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def executable_identity(command_template: str) -> dict[str, Any]:
    """Resolve the executable for an agent command without expanding the prompt."""

    try:
        tokens = shlex.split(command_template)
    except ValueError as exc:
        raise ValueError(f"Invalid agent command template: {exc}") from exc
    if not tokens:
        raise ValueError("Agent command template is empty")

    executable = tokens[0]
    resolved = shutil.which(executable)
    if resolved is None:
        raise ValueError(
            f"Agent executable is not available on PATH: {executable}"
        )

    resolved_path = Path(resolved).resolve()
    version_probe = _run_probe([str(resolved_path), "--version"])
    return {
        "command": executable,
        "resolved_name": resolved_path.name,
        "version": _bounded_version_text(version_probe),
        "binary_sha256": _hash_file(resolved_path),
    }


def resolve_commit(repository_path: Path, ref: str) -> str:
    """Resolve a manifest commit/ref to the exact commit used for replay."""

    if not repository_path.exists():
        raise ValueError(f"Repository path does not exist: {repository_path}")

    inside = _run_probe(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repository_path,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise ValueError(f"Directory is not a Git repository: {repository_path}")

    result = _run_probe(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=repository_path,
    )
    if result.returncode != 0:
        detail = _bounded_version_text(result) or "unknown Git error"
        raise ValueError(f"Unable to resolve base commit {ref!r}: {detail}")
    return result.stdout.strip().lower()


def environment_identity() -> dict[str, Any]:
    """Capture a bounded, non-secret execution-environment fingerprint."""

    git_probe = _run_probe(["git", "--version"])
    return {
        "agentbench_version": __version__,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "git_version": _bounded_version_text(git_probe),
    }


def build_suite_lock(loaded: LoadedSuiteManifest) -> dict[str, Any]:
    """Resolve a suite into a deterministic reproducibility lock."""

    tasks_by_id = {task.id: task for task in loaded.manifest.tasks}
    agents_by_id = {agent.id: agent for agent in loaded.manifest.agents}

    tasks: list[dict[str, Any]] = []
    for resource_id in loaded.manifest.selected_task_ids():
        task = tasks_by_id[resource_id]
        repo = loaded.resolve_repository_path(task)
        tasks.append(
            {
                "id": resource_id,
                "repository_path": task.repository_path,
                "requested_base_commit": task.base_commit.lower(),
                "resolved_base_commit": resolve_commit(repo, task.base_commit),
                "agent_prompt_sha256": sha256(
                    task.agent_prompt.encode("utf-8")
                ).hexdigest(),
                "setup_command": task.setup_command,
                "test_command": task.test_command,
                "timeout": task.timeout,
                "category": task.category,
                "difficulty": task.difficulty,
                "tags": list(task.tags),
            }
        )

    agents: list[dict[str, Any]] = []
    for resource_id in loaded.manifest.selected_agent_ids():
        agent = agents_by_id[resource_id]
        agents.append(
            {
                "id": resource_id,
                "command_template": agent.command_template,
                "executable": executable_identity(agent.command_template),
            }
        )

    payload: dict[str, Any] = {
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "suite": {
            "id": loaded.manifest.id,
            "schema_version": loaded.manifest.schema_version,
            "manifest_sha256": loaded.sha256,
            "benchmark_pack": (
                loaded.manifest.benchmark_pack.model_dump(mode="json")
                if loaded.manifest.benchmark_pack is not None
                else None
            ),
        },
        "tasks": tasks,
        "agents": agents,
        "experiment": {
            "tasks": loaded.manifest.selected_task_ids(),
            "agents": loaded.manifest.selected_agent_ids(),
            "repetitions": loaded.manifest.experiment.repetitions,
            "stop_on_error": loaded.manifest.experiment.stop_on_error,
        },
        "environment": environment_identity(),
    }
    payload["identity_sha256"] = canonical_sha256(payload)
    return payload


def load_suite_lock(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Suite lock does not exist: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid suite lock JSON: {exc}") from exc
    lock = SuiteLock.model_validate(raw)
    if lock.lock_schema_version not in SUPPORTED_LOCK_SCHEMA_VERSIONS:
        raise ValueError(
            f"Unsupported lock_schema_version: {lock.lock_schema_version}"
        )
    payload = lock.model_dump(mode="json")
    claimed = payload.pop("identity_sha256")
    calculated = canonical_sha256(payload)
    if calculated != claimed:
        raise ValueError(
            "Suite lock identity is invalid: contents do not match identity_sha256"
        )
    payload["identity_sha256"] = claimed
    return payload


def write_suite_lock(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _diff_values(expected: Any, actual: Any, prefix: str = "") -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            path = f"{prefix}.{key}" if prefix else key
            if key not in expected:
                drift.append({"path": path, "expected": None, "actual": actual[key]})
            elif key not in actual:
                drift.append({"path": path, "expected": expected[key], "actual": None})
            else:
                drift.extend(_diff_values(expected[key], actual[key], path))
        return drift

    if isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            drift.append({"path": prefix, "expected": expected, "actual": actual})
        return drift

    if expected != actual:
        drift.append({"path": prefix, "expected": expected, "actual": actual})
    return drift


def verify_suite_lock(
    loaded: LoadedSuiteManifest,
    expected_lock: dict[str, Any],
) -> dict[str, Any]:
    """Compare the current resolved suite/environment against a lock."""

    current = build_suite_lock(loaded)
    if expected_lock.get("identity_sha256") == current["identity_sha256"]:
        return {
            "valid": True,
            "expected_identity_sha256": expected_lock["identity_sha256"],
            "current_identity_sha256": current["identity_sha256"],
            "drift": [],
            "current_lock": current,
        }

    expected_compare = deepcopy(expected_lock)
    current_compare = deepcopy(current)
    expected_compare.pop("identity_sha256", None)
    current_compare.pop("identity_sha256", None)
    return {
        "valid": False,
        "expected_identity_sha256": expected_lock.get("identity_sha256"),
        "current_identity_sha256": current["identity_sha256"],
        "drift": _diff_values(expected_compare, current_compare),
        "current_lock": current,
    }


def capture_run_provenance(command_template: str) -> dict[str, Any]:
    """Capture bounded provenance for one concrete benchmark run."""

    return {
        "environment": environment_identity(),
        "agent_executable": executable_identity(command_template),
    }


__all__ = [
    "LOCK_SCHEMA_VERSION",
    "SuiteLock",
    "build_suite_lock",
    "canonical_sha256",
    "capture_run_provenance",
    "environment_identity",
    "executable_identity",
    "load_suite_lock",
    "resolve_commit",
    "verify_suite_lock",
    "write_suite_lock",
]
