# External benchmark provider example

This directory is a standalone Python distribution used to prove AgentBench's
benchmark-provider SPI through real package metadata.

Install AgentBench first, then:

    python -m pip install -e ./examples/external_pack_provider --no-deps
    agentbench pack show example-external-v1

There is no registration call in AgentBench core. Discovery occurs through the
agentbench.pack_providers entry-point group declared in this package's
pyproject.toml.
