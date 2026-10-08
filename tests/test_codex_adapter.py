"""Codex provider contract and structured evidence regression coverage."""

from types import SimpleNamespace

import pytest

from agentbench.adapters.codex import CodexAgentAdapter
from agentbench.adapters.registry import create_default_adapter_registry


def test_codex_exec_enforces_jsonl_without_shell_expansion():
    adapter = create_default_adapter_registry().create(
        {"command_template": "codex exec '{prompt}'", "name": "codex"}
    )
    assert isinstance(adapter, CodexAgentAdapter)
    argv = adapter.build_argv("fix this; echo BAD")
    assert argv == ["codex", "exec", "--json", "fix this; echo BAD"]
    assert adapter.build_argv("more").count("--json") == 1


@pytest.mark.parametrize("command", [
    "codex '{prompt}'",
    "python runner.py '{prompt}'",
])
def test_codex_adapter_rejects_non_exec_commands(command):
    adapter = CodexAgentAdapter({"command_template": command})
    with pytest.raises(ValueError, match="Codex adapter requires"):
        adapter.build_argv("fix")


def test_codex_jsonl_metadata_deduplicates_activity_and_records_completion():
    adapter = CodexAgentAdapter({"command_template": "codex exec '{prompt}'"})
    adapter.last_result = SimpleNamespace(
        stdout="\n".join([
            '{"type":"item.started","item":{"id":"call1","type":"command_execution"}}',
            '{"type":"item.completed","item":{"id":"call1","type":"command_execution"}}',
            '{"type":"item.completed","item":{"id":"call2","type":"file_change"}}',
            '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}',
        ]),
        stderr="", returncode=0, timed_out=False, duration_seconds=1.2,
    )
    data = adapter.collect_metadata()
    assert data["execution_evidence"] == {
        "source": "codex_jsonl",
        "turn_completed": True,
        "tool_activity_count": 2,
        "termination_reason": "completed",
    }
    assert data["usage"]["total_tokens"] == 10
    assert data["usage"]["cost_usd"] is None


def test_codex_malformed_output_and_failure_are_not_success():
    adapter = CodexAgentAdapter({"command_template": "codex exec '{prompt}'"})
    adapter.last_result = SimpleNamespace(
        stdout='{"type": bad}', stderr="failed",
        returncode=1, timed_out=False, duration_seconds=0.1,
    )
    data = adapter.collect_metadata()["execution_evidence"]
    assert data["source"] is None
    assert data["turn_completed"] is False
    assert data["tool_activity_count"] is None
    assert data["termination_reason"] == "process_error"


def test_codex_timeout_retains_timeout_reason_even_with_partial_events():
    adapter = CodexAgentAdapter({"command_template": "codex exec '{prompt}'"})
    adapter.last_result = SimpleNamespace(
        stdout='{"type":"item.started","item":{"id":"cmd","type":"command_execution"}}',
        stderr="", returncode=-9, timed_out=True, duration_seconds=2.0,
    )
    evidence = adapter.collect_metadata()["execution_evidence"]
    assert evidence["termination_reason"] == "timeout"
    assert evidence["tool_activity_count"] == 1
    assert evidence["turn_completed"] is False
