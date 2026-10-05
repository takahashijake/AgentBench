from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from agentbench.adapters.shell import ShellAgentAdapter
from agentbench.execution import run_process


def test_agent_prompt_is_one_argv_value_not_shell_code(tmp_path: Path):
    code = "import sys; print(sys.argv[1])"
    template = shlex.join([sys.executable, "-c", code, "{prompt}"])
    adapter = ShellAgentAdapter(
        {
            "name": "fixture",
            "model": "fixture",
            "command_template": template,
        }
    )
    prompt = '$(touch hacked) "quoted" ; echo should-not-run'

    exit_code, stdout, stderr = adapter.run_task(prompt, timeout=5, cwd=tmp_path)

    assert exit_code == 0, stderr
    assert stdout.strip() == prompt
    assert not (tmp_path / "hacked").exists()


def test_process_timeout_is_bounded(tmp_path: Path):
    result = run_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        timeout=0.2,
    )

    assert result.timed_out is True
    assert result.returncode != 0
    assert result.duration_seconds < 5
    assert "timed out" in result.stderr


def test_process_closes_stdin_for_noninteractive_automation(
    tmp_path: Path,
    monkeypatch,
):
    real_popen = subprocess.Popen
    observed: dict[str, object] = {}

    def recording_popen(*args, **kwargs):
        observed["stdin"] = kwargs.get("stdin")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "agentbench.execution.process.subprocess.Popen",
        recording_popen,
    )
    result = run_process(
        [
            sys.executable,
            "-c",
            "import sys; data = sys.stdin.read(); print(len(data))",
        ],
        cwd=tmp_path,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "0"
    assert observed["stdin"] == subprocess.DEVNULL


def test_process_env_overrides_preserve_parent_environment(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("AGENTBENCH_PARENT_SENTINEL", "parent")
    monkeypatch.setenv("AGENTBENCH_OVERRIDE_SENTINEL", "parent-value")

    result = run_process(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "print(os.environ['AGENTBENCH_PARENT_SENTINEL']); "
                "print(os.environ['AGENTBENCH_OVERRIDE_SENTINEL'])"
            ),
        ],
        cwd=tmp_path,
        timeout=5,
        env={"AGENTBENCH_OVERRIDE_SENTINEL": "child-value"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["parent", "child-value"]
