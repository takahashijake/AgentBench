# Reproducible Benchmark Campaigns

A campaign is an ordered collection of locked AgentBench suites. Use campaigns
when one evaluation question spans several corpora or suite configurations.

## Define and validate

```yaml
schema_version: 1
id: portfolio-campaign
name: Portfolio Campaign
members:
  - id: smoke
    suite: benchmarks/smoke/suite.yaml
    lock: benchmarks/smoke/suite.lock.json
  - id: engineering
    suite: benchmarks/engineering/suite.yaml
    lock: benchmarks/engineering/suite.lock.json
```

Member IDs must be unique. Relative suite/lock paths are resolved from the
campaign manifest.

```bash
agentbench campaign validate campaign.yaml
```

Validation loads every suite and verifies every suite lock against current
resolved inputs/environment. The same complete validation happens before
`campaign run`. If any member has drift, no campaign row is created.

## Run

```bash
agentbench campaign run campaign.yaml \
  --output results/campaign.json \
  --markdown results/campaign.md
```

Every member still executes through the normal SuiteService → ExperimentService →
BenchmarkService lifecycle.

## Persistence

For every campaign member AgentBench stores member ID/ordinal, suite manifest
identity, lock identity, experiment ID, terminal status/error, and canonical suite
report. The campaign stores its normalized definition and manifest SHA-256.

## Cross-suite ranking

Campaign aggregation maps database agent IDs back to each suite's logical agent
resource ID. Canonical eligible, success, benchmark, skipped, and orchestration
counts are summed across suites.

Success rate and the 95% Wilson interval are recomputed from those totals. The
lower Wilson bound is the campaign reliability score. Percentages are not
averaged.

## Re-export

```bash
agentbench campaign report 7 \
  --output results/campaign-7.json \
  --markdown results/campaign-7.md
```

This reads persisted campaign/member state and does not re-run suites.

Benchmark test failures remain benchmark measurements; campaign orchestration
failure is reserved for experiment/member execution failures.

## Persisted campaign progress

`agentbench campaign report <campaign-id>` includes a machine-readable `progress` object with `total_members`, `terminal_members`, `remaining_members`, `completion_fraction`, `status_counts`, `failed_member_ids`, and `skipped_member_ids`. The counts use persisted campaign-member states and remain meaningful if the campaign process stopped while a member was running. A running member is not assumed to have succeeded. This does not resume an interrupted campaign or infer per-worker utilization.
