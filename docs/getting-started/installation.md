# Installation

## Requirements

AgentBench supports Python 3.11 through 3.13. Git is required because each benchmark trial is executed from a pinned commit in an isolated worktree. The core product is CPU-only; external coding agents may have their own GPU, runtime, or credential requirements.

## Local install

```bash
git clone https://github.com/takahashijake/AgentBench.git
cd AgentBench
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Verify the install:

```bash
agentbench --version
agentbench doctor
agentbench pack list
```

AgentBench does not require API credentials itself. Credentials required by a configured external agent remain the responsibility of that agent and should be supplied through its documented environment/configuration path. Do not embed secrets in suite manifests or command templates.
