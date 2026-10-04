from __future__ import annotations

import pytest

from agentbench.statistics import (
    build_agent_ranking,
    build_pairwise_task_comparison,
    numeric_summary,
    wilson_interval,
)


def test_wilson_interval_is_bounded_and_matches_known_example():
    interval = wilson_interval(5, 10)

    assert interval is not None
    assert interval["method"] == "wilson_score"
    assert interval["low"] == pytest.approx(0.2366, abs=0.001)
    assert interval["high"] == pytest.approx(0.7634, abs=0.001)
    assert wilson_interval(0, 0) is None


def test_numeric_summary_uses_student_t_for_repeated_measurements():
    summary = numeric_summary([1.0, 2.0, 3.0])

    assert summary["measurements"] == 3
    assert summary["average"] == 2.0
    assert summary["median"] == 2.0
    assert summary["standard_deviation"] == 1.0
    interval = summary["confidence_interval_95"]
    assert interval["method"] == "student_t_mean"
    assert interval["low"] == pytest.approx(-0.484, abs=0.01)
    assert interval["high"] == pytest.approx(4.484, abs=0.01)


def test_ranking_prefers_conservative_reliability_over_raw_small_sample_rate():
    rows = [
        {
            "agent_config_id": 1,
            "agent_name": "ten-trial-agent",
            "metrics": {
                "planned_runs": 10,
                "successful_runs": 8,
                "success_rate": 0.8,
                "orchestration_errors": 0,
                "runtime_seconds": {"median": 5.0},
                "tokens": {"average": 100},
                "statistics": {
                    "success_rate_confidence_interval_95": wilson_interval(8, 10)
                },
            },
        },
        {
            "agent_config_id": 2,
            "agent_name": "one-trial-agent",
            "metrics": {
                "planned_runs": 1,
                "successful_runs": 1,
                "success_rate": 1.0,
                "orchestration_errors": 0,
                "runtime_seconds": {"median": 1.0},
                "tokens": {"average": 10},
                "statistics": {
                    "success_rate_confidence_interval_95": wilson_interval(1, 1)
                },
            },
        },
    ]

    ranking = build_agent_ranking(rows)

    assert ranking["entries"][0]["agent_name"] == "ten-trial-agent"
    assert ranking["entries"][0]["rank"] == 1
    assert ranking["entries"][1]["rank"] == 2


def test_pairwise_comparison_keeps_equal_quality_as_tie():
    cells = [
        {"task_id": 1, "agent_config_id": 1, "agent_name": "a", "metrics": {"success_rate": 1.0}},
        {"task_id": 1, "agent_config_id": 2, "agent_name": "b", "metrics": {"success_rate": 0.0}},
        {"task_id": 2, "agent_config_id": 1, "agent_name": "a", "metrics": {"success_rate": 0.5}},
        {"task_id": 2, "agent_config_id": 2, "agent_name": "b", "metrics": {"success_rate": 0.5}},
    ]

    comparison = build_pairwise_task_comparison(cells, [1, 2])[0]

    assert comparison["tasks_compared"] == 2
    assert comparison["left_task_wins"] == 1
    assert comparison["right_task_wins"] == 0
    assert comparison["ties"] == 1
    assert comparison["left_decisive_win_rate"] == 1.0
