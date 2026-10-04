"""Database-free result-bundle format, verification, and extraction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile


BUNDLE_SCHEMA_VERSION = 1
MAX_BUNDLE_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BundleValidationError(ValueError):
    """Raised when a result bundle violates the portable bundle contract."""


@dataclass(frozen=True)
class VerifiedResultBundle:
    path: Path
    manifest: dict[str, Any]
    report: dict[str, Any]

    @property
    def identity_sha256(self) -> str:
        return str(self.manifest["identity_sha256"])


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def safe_member_name(name: str) -> str:
    if "\\" in name:
        raise BundleValidationError(f"Bundle member uses backslashes: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts:
        raise BundleValidationError(f"Unsafe bundle member path: {name!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise BundleValidationError(f"Unsafe bundle member path: {name!r}")
    return path.as_posix()


def deterministic_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def verify_result_bundle(path: str | Path) -> VerifiedResultBundle:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise BundleValidationError(f"Result bundle does not exist: {source}")

    try:
        archive = zipfile.ZipFile(source, "r")
    except zipfile.BadZipFile as exc:
        raise BundleValidationError(f"Invalid ZIP result bundle: {source}") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_BUNDLE_FILES + 1:
            raise BundleValidationError("Result bundle contains too many files")

        names = [safe_member_name(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise BundleValidationError("Result bundle contains duplicate member names")
        if "bundle.json" not in names:
            raise BundleValidationError("Result bundle is missing bundle.json")

        total_size = sum(int(info.file_size) for info in infos)
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise BundleValidationError("Result bundle is too large to verify safely")

        try:
            manifest = json.loads(archive.read("bundle.json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError("bundle.json is not valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict):
            raise BundleValidationError("bundle.json root must be an object")
        if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION:
            raise BundleValidationError(
                "Unsupported result bundle schema version: "
                f"{manifest.get('bundle_schema_version')!r}"
            )

        identity = manifest.get("identity_sha256")
        core = dict(manifest)
        core.pop("identity_sha256", None)
        expected_identity = sha256_bytes(canonical_json_bytes(core))
        if identity != expected_identity:
            raise BundleValidationError("Result bundle identity digest does not match")

        declared = manifest.get("files")
        if not isinstance(declared, list):
            raise BundleValidationError("Result bundle files must be a list")

        declared_names: list[str] = []
        for item in declared:
            if not isinstance(item, dict):
                raise BundleValidationError("Invalid file entry in bundle manifest")
            name = safe_member_name(str(item.get("path") or ""))
            declared_names.append(name)
            if name == "bundle.json":
                raise BundleValidationError("bundle.json must not declare itself")
            if name not in names:
                raise BundleValidationError(f"Declared bundle file is missing: {name}")
            data = archive.read(name)
            if len(data) != int(item.get("size", -1)):
                raise BundleValidationError(f"Size mismatch for bundle file: {name}")
            if sha256_bytes(data) != item.get("sha256"):
                raise BundleValidationError(f"Digest mismatch for bundle file: {name}")

        if len(declared_names) != len(set(declared_names)):
            raise BundleValidationError("Bundle manifest declares duplicate files")
        actual_payloads = sorted(name for name in names if name != "bundle.json")
        if sorted(declared_names) != actual_payloads:
            raise BundleValidationError(
                "Bundle contains undeclared payload files or omits declared files"
            )

        try:
            report = json.loads(archive.read("report.json"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BundleValidationError(
                "Result bundle lacks a valid report.json"
            ) from exc
        if not isinstance(report, dict):
            raise BundleValidationError("report.json root must be an object")

    return VerifiedResultBundle(path=source, manifest=manifest, report=report)


def inspect_result_bundle(path: str | Path) -> dict[str, Any]:
    verified = verify_result_bundle(path)
    return {
        "valid": True,
        "path": str(verified.path),
        "identity_sha256": verified.identity_sha256,
        "manifest": verified.manifest,
        "report": verified.report,
    }


def extract_result_bundle(
    path: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    verified = verify_result_bundle(path)
    target = Path(destination).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise BundleValidationError(
            f"Bundle extraction directory is not empty: {target}"
        )
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(verified.path, "r") as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = safe_member_name(info.filename)
            output = (target / Path(*PurePosixPath(name).parts)).resolve()
            try:
                output.relative_to(target)
            except ValueError as exc:
                raise BundleValidationError(
                    f"Bundle extraction escaped destination: {name}"
                ) from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(info))

    return {
        "extracted": True,
        "source": str(verified.path),
        "destination": str(target),
        "identity_sha256": verified.identity_sha256,
        "file_count": len(verified.manifest["files"]) + 1,
    }


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BundleValidationError",
    "VerifiedResultBundle",
    "canonical_json_bytes",
    "deterministic_zip_info",
    "extract_result_bundle",
    "inspect_result_bundle",
    "safe_member_name",
    "sha256_bytes",
    "verify_result_bundle",
]
