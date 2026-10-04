# Statistical analysis

AgentBench treats repeated trials as measurements rather than presenting one run as a definitive model comparison.

## Success-rate uncertainty

For a group with `k` successful eligible trials out of `n` eligible planned trials, AgentBench reports the observed success rate and a two-sided 95% Wilson score interval.

V4 distinguishes:

- `planned_runs` — every matrix cell intended by the experiment;
- `eligible_planned_runs` — planned cells the current host can execute;
- `skipped_runs` — cells excluded before agent execution because frozen resource requirements were not satisfied;
- `orchestration_errors` — eligible cells where AgentBench could not complete orchestration;
- `benchmark_runs` — cells that produced a canonical benchmark run.

The agent success denominator is **eligible planned runs**. A host limitation therefore cannot make an agent appear less reliable. An orchestration error on an eligible cell remains in the denominator and does not silently disappear.

A separate benchmark-success interval is available over produced `BenchmarkRun` rows.

Wilson intervals were chosen because they remain well behaved for small samples and success rates near zero or one.

## Numeric measurements

Runtime, measured token counts, and code-change counts expose descriptive summaries. With at least two values AgentBench reports sample mean, median, minimum/maximum, sample standard deviation, and a two-sided 95% Student-t interval for the sample mean.

No SciPy dependency is required.

## Leaderboard methodology

The default ranking is conservative. Sort order is:

1. lower bound of the 95% Wilson success interval
2. observed success rate
3. lower orchestration-error rate
4. lower median runtime
5. stable agent name/ID

The lower Wilson bound is the **reliability score**.

## Pairwise task comparison

For every pair of agents, AgentBench compares observed success rate on each task. Higher task success rate is a win, lower is a loss, and equal is a tie. Runtime does not break equal-quality outcomes.

V3+ also reports mean paired success-rate difference and an exact two-sided sign-test p-value over decisive tasks. These are descriptive; the sign test does not alter rank and AgentBench does not claim task/trial independence.

## Token coverage

Token telemetry is optional because generic shell agents do not share one usage format. Coverage is:

```text
runs with measured total tokens / benchmark runs
```

Missing usage is unknown, not zero.

## Interpretation limits

AgentBench does not claim repeated trials are statistically independent, rank differences are universally significant, its built-in corpus estimates universal coding ability, or runtime/token comparisons are fair across uncontrolled hardware/toolchains.

V4 resource eligibility prevents one specific confound—executing tasks on hosts that cannot satisfy declared requirements—but does not make all experimental assumptions true.
