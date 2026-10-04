"""Benchmark-pack domain and extension surface."""

from .builtin import BuiltinPackProvider, CORE_V2, CORE_V3, SMOKE_V2
from .compatibility import (
    COMPATIBILITY_SCHEMA_VERSION,
    compare_resolved_packs,
    pack_content_sha256,
    task_content_sha256,
)
from .discovery import PACK_PROVIDER_ENTRYPOINT_GROUP, discover_pack_providers
from .materializer import PackMaterializationResult, PackMaterializer, parse_agent_spec
from .models import BenchmarkPack, PackTaskSpec
from .provider import (
    BenchmarkPackProvider,
    DuplicatePackError,
    PackNotFoundError,
    PackProviderError,
    PackRegistry,
    ResolvedPack,
)

__all__ = [
    "BenchmarkPack",
    "BenchmarkPackProvider",
    "BuiltinPackProvider",
    "COMPATIBILITY_SCHEMA_VERSION",
    "CORE_V2",
    "CORE_V3",
    "DuplicatePackError",
    "PACK_PROVIDER_ENTRYPOINT_GROUP",
    "PackMaterializationResult",
    "PackMaterializer",
    "PackNotFoundError",
    "PackProviderError",
    "PackRegistry",
    "PackTaskSpec",
    "ResolvedPack",
    "SMOKE_V2",
    "compare_resolved_packs",
    "discover_pack_providers",
    "pack_content_sha256",
    "task_content_sha256",
    "parse_agent_spec",
]
