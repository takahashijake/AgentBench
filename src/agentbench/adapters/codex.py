"""Codex CLI adapter: structured execution evidence without shell interpolation."""

from __future__ import annotations

import json
from typing import Any

from .shell import ShellAgentAdapter


class CodexAgentAdapter(ShellAgentAdapter):
    """Run an explicitly configured Codex exec command with JSONL events."""

    def build_argv(self, prompt: str) -> list[str]:
        argv = super().build_argv(prompt)
        executable = argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if executable not in {"codex", "codex.exe"}:
            raise ValueError("Codex adapter requires the codex executable")
        if len(argv) < 2 or argv[1] != "exec":
            raise ValueError(
                "Codex adapter requires a noninteractive 'codex exec' command"
            )
        if "--json" not in argv:
            argv.insert(2, "--json")
        return argv

    def collect_metadata(self) -> dict[str, Any]:
        metadata = super().collect_metadata()
        metadata["adapter"] = "codex"
        metadata["execution_evidence"] = {
            "source": None,
            "turn_completed": None,
            "tool_activity_count": None,
            "termination_reason": None,
        }
        result = self.last_result
        if result is None:
            return metadata

        completed = 0
        tool_items: set[str] = set()
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type == "turn.completed":
                completed += 1
            if event_type in {"item.started", "item.completed"}:
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") in {
                    "command_execution",
                    "file_change",
                    "mcp_tool_call",
                    "web_search",
                }:
                    item_id = item.get("id")
                    if isinstance(item_id, str) and item_id:
                        tool_items.add(item_id)

        metadata["execution_evidence"] = {
            "source": "codex_jsonl" if completed or tool_items else None,
            "turn_completed": bool(completed),
            "tool_activity_count": len(tool_items) if completed or tool_items else None,
            "termination_reason": (
                "timeout"
                if result.timed_out
                else "process_error"
                if result.returncode != 0
                else "completed"
                if completed
                else "unknown"
            ),
        }
        return metadata


__all__ = ["CodexAgentAdapter"]
