"""System-health and benchmark-pack HTTP routes."""

from fastapi import APIRouter, HTTPException

from ... import __version__
from ...adapters import create_adapter_registry
from ...packs import default_pack_registry, get_pack, list_packs


router = APIRouter()


@router.get("/api/health")
def health():
    registry = default_pack_registry()
    return {
        "status": "ok",
        "version": __version__,
        "pack_provider_errors": list(registry.discovery_errors),
        "adapter_provider_errors": list(
            create_adapter_registry(discover_plugins=True).discovery_errors
        ),
    }


@router.get("/api/packs")
def api_packs():
    registry = default_pack_registry()
    return {
        "packs": list_packs(registry),
        "providers": list(registry.provider_ids),
        "discovery_errors": list(registry.discovery_errors),
    }


@router.get("/api/packs/{pack_id}")
def api_pack(pack_id: str):
    try:
        pack = get_pack(pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return next(row for row in list_packs() if row["id"] == pack.id)



@router.get("/api/adapters")
def api_adapters():
    registry = create_adapter_registry(discover_plugins=True)
    return {
        "adapters": registry.catalog(),
        "providers": list(registry.provider_ids),
        "discovery_errors": list(registry.discovery_errors),
    }


@router.get("/api/adapters/{adapter_id}")
def api_adapter(adapter_id: str):
    registry = create_adapter_registry(discover_plugins=True)
    try:
        resolved = registry.get(adapter_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return next(
        row
        for row in registry.catalog()
        if row["id"] == resolved.profile.id
    )
