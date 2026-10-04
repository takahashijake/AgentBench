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
from agentbench.models.database import Base, Campaign
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
