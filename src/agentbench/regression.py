"""Baseline-versus-candidate regression analysis for portable result bundles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .result_bundles import VerifiedResultBundle, verify_result_bundle


REGRESSION_SCHEMA_VERSION = 1


class RegressionComparisonError(ValueError):
    """Raised when two bundles cannot be compared as the same benchmark."""


@dataclass(frozen=True)
class RegressionPolicy:
    max_success_rate_drop: float = 0.0
    max_reliability_drop: float = 0.0
    max_orchestration_error_rate_increase: float = 0.0
    max_median_runtime_increase_ratio: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_success_rate_drop",
            "max_reliability_drop",
            "max_orchestration_error_rate_increase",
        ):
            value = float(getattr(self, name))
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if (
            self.max_median_runtime_increase_ratio is not None
            and self.max_median_runtime_increase_ratio < 0
        ):
            raise ValueError(
                "max_median_runtime_increase_ratio must be >= 0 when provided"
            )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _task_projection(experiment: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots = experiment.get("task_snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise RegressionComparisonError(
            "Portable experiment does not contain task snapshots"
        )
    projected: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise RegressionComparisonError("Invalid portable task snapshot")
        projected.append(
            {
                "name": snapshot.get("name"),
                "description": snapshot.get("description"),
                "base_commit": snapshot.get("base_commit"),
                "agent_prompt_sha256": snapshot.get("agent_prompt_sha256"),
                "setup_command": snapshot.get("setup_command"),
                "test_command": snapshot.get("test_command"),
                "timeout": snapshot.get("timeout"),
                "requirements": snapshot.get("requirements") or {},
            }
        )
    return sorted(
        projected,
        key=lambda value: _canonical_bytes(value),
    )


def _task_fingerprint(experiment: dict[str, Any]) -> str:
    return sha256(_canonical_bytes(_task_projection(experiment))).hexdigest()


def _agent_metrics(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise RegressionComparisonError("Bundle report does not contain a summary")
    rows = summary.get("by_agent")
    if not isinstance(rows, list):
        raise RegressionComparisonError("Bundle report does not contain by_agent rows")

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RegressionComparisonError("Invalid by_agent row")
        name = str(row.get("agent_name") or "").strip()
        metrics = row.get("metrics")
        if not name or not isinstance(metrics, dict):
            raise RegressionComparisonError("Invalid by_agent identity or metrics")
        if name in result:
            raise RegressionComparisonError(
                f"Agent names must be unique for regression comparison: {name!r}"
            )
        result[name] = metrics
    return result


def _rate(numerator: Any, denominator: Any) -> float | None:
    try:
        den = int(denominator)
        num = int(numerator)
    except (TypeError, ValueError):
        return None
    if den <= 0:
        return None
    return num / den


def _metric_value(metrics: dict[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = metrics
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _agent_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    eligible = metrics.get("eligible_planned_runs")
    errors = metrics.get("orchestration_errors")
    reliability = _metric_value(
        metrics,
        ("statistics", "success_rate_confidence_interval_95", "low"),
    )
    return {
        "success_rate": _metric_value(metrics, ("success_rate",)),
        "reliability_score": reliability,
        "orchestration_error_rate": _rate(errors, eligible),
        "median_runtime_seconds": _metric_value(
            metrics,
            ("runtime_seconds", "median"),
        ),
        "eligible_planned_runs": eligible,
        "successful_runs": metrics.get("successful_runs"),
        "orchestration_errors": errors,
    }


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _runtime_ratio(
    candidate: float | None,
    baseline: float | None,
) -> float | None:
    if candidate is None or baseline is None or baseline <= 0:
        return None
    return candidate / baseline


def compare_verified_bundles(
    baseline: VerifiedResultBundle,
    candidate: VerifiedResultBundle,
) -> dict[str, Any]:
    baseline_tasks = _task_projection(baseline.experiment)
    candidate_tasks = _task_projection(candidate.experiment)
    if baseline_tasks != candidate_tasks:
        raise RegressionComparisonError(
            "Baseline and candidate portable task definitions do not match"
        )

    baseline_repetitions = baseline.experiment.get("repetitions")
    candidate_repetitions = candidate.experiment.get("repetitions")
    if baseline_repetitions != candidate_repetitions:
        raise RegressionComparisonError(
            "Baseline and candidate repetition counts do not match"
        )

    baseline_agents = _agent_metrics(baseline.report)
    candidate_agents = _agent_metrics(candidate.report)
    if set(baseline_agents) != set(candidate_agents):
        missing = sorted(set(baseline_agents) - set(candidate_agents))
        added = sorted(set(candidate_agents) - set(baseline_agents))
        raise RegressionComparisonError(
            "Baseline and candidate agent sets do not match: "
            f"missing={missing}, added={added}"
        )

    rows: list[dict[str, Any]] = []
    for name in sorted(baseline_agents):
        baseline_snapshot = _agent_snapshot(baseline_agents[name])
        candidate_snapshot = _agent_snapshot(candidate_agents[name])
        rows.append(
            {
                "agent_name": name,
                "baseline": baseline_snapshot,
                "candidate": candidate_snapshot,
                "deltas": {
                    "success_rate": _delta(
                        candidate_snapshot["success_rate"],
                        baseline_snapshot["success_rate"],
                    ),
                    "reliability_score": _delta(
                        candidate_snapshot["reliability_score"],
                        baseline_snapshot["reliability_score"],
                    ),
                    "orchestration_error_rate": _delta(
                        candidate_snapshot["orchestration_error_rate"],
                        baseline_snapshot["orchestration_error_rate"],
                    ),
                    "median_runtime_ratio": _runtime_ratio(
                        candidate_snapshot["median_runtime_seconds"],
                        baseline_snapshot["median_runtime_seconds"],
                    ),
                },
            }
        )

    return {
        "regression_schema_version": REGRESSION_SCHEMA_VERSION,
        "compatible": True,
        "task_fingerprint_sha256": _task_fingerprint(baseline.experiment),
        "repetitions": baseline_repetitions,
        "baseline": {
            "bundle_identity_sha256": baseline.identity_sha256,
            "experiment": baseline.manifest.get("experiment"),
        },
        "candidate": {
            "bundle_identity_sha256": candidate.identity_sha256,
            "experiment": candidate.manifest.get("experiment"),
        },
        "agents": rows,
    }


def compare_bundles(
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> dict[str, Any]:
    return compare_verified_bundles(
        verify_result_bundle(baseline_path),
        verify_result_bundle(candidate_path),
    )


def evaluate_regression_gate(
    comparison: dict[str, Any],
    policy: RegressionPolicy,
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    for row in comparison.get("agents") or []:
        name = str(row.get("agent_name") or "unknown")
        deltas = row.get("deltas") or {}

        success_delta = deltas.get("success_rate")
        if (
            success_delta is not None
            and success_delta < -policy.max_success_rate_drop
        ):
            violations.append(
                {
                    "agent_name": name,
                    "metric": "success_rate",
                    "actual_delta": success_delta,
                    "allowed_drop": policy.max_success_rate_drop,
                }
            )

        reliability_delta = deltas.get("reliability_score")
        if (
            reliability_delta is not None
            and reliability_delta < -policy.max_reliability_drop
        ):
            violations.append(
                {
                    "agent_name": name,
                    "metric": "reliability_score",
                    "actual_delta": reliability_delta,
                    "allowed_drop": policy.max_reliability_drop,
                }
            )

        error_delta = deltas.get("orchestration_error_rate")
        if (
            error_delta is not None
            and error_delta > policy.max_orchestration_error_rate_increase
        ):
            violations.append(
                {
                    "agent_name": name,
                    "metric": "orchestration_error_rate",
                    "actual_delta": error_delta,
                    "allowed_increase": policy.max_orchestration_error_rate_increase,
                }
            )

        runtime_ratio = deltas.get("median_runtime_ratio")
        if (
            policy.max_median_runtime_increase_ratio is not None
            and runtime_ratio is not None
            and runtime_ratio
            > 1.0 + policy.max_median_runtime_increase_ratio
        ):
            violations.append(
                {
                    "agent_name": name,
                    "metric": "median_runtime_seconds",
                    "actual_ratio": runtime_ratio,
                    "allowed_increase_ratio": (
                        policy.max_median_runtime_increase_ratio
                    ),
                }
            )

    return {
        **comparison,
        "policy": policy.as_dict(),
        "passed": not violations,
        "violation_count": len(violations),
        "violations": violations,
    }


def gate_bundles(
    baseline_path: str | Path,
    candidate_path: str | Path,
    *,
    policy: RegressionPolicy,
) -> dict[str, Any]:
    return evaluate_regression_gate(
        compare_bundles(baseline_path, candidate_path),
        policy,
    )


__all__ = [
    "REGRESSION_SCHEMA_VERSION",
    "RegressionComparisonError",
    "RegressionPolicy",
    "compare_bundles",
    "compare_verified_bundles",
    "evaluate_regression_gate",
    "gate_bundles",
]
