from __future__ import annotations

from agentbench.reporting import render_markdown_report


def test_markdown_report_surfaces_comparison_and_reproducibility():
    report = {
        "suite": {
            "id": "demo",
            "name": "Demo Suite",
            "manifest_sha256": "a" * 64,
        },
        "experiment": {
            "id": 4,
            "name": "Demo",
            "status": "completed",
            "planned_runs": 2,
        },
        "lock": {
            "lock_schema_version": 1,
            "identity_sha256": "b" * 64,
        },
        "summary": {
            "overall": {
                "planned_runs": 2,
                "benchmark_runs": 2,
                "success_rate": 0.5,
                "completion_rate": 1.0,
                "orchestration_errors": 0,
                "tests_passed": 10,
                "tests_failed": 1,
                "runtime_seconds": {"average": 2.5, "total": 5.0},
            },
            "by_agent": [
                {
                    "agent_name": "agent-a",
                    "metrics": {
                        "benchmark_runs": 2,
                        "success_rate": 0.5,
                        "tests_passed": 10,
                        "runtime_seconds": {"average": 2.5},
                        "changes": {"files_changed_total": 3},
                    },
                }
            ],
            "by_task": [
                {
                    "task_name": "task-a",
                    "metrics": {
                        "benchmark_runs": 2,
                        "success_rate": 0.5,
                        "orchestration_errors": 0,
                    },
                }
            ],
        },
    }

    rendered = render_markdown_report(report)

    assert "# Demo Suite" in rendered
    assert "**Success rate:** 50.0%" in rendered
    assert "agent-a" in rendered
    assert "task-a" in rendered
    assert "bbbbbbbb" in rendered
    assert "isolated detached worktree" in rendered
