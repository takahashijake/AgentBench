"""Provider SPI and registry for benchmark corpora."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .models import BenchmarkPack


class PackProviderError(ValueError):
    """Base error for benchmark-pack provider failures."""


class PackNotFoundError(PackProviderError):
    """Raised when no registered provider owns a requested pack."""


class DuplicatePackError(PackProviderError):
    """Raised when providers claim the same globally stable pack ID."""


@runtime_checkable
class BenchmarkPackProvider(Protocol):
    """Stable structural interface implemented by corpus providers."""

    @property
    def provider_id(self) -> str:
        ...

    def packs(self) -> tuple[BenchmarkPack, ...]:
        ...


@dataclass(frozen=True)
class ResolvedPack:
    provider_id: str
    pack: BenchmarkPack


@dataclass
class PackRegistry:
    """Explicit registry that keeps provider discovery out of core services."""

    _packs: dict[str, ResolvedPack] = field(default_factory=dict)
    _providers: dict[str, BenchmarkPackProvider] = field(default_factory=dict)
    discovery_errors: list[str] = field(default_factory=list)

    def register(self, provider: BenchmarkPackProvider) -> None:
        provider_id = str(provider.provider_id).strip()
        if not provider_id:
            raise PackProviderError("Benchmark pack provider_id must not be empty")
        if provider_id in self._providers:
            raise PackProviderError(
                f"Benchmark pack provider already registered: {provider_id}"
            )

        packs = tuple(provider.packs())
        local_ids = [pack.id for pack in packs]
        if len(local_ids) != len(set(local_ids)):
            raise DuplicatePackError(
                f"Provider {provider_id!r} returned duplicate pack IDs"
            )

        collisions = sorted(pack_id for pack_id in local_ids if pack_id in self._packs)
        if collisions:
            owners = {
                pack_id: self._packs[pack_id].provider_id for pack_id in collisions
            }
            raise DuplicatePackError(
                f"Pack IDs already registered: {owners}; provider={provider_id!r}"
            )

        self._providers[provider_id] = provider
        for pack in packs:
            self._packs[pack.id] = ResolvedPack(provider_id=provider_id, pack=pack)

    def get(self, pack_id: str) -> ResolvedPack:
        try:
            return self._packs[pack_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._packs)) or "<none>"
            raise PackNotFoundError(
                f"Unknown benchmark pack {pack_id!r}; available: {available}"
            ) from exc

    def catalog(self) -> list[dict[str, object]]:
        from .compatibility import pack_content_sha256, task_content_sha256

        rows: list[dict[str, object]] = []
        for pack_id in sorted(self._packs):
            resolved = self._packs[pack_id]
            pack = resolved.pack
            rows.append(
                {
                    "id": pack.id,
                    "version": pack.version,
                    "provider": resolved.provider_id,
                    "compatibility_id": pack.effective_compatibility_id,
                    "content_sha256": pack_content_sha256(pack),
                    "name": pack.name,
                    "description": pack.description,
                    "task_count": len(pack.tasks),
                    "tasks": [
                        {
                            "id": task.id,
                            "category": task.category,
                            "difficulty": task.difficulty,
                            "tags": list(task.tags),
                            "content_sha256": task_content_sha256(task),
                        }
                        for task in pack.tasks
                    ],
                }
            )
        return rows

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


__all__ = [
    "BenchmarkPackProvider",
    "DuplicatePackError",
    "PackNotFoundError",
    "PackProviderError",
    "PackRegistry",
    "ResolvedPack",
]
