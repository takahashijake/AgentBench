from sqlalchemy.orm import configure_mappers


def test_api_import_and_mapper_configuration():
    configure_mappers()

    from agentbench.api import TEMPLATES_DIR, app

    assert app.title == "AgentBench Local"
    assert app.version == "2.0.0"

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/dashboard" in paths
    assert "/docs" in paths
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
