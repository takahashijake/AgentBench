# Interpreting Results

AgentBench reports observed outcomes plus uncertainty rather than only a single score.

Use the experiment leaderboard for aggregate reliability and pairwise comparisons. Inspect individual runs when a result is surprising: each canonical run links back to task configuration, process logs, Git evidence, provenance, cleanup status, and test outcomes.

Important interpretation rules:

- a missing token measurement is unknown, not zero;
- Wilson intervals describe uncertainty in observed success proportions;
- repeated numeric measurements use explicit summaries and intervals;
- pairwise sign-test output is descriptive and does not manufacture leaderboard rank;
- built-in packs are deterministic engineering fixtures, not claims of universal model quality.

For portable review, export and verify a result bundle before sharing it.
