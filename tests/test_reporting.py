from __future__ import annotations

from agentbench.reporting import render_leaderboard_markdown, render_markdown_report
from agentbench.statistics import wilson_interval


def make_summary():
    return {
        "analysis_schema_version": 2,
        "overall": {
            "planned_runs": 10,
            "benchmark_runs": 10,
            "successful_runs": 8,
            "failed_runs": 2,
            "success_rate": 0.8,
            "completion_rate": 1.0,
            "orchestration_errors": 0,
            "tests_passed": 40,
            "tests_failed": 2,
            "runtime_seconds": {
                "measurements": 10,
                "average": 2.5,
                "median": 2.2,
                "total": 25.0,
                "confidence_interval_95": {
                    "low": 2.0,
                    "high": 3.0,
                    "confidence": 0.95,
                    "method": "student_t_mean",
                },
            },
            "tokens": {
                "measurements": 8,
                "coverage_rate": 0.8,
                "average": 1200.0,
                "median": 1100.0,
            },
            "statistics": {
                "success_rate_confidence_interval_95": wilson_interval(8, 10),
            },
        },
        "by_agent": [
            {
                "agent_config_id": 1,
                "agent_name": "agent-a",
                "metrics": {
                    "planned_runs": 5,
                    "benchmark_runs": 5,
                    "successful_runs": 5,
                    "success_rate": 1.0,
                    "tests_passed": 25,
                    "runtime_seconds": {"median": 2.0},
                    "tokens": {"average": 1000.0},
                    "changes": {"files_changed_total": 5},
                    "statistics": {
                        "success_rate_confidence_interval_95": wilson_interval(5, 5),
                    },
                },
            },
            {
                "agent_config_id": 2,
                "agent_name": "agent-b",
                "metrics": {
                    "planned_runs": 5,
                    "benchmark_runs": 5,
                    "successful_runs": 3,
                    "success_rate": 0.6,
                    "tests_passed": 15,
                    "runtime_seconds": {"median": 3.0},
                    "tokens": {"average": 1400.0},
                    "changes": {"files_changed_total": 6},
                    "statistics": {
                        "success_rate_confidence_interval_95": wilson_interval(3, 5),
                    },
                },
            },
        ],
        "by_task": [
            {
                "task_id": 1,
                "task_name": "task-a",
                "metrics": {
                    "planned_runs": 10,
                    "benchmark_runs": 10,
                    "successful_runs": 8,
                    "success_rate": 0.8,
                    "orchestration_errors": 0,
                    "statistics": {
                        "success_rate_confidence_interval_95": wilson_interval(8, 10),
                    },
                },
            }
        ],
        "ranking": {
            "method": "lower_wilson_then_success_then_errors_then_runtime",
            "description": "Conservative reliability ranking.",
            "entries": [
                {
                    "rank": 1,
                    "agent_config_id": 1,
                    "agent_name": "agent-a",
                    "reliability_score": wilson_interval(5, 5)["low"],
                    "success_rate": 1.0,
                    "success_rate_confidence_interval_95": wilson_interval(5, 5),
                    "median_runtime_seconds": 2.0,
                    "average_tokens": 1000.0,
                },
                {
                    "rank": 2,
                    "agent_config_id": 2,
                    "agent_name": "agent-b",
                    "reliability_score": wilson_interval(3, 5)["low"],
                    "success_rate": 0.6,
                    "success_rate_confidence_interval_95": wilson_interval(3, 5),
                    "median_runtime_seconds": 3.0,
                    "average_tokens": 1400.0,
                },
            ],
        },
        "pairwise_task_comparison": [
            {
                "left_agent_name": "agent-a",
                "right_agent_name": "agent-b",
                "left_task_wins": 1,
                "right_task_wins": 0,
                "ties": 0,
                "tasks_compared": 1,
            }
        ],
    }


def test_markdown_report_surfaces_v2_corpus_uncertainty_and_reproducibility():
    report = {
        "suite": {
            "id": "demo",
            "name": "Demo Suite",
            "manifest_sha256": "a" * 64,
            "benchmark_pack": {
                "id": "core-v2",
                "version": "2.0.0",
                "description": "deterministic corpus",
            },
        },
        "experiment": {
            "id": 4,
            "name": "Demo",
            "status": "completed",
            "planned_runs": 10,
        },
        "lock": {
            "lock_schema_version": 1,
            "identity_sha256": "b" * 64,
        },
        "summary": make_summary(),
    }

    rendered = render_markdown_report(report)

    assert "# Demo Suite" in rendered
    assert "**Pack:** core-v2 2.0.0" in rendered
    assert "**Success rate:** 80.0%" in rendered
    assert "**95% success interval:**" in rendered
    assert "**Median runtime:** 2.20 s" in rendered
    assert "**Token coverage:** 80.0%" in rendered
    assert "## Conservative ranking" in rendered
    assert "agent-a" in rendered
    assert "agent-b" in rendered
    assert "## Pairwise task outcomes" in rendered
    assert "task-a" in rendered
    assert "bbbbbbbb" in rendered
    assert "not claim that repetitions are independent" in rendered
    assert "isolated detached worktree" in rendered


def test_leaderboard_markdown_discloses_method_and_keeps_pairwise_ties_semantic():
    summary = make_summary()

    rendered = render_leaderboard_markdown(summary, title="Comparison")

    assert "# Comparison" in rendered
    assert "Reliability" in rendered
    assert "Conservative reliability ranking." in rendered
    assert "agent-a" in rendered
    assert "agent-b" in rendered
    assert "Pairwise task outcomes" in rendered
    assert "runtime is not used to manufacture a quality win" in rendered
