"""Persistent orchestration and aggregation for multi-suite campaigns."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..campaigns import LoadedCampaignManifest, prepare_campaign
from ..models.database import Campaign, CampaignMemberRun
from ..statistics import wilson_interval
from ..timeutils import utc_now
from .suite import SuiteService


CAMPAIGN_REPORT_SCHEMA_VERSION = 1


class CampaignNotFoundError(ValueError):
    pass


def _campaign_ranking(by_agent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in by_agent:
        eligible = int(row["eligible_planned_runs"])
        successes = int(row["successful_runs"])
        errors = int(row["orchestration_errors"])
        interval = wilson_interval(successes, eligible)
        success_rate = successes / eligible if eligible else None
        error_rate = errors / eligible if eligible else None
        rows.append(
            {
                **row,
                "success_rate": success_rate,
                "success_rate_confidence_interval_95": interval,
                "reliability_score": interval["low"] if interval else 0.0,
                "orchestration_error_rate": error_rate,
            }
        )
    rows.sort(
        key=lambda item: (
            -float(item["reliability_score"]),
            -float(item["success_rate"] if item["success_rate"] is not None else -1.0),
            float(
                item["orchestration_error_rate"]
                if item["orchestration_error_rate"] is not None
                else 1.0
            ),
            str(item["agent_name"]),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


class CampaignService:
    def __init__(
        self,
        db: Session,
        *,
        artifact_root: Path | None = None,
        suite_service: SuiteService | None = None,
    ):
        self.db = db
        if suite_service is not None and suite_service.db is not db:
            raise ValueError("Injected SuiteService must use the same database session")
        self.suites = suite_service or SuiteService(db, artifact_root=artifact_root)

    def get_campaign(self, campaign_id: int) -> Campaign:
        row = (
            self.db.query(Campaign)
            .filter(Campaign.id == int(campaign_id))
            .one_or_none()
        )
        if row is None:
            raise CampaignNotFoundError(f"Campaign not found: {campaign_id}")
        return row

    def run_campaign(self, loaded: LoadedCampaignManifest) -> Campaign:
        prepared = prepare_campaign(loaded)

        campaign = Campaign(
            campaign_key=loaded.manifest.id,
            name=loaded.manifest.name or loaded.manifest.id,
            description=loaded.manifest.description,
            manifest_sha256=loaded.sha256,
            definition=loaded.manifest.model_dump(mode="json"),
            stop_on_error=loaded.manifest.stop_on_error,
            status="running",
            started_at=utc_now(),
        )
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)

        campaign_id = int(campaign.id)
        member_database_ids: list[int] = []
        for ordinal, item in enumerate(prepared, start=1):
            member = CampaignMemberRun(
                campaign_id=campaign_id,
                member_id=item.id,
                ordinal=ordinal,
                suite_id=item.suite.manifest.id,
                suite_manifest_sha256=item.suite.sha256,
                lock_identity_sha256=str(item.lock["identity_sha256"]),
                status="planned",
            )
            self.db.add(member)
            self.db.flush()
            member_database_ids.append(int(member.id))
        self.db.commit()

        failed = False
        for member_index, (item, member_database_id) in enumerate(
            zip(prepared, member_database_ids)
        ):
            (
                self.db.query(CampaignMemberRun)
                .filter(CampaignMemberRun.id == member_database_id)
                .update(
                    {
                        CampaignMemberRun.status: "running",
                        CampaignMemberRun.started_at: utc_now(),
                    },
                    synchronize_session=False,
                )
            )
            self.db.commit()

            try:
                imported, experiment, summary = self.suites.execute_suite(item.suite)
                report = self.suites.build_report(
                    item.suite,
                    imported,
                    experiment,
                    summary,
                )
                report["lock"] = item.lock
                terminal_status = (
                    "completed" if experiment.status == "completed" else "failed"
                )
                (
                    self.db.query(CampaignMemberRun)
                    .filter(CampaignMemberRun.id == member_database_id)
                    .update(
                        {
                            CampaignMemberRun.experiment_id: int(experiment.id),
                            CampaignMemberRun.report_json: report,
                            CampaignMemberRun.status: terminal_status,
                            CampaignMemberRun.completed_at: utc_now(),
                        },
                        synchronize_session=False,
                    )
                )
                if terminal_status == "failed":
                    failed = True
            except Exception as exc:
                self.db.rollback()
                (
                    self.db.query(CampaignMemberRun)
                    .filter(CampaignMemberRun.id == member_database_id)
                    .update(
                        {
                            CampaignMemberRun.status: "error",
                            CampaignMemberRun.error: f"{type(exc).__name__}: {exc}",
                            CampaignMemberRun.completed_at: utc_now(),
                        },
                        synchronize_session=False,
                    )
                )
                failed = True
            self.db.commit()

            if failed and loaded.manifest.stop_on_error:
                skipped_at = utc_now()
                skipped_reason = (
                    "not attempted because campaign stop_on_error was triggered "
                    "by an earlier member"
                )
                for skipped_id in member_database_ids[member_index + 1 :]:
                    (
                        self.db.query(CampaignMemberRun)
                        .filter(
                            CampaignMemberRun.id == skipped_id,
                            CampaignMemberRun.status == "planned",
                        )
                        .update(
                            {
                                CampaignMemberRun.status: "skipped",
                                CampaignMemberRun.error: skipped_reason,
                                CampaignMemberRun.completed_at: skipped_at,
                            },
                            synchronize_session=False,
                        )
                    )
                self.db.commit()
                break

        (
            self.db.query(Campaign)
            .filter(Campaign.id == campaign_id)
            .update(
                {
                    Campaign.status: "failed" if failed else "completed",
                    Campaign.completed_at: utc_now(),
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        self.db.expire_all()
        return self.get_campaign(campaign_id)

    @staticmethod
    def _aggregate(campaign: Campaign) -> dict[str, Any]:
        totals: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "member_count": 0,
                "eligible_planned_runs": 0,
                "successful_runs": 0,
                "benchmark_runs": 0,
                "skipped_runs": 0,
                "orchestration_errors": 0,
            }
        )

        for member in campaign.members:
            report = member.report_json if isinstance(member.report_json, dict) else {}
            summary = report.get("summary") if isinstance(report, dict) else {}
            resources = report.get("resources") if isinstance(report, dict) else {}
            if not isinstance(summary, dict) or not isinstance(resources, dict):
                continue
            agent_resources = resources.get("agents") or []
            logical_by_database_id = {
                int(item["database_id"]): str(item["id"])
                for item in agent_resources
                if isinstance(item, dict)
                and item.get("database_id") is not None
                and item.get("id")
            }

            seen: set[str] = set()
            for row in summary.get("by_agent") or []:
                if not isinstance(row, dict):
                    continue
                database_id = row.get("agent_config_id")
                logical = logical_by_database_id.get(
                    int(database_id) if database_id is not None else -1,
                    str(row.get("agent_name") or "unknown"),
                )
                metrics = row.get("metrics") or {}
                target = totals[logical]
                if logical not in seen:
                    target["member_count"] += 1
                    seen.add(logical)
                for key in (
                    "eligible_planned_runs",
                    "successful_runs",
                    "benchmark_runs",
                    "skipped_runs",
                    "orchestration_errors",
                ):
                    target[key] += int(metrics.get(key) or 0)

        by_agent = [
            {"agent_name": name, **values} for name, values in sorted(totals.items())
        ]
        ranking = _campaign_ranking(by_agent)
        overall: dict[str, Any] = {
            key: sum(int(row[key]) for row in by_agent)
            for key in (
                "eligible_planned_runs",
                "successful_runs",
                "benchmark_runs",
                "skipped_runs",
                "orchestration_errors",
            )
        }
        overall["success_rate"] = (
            overall["successful_runs"] / overall["eligible_planned_runs"]
            if overall["eligible_planned_runs"]
            else None
        )
        return {
            "overall": overall,
            "by_agent": by_agent,
            "ranking": ranking,
        }

    def build_report(self, campaign_id: int) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        members = [
            {
                "id": int(item.id),
                "member_id": item.member_id,
                "ordinal": int(item.ordinal),
                "suite_id": item.suite_id,
                "suite_manifest_sha256": item.suite_manifest_sha256,
                "lock_identity_sha256": item.lock_identity_sha256,
                "experiment_id": (
                    int(item.experiment_id) if item.experiment_id is not None else None
                ),
                "status": item.status,
                "error": item.error,
                "started_at": (
                    item.started_at.isoformat() if item.started_at is not None else None
                ),
                "completed_at": (
                    item.completed_at.isoformat()
                    if item.completed_at is not None
                    else None
                ),
            }
            for item in campaign.members
        ]
        return {
            "campaign_report_schema_version": CAMPAIGN_REPORT_SCHEMA_VERSION,
            "campaign": {
                "id": int(campaign.id),
                "campaign_key": campaign.campaign_key,
                "name": campaign.name,
                "description": campaign.description,
                "manifest_sha256": campaign.manifest_sha256,
                "stop_on_error": bool(campaign.stop_on_error),
                "status": campaign.status,
                "started_at": (
                    campaign.started_at.isoformat()
                    if campaign.started_at is not None
                    else None
                ),
                "completed_at": (
                    campaign.completed_at.isoformat()
                    if campaign.completed_at is not None
                    else None
                ),
            },
            "members": members,
            "aggregate": self._aggregate(campaign),
        }


__all__ = [
    "CAMPAIGN_REPORT_SCHEMA_VERSION",
    "CampaignNotFoundError",
    "CampaignService",
]
