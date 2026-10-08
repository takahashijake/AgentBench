from __future__ import annotations

import json
from pathlib import Path
import shlex
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import yaml

from agentbench.campaigns import (
    load_campaign_manifest,
    validate_campaign,
)
from agentbench.cli import main
from agentbench.manifests import load_suite_manifest
from agentbench.models.database import Base, Campaign, CampaignMemberRun
from agentbench.packs import materialize_pack
from agentbench.provenance import build_suite_lock, write_suite_lock
from agentbench.reporting import render_campaign_markdown
from agentbench.services.campaign import CampaignService


AGENT = {
    "id": "fixture",
    "description": "campaign fixture agent",
    "command_template": shlex.join([sys.executable, "-c", "pass"]) + " {prompt}",
}


def make_campaign_definition(tmp_path: Path) -> Path:
    for name in ("first", "second"):
        root = tmp_path / name
        result = materialize_pack(
            "smoke-v2",
            root,
            agents=[AGENT],
            repetitions=1,
            max_workers=1,
        )
        suite = load_suite_manifest(result["manifest_path"])
        write_suite_lock(root / "suite.lock.json", build_suite_lock(suite))

    campaign_path = tmp_path / "campaign.yaml"
    campaign_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": "portfolio-campaign",
                "name": "Portfolio Campaign",
                "description": "Two locked smoke suites",
                "stop_on_error": False,
                "members": [
                    {
                        "id": "smoke-first",
                        "suite": "first/suite.yaml",
                        "lock": "first/suite.lock.json",
                    },
                    {
                        "id": "smoke-second",
                        "suite": "second/suite.yaml",
                        "lock": "second/suite.lock.json",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return campaign_path


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_campaign_validation_verifies_all_locked_members(tmp_path: Path):
    campaign_path = make_campaign_definition(tmp_path)
    loaded = load_campaign_manifest(campaign_path)

    validation = validate_campaign(loaded)

    assert validation["valid"] is True
    assert validation["campaign_id"] == "portfolio-campaign"
    assert validation["member_count"] == 2
    assert [row["planned_runs"] for row in validation["members"]] == [2, 2]
    assert all(row["lock_identity_sha256"] for row in validation["members"])


def test_campaign_executes_two_suites_and_aggregates_agents(tmp_path: Path):
    campaign_path = make_campaign_definition(tmp_path)
    loaded = load_campaign_manifest(campaign_path)
    db = make_session()
    service = CampaignService(db, artifact_root=tmp_path / "artifacts")

    campaign = service.run_campaign(loaded)
    report = service.build_report(int(campaign.id))

    assert campaign.status == "completed"
    assert len(campaign.members) == 2
    assert [row["status"] for row in report["members"]] == [
        "completed",
        "completed",
    ]
    assert all(row["experiment_id"] for row in report["members"])

    aggregate = report["aggregate"]
    assert report["progress"]["total_members"] == 2
    assert report["progress"]["terminal_members"] == 2
    assert report["progress"]["remaining_members"] == 0
    assert report["progress"]["completion_fraction"] == 1.0
    assert report["progress"]["status_counts"]["completed"] == 2
    assert aggregate["overall"]["eligible_planned_runs"] == 4
    assert aggregate["overall"]["benchmark_runs"] == 4
    assert aggregate["overall"]["orchestration_errors"] == 0
    assert len(aggregate["ranking"]) == 1
    ranking = aggregate["ranking"][0]
    assert ranking["agent_name"] == "fixture"
    assert ranking["member_count"] == 2
    assert ranking["eligible_planned_runs"] == 4

    rendered = render_campaign_markdown(report)
    assert "# Portfolio Campaign" in rendered
    assert "smoke-first" in rendered
    assert "smoke-second" in rendered


def test_campaign_lock_drift_fails_before_persistence_or_execution(tmp_path: Path):
    campaign_path = make_campaign_definition(tmp_path)
    first_suite = tmp_path / "first" / "suite.yaml"
    payload = yaml.safe_load(first_suite.read_text(encoding="utf-8"))
    payload["experiment"]["repetitions"] = 2
    first_suite.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    loaded = load_campaign_manifest(campaign_path)
    db = make_session()
    service = CampaignService(db, artifact_root=tmp_path / "artifacts")

    with pytest.raises(ValueError, match="lock verification failed"):
        service.run_campaign(loaded)
    assert db.query(Campaign).count() == 0


def test_campaign_cli_validate_is_machine_readable(tmp_path: Path, capsys):
    campaign_path = make_campaign_definition(tmp_path)

    assert main(["campaign", "validate", str(campaign_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["member_count"] == 2


def test_campaign_stop_on_error_preserves_unattempted_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    campaign_path = make_campaign_definition(tmp_path)
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8"))
    payload["stop_on_error"] = True
    campaign_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    loaded = load_campaign_manifest(campaign_path)
    db = make_session()
    service = CampaignService(db, artifact_root=tmp_path / "artifacts")
    calls = 0

    def fail_first(_suite):
        nonlocal calls
        calls += 1
        assert db.query(CampaignMemberRun).count() == 2
        raise RuntimeError("fixture campaign failure")

    monkeypatch.setattr(service.suites, "execute_suite", fail_first)

    campaign = service.run_campaign(loaded)
    report = service.build_report(int(campaign.id))

    assert calls == 1
    assert campaign.status == "failed"
    assert len(campaign.members) == 2
    assert [row["status"] for row in report["members"]] == ["error", "skipped"]
    assert report["members"][0]["started_at"] is not None
    assert report["members"][1]["started_at"] is None
    assert report["members"][1]["completed_at"] is not None
    assert "stop_on_error" in report["members"][1]["error"]
    assert report["aggregate"]["overall"]["benchmark_runs"] == 0
    assert report["progress"]["status_counts"]["error"] == 1
    assert report["progress"]["status_counts"]["skipped"] == 1
    assert report["progress"]["failed_member_ids"] == ["smoke-first"]
    assert report["progress"]["skipped_member_ids"] == ["smoke-second"]


def test_campaign_report_shows_interrupted_members_without_reexecution(tmp_path: Path):
    db = make_session()
    campaign = Campaign(
        campaign_key="interrupted",
        name="Interrupted campaign",
        manifest_sha256="a" * 64,
        definition={},
        stop_on_error=False,
        status="running",
    )
    db.add(campaign)
    db.flush()
    db.add_all(
        [
            CampaignMemberRun(
                campaign_id=campaign.id,
                member_id="done",
                ordinal=1,
                suite_id="s1",
                suite_manifest_sha256="b" * 64,
                lock_identity_sha256="c" * 64,
                status="completed",
            ),
            CampaignMemberRun(
                campaign_id=campaign.id,
                member_id="active",
                ordinal=2,
                suite_id="s2",
                suite_manifest_sha256="d" * 64,
                lock_identity_sha256="e" * 64,
                status="running",
            ),
            CampaignMemberRun(
                campaign_id=campaign.id,
                member_id="pending",
                ordinal=3,
                suite_id="s3",
                suite_manifest_sha256="f" * 64,
                lock_identity_sha256="0" * 64,
                status="planned",
            ),
        ]
    )
    db.commit()

    report = CampaignService(db).build_report(campaign.id)
    progress = report["progress"]
    assert progress["total_members"] == 3
    assert progress["terminal_members"] == 1
    assert progress["remaining_members"] == 2
    assert progress["completion_fraction"] == pytest.approx(1 / 3)
    assert progress["status_counts"]["running"] == 1
    assert progress["status_counts"]["planned"] == 1
    assert progress["failed_member_ids"] == []
