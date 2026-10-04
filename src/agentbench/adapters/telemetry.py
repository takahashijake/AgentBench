"""Typed adapter telemetry contracts.

Persistence continues to use JSON-compatible dictionaries, while adapters can
exchange validated telemetry values internally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..usage import extract_usage_metadata


@dataclass(frozen=True)
class UsageTelemetry:
    source: str | None = None
    structured_events_scanned: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        numeric = (
            self.structured_events_scanned,
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.cached_input_tokens,
        )
        if any(value is not None and value < 0 for value in numeric):
            raise ValueError("Usage telemetry counters must be non-negative")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("Usage telemetry cost must be non-negative")

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "UsageTelemetry":
        return cls(
            source=(
                str(payload["source"])
                if payload.get("source") is not None
                else None
            ),
            structured_events_scanned=int(
                payload.get("structured_events_scanned") or 0
            ),
            prompt_tokens=_optional_int(payload.get("prompt_tokens")),
            completion_tokens=_optional_int(payload.get("completion_tokens")),
            total_tokens=_optional_int(payload.get("total_tokens")),
            cached_input_tokens=_optional_int(payload.get("cached_input_tokens")),
            cost_usd=_optional_float(payload.get("cost_usd")),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "structured_events_scanned": self.structured_events_scanned,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cost_usd": self.cost_usd,
        }


class TelemetryParser(Protocol):
    def parse(self, stdout: str, stderr: str = "") -> UsageTelemetry:
        ...


class StructuredJsonTelemetryParser:
    """Typed facade over AgentBench's conservative JSON/JSONL usage parser."""

    def parse(self, stdout: str, stderr: str = "") -> UsageTelemetry:
        return UsageTelemetry.from_mapping(
            extract_usage_metadata(stdout, stderr)
        )


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


__all__ = [
    "StructuredJsonTelemetryParser",
    "TelemetryParser",
    "UsageTelemetry",
]
