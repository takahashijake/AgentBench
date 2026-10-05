"""Process execution helpers with bounded, process-tree-aware timeouts."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float


def _terminate_process_tree(
    process: subprocess.Popen[str], grace_seconds: float = 2.0
) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=max(grace_seconds, 1.0),
                check=False,
            )
        except Exception:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            process.terminate()

    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            process.kill()

    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()


def run_process(
    argv: Sequence[str],
    cwd: Path,
    timeout: float,
    env: Optional[Mapping[str, str]] = None,
) -> ProcessResult:
    """Run argv without a shell and terminate the whole process group on timeout."""
    if not argv:
        raise ValueError("argv must not be empty")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    popen_kwargs: dict[str, object] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process_env: dict[str, str] | None = None
    if env is not None:
        process_env = os.environ.copy()
        process_env.update(env)

    started = time.monotonic()
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=process_env,
        **popen_kwargs,
    )

    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()

    duration = time.monotonic() - started
    returncode = process.returncode if process.returncode is not None else 124
    if timed_out and returncode == 0:
        returncode = 124

    if timed_out:
        suffix = f"\n[agentbench] process timed out after {timeout:.1f} seconds\n"
        stderr = (stderr or "") + suffix

    return ProcessResult(
        returncode=returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
        duration_seconds=duration,
    )


def run_shell_command(
    command: str,
    cwd: Path,
    timeout: float,
    env: Optional[Mapping[str, str]] = None,
) -> ProcessResult:
    """Run an explicitly configured setup/test shell command with bounded timeout."""
    if os.name == "nt":
        argv = ["cmd.exe", "/d", "/s", "/c", command]
    else:
        argv = ["/bin/sh", "-lc", command]
    return run_process(argv, cwd=cwd, timeout=timeout, env=env)
