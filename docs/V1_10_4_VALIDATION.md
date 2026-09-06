# v1.10.4 implementation and verification

This record describes the v1.10.4 implementation and checks completed on 2026-09-04.

Baseline: v1.10.3, 403 backend tests and 118 frontend tests passed during the preceding audit.
The production application is separate from this checkout. Test containers never write its data.

## Stages

- [x] Consistent backup and isolated restore verification; current progress reporting.
- [x] Validated terminal evidence, consistent tournament scoring, horizon governance.
- [x] Finite season handover and persisted five-minute unresolved-inventory deadline.
- [x] Fair checkpoint scheduler and bounded asynchronous validated reserve refresh.
- [x] Training publication safety and bounded Coach admission.
- [x] Paged Champion history and bounded artifact storage.
- [x] v1.10.4 metadata, README and technical documentation.
- [x] Final regression suites, fault/restart checks, build and release verification.

Confirmed terminal losses must preserve complete/comparable season accounting. Unknown inventory
retains uncertainty and original learning denominators. The 70% coverage gate and existing freshness,
risk, and authority requirements remain in force.

## Restore and performance evidence

- The consistent pre-change SQLite backup is 10,704,449,536 bytes, schema 13. Its read-only
  `PRAGMA quick_check` returned `ok`.
- Migration on a separate restored copy took 0.036 seconds. Checksums of all rows in fills,
  ledger entries, positions, paper orders, seasons, learning observations, evidence episodes,
  models and artifacts matched before and after. Unrelated settings also matched. Nine Champion
  events imported; reopening was idempotent. Invalid sidecar data rolls back the schema advance.
- The restored cohort contained 5,116 observations, 1,041 evidence episodes, 1,000 models and
  1,000 skill artifacts. The first snapshot implementation took 12.544 seconds under the event
  boundary and was rejected. Freezing serialized inputs and reconstructing them in the fitting
  worker reduced the measured boundary work to 0.068 seconds. Independent runs are timing
  samples, not latency guarantees; production load and hardware still matter.
- Retention query plans use `idx_market_events_kind_time` and `idx_decisions_created`. Bounded
  100-row cleanup on the copy took 1.492 seconds during concurrent checks, then 0.288 seconds.
  The earlier 267-second stall was not reproduced; the existing SQL was retained rather than
  changing its semantics without evidence. Progress age remains visible during future delays.
- One public RPC dry run fetched ten unique accounts for four historical Discovery curves in
  0.280 seconds. All four passed current owner/PDA/mint/fee/layout validation. Two had only
  12–13 lamports of real quote reserves: accepted route data is not automatically a usable exit.
  No historical checkpoint was backfilled and no production learning record was changed.

## Regression coverage

Final results: 460 backend tests and 120 frontend tests passed. The final backend run after the
additional fault review took 127.14 seconds; the frontend was unchanged during that review.
Backend Ruff lint, formatting,
Mypy (32 source files), frontend ESLint/TypeScript/Vite production build and Git whitespace checks
passed. Backend `pip-audit` and frontend production dependency audit reported no known
vulnerabilities. The backend suite emits one upstream Starlette/AnyIO deprecation warning.

The local `signal-arcade:v1.10.4` image was built successfully:
`sha256:0658a82036ba92c01adae24a5f2a6099679058eebad39ea4b8603f2dba685972`.
It started as the unprivileged application user with a read-only root filesystem, no network,
one CPU, a 1 GiB memory limit and temporary Demo data. Health reported version 1.10.4 and healthy
background workers. Snapshot, seasons, Champion history and Decision Lab endpoints returned
success; both bundled frontend assets loaded; the temporary database used schema 14.

Tests cover malformed/null/wrong-owner accounts, unsupported extensions, pool/vault/mint mismatch,
stale and future slots, duplicate probes, failed proof chains, empty pools and returning liquidity.
They also cover missing primary Exit checkpoints, secondary-horizon governance, preserved fee
budgets, actual Decision Lab executable-liquidity checks, scheduler fairness, RPC batching, stale
training publication, failed fits, interrupted migration, paged history and archived payloads.

Season tests exercise one persisted deadline across restart, unknown accounting without false
write-offs, a real event worker handing over during continuing arrivals, out-of-order priorities,
and new arrivals racing critical producers waiting for capacity. Existing API, broker, provider,
drawdown, profile, rollback, Coach, XGBoost and upgrade tests remain part of the full suite.

## Additional fault review

A second edge-case review reproduced and fixed three failures before deployment, adding six
regression cases:

- Mainnet/Demo changes could leave later events parked behind a season boundary and allow an
  already-dequeued old-source batch into the new feature cache. Source changes now discard all
  queued/parked rows without consuming in-flight accounting, and fence the old sequence range.
  Regressions check that fresh events still work afterward and that an awaited direct-ingestion
  write cannot carry an old-source event across the switch.
- Cancellation during the batch collection delay could leave an in-flight count and unfinished
  queue work behind. The collection delay now belongs to the worker's cleanup scope.
- A failed artifact write could leave the parent model saved, making retraining believe the
  incomplete generation was already published. Publication now commits model records, artifacts
  and pending states together, and installs their live view only after commit. Tests cover a
  mid-publication write error, a real deferred-constraint failure at SQLite commit, and retry after
  reopening the database and learner.

## Rollout limits

The existing app on port 8765 remains on its original v1.10.3 image and data. This implementation
has not been deployed to that container or published to a registry. Test containers are removed
after verification. The original consistent backup and JSON verification records are retained;
the disposable migrated/benchmarked copy is removed to recover disk space. Take a fresh consistent
backup at deployment time so subsequent paper activity is included in the rollback point.

The optional learning reserve worker starts disabled and requires a staged Shadow rollout. Its
limits and enable setting are documented in README, `.env.example` and both Compose stacks.
This release grants no new model consent. Unknowns remain unknown, including unverifiable tokens
whose season eventually closes as non-comparable.

A 48–72 hour production soak, useful future Champions and profitability are not established by
these checks. The prospective portfolio experiment is a separate future version, as required by
the accepted plan; it is not included or represented as completed here. Heavy archived model
payloads cannot be reconstructed from retained hashes alone. Protected artifacts and immutable
journals can exceed a configured disk target, so backups and storage still need monitoring.
