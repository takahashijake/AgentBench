from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentbench.adapters.shell import ShellAgentAdapter
from agentbench.defaults import DEFAULT_AGENT_COMMAND_TEMPLATE
from agentbench.models.database import AgentConfig, Base
from agentbench.schemas import AgentConfigCreate
from agentbench.services.benchmark import BenchmarkService


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_default_agent_command_is_consistent_across_product_surfaces():
    assert "--approval-mode auto-edit" in DEFAULT_AGENT_COMMAND_TEMPLATE

    adapter = ShellAgentAdapter({})
    assert adapter.command_template == DEFAULT_AGENT_COMMAND_TEMPLATE

    schema = AgentConfigCreate(name="schema-default")
    assert schema.command_template == DEFAULT_AGENT_COMMAND_TEMPLATE

    db = make_session()
    service = BenchmarkService(db)
    assert (
        service.create_agent_adapter().command_template
        == DEFAULT_AGENT_COMMAND_TEMPLATE
    )

    row = AgentConfig(name="database-default")
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.command_template == DEFAULT_AGENT_COMMAND_TEMPLATE
