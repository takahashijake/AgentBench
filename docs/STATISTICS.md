# Statistical analysis

AgentBench V2 treats repeated trials as measurements rather than presenting one
run as a definitive model comparison.

## Success-rate uncertainty

For a group with `k` successful trials out of `n` planned trials, AgentBench
reports the observed success rate and a two-sided 95% Wilson score interval.

Wilson intervals were chosen because they remain well behaved for small samples
and success rates near zero or one.

The overall success denominator is the **planned trial count**. An orchestration
error therefore does not silently disappear from the reliability picture.

A separate benchmark-success interval is also available over produced
`BenchmarkRun` rows.

## Numeric measurements

Runtime, measured token counts, and code-change counts expose descriptive
summaries. When at least two values exist, AgentBench reports:

- sample mean
- median
- minimum and maximum
- sample standard deviation
- two-sided 95% Student-t interval for the sample mean

For larger degrees of freedom the implementation uses standard tabulated
approximations approaching the normal critical value.

No SciPy dependency is required.

## Leaderboard methodology

The default ranking is intentionally conservative.

Sort order:

1. lower bound of the 95% Wilson success interval
2. observed success rate
3. lower orchestration-error rate
4. lower median runtime
5. stable agent name/ID

The lower Wilson bound is called the **reliability score** in reports.

Example intuition:

- Agent A: 1 success in 1 trial → observed 100%, very wide uncertainty
- Agent B: 8 successes in 10 trials → observed 80%, much more evidence

Agent B can outrank Agent A because its conservative lower bound is stronger.

This avoids rewarding tiny samples simply for being tiny.

## Pairwise task comparison

For every pair of agents, AgentBench compares observed success rate on each task.

- higher task success rate → task win
- lower task success rate → task loss
- equal task success rate → tie

Runtime is **not** used to turn equal-quality task outcomes into wins.

The table is descriptive. It is not a paired hypothesis test.

## Token coverage

Token telemetry is optional because generic shell agents do not share a universal
usage format.

When structured usage is available, AgentBench reports token summaries and a
coverage rate:

```text
runs with measured total tokens / benchmark runs
```

Missing usage is not treated as zero.

## Interpretation limits

AgentBench does not currently claim:

- repeated trials are statistically independent
- rank differences are statistically significant
- the built-in four-task corpus estimates universal coding ability
- token or runtime comparisons are fair across different hardware/tool configs
  unless the experiment is controlled accordingly

The reproducibility lock helps make those controls visible; it does not make
experimental assumptions true.

Future work can add paired tests, bootstrap comparisons, and larger task corpora
where their assumptions are defensible.
