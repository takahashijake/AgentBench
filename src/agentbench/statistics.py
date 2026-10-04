"""Statistical summaries and transparent agent rankings for AgentBench V2.

The module deliberately uses only the Python standard library so benchmark analysis
does not add a heavyweight scientific dependency. Intervals are descriptive,
two-sided 95% intervals: Wilson score for proportions and Student-t intervals for
sample means. Ranking uses the lower Wilson bound as a conservative reliability
score and exposes every tie-break explicitly.
"""

from __future__ import annotations

from itertools import combinations
import math
from statistics import mean, median, stdev
from typing import Any, Iterable


_Z_95 = 1.959963984540054

# Two-sided 95% Student-t critical values for degrees of freedom 1..30.
_T_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def wilson_interval(successes: int, total: int) -> dict[str, Any] | None:
    """Return a two-sided 95% Wilson score interval for a binomial proportion."""

    successes = int(successes)
    total = int(total)
    if total <= 0:
        return None
    if successes < 0 or successes > total:
        raise ValueError("successes must be between 0 and total")

    p = successes / total
    z2 = _Z_95 * _Z_95
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    margin = (
        _Z_95
        * math.sqrt((p * (1.0 - p) / total) + (z2 / (4.0 * total * total)))
        / denominator
    )
    return {
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
        "confidence": 0.95,
        "method": "wilson_score",
        "successes": successes,
        "total": total,
    }


def _t_critical_95(df: int) -> float:
    if df <= 0:
        raise ValueError("degrees of freedom must be positive")
    if df <= 30:
        return _T_95[df]
    if df <= 40:
        return 2.021
    if df <= 60:
        return 2.000
    if df <= 120:
        return 1.980
    return _Z_95


def numeric_summary(values: Iterable[float | int]) -> dict[str, Any]:
    """Summarize finite numeric measurements with an optional mean CI."""

    data = [float(value) for value in values if math.isfinite(float(value))]
    if not data:
        return {
            "measurements": 0,
            "total": 0.0,
            "average": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "standard_deviation": None,
            "confidence_interval_95": None,
        }

    n = len(data)
    avg = mean(data)
    sd = stdev(data) if n >= 2 else None
    interval = None
    if sd is not None:
        half_width = _t_critical_95(n - 1) * sd / math.sqrt(n)
        interval = {
            "low": avg - half_width,
            "high": avg + half_width,
            "confidence": 0.95,
            "method": "student_t_mean",
            "measurements": n,
        }

    return {
        "measurements": n,
        "total": sum(data),
        "average": avg,
        "median": median(data),
        "minimum": min(data),
        "maximum": max(data),
        "standard_deviation": sd,
        "confidence_interval_95": interval,
    }


def build_agent_ranking(by_agent: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic conservative leaderboard from aggregate agent rows."""

    entries: list[dict[str, Any]] = []
    for row in by_agent:
        metrics = row.get("metrics", {}) or {}
        planned = int(metrics.get("planned_runs") or 0)
        successes = int(metrics.get("successful_runs") or 0)
        interval = (metrics.get("statistics") or {}).get(
            "success_rate_confidence_interval_95"
        ) or wilson_interval(successes, planned)
        reliability = interval["low"] if interval else 0.0
        orchestration_errors = int(metrics.get("orchestration_errors") or 0)
        error_rate = orchestration_errors / planned if planned else 1.0
        runtime = metrics.get("runtime_seconds", {}) or {}
        runtime_median = runtime.get("median")
        entries.append(
            {
                "agent_config_id": row.get("agent_config_id"),
                "agent_name": row.get("agent_name"),
                "planned_runs": planned,
                "successful_runs": successes,
                "success_rate": metrics.get("success_rate"),
                "success_rate_confidence_interval_95": interval,
                "reliability_score": reliability,
                "orchestration_error_rate": error_rate,
                "median_runtime_seconds": runtime_median,
                "average_tokens": (metrics.get("tokens", {}) or {}).get("average"),
            }
        )

    def sort_key(entry: dict[str, Any]) -> tuple[Any, ...]:
        success_rate = entry["success_rate"]
        runtime = entry["median_runtime_seconds"]
        return (
            -float(entry["reliability_score"]),
            -float(success_rate if success_rate is not None else -1.0),
            float(entry["orchestration_error_rate"]),
            float(runtime) if runtime is not None else math.inf,
            str(entry.get("agent_name") or ""),
            int(entry.get("agent_config_id") or 0),
        )

    entries.sort(key=sort_key)
    for index, entry in enumerate(entries, start=1):
        entry["rank"] = index

    return {
        "method": "lower_wilson_then_success_then_errors_then_runtime",
        "description": (
            "Agents are ranked by the lower bound of the 95% Wilson success-rate "
            "interval, then observed success rate, orchestration error rate, median "
            "runtime, and stable agent identity. The score is conservative and is "
            "not a claim of statistical significance."
        ),
        "entries": entries,
    }


def exact_two_sided_sign_test(wins: int, losses: int) -> dict[str, Any] | None:
    """Exact two-sided sign test over decisive paired task outcomes.

    Ties are excluded. The null is an equal probability of either agent winning a
    decisive task. Independence across benchmark tasks remains an experimental
    assumption, so this result is reported but never used to manufacture rank.
    """

    wins = int(wins)
    losses = int(losses)
    if wins < 0 or losses < 0:
        raise ValueError("wins and losses must be non-negative")
    decisive = wins + losses
    if decisive == 0:
        return None
    tail = min(wins, losses)
    probability = sum(math.comb(decisive, k) for k in range(tail + 1)) / (2**decisive)
    return {
        "method": "exact_two_sided_sign_test",
        "p_value": min(1.0, 2.0 * probability),
        "decisive_tasks": decisive,
        "wins": wins,
        "losses": losses,
        "null_win_probability": 0.5,
    }


def build_pairwise_task_comparison(
    by_cell: list[dict[str, Any]],
    agent_order: list[int],
) -> list[dict[str, Any]]:
    """Compare agents task-by-task using observed success rate only.

    Runtime is intentionally not used to turn equal-quality outcomes into wins.
    Ties remain ties so the table is easy to interpret and does not imply a
    significance test.
    """

    cells: dict[tuple[int, int], dict[str, Any]] = {}
    names: dict[int, str] = {}
    task_ids: set[int] = set()
    for row in by_cell:
        task_id = int(row["task_id"])
        agent_id = int(row["agent_config_id"])
        cells[(task_id, agent_id)] = row
        names[agent_id] = str(row.get("agent_name") or f"agent-{agent_id}")
        task_ids.add(task_id)

    comparisons: list[dict[str, Any]] = []
    for left_id, right_id in combinations(agent_order, 2):
        wins = losses = ties = compared = 0
        differences: list[float] = []
        for task_id in sorted(task_ids):
            left = cells.get((task_id, left_id))
            right = cells.get((task_id, right_id))
            if left is None or right is None:
                continue
            left_rate = (left.get("metrics") or {}).get("success_rate")
            right_rate = (right.get("metrics") or {}).get("success_rate")
            if left_rate is None or right_rate is None:
                continue
            compared += 1
            differences.append(float(left_rate) - float(right_rate))
            if left_rate > right_rate:
                wins += 1
            elif left_rate < right_rate:
                losses += 1
            else:
                ties += 1

        decisive = wins + losses
        comparisons.append(
            {
                "left_agent_config_id": left_id,
                "left_agent_name": names.get(left_id, f"agent-{left_id}"),
                "right_agent_config_id": right_id,
                "right_agent_name": names.get(right_id, f"agent-{right_id}"),
                "tasks_compared": compared,
                "left_task_wins": wins,
                "right_task_wins": losses,
                "ties": ties,
                "left_decisive_win_rate": wins / decisive if decisive else None,
                "mean_success_rate_difference": (
                    mean(differences) if differences else None
                ),
                "exact_sign_test": exact_two_sided_sign_test(wins, losses),
            }
        )
    return comparisons


__all__ = [
    "build_agent_ranking",
    "build_pairwise_task_comparison",
    "exact_two_sided_sign_test",
    "numeric_summary",
    "wilson_interval",
]
