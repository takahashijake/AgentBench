"""Benchmark-pack domain and extension surface."""

from .builtin import BuiltinPackProvider, CORE_V2, CORE_V3, SMOKE_V2
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
    "discover_pack_providers",
    "parse_agent_spec",
]
