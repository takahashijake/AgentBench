"""Versioned multi-suite campaign manifests and validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from .manifests import LoadedSuiteManifest, load_suite_manifest
from .provenance import load_suite_lock, verify_suite_lock


_RESOURCE_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class CampaignMember(BaseModel):
    """One locked suite participating in a campaign."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID)
    suite: str = Field(..., min_length=1)
    lock: str = Field(..., min_length=1)


class CampaignManifest(BaseModel):
    """Top-level campaign definition."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1)
    id: str = Field(..., min_length=1, max_length=128, pattern=_RESOURCE_ID)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    stop_on_error: bool = False
    members: list[CampaignMember] = Field(..., min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_campaign(self) -> "CampaignManifest":
        if self.schema_version != 1:
            raise ValueError(
                f"Unsupported campaign schema_version: {self.schema_version}"
            )
        ids = [item.id for item in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("Campaign member IDs must be unique")
        return self


@dataclass(frozen=True)
class LoadedCampaignManifest:
    path: Path
    manifest: CampaignManifest
    sha256: str

    def resolve(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.path.parent / path
        return path.resolve()

    def suite_path(self, member: CampaignMember) -> Path:
        return self.resolve(member.suite)

    def lock_path(self, member: CampaignMember) -> Path:
        return self.resolve(member.lock)


@dataclass(frozen=True)
class PreparedCampaignMember:
    id: str
    suite: LoadedSuiteManifest
    lock: dict[str, Any]
    lock_path: Path


def _canonical_bytes(manifest: CampaignManifest) -> bytes:
    return json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_campaign_manifest(path: str | Path) -> LoadedCampaignManifest:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Campaign manifest does not exist: {source}")
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML/JSON campaign manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Campaign manifest root must be a mapping/object")
    manifest = CampaignManifest.model_validate(raw)
    return LoadedCampaignManifest(
        path=source,
        manifest=manifest,
        sha256=sha256(_canonical_bytes(manifest)).hexdigest(),
    )


def prepare_campaign(
    loaded: LoadedCampaignManifest,
) -> tuple[PreparedCampaignMember, ...]:
    """Verify every member lock before campaign execution is allowed to mutate state."""

    prepared: list[PreparedCampaignMember] = []
    for member in loaded.manifest.members:
        suite = load_suite_manifest(loaded.suite_path(member))
        lock_path = loaded.lock_path(member)
        expected = load_suite_lock(lock_path)
        verification = verify_suite_lock(suite, expected)
        if not verification["valid"]:
            drift = verification["drift"]
            preview = "; ".join(
                f"{item['path']}: {item['expected']!r} -> {item['actual']!r}"
                for item in drift[:5]
            )
            suffix = "" if len(drift) <= 5 else f"; +{len(drift) - 5} more"
            raise ValueError(
                f"Campaign member {member.id!r} lock verification failed: "
                f"{preview}{suffix}"
            )
        prepared.append(
            PreparedCampaignMember(
                id=member.id,
                suite=suite,
                lock=expected,
                lock_path=lock_path,
            )
        )
    return tuple(prepared)


def validate_campaign(loaded: LoadedCampaignManifest) -> dict[str, Any]:
    prepared = prepare_campaign(loaded)
    return {
        "valid": True,
        "campaign_schema_version": loaded.manifest.schema_version,
        "campaign_id": loaded.manifest.id,
        "manifest_path": str(loaded.path),
        "manifest_sha256": loaded.sha256,
        "stop_on_error": loaded.manifest.stop_on_error,
        "member_count": len(prepared),
        "members": [
            {
                "id": item.id,
                "suite_id": item.suite.manifest.id,
                "suite_manifest_sha256": item.suite.sha256,
                "lock_identity_sha256": item.lock["identity_sha256"],
                "planned_runs": (
                    len(item.suite.manifest.selected_task_ids())
                    * len(item.suite.manifest.selected_agent_ids())
                    * item.suite.manifest.experiment.repetitions
                ),
            }
            for item in prepared
        ],
    }


__all__ = [
    "CampaignManifest",
    "CampaignMember",
    "LoadedCampaignManifest",
    "PreparedCampaignMember",
    "load_campaign_manifest",
    "prepare_campaign",
    "validate_campaign",
]
