# v1.10.5 overnight review — 6 September 2026

This is the pre-fix audit. The subsequent implementation and verification are documented in
[overnight reliability fixes](V1_10_5_OVERNIGHT_FIXES.md); the observations below retain their
original build and time context.

**Result: useful improvements are verified, but community release and Entry activation are not signed off.** The overnight run exposed a remaining reserve-refresh coverage limitation, a season-boundary processing stall and a retention backlog. Coach also made no new research attempts. Reaching 70% coverage alone would not qualify the current Entry models.

This was a read-only production review. No settings, gates, trading rules, model recipes, seasons, running containers or learning records were changed. Local review scripts and this report were added. Times below are UTC; add one hour for the user's British Summer Time.

## Scope and verification

- Primary capture: 6 September at approximately 05:21; independent database checks at 05:26–05:30.
- Deployed container started 5 September at 21:26:10. Image: `sha256:650a2a16c5f7b089187952db19e1a414d456f6e392a84aa9c13e143a389b5203`.
- Live backend, built frontend assets, README and changelog matched the working release. The same source has the saved passing 596-test backend result and 315 identical sizing-comparison cases. Those test suites were not rerun during this read-only audit.
- Inspected authenticated health, snapshot, seasons and diagnostics APIs, the completed diagnostics export, Docker logs and metadata, selected source paths, and small/indexed database queries. Database helpers used read-only SQLite connections and a read-only volume in isolated, CPU-limited containers.
- Did not run a full database scan, force a checkpoint/VACUUM, replay a production rollover, or call additional on-chain providers.
- Browser automation could not open the local site (`ERR_BLOCKED_BY_CLIENT`). This review verifies live server state and deployed UI assets, not a fresh visual inspection on desktop/mobile.

## What worked overnight

All six monitored core workers were alive, with no container restart, OOM termination, error-level log or traceback found. The captured boot processed approximately 5.17 million events. Across 428 retained minute intervals, both overall and critical processing p95 were within the one-second histogram bucket. The interval after the first rollover incident through the morning capture contained no further expired or shed events.

Training completed 129 runs and 129 publications, with no reported training error. One stale job was discarded. Of 121 retained training timing events in this boot:

| Phase | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Prepare complete input snapshot | 0.464 s | 0.795 s | 1.037 s |
| Reconstruct isolated inputs | 1.746 s | 2.339 s | 3.032 s |
| Fit | 0.676 s | 1.182 s | 3.109 s |

These measurements support the previous training-copy performance improvement. They do not establish better trading returns. Diagnostics recorded 78 skipped records, so the timing-event count is not identical to the completed-run count; missing telemetry is not treated as zero work.

A final health read around 05:34 showed all core workers alive, 132 fits/publications, no training error, and no additional expired events. The preceding five-minute window had no shedding/expiry and a p95 lag bucket of two seconds; instantaneous lag was 0.073 seconds with queue depth 145. This later short window is separate from the overnight aggregate above.

Current-season ledger transactions balanced, fills had matching orders, the execution audit was verified, and the UI gate artifact identities matched the corresponding candidates. The current profile remained 400 USDC, Balanced, 25% drawdown. Challenger and Local AI remained in Shadow.

## Learning coverage: the main remaining limitation

Operational Entry coverage rose from the previous evening's 41.1% to 53.3% at the primary capture. An independent reconstruction using the production cohort-selection methods at 05:26 found **539 usable outcomes out of the latest 1,000 (53.9%)**. The cohort covered decisions from 01:46:33 to 05:21:11.

| Five-minute outcome | Count |
| --- | ---: |
| Usable | 539 |
| Stale cached route | 272 |
| Executable exit quote unavailable | 188 |
| Checkpoint window elapsed | 1 |

The operational cohort contained 893 Discovery rows and 107 Policy rows. Policy had 102 usable and five unavailable exits. The narrower current candidate proof population in the earlier snapshot had 65 usable Policy outcomes out of 67 (97.0%). These are different populations and should not be substituted for each other.

Indexed lookups of each token's retained creation event found **266 of the 272 stale rows were Mayhem-mode tokens**. `validated_learning_state()` deliberately rejects Mayhem bonding curves with `unsupported_mayhem_curve`. The boot had 6,370 such rejections; these are attempts, not unique tokens. This is strong evidence that unsupported background refresh is the dominant remaining stale-route limitation in the current cohort. It is not predominantly an ordinary checkpoint scheduling failure.

The refresh already contributed 228 of the 539 usable outcomes in this cohort. Two more carried watchdog account proof. Existing bounded refresh is therefore doing useful work.

Supporting Mayhem safely requires verifying its supply and fee calculation against the official SDK, account layout and ownership, quote mint, mapping, timestamps/slots, migration and empty-reserve behavior. Removing the rejection alone would be insufficient: current non-Mayhem code deliberately uses a fixed supply for fee selection. The [official Pump fee documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/FEE_PROGRAM_README.md) describes the dependence of fee tiers on reserve-derived market capitalization and supply. The [official integration documentation](https://github.com/pump-fun/pump-public-docs/blob/main/README.md) links the supported SDK. Exact Mayhem quote equivalence has **not** been validated in this audit.

The 188 unavailable-quote checkpoints retain only the generic failure label; the exception branch does not retain the rejected quote reason or reserve proof. Their underlying causes cannot all be reconstructed exactly from these saved checkpoints. Preserve compact failure reason/provenance on future unknown checkpoints so liquidity, fees, invalid routes and implementation failures can be distinguished. Do not turn existing unknowns into zero returns or backfill past prices from today's chain state.

No guarantee follows that Mayhem support will deliver 70%: fresh quotes can still fail, and the cohort changes. Keep all tokens in the denominator and keep the 70% requirement.

## Entry still needs economic proof

The latest fitted Entry cohort at the primary capture had 47.3% model coverage. This is separate from the operational 53.3% coverage because the fitting cohort and eligibility rules differ.

Foundation proof was 12/16. In addition to coverage, the Linear model's highest-ranked validation group returned approximately **−15.60% after costs**, below the required positive return. XGBoost's corresponding group returned approximately **−13.22%**. XGBoost improved on its naive forecast and ranked better than Baseline, but its validation error improvement over the paired Linear model was only about 0.26%, below its required 2% complexity improvement.

XGBoost therefore remains legitimately unqualified. It is not waiting for a Linear champion to appear. Better collection should make qualification more trustworthy; it may also expose additional losses. It must not manufacture a champion.

The completed seasons also do not demonstrate profitability: season 31 ended at −101.729199 USDC and season 32 at −101.849876 USDC from 400 USDC bankrolls. Season 31 includes trading before this deployment. Season 33 was still running, around 388.17 USDC at the primary capture. These outcomes must not be advertised as a validated trading edge.

## Seasons and battles

Automatic rollover completed at 22:28:04 (31 → 32) and 03:39:46 (32 → 33), with the configured profile retained and trading resumed. Both archived seasons were complete and comparable.

Season 32 recorded four terminal write-offs. All four had verified, repeated account probes at increasing slots; the recorded blocker was fees exceeding sell proceeds. They were marked `was_executed=false`, rather than invented sell fills. This supports the intended handling of economically non-executable dormant inventory without waiting indefinitely.

Eight champion events were saved overnight: seven Exit crown retentions and one inconclusive Sizing comparison. Sizing's completed comparison had 120 usable outcomes out of 124 and an edge near −0.30 percentage points. Its next comparison had progressed to 77/80 with an average edge near +0.86 pp but uncertainty spanning zero. Exit's next comparison had reached 14/14. These tournaments are progressing.

The repeated zero Exit edges are compatible with equal selected timing policies, not evidence of a frozen bar or stalled learner. They do not show the contender improving. Avoid labeling equal-policy crown retentions as proof of superior performance.

## Season-boundary performance finding

All **9,107 expired and 507 shed candidate events** occurred in the interval 22:27:07–22:29:33, which contained the first automatic rollover. Maximum measured lag reached 82.48 seconds; critical lag reached 81.54 seconds and the queue reached 10,000. The code protects held-position, pending-order and due-outcome traffic through backpressure, but those events can still be delayed. A continuity gap is recorded for affected candidate mints.

The worker's `_finish_season_boundary()` awaits rollover while holding the event lock. `Database.rollover_paper_state()` clears all current paper tables, including the entire decisions table, in its atomic transaction. Startup contained 79,457 decision records; a current sample averaged about 14.5 KB of JSON per decision. The first boundary released approximately 1.3 GB of live database pages. This makes bulk season cleanup the leading explanation for the long pause.

No training fit/publication overlapped the incident, and ordinary measured batch, heartbeat and storage phases were much shorter. However, the dedicated boundary path has no complete phase timing, so this audit cannot distinguish the exact contributions of deletion, SQLite commit/checkpoint, disk latency and other boundary work. Do not report the 82 seconds as a measured duration of a single SQL statement.

Before release, instrument the complete boundary, reproduce the large-history case on an isolated fixture, and separate bounded archival/cleanup from the shortest possible atomic season handover. Preserve pending-order handling, exact successor creation, learning continuity, chronology, rollback and crash recovery. Simply dropping the event lock or making the handover non-atomic would be unsafe.

## Storage, Coach and Local AI

The main database had 14.965 GB live data against a 17.180 GB configured budget at capture. Its WAL file occupied 1.323 GB; physical WAL size alone does not establish uncheckpointed backlog. Physical E: free space was approximately 20.43 GB. No disk-full error was found.

**Retention is falling behind.** The oldest retained raw trade was from 3 September at 13:18, about 64 hours old despite the 24-hour setting. The retained storage events show 40,275 raw-trade removals overnight, while roughly 795,000 events were persisted. These incoming events are not all trades, but the retained age and rising live usage independently confirm the backlog. Below the 90% byte-budget target, retention is limited to 50 raw rows per enrichment pass and may defer for traffic. The urgent byte-budget path has additional work allowance; its ability to catch up at sustained current traffic was not demonstrated overnight.

Use a separate paced cleanup worker with small transactions and a bounded time/CPU budget that can retire more expired rows than arrive. Measure oldest retained age, incoming/removal rates and actual bytes. Validate protected learning/trading evidence remains untouched. Do not solve this with a large blocking delete or simply increasing the storage allowance.

API table counts also remained stamped at startup (21:27:48), despite later season transitions. Capacity readings continued to refresh. The current StorageManager uses capacity values, not those stale table counters; this is an API/diagnostic freshness issue, not evidence that live trading rows stopped updating. Prefer bounded refresh or explicitly unavailable/dated counters over full-table counts on the trading connection.

The separate diagnostics store used only about 4.14 MB of its 512 MiB allowance, with no early eviction and no recorder error. Its recorded gaps must remain visible. No larger diagnostics bucket is justified by this run.

Process RSS grew from roughly 0.91 GB after startup to around 1.8 GB, with the final hours fluctuating around 1.7–1.86 GB. Docker reported about 2.61 GiB container usage out of 15.55 GiB available and no OOM. This is not proof of a memory leak or of a permanent plateau; include memory in the next longer soak.

Coach retained the same seven reviews and made no new research attempt in this boot. `_coach_can_run()` rejects any active position or pending order, as well as processing pressure. The guard protects execution, but this run shows that continuous trading can starve optional research. Its displayed global outcome total also differs from the unrefreshed exact-context diagnostic count. Diagnose deferred duration/reasons, and design resumable bounded screening on detached input before relaxing any execution-priority rule. Existing forward evidence and zero-influence limits must remain intact.

Local AI produced 294 assessments since boot: 290 valid and four timeout/unavailable responses. Valid response latency was about 15.75 seconds median and 17.20 seconds p95, with 106 support and 184 insufficient-evidence verdicts, and no applied decisions. The broader retained qualification cohort still failed its validity, veto-value and 2.5-second latency requirements. Local AI is functioning in Shadow, but it is not ready for Guarded influence. Do not weaken those gates merely to turn it on.

## Recommended next stages

1. Verify and implement background-only Mayhem refresh with official quote-equivalence fixtures and strict account validation. Preserve failures as unknown, original timing windows, provider pacing, market-pressure yielding and Policy priority. Add compact unknown-quote diagnostics.
2. Measure and fix the large-season boundary pause using isolated backlog fixtures. Test crash/retry, double rollover, dormant write-off, pending orders and learning continuity, then observe at least one natural rollover under traffic.
3. Let bounded retention catch up sustainably without competing with execution. Test restart, cancellation, no expired rows, exhausted optional history, busy market and actual physical disk accounting. Repair stale API counters without writer-lock table scans.
4. Address Coach starvation and its progress reporting through measured, resumable optional work. Treat Local AI latency/qualification as a separate hardware/model evaluation, not an Entry gate change.
5. Repeat a 4–6 hour soak with comparable traffic and profile. Require no recurrence of the rollover backlog, improving retention age/bytes, progressing complete learning jobs, explicit unknown causes and healthy accounting. Entry activation still requires every proof gate; neither a successful soak nor 70% alone authorizes it.

Raw evidence remains in the local `audit` directory: `overnight-20260906.json`, `overnight-20260906-analysis.json`, `overnight-cohort-20260906.json`, `overnight-aux-20260906.json`, and `live-fix-deployment-overnight-20260906.json`. Keep these separate from community source distribution.
