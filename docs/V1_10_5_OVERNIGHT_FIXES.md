# v1.10.5 overnight reliability fixes

The [6 September overnight review](V1_10_5_OVERNIGHT_REVIEW_2026_09_06.md) found
healthy routine training but three operational gaps: unsupported Mayhem refreshes, a large
decision-history deletion at rollover, and background work repeatedly deferred during normal
traffic. These fixes preserve the existing learning and activation requirements.

## Coverage

Verified Mayhem bonding curves use the same batched mint account already required for route
validation. Current mint supply selects the fee tier, matching `@pump-fun/pump-sdk@1.36.0`;
ordinary bonding curves continue to use the SDK's fixed billion-token supply. Mint executable
accounts, wrong owners/mints/routes, unsupported extensions, migrations, late responses and
invalid supply still fail closed. The refresh does not add calls to the trading decision path.

Unquotable Discovery, Policy and sizing checkpoints retain bounded reserve and fee details and
the actual quote error, while returns remain unknown. Old checkpoints are not backfilled or
relabelled. Better route coverage does not establish positive returns, predictive validity or
Champion readiness. XGBoost still needs its independent proof and paired Linear improvement.

## Rollover and storage

The existing atomic season transaction renames a nonempty current decision journal and creates
an empty replacement. It does not copy or delete every large decision JSON record during the
handover. The SQLite catalog preserves the retired-table cleanup queue across restarts. Cleanup
deletes at most 50 rows per category per pass, adapts downward on slow transactions and drops
only exhausted retired tables. Fills, orders, learning records and season accounting follow the
existing archival rules. An aborted rollover rolls the table handover back with the season.

This stays on schema 14. Older schema-14 builds can read the current tables but will not clean
retired journals until upgraded again. Retired bytes count against the existing main database
budget; they are not moved into diagnostics. Freed SQLite pages are reusable even when the
physical database file does not shrink. No full VACUUM is added to the running app.

Cleanup runs independently of optional provider enrichment, at most four passes per second
while behind, using 50 ms query budgets and short writer transactions. Normal in-flight market
batches do not indefinitely block progress; routine cleanup waits while a model fit is active.
Queue pressure, maintenance and cancellation still
yield. A detached 50 ms read budget, sampled at most once per minute, refreshes only counters it can complete, preserving the
actual timestamp for each count. Settings reports the observed oldest raw trade when retention
is behind. Compact cleanup events are aggregated at most once per minute. The separate
512 MiB diagnostics allowance and its retention policy are unchanged.

## Coach

Healthy open positions and an ordinary in-flight event batch no longer automatically exclude
research. Pending orders, stale/unexecutable active positions, imminent normal hold reviews,
queue/lag pressure, season boundaries, maintenance, storage work and model fitting retain priority.
The detached reader pauses outside SQLite's virtual machine between 25-row batches. Candidate
screening pauses between bounded rules. Both preserve the full cohort and have a 30-second
work deadline. Cancellation joins the worker; incomplete reads are discarded and cannot qualify
an experiment. Context and permission checks still precede inference and publication.

Local AI's separate validity, latency and value gates have not been lowered. Coach research is
still advisory and proposals need new forward proof. No Champion or Active mode is forced.

## Verification status

Verification on 6 September 2026:

- All **721 backend tests** and **314 frontend tests** passed. Strict mypy passed for 37 source
  files; Ruff and frontend lint passed; the production TypeScript/Vite build completed.
- Coverage tests include **108 fee-inclusive sell vectors generated with the actual pinned
  official SDK**, plus invalid-route cases. No app dependency was added for this reference test.
- Background regressions cover rollover rollback/restart, bounded cleanup, continuous traffic,
  Coach pause/resume, cancellation and identical candidate values.
- Parsed-source comparison against the pinned pre-upgrade image confirms unchanged configuration,
  models, strategy, broker, curve arithmetic, features, XGBoost and training-copy modules. All 135
  other existing LearningEngine/module functions are identical; three checkpoint methods only
  gained failure evidence through the new helper. Learning constants and gates are unchanged.
- An isolated 8,000-row journal with 120 MB of JSON took 957 ms to bulk delete and 10 ms to
  rotate. Twenty subsequent 50-row cleanup calls reclaimed 1,000 rows, taking 4–25 ms each.
  These are synthetic measurements on this host, not a forecast for every disk or season.
- The production storage card was visually checked at 1440 px and 390 px widths, with no page
  overflow or browser errors. The changed message uses ordinary HTML; Arena assets remain lazy.
- Deployment used the existing maintenance API and preserved the environment, named data volume,
  season 33, 400 USDC Balanced profile and 25% drawdown. Accounting and gate-subject checks passed.
  The database remains schema 14. A pinned rollback image is retained locally.
- The authenticated diagnostics export completed after deployment: 2,891 data records, about
  4.98 MB, in 1.47 seconds. A pre-deployment export during temporary processing pressure was
  correctly marked incomplete; it was not used as a complete audit.

## Live observation

The first rollout started on 6 September at 06:09 UTC. By 06:24 it had processed 100,074 events
with zero drops, errors, warnings, OOMs or container restarts. Two model fits published successfully;
the second completed in 2.32 seconds. The first fit took 12.94 seconds and a sampled queue lag
briefly reached 4.32 seconds before recovering. The final scheduling refinement therefore defers
routine cleanup while a model fit is active, with a regression covering its eventual resume.

Entry coverage moved from 571/1,000 before deployment to 581/1,000 at this first-stage check.
The refresh worker wrote 152 checkpoint updates. A bounded database sample found 30 usable
Mayhem checkpoints across horizons; 23 other Mayhem checkpoints correctly remained unknown.
New quote-failure details identified inadequate real reserves and fees exceeding sell proceeds.
These are checkpoint counts, not distinct tokens, and this small window cannot forecast 70% coverage.

Coach completed a valid historical screening review with no eligible experiment, then waited for
25 new outcomes. Cleanup reclaimed tens of thousands of old raw trades while retaining protected
records. Its backlog is still substantial and is expected to clear progressively, not instantly.

The final image is `sha256:197672dc40e20457dd5a31e324ccd1036c9dbccfd476a338daa629363791c69c`.
At 06:34 UTC it had processed 62,164 events with zero drops, errors, warnings, OOMs or restarts;
all seven monitored workers were healthy. Its first fit published in 3.92 seconds. The latest
five-minute processing p95 was within the 0.5-second histogram bucket. Twelve observations
spanned 5.5 minutes, including the cleanup worker resuming and reclaiming more old raw rows.
Accounting and proof identities passed the final check. Season 33 and its settings were preserved.
The old schema-14 image also successfully read the current journal and settings in an isolated
rollback-compatibility fixture containing a retired journal.

Current Entry coverage is **588/1,000 (58.8%)**, versus 571/1,000 immediately before the first
rollout. The window still contains older evidence and is below the unchanged 70% gate. Entry
activation has not been earned; coverage alone would not satisfy all other proof requirements.

The identified fixes are implemented and live. Community publishing remains pending a further
3–6 hour soak, sustained coverage and cleanup progress, and the next natural rollover. The
rollover fix has transaction, interruption and performance tests; a natural production rollover
has not occurred in these post-fix windows. A short validation cannot establish long-term
profitability or the absence of every possible defect.

## Follow-up edge-case check — 6 September, 06:37–06:43 UTC

Two additional regressions cover a cleanup backlog of 19 retired seasons (beyond the
16-table catalog page), restart and exact chunk limits, and cancellation while a cleanup
thread is still using the database. All eight storage regressions passed; the new tests
also pass Ruff and formatting checks. The earlier 721-test backend run remains the full-suite
baseline; these two additions were checked separately. No runtime code or live settings
changed during this follow-up, so no further app restart was required.

The authenticated live check again verified accounting, candidate/gate identities, schema 14,
season 33 and its existing settings. By 06:42 UTC the current image had processed 136,411
events with no drops. It had published three fits; the two newer fits completed in 2.86 and
3.39 seconds. Coach saved a valid screening review at 06:38:46, with no experiment meeting
the screening floor, then waited for new outcomes. Cleanup had reclaimed 47,636 old raw
trades since this boot and continued to advance the oldest retained timestamp. The backlog
remains substantial. Entry coverage was 591/1,000 (59.1%); the 70% requirement remains unmet.

Six live observations over 151 seconds found every monitored worker healthy. Container
logs had no errors or warnings, and there were no restarts or OOMs. Diagnostics nevertheless
captured a transient 6.10-second maximum processing lag, including a 3.65-second maximum
for critical events, in the 06:40–06:41 interval. This overlapped local validation; the
available evidence does not establish its cause. Cleanup deferred/shrank its batches under
pressure, then resumed at 50 rows. Four subsequent samples across 90 seconds measured
0.123, 0.018, 0.036 and 0.096 seconds, with no drops. By 06:43:45 the five-minute p95 had
improved from the 5-second to the 2-second bucket, still including the earlier spike. This is a performance
watchpoint for the longer soak, not evidence that latency is always below one second.

No additional runtime defect was reproduced by this check. A natural production rollover
and the longer soak remain outstanding before community publishing.

Later verification: [final release review](V1_10_5_FINAL_RELEASE_REVIEW.md), including live
desktop/mobile UI, exact deployed-source matching and refreshed dependency advisories.
