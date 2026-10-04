from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src" / "agentbench"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(("." * node.level) + (node.module or ""))
    return imports


def test_benchmark_service_depends_on_adapter_abstraction_not_shell_implementation():
    imports = imported_modules(SRC / "services" / "benchmark.py")

    assert not any(name.endswith("adapters.shell") for name in imports)
    assert any(name.endswith("adapters.registry") for name in imports)


def test_pack_provider_contract_is_free_of_materialization_dependencies():
    imports = imported_modules(SRC / "benchmark_packs" / "provider.py")

    assert "subprocess" not in imports
    assert "yaml" not in imports
    assert "pathlib" not in imports


def test_statistics_and_reporting_do_not_depend_on_orchestration_services():
    for relative in ("statistics.py", "reporting.py"):
        imports = imported_modules(SRC / relative)
        assert not any(".services" in name for name in imports)
        assert not any(".models" in name for name in imports)


def test_api_composition_root_stays_thin():
    source = (SRC / "api" / "__init__.py").read_text(encoding="utf-8")
    imports = imported_modules(SRC / "api" / "__init__.py")

    assert len(source.splitlines()) < 40
    assert not any(".services" in name for name in imports)
    assert not any(".models" in name for name in imports)


def test_result_bundle_module_does_not_depend_on_cli_or_api():
    imports = imported_modules(SRC / "result_bundles.py")

    assert not any(".cli" in name for name in imports)
    assert not any(".api" in name for name in imports)
