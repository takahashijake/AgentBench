# Installation

Requirements: Python 3.11–3.13 and Git.

```bash
git clone https://github.com/takahashijake/AgentBench.git
cd AgentBench
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
agentbench doctor
```

External coding agents and their credentials are installed/configured separately.
