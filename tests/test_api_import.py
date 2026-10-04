from sqlalchemy.orm import configure_mappers


def test_api_import_and_mapper_configuration():
    configure_mappers()

    from agentbench.api import TEMPLATES_DIR, app

    assert app.title == "AgentBench Local"
    assert app.version == "8.0.0"

    paths = set(app.openapi()["paths"])
    assert "/" in paths
    assert "/dashboard" in paths
    assert app.docs_url == "/docs"
    assert "/api/health" in paths
    assert "/api/packs" in paths
    assert "/api/packs/{pack_id}" in paths
    assert "/experiments" in paths
    assert "/experiments/{experiment_id}" in paths
    assert (TEMPLATES_DIR / "index.html").is_file()
    assert (TEMPLATES_DIR / "dashboard.html").is_file()
    assert (TEMPLATES_DIR / "run_detail.html").is_file()
    assert (TEMPLATES_DIR / "experiments.html").is_file()
    assert (TEMPLATES_DIR / "experiment_detail.html").is_file()
    assert "/api/experiments" in paths
    assert "/api/experiments/{experiment_id}/run" in paths
    assert "/api/experiments/{experiment_id}/results" in paths
    assert "/api/experiments/{experiment_id}/leaderboard" in paths


def test_packaged_templates_compile():
    from agentbench.api import templates

    for name in (
        "index.html",
        "dashboard.html",
        "run_detail.html",
        "experiments.html",
        "experiment_detail.html",
    ):
        assert templates.get_template(name) is not None


def test_application_factory_returns_independent_fastapi_instances():
    from agentbench.api import create_app

    first = create_app()
    second = create_app()

    assert first is not second
    assert set(first.openapi()["paths"]) == set(second.openapi()["paths"])
