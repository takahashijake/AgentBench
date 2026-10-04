"""Conservative extraction of structured usage metadata from agent output."""

from __future__ import annotations

import json
import re
import shlex
from typing import Any, Iterable


_TOKEN_ALIASES = {
    "prompt_tokens": {"prompt_tokens", "input_tokens", "inputTokens"},
    "completion_tokens": {"completion_tokens", "output_tokens", "outputTokens"},
    "total_tokens": {"total_tokens", "totalTokens"},
    "cached_input_tokens": {
        "cached_input_tokens",
        "cache_read_input_tokens",
        "cachedInputTokens",
    },
}
_COST_KEYS = {"cost_usd", "costUSD", "total_cost_usd"}


def detect_agent_family(command_template: str) -> str:
    """Infer a stable family label from the command executable."""

    try:
        tokens = shlex.split(command_template)
    except ValueError:
        return "unknown"
    if not tokens:
        return "unknown"
    executable = tokens[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "codex" in executable:
        return "codex"
    if "qwen" in executable:
        return "qwen"
    if "claude" in executable:
        return "claude"
    if "gemini" in executable:
        return "gemini"
    return "shell"


def _objects_from_lines(text: str) -> Iterable[dict[str, Any]]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _coerce_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        return int(value)
    return None


def _coerce_nonnegative_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def extract_usage_metadata(stdout: str, stderr: str = "") -> dict[str, Any]:
    """Extract token/cost fields only from complete JSON/JSONL objects.

    The parser is intentionally conservative: arbitrary prose containing numbers
    is ignored. If multiple structured events report cumulative usage, the maximum
    observed value for each counter is retained.
    """

    objects = list(_objects_from_lines(stdout)) + list(_objects_from_lines(stderr))
    counters: dict[str, int] = {}
    cost_usd: float | None = None

    for root in objects:
        for obj in _walk_dicts(root):
            for canonical, aliases in _TOKEN_ALIASES.items():
                for key in aliases:
                    if key in obj:
                        value = _coerce_nonnegative_int(obj[key])
                        if value is not None:
                            counters[canonical] = max(counters.get(canonical, 0), value)
            for key in _COST_KEYS:
                if key in obj:
                    value = _coerce_nonnegative_float(obj[key])
                    if value is not None:
                        cost_usd = max(cost_usd or 0.0, value)

    prompt = counters.get("prompt_tokens")
    completion = counters.get("completion_tokens")
    total = counters.get("total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
        counters["total_tokens"] = total

    return {
        "source": "structured_json_output"
        if counters or cost_usd is not None
        else None,
        "structured_events_scanned": len(objects),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_input_tokens": counters.get("cached_input_tokens"),
        "cost_usd": cost_usd,
    }


__all__ = [
    "detect_agent_family",
    "extract_usage_metadata",
]
