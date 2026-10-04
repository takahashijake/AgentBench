"""Deterministic static publication for verified AgentBench evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from . import __version__
from .result_bundles import (
    ResultBundleService,
    VerifiedResultBundle,
    verify_result_bundle,
)


PUBLICATION_SCHEMA_VERSION = 1
_PUBLICATION_FILES = ("index.html", "report.json")


class PublicationValidationError(ValueError):
    """Raised when a static publication violates its integrity contract."""


@dataclass(frozen=True)
class VerifiedPublication:
    path: Path
    manifest: dict[str, Any]
    report: dict[str, Any]

    @property
    def identity_sha256(self) -> str:
        return str(self.manifest["identity_sha256"])


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _fmt_percent(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return escape(str(value))
    if number.is_integer():
        return str(int(number))
    return f"{number:.{digits}f}"


def _render_ranking_rows(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    ranking = summary.get("ranking") or {}
    rows = ranking.get("entries") or []
    if not rows:
        return '<tr><td colspan="6">No ranking rows available.</td></tr>'
    rendered: list[str] = []
    for row in rows:
        rendered.append(
            "<tr>"
            f"<td>{escape(str(row.get('rank', 'n/a')))}</td>"
            f"<td>{escape(str(row.get('agent_name', 'unknown')))}</td>"
            f"<td>{_fmt_percent(row.get('reliability_score'))}</td>"
            f"<td>{_fmt_percent(row.get('success_rate'))}</td>"
            f"<td>{_fmt_number(row.get('median_runtime_seconds'))}</td>"
            f"<td>{_fmt_number(row.get('average_total_tokens'))}</td>"
            "</tr>"
        )
    return "".join(rendered)


def _render_worker_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    workers = summary.get("worker_summary") or {}
    if not workers:
        return "<p>No distributed-worker activity was recorded.</p>"
    owners = workers.get("owners") or []
    return (
        '<dl class="stats">'
        f"<div><dt>Worker attempts</dt><dd>{_fmt_number(workers.get('attempt_count'))}</dd></div>"
        f"<div><dt>Active leases</dt><dd>{_fmt_number(workers.get('active_count'))}</dd></div>"
        f"<div><dt>Expired active leases</dt><dd>{_fmt_number(workers.get('expired_active_count'))}</dd></div>"
        f"<div><dt>Distinct owners</dt><dd>{len(owners)}</dd></div>"
        "</dl>"
    )


def render_publication_html(
    report: dict[str, Any],
    *,
    source_bundle_identity: str,
) -> str:
    """Render a standalone, dependency-free report page."""

    experiment = report.get("experiment") or {}
    summary = report.get("summary") or {}
    overall = summary.get("overall") or {}
    latest = summary.get("latest_execution") or {}
    title = str(experiment.get("name") or "AgentBench experiment")
    description = experiment.get("description")
    description_html = (
        f'<p class="lede">{escape(str(description))}</p>' if description else ""
    )
    source_short = escape(source_bundle_identity[:16])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · AgentBench</title>
<style>
:root {{ color-scheme: light dark; --bg:#0b1020; --panel:#11182b; --text:#e8edf7; --muted:#9ba8bd; --line:#27324a; --accent:#8ab4ff; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1120px; margin:0 auto; padding:56px 24px 80px; }}
header {{ margin-bottom:32px; }}
h1 {{ font-size:clamp(2rem,5vw,4rem); line-height:1.05; margin:0 0 12px; }}
h2 {{ margin-top:0; }}
.lede,.muted {{ color:var(--muted); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; margin:24px 0; }}
.card,section {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:20px; margin:18px 0; }}
.card strong {{ display:block; font-size:1.55rem; }}
.card span {{ color:var(--muted); }}
table {{ width:100%; border-collapse:collapse; overflow:auto; }}
th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-weight:600; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
.stats div {{ border:1px solid var(--line); border-radius:10px; padding:12px; }}
dt {{ color:var(--muted); }}
dd {{ margin:2px 0 0; font-size:1.25rem; }}
a {{ color:var(--accent); }}
code {{ overflow-wrap:anywhere; }}
footer {{ color:var(--muted); margin-top:32px; font-size:.9rem; }}
</style>
</head>
<body>
<main>
<header>
<p class="muted">AgentBench {escape(__version__)} · verified static publication</p>
<h1>{escape(title)}</h1>
{description_html}
<p class="muted">Source bundle <code>{source_short}…</code></p>
</header>

<div class="grid">
<div class="card"><strong>{escape(str(experiment.get("status", "unknown")))}</strong><span>experiment status</span></div>
<div class="card"><strong>{_fmt_number(overall.get("successful_runs"))}</strong><span>successful runs</span></div>
<div class="card"><strong>{_fmt_percent(overall.get("success_rate"))}</strong><span>eligible success rate</span></div>
<div class="card"><strong>{_fmt_number(overall.get("skipped_runs", 0))}</strong><span>resource-skipped runs</span></div>
<div class="card"><strong>{escape(str(latest.get("mode", "n/a")))}</strong><span>latest execution mode</span></div>
<div class="card"><strong>{_fmt_number(latest.get("max_workers"))}</strong><span>latest worker count</span></div>
</div>

<section>
<h2>Conservative leaderboard</h2>
<table>
<thead><tr><th>Rank</th><th>Agent</th><th>Reliability</th><th>Success</th><th>Median runtime (s)</th><th>Avg tokens</th></tr></thead>
<tbody>{_render_ranking_rows(report)}</tbody>
</table>
</section>

<section>
<h2>Distributed execution</h2>
{_render_worker_summary(report)}
</section>

<section>
<h2>Evidence</h2>
<p>This page is a presentation layer over a verified AgentBench result bundle. The publication manifest hashes this HTML and the canonical report JSON.</p>
<p><a href="report.json">Open machine-readable report.json</a> · <a href="publication.json">Open publication.json</a></p>
</section>

<footer>Generated without external JavaScript, fonts, analytics, or network dependencies.</footer>
</main>
</body>
</html>
"""


def _prepare_destination(destination: str | Path) -> Path:
    target = Path(destination).expanduser().resolve()
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"Publication destination is not a directory: {target}")
        if any(target.iterdir()):
            raise ValueError(f"Publication destination must be empty: {target}")
    else:
        target.mkdir(parents=True)
    return target


def publish_verified_bundle(
    verified: VerifiedResultBundle,
    destination: str | Path,
) -> dict[str, Any]:
    target = _prepare_destination(destination)
    report_bytes = _pretty_json_bytes(verified.report)
    html_bytes = (
        render_publication_html(
            verified.report,
            source_bundle_identity=verified.identity_sha256,
        )
        + "\n"
    ).encode("utf-8")
    payloads = {
        "index.html": html_bytes,
        "report.json": report_bytes,
    }
    files = [
        {
            "path": name,
            "sha256": _sha256_bytes(payloads[name]),
            "size": len(payloads[name]),
        }
        for name in _PUBLICATION_FILES
    ]
    core = {
        "publication_schema_version": PUBLICATION_SCHEMA_VERSION,
        "agentbench_version": __version__,
        "source_bundle_identity_sha256": verified.identity_sha256,
        "experiment": verified.manifest.get("experiment"),
        "files": files,
    }
    manifest = {
        **core,
        "identity_sha256": _sha256_bytes(_canonical_json_bytes(core)),
    }

    for name, content in payloads.items():
        (target / name).write_bytes(content)
    (target / "publication.json").write_bytes(_pretty_json_bytes(manifest))

    return {
        "published": True,
        "path": str(target),
        "publication_schema_version": PUBLICATION_SCHEMA_VERSION,
        "identity_sha256": manifest["identity_sha256"],
        "source_bundle_identity_sha256": verified.identity_sha256,
        "file_count": len(files),
    }


def publish_bundle(bundle: str | Path, destination: str | Path) -> dict[str, Any]:
    return publish_verified_bundle(verify_result_bundle(bundle), destination)


def publish_experiment(
    db: Session,
    experiment_id: int,
    destination: str | Path,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agentbench-publication-") as tmp:
        bundle = Path(tmp) / "result.zip"
        ResultBundleService(db).export(experiment_id, bundle)
        return publish_bundle(bundle, destination)


def verify_publication(path: str | Path) -> VerifiedPublication:
    root = Path(path).expanduser().resolve()
    manifest_path = root / "publication.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise PublicationValidationError(
            f"Publication directory is missing publication.json: {root}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PublicationValidationError(
            "publication.json is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise PublicationValidationError("publication.json root must be an object")
    if manifest.get("publication_schema_version") != PUBLICATION_SCHEMA_VERSION:
        raise PublicationValidationError(
            "Unsupported publication schema version: "
            f"{manifest.get('publication_schema_version')!r}"
        )

    identity = manifest.get("identity_sha256")
    core = dict(manifest)
    core.pop("identity_sha256", None)
    if identity != _sha256_bytes(_canonical_json_bytes(core)):
        raise PublicationValidationError("Publication identity digest does not match")

    declared = manifest.get("files")
    if not isinstance(declared, list):
        raise PublicationValidationError("Publication files must be a list")
    declared_names: list[str] = []
    for item in declared:
        if not isinstance(item, dict):
            raise PublicationValidationError("Invalid publication file entry")
        name = str(item.get("path") or "")
        if name not in _PUBLICATION_FILES:
            raise PublicationValidationError(
                f"Unexpected publication payload: {name!r}"
            )
        declared_names.append(name)
        candidate = root / name
        if not candidate.is_file() or candidate.is_symlink():
            raise PublicationValidationError(f"Publication payload is missing: {name}")
        data = candidate.read_bytes()
        if len(data) != int(item.get("size", -1)):
            raise PublicationValidationError(
                f"Size mismatch for publication file: {name}"
            )
        if _sha256_bytes(data) != item.get("sha256"):
            raise PublicationValidationError(
                f"Digest mismatch for publication file: {name}"
            )

    if sorted(declared_names) != sorted(_PUBLICATION_FILES):
        raise PublicationValidationError("Publication manifest has incomplete file set")
    actual = sorted(
        item.name
        for item in root.iterdir()
        if item.is_file() and item.name != "publication.json"
    )
    if actual != sorted(_PUBLICATION_FILES):
        raise PublicationValidationError(
            "Publication directory contains undeclared payload files"
        )

    try:
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PublicationValidationError("report.json is not valid UTF-8 JSON") from exc
    if not isinstance(report, dict):
        raise PublicationValidationError("report.json root must be an object")

    return VerifiedPublication(path=root, manifest=manifest, report=report)


__all__ = [
    "PUBLICATION_SCHEMA_VERSION",
    "PublicationValidationError",
    "VerifiedPublication",
    "publish_bundle",
    "publish_experiment",
    "publish_verified_bundle",
    "render_publication_html",
    "verify_publication",
]
