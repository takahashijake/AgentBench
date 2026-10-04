"""Deterministic static publication from verified result bundles.

This module is deliberately database-free. It trusts only data that has passed the
portable bundle verifier and emits self-contained files suitable for static
hosting (including GitHub Pages).
"""

from __future__ import annotations

import html
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .bundle_format import (
    VerifiedResultBundle,
    canonical_json_bytes,
    sha256_bytes,
    verify_result_bundle,
)


PUBLICATION_SCHEMA_VERSION = 1


class PublicationError(ValueError):
    """Raised when a static publication cannot be produced safely."""


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _number(value: object, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return _escape(value)


def _percent(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return _escape(value)


def _render_ranking(summary: dict[str, Any]) -> str:
    ranking = summary.get("ranking") or {}
    entries = ranking.get("entries") or []
    if not entries:
        return "<p>No ranked agents are available in this result.</p>"

    rows = []
    for row in entries:
        interval = row.get("success_rate_confidence_interval_95") or {}
        low = _percent(interval.get("low"))
        high = _percent(interval.get("high"))
        rows.append(
            "<tr>"
            f"<td>{_escape(row.get('rank'))}</td>"
            f"<td>{_escape(row.get('agent_name', 'unknown'))}</td>"
            f"<td>{_percent(row.get('reliability_score'))}</td>"
            f"<td>{_percent(row.get('success_rate'))}</td>"
            f"<td>{low} – {high}</td>"
            f"<td>{_number(row.get('median_runtime_seconds'))}</td>"
            f"<td>{_number(row.get('average_tokens'), digits=0)}</td>"
            "</tr>"
        )
    description = _escape(ranking.get("description") or "")
    return (
        "<table><thead><tr>"
        "<th>Rank</th><th>Agent</th><th>Reliability</th><th>Success</th>"
        "<th>95% success CI</th><th>Median runtime (s)</th><th>Avg tokens</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + (f"<p class=\"method\">{description}</p>" if description else "")
    )


def _render_pairwise(summary: dict[str, Any]) -> str:
    rows = summary.get("pairwise_task_comparison") or []
    if not rows:
        return "<p>Pairwise comparison requires at least two agents.</p>"

    rendered = []
    for row in rows:
        sign = row.get("exact_sign_test") or {}
        rendered.append(
            "<tr>"
            f"<td>{_escape(row.get('left_agent_name', 'unknown'))}</td>"
            f"<td>{_escape(row.get('right_agent_name', 'unknown'))}</td>"
            f"<td>{_escape(row.get('left_task_wins', 0))}</td>"
            f"<td>{_escape(row.get('right_task_wins', 0))}</td>"
            f"<td>{_escape(row.get('ties', 0))}</td>"
            f"<td>{_percent(row.get('mean_success_rate_difference'))}</td>"
            f"<td>{_number(sign.get('p_value'), digits=4)}</td>"
            f"<td>{_escape(row.get('tasks_compared', 0))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Agent A</th><th>Agent B</th><th>A wins</th><th>B wins</th>"
        "<th>Ties</th><th>Mean Δ success</th><th>Exact sign p</th><th>Tasks</th>"
        "</tr></thead><tbody>"
        + "".join(rendered)
        + "</tbody></table>"
        "<p class=\"method\">The exact sign test is descriptive and does not "
        "alter AgentBench ranking.</p>"
    )


def render_static_report(verified: VerifiedResultBundle) -> str:
    """Render one dependency-free HTML report from verified bundle data."""

    report = verified.report
    experiment = report.get("experiment") or {}
    summary = report.get("summary") or {}
    overall = summary.get("overall") or {}
    name = _escape(experiment.get("name") or "AgentBench experiment")
    identity = _escape(verified.identity_sha256)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} · AgentBench</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 1120px; margin: 0 auto; padding: 2rem; line-height: 1.5; }}
h1, h2 {{ line-height: 1.15; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); gap: .75rem; }}
.card {{ border: 1px solid #8886; border-radius: .6rem; padding: .8rem; }}
.label {{ opacity: .7; font-size: .85rem; }}
.value {{ font-size: 1.25rem; font-weight: 650; }}
table {{ border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }}
th, td {{ border-bottom: 1px solid #8885; text-align: left; padding: .55rem .65rem; white-space: nowrap; }}
code {{ overflow-wrap: anywhere; }}
.method {{ opacity: .75; }}
footer {{ margin-top: 3rem; opacity: .7; }}
</style>
</head>
<body>
<header>
<p>AgentBench verified static report</p>
<h1>{name}</h1>
<p>Status: <strong>{_escape(experiment.get("status", "unknown"))}</strong></p>
</header>
<section>
<h2>Experiment result</h2>
<div class="cards">
<div class="card"><div class="label">Planned runs</div><div class="value">{_escape(overall.get("planned_runs", experiment.get("planned_runs", "—")))}</div></div>
<div class="card"><div class="label">Success rate</div><div class="value">{_percent(overall.get("success_rate"))}</div></div>
<div class="card"><div class="label">Completion rate</div><div class="value">{_percent(overall.get("completion_rate"))}</div></div>
<div class="card"><div class="label">Orchestration errors</div><div class="value">{_escape(overall.get("orchestration_errors", 0))}</div></div>
</div>
</section>
<section>
<h2>Conservative ranking</h2>
{_render_ranking(summary)}
</section>
<section>
<h2>Pairwise task outcomes</h2>
{_render_pairwise(summary)}
</section>
<section>
<h2>Verification</h2>
<p>Source bundle identity:</p>
<p><code>{identity}</code></p>
<p>This page was generated only after bundle manifest and payload digests were verified.</p>
</section>
<footer>
<p>Machine-readable data: <a href="report.json">report.json</a> · <a href="bundle.json">bundle.json</a> · <a href="publication.json">publication.json</a></p>
</footer>
</body>
</html>
"""


def publish_result_bundle(
    bundle_path: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    """Verify a result bundle and atomically create a deterministic static site."""

    verified = verify_result_bundle(bundle_path)
    target = Path(destination).expanduser().resolve()
    if target.exists():
        raise PublicationError(f"Publication destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    payloads = {
        "index.html": render_static_report(verified).encode("utf-8"),
        "report.json": canonical_json_bytes(verified.report),
        "bundle.json": canonical_json_bytes(verified.manifest),
    }
    file_manifest = [
        {
            "path": name,
            "sha256": sha256_bytes(payloads[name]),
            "size": len(payloads[name]),
        }
        for name in sorted(payloads)
    ]
    publication_core = {
        "publication_schema_version": PUBLICATION_SCHEMA_VERSION,
        "source_bundle_identity_sha256": verified.identity_sha256,
        "experiment": verified.manifest.get("experiment"),
        "files": file_manifest,
    }
    publication = {
        **publication_core,
        "identity_sha256": sha256_bytes(canonical_json_bytes(publication_core)),
    }
    payloads["publication.json"] = canonical_json_bytes(publication)

    temp = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.tmp-",
            dir=str(target.parent),
        )
    )
    try:
        for name in sorted(payloads):
            (temp / name).write_bytes(payloads[name])
        temp.replace(target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    return {
        "published": True,
        "source_bundle": str(verified.path),
        "source_bundle_identity_sha256": verified.identity_sha256,
        "destination": str(target),
        "publication_schema_version": PUBLICATION_SCHEMA_VERSION,
        "identity_sha256": publication["identity_sha256"],
        "file_count": len(payloads),
    }


__all__ = [
    "PUBLICATION_SCHEMA_VERSION",
    "PublicationError",
    "publish_result_bundle",
    "render_static_report",
]
