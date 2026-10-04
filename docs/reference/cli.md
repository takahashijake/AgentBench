# CLI Reference

Run `agentbench --help` and subcommand help for the installed version. The primary surface is:

```text
agentbench doctor
agentbench pack list
agentbench pack show <pack>
agentbench pack materialize <pack> -o <dir> --agent <id=command>...
agentbench validate <suite>
agentbench lock <suite>
agentbench verify <suite> <lock>
agentbench import <suite>
agentbench run <suite>
agentbench replay <suite> <lock>
agentbench results <experiment-id>
agentbench leaderboard <experiment-id>
agentbench bundle export <experiment-id> -o <file.zip>
agentbench bundle verify <file.zip>
agentbench bundle inspect <file.zip>
agentbench bundle extract <file.zip> -o <directory>
agentbench serve
```

Human-readable output is the default. JSON/Markdown report outputs are available on commands that produce reusable analysis artifacts. Invalid user input should fail with a non-zero exit and an actionable message.
