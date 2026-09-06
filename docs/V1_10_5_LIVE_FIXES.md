# v1.10.5 live-review fixes — 2026-09-05

The first live review reproduced recurring delayed processing, stale dashboard snapshots and
several presentation mismatches. This follow-up preserves schema 14, trading rules, model recipes,
activation consent and the 70% qualification gate.

## Changes and regression coverage

- Training checks the existing exact-cohort readiness condition before serializing retained data.
  Concurrent new requests remain queued. Empty fits do not prune unchanged history or claim a
  published model. Original observation and governance receipts remain intact.
- Frozen fitting inputs omit Discovery sizing trials and previous Challenger evaluation receipts;
  full Policy sizing trials remain. Publication retains the season/authority fence and atomic write.
- A single dashboard refresh keeps its FIFO event-lock waiter through response timeouts or browser
  cancellation. Shutdown joins the snapshot thread before releasing its state boundary.
- Retention starts with at most 50 rows per category and reduces chunk size on slow/interrupted work.
  History and capacity-budget deletion stages each have a 200 ms SQLite query budget. Interrupted
  transactions roll back, completed
  chunks remain committed, and the progress handler is always removed before subsequent writes.
  Filesystem commits/rollback may exceed the query budget; this is not a real-time guarantee.
  Cancellation joins the maintenance worker before database shutdown. Fills, orders, entry decisions,
  ledger records, learning evidence and season scorecards are never retention targets.
- v2 and v3 season accounting are recognized separately. Unknown versions fail closed. Elective
  reset/end-now boundaries cannot count as comparable results. Earlier recorded flags remain in
  `recorded_comparable`; the archived scorecard is not rewritten.
- Skill gates identify their artifact and describe the testing contender when available. A saved
  Champion is labelled “Champion available,” separately from the newest contender's proof.
- The local AI provider description includes reviews, Coach research and explanations. API storage
  row counts have a startup-census timestamp; capacity and maintenance data continue to refresh.

## Isolated measurements

The same retained fixture contained 5,089 observations, 1,490 episodes, 1,000 models and 1,000 skill
artifacts. On a one-CPU isolated container:

| Measurement | Before | After |
| --- | ---: | ---: |
| No-op training preparation/check/publication | 4.62 s | 0.066 s readiness check |
| Frozen inputs for an actual due fit | 79.70 MB | 36.67 MB |
| Reconstruction plus actual fitting | 2.81 s | 1.67 s |

The actual fit produced one model and four skill artifacts. Coefficients, parameters, metrics,
evidence digests and qualification results matched exactly after normalizing generated identities
and creation timestamps. These timings are fixture measurements, not a claim of overall throughput
or profitable learning.

A separate 600-observation synthetic fixture exercised actual XGBoost fitting through both frozen
representations. Its binary payload, metrics, parameters, evidence digest and qualification result
also matched exactly.

The full backend run passed 469 tests. Following the final cancellation refinement, all 77 directly
affected worker/provider tests passed, including the added shutdown regression; the additional
XGBoost parity regression passed separately. The frontend passed
206 tests across 12 files. Strict Python/TypeScript checking, lint and the production build passed.
One existing Starlette/AnyIO deprecation warning and the existing lazy-renderer chunk-size warning
remain. Runtime dependency versions are unchanged and all 32 packaged Python source hashes match.

Initial live-fix image: `sha256:eb9257933bb7ccb041fb15d5a73878e5045f8913d31f7fdd7aef85542a13160c`.
Fresh disposable data passed schema, health, worker, snapshot, Seasons, Champion Journey, AI Lab,
startup asset and lazy asset checks. The current asset manifest is `V1_10_5_ASSETS.json`.

## Live rollout

The running app was prepared through its upgrade API. Its stopped active database passed
`quick_check`; a 2.84 GB compressed backup of active data passed verification of every file hash.
Previously preserved nested backups were not duplicated. The previous v1.10.5 image remains
available for rollback. Season 31, 400 USDC, Balanced, custom 25% drawdown, one-hour auto-season,
learning/AI Shadow modes and existing histories/settings were preserved. No season reset occurred.

The first 12 live samples, with reserve refresh disabled and UI testing underway, processed another
9,696 events without drops. Maximum sampled queue depth was 376/10,000; latest-event lag peaked at
3.25 seconds and protected-event lag at 0.319 seconds. Sampled snapshot age was at most 4.21 seconds.
Skipped training preparation took about 40 ms. These are short observations under varying traffic,
not a controlled claim of a particular overall throughput improvement.

The local `.env` then enabled reserve refresh with at most five routes every ten seconds. Distributed
defaults remain disabled. During the next 36 samples, the worker made seven requests, accepted six
routes and wrote six checkpoint updates. Sixteen rejection events were for unsupported Mayhem
curves; these remained unknown. No events were dropped in that observation window. New live paper
fills and learning observations were recorded; repeated ledger checks found no imbalanced
transactions or orphan fill/order references. The saved Champion journal retained all 17 events.

The UI checks covered 44 main/learning/Arena views, nine detail views and seven settled phone views.
All four Arena actions used 3D and released their canvases after close. Two simultaneously visible
3D windows also completed a one-minute check with one canvas each and none after close. No page
errors or app mutation requests occurred. Immediate desktop-to-phone resize samples briefly
reported horizontal overflow; fresh phone loads and settled 320/390-pixel checks did not reproduce
persistent overflow. v3 accounting, manual exclusion and named contender gates rendered correctly.

Sparse monitoring can receive the older timestamped cache on the first request after an idle
period. A specific follow-up check saw a 38.56-second old initial response become a 0.31-second old
snapshot one second later. The queued refresh made progress; this differs from the earlier
198.59-second snapshot that repeatedly lost its lock waiter. The UI retains its stale-data guard.

The later live check completed and published one model without a training error. Its measured
phases were 0.323 s preparation, 0.579 s reconstruction, 0.314 s fitting and 1.152 s publication.
Subsequent not-due requests skipped in approximately 15-52 ms. This confirms the live training
path progresses; publishing a model does not mean it qualified or became an active Champion.

Rolling five-minute outcome availability moved from 32.5% to 33.0%, still below 70%. This rollout
demonstrates validated checkpoint recovery, not achievement of the coverage target or better
forward returns. XGBoost parity is established on synthetic evidence; the live cohort had
187 of the 250 required eligible rows and no nonlinear artifact yet. Coach and Shadow reviews
may wait to protect active positions or market throughput.

Scheduled cleanup also made progress. A 50-row history pass took 0.326 s and reduced the next
chunk to 25. Subsequent observed history passes removed 25 rows in 0.047 s and 30 rows in 0.114 s.
One complete pass took 1.410 s, including 1.357 s in optional incident/AI history work. These
measurements include thread scheduling and lock waits. The 200 ms SQLite work budget does not
bound the entire maintenance pass. The legacy backlog remains; sustained reclamation relative
to new writes and disk capacity still need observation during the longer run.

The final read-only ledger check found 26 fills, two positions, 5,040 observations and 1,512
learning episodes, with no imbalanced transactions or orphan fill/order references. All workers
were healthy, with no container restart or OOM. Brief latest-event lag spikes persisted during
the maintenance observation window; the exact sampled peaks are recorded below. They prevent
claiming the live app is free of latency spikes.

The final 24-sample window processed another 25084 events with zero drops.
Maximum sampled queue depth was 527/10,000, latest-event lag 5.555 s and
protected-event lag 1.442 s. All sampled background workers remained healthy.
Since the staged restart, reserve refresh made 19 requests and recovered 14 checkpoints;
56 unsupported-Mayhem rejection events remained unknown. These counts are requests/checkpoint
updates, not independent tokens or proof of a lasting coverage improvement.

A short check cannot establish a 48–72-hour soak, all-device behavior, an achieved coverage target
or a forward trading edge. The optional reserve worker remains subject to provider quotas and
market pressure; invalid or unavailable account state remains unknown. Community-release confidence
still requires those longer observations.

## Additional edge-case review

The next review reproduced a cleanup contention bug in both history retention and capacity-budget
cleanup. The bounded deletion correctly yielded to another writer, but its unconditional cache
invalidation then reacquired that writer lock without a timeout. Invalidation now happens only
after a successful deletion, while the transaction helper still owns the lock. No-op/interrupted
work no longer performs this second wait. Committed deletions still invalidate cached counts.

Two new regressions hold the writer lock throughout the attempted cleanup and require it to return
before the writer releases the connection. They failed before the correction and passed afterward.
A third new regression confirms that a failed dashboard refresh releases its state boundary,
preserves the prior cache and allows a later request to recover. The focused database/provider
suite passed 121 tests, and the earlier season/refresh/training fault suite also passed.

Live reinspection found no ledger imbalance, orphan fills, container restart or OOM. An idle
dashboard briefly returned its explicitly timestamped older cache during maintenance, then
refreshed within the subsequent requests. This is not evidence of continuous UI polling latency;
the stale-data guard remains necessary. The correction changes no schema, trading rules,
settings, learning recipes or qualification requirements.

The contention correction is packaged as sha256:42f74cf3aa9c3fac56732e9c444e1db53d177742d321ae95c41a580e107575dc. All 32 packaged
Python source files match the working source; only database.py differs from the initial live-fix
image. Runtime dependencies and frontend asset hashes are unchanged. Disposable-data startup,
health, schema 14, API and static/lazy asset checks passed. Ruff and strict Python type checks
passed, and all three final contention/recovery regressions passed.

The correction was applied through the existing upgrade API and the operation completed on
restart. Season 31, its 400 USDC Balanced profile with custom 25% drawdown, the staged reserve
settings, and Shadow modes remained preserved. The subsequent paper exit was recorded at
07:48:11 UTC after market processing resumed; the ledger audit still balanced with 28 fills
and no orphan fill/order references. The verified earlier backup and initial live-fix image
remain available. No data migration, season reset or history restore was performed.

The six-sample post-correction window processed another 4636 events with zero drops
and all background workers healthy. Queue depth peaked at 16/10,000. The latest-event
lag samples peaked at 0.073 s; one protected-event lag sample was 4.878 s before returning
to 0.093 s. This short check does not establish latency stability. Reserve refresh recovered
13 checkpoints since this restart; unavailable route identities and unsupported Mayhem state
remained unknown. Coverage in the post-restart snapshot was 33.9%, below the unchanged 70% gate.
