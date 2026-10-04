from sqlalchemy.orm import configure_mappers


def test_api_import_and_mapper_configuration():
    configure_mappers()

    from agentbench.api import app

    assert app.title == "AgentBench Local"
    assert app.version == "0.2.0"
