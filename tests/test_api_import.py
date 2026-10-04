from sqlalchemy.orm import configure_mappers


def test_api_import_and_mapper_configuration():
    configure_mappers()

    from agentbench.api import app

    assert app.title == "AgentBench Local"
    assert app.version == "1.0.0"

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/dashboard" in paths
    assert "/docs" in paths
    assert "/api/experiments" in paths
    assert "/api/experiments/{experiment_id}/run" in paths
    assert "/api/experiments/{experiment_id}/results" in paths
