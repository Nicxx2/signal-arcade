# v1.10.7 burst-performance follow-up — 7 September 2026

This document records the initial burst review and the subsequent staged follow-up. Neither changes
the version, database schema, dependencies, model recipes, permissions or trading rules. Each live
update follows isolated validation. Historical observations below retain their original build and
time bounds; the latest follow-up is at the end. Comparable busy conditions remain necessary to
measure the combined effect on queue losses and lag.

## What the retained evidence establishes

The same-boot diagnostics confirm the queue overrun at **18:16:15–18:19:05 UTC**: 1,050 candidate
events were shed, 6,290 expired, queue depth reached 10,000, overall lag reached 40.37 seconds and
critical lag reached 16.35 seconds. At the **18:21 UTC** observation, queue depth was 3, critical lag
was about 0.1 seconds and cumulative losses had not increased at that observation. Workers remained
running; no restart or out-of-memory event was recorded. Recovery did not erase the lost candidates.

The immediately preceding **18:13:01–18:16:15 UTC** intervals had the same boot, configuration and
active learning mode. They are a useful comparison, but their event mix is not identical:

| Recorded measure | Preceding 194 seconds | Affected 170 seconds |
| --- | ---: | ---: |
| Admitted events/second | 271.6 | 272.6 |
| Processed events/second | 258.6 | 190.4 |
| Mean persistence phase | 9.77 ms | 18.39 ms |
| Mean event-learning phase | 2.31 ms | 3.16 ms |
| Mean heartbeat phase | 863 ms | 1,409 ms |
| Dashboard calculations | 0 | 5, totaling 14.12 s |
| App CPU seconds / elapsed second | 0.90 | 1.02 |

This establishes a processing-capacity shortfall, with increased work/waiting across several
paths. It does not establish a single initiating cause. Learning work per processed event also
increased. Phase times include scheduling and lock waits and overlap with event batches and other
workers; adding them would overstate total work. The interval can hide shorter arrival spikes.

Dashboard activity overlapped the problem and a snapshot holds the market boundary while building
a consistent view. It therefore contributes work and blocking, but the logs do not prove that a
browser initiated the overrun. Investigative dashboard requests also contribute to that count.
The existing diagnostics cannot separate SQLite execution, writer-lock waiting, storage latency
and host scheduling within the persistence measurement.

Training continued with Linear and XGBoost publications; Sizing and Exit monitoring remained
healthy in the reviewed snapshots. Entry's operational coverage was about 46.5%, with independent
fit/proof failures still visible. At **18:39:35 UTC**, on the unchanged build, the queue was 4,880 and
cumulative expiries had reached 9,654. This later observation rules out treating the earlier recovery
as permanent resolution. Its operational Entry coverage was 46.3% (463/1,000), not a training score.

## Reproduced costs and changes

1. **Reject otherwise unusable training rows before the Policy lookup.** The old selection path
   computed identity hashes even for the wrong requested cohort, absent/unavailable primary labels
   or incomplete features. Four regression cases reproduced this extra work while already returning
   the correct rows. Reordering the pure filters preserves the exact sorted training population.
   It does not delete unknown observations or change any coverage denominator.
2. **Reuse immutable Policy identity digests.** A synthetic active-Champion fixture with 5,000
   Policy records performed 25,120 identity hashes during one status calculation. The digest is a
   pure function of six immutable strings/optional strings. A thread-safe, process-local LRU now
   retains at most 16,384 such results. It retains no observation objects, outcomes, model arrays,
   qualification decisions or health results. Every call still checks current identity receipts
   and proof facts. Changed contract fields, eviction and restart produce the same durable digest.
3. **Invalidate market-write counts before releasing the writer boundary.** Deterministic
   concurrent-reader tests showed committed counts of 1 or 2 while the cache still reported 0.
   The event writer then had to acquire the writer lock again merely to invalidate that cache.
   Invalidation now occurs inside the existing transaction boundary. Both single writes and batches
   finish without waiting behind the simulated subsequent maintenance owner. Duplicate handling,
   rollback and durable-before-fill behavior are preserved.

These are confirmed avoidable costs/races. Their exact contribution to the historical 40-second
lag cannot be reconstructed from the available aggregate diagnostics.

## Equivalent isolated comparisons

The comparison used a network-disabled container capped at one CPU and 1,800 MiB, with temporary
SQLite storage and no production volume mount. The historical fixture had already been copied
before this task. Its 5,089 observations and 1,490 evidence episodes do not represent the complete
current active-Champion state, so a separate synthetic fixture earned an actual manipulation
Champion through the existing test path and expanded Policy evidence to 5,000 records.

Old and new functions alternated in the same process on identical evidence. One warm-up pair was
excluded, then six observations per variant were measured. Complete status JSON was identical
across every before/after observation within each fixture.

| Median learning-status CPU time | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Copied historical fixture | 369 ms | 243 ms | 34% |
| Active-Champion synthetic fixture | 552 ms | 335 ms | 39% |

Median wall times were 391→243 ms and 552→335 ms respectively. An earlier pair of separate runs
was slower after the change because host load differed; that pair is not evidence of improvement.
CPU measurements and alternating runs address this confound more directly. They are measurements
of these functions, not end-to-end event throughput, XGBoost training speed or trading performance.
The active fixture uses synthetic proof for isolation, not evidence of a live Champion's profits.

## Correctness and edge-case checks

- Stage 1: 40 focused selection, Policy-identity, candidate-selection and training tests passed.
- Stage 2: 162 focused learning, activation, composition, Coach lifecycle, restart and candidate
  tests passed. Added checks cover exact historical digest compatibility, all contract fields,
  `None` versus empty configuration, mutable outcomes/clocks, bounded eviction and concurrent reads.
- Stage 3: 127 market, database, cleanup, watchdog/provider, queue and runtime-pressure tests passed.
  New cases cover the concurrent write/cache handoff, duplicates, batch rollback and a successful
  write after rollback. Existing cases exercise urgent arrivals during candidate batches,
  cancellation, unavailable routes, cleanup overlap, season boundaries and restart recovery.

The full backend suite passed **1,063 tests**, with no failures or skips. Ruff lint and formatting
passed for **93 Python files**; strict mypy passed for **38 backend source files**. One existing
Starlette/AnyIO deprecation warning was reported. `git diff --check` also passed. Frontend source,
API response shape, runtime dependencies and version metadata were unchanged by these fixes;
the paired learning-status comparisons preserve the existing readout contract.

A subsequent edge-case review kept both backend files byte-identical to that validated build.
**119 focused regressions passed**, including six additional cases for independent learning
workspaces sharing a warm digest cache, changed Policy outcomes and original clocks, NaN/infinite
features, and a SQLite failure at COMMIT after cache invalidation. Unknown outcomes still count
against coverage; a reserved Discovery twin stays excluded; failed commits preserve existing
events and allow a clean retry. No further runtime change was needed. This targeted follow-up
supplements the earlier full-suite run rather than representing a second full-suite run.

## Operational boundaries and release assessment

No live settings, database records or permissions were changed. No live service was paused,
restarted, deployed or pushed. Investigative reads were serial and bounded. Offline checks consumed
up to one CPU per validation container on an eight-logical-CPU Docker host; later live observations
are therefore not a clean before/after performance experiment.

The final read at **19:02:57 UTC** still identified the previous image, with zero restarts and no
OOM flag. All seven workers were running, queue depth was 3 and critical lag was 0.031 seconds,
but cumulative candidate losses had reached **8,191 shed + 46,745 expired**. The recent-loss warning
correctly remained. The 12 retained intervals read alongside it include another full-queue interval
at **18:56:57–18:59:14 UTC**, with a recorded gap and 11.02-second critical-lag maximum. Those
intervals overlap isolated validation on the same host; they cannot establish the app's standalone
performance or the uninstalled fixes' effect.

The first on-demand snapshot was old and started a refresh. A bounded follow-up obtained a view
generated at **19:04:30 UTC**, only 3.1 seconds old: paper accounting was verified; Sizing and Exit
were active with healthy monitoring; 33 models had been published without a training error;
Entry's operational coverage was **45.3% (453/1,000)** and it remained unqualified. Coach reported no
error and an attempt at 19:01:20 UTC. Cleanup had advanced to 216,305 retired raw trades this boot,
although retention age was still roughly 29 hours. These observations establish continuing work
and recovery, not sustained burst tolerance or qualification progress.

The queue capacity, expiry/admission rules and urgent-work safeguards remain unchanged. Baseline
approval, route and fee requirements, hard exits, Champion/Coach permissions, activation/demotion,
chronological validation, Policy retention, Linear/XGBoost comparison and the 70% requirement
remain intact. No learning process was disabled and no warning was suppressed.

Cleanup still uses bounded transactions and can lag its retention target under pressure. The
18:39 snapshot used a one-row adaptive chunk and retained its oldest trade for about 28 hours
52 minutes against a 24-hour target. Cleanup had advanced, and allocated storage remained below
the configured 16 GiB budget. The evidence does not yet identify a safe additional cleanup change.
Watch the age of the oldest retained trade, useful/allocated bytes, WAL growth and cleanup progress
over comparable busy windows. Coach/provider starvation and long-season endurance also require
longer observation; no new causal defect was established in those paths in this review.

These changes add no schema migration. A rollback can restore the preceding compatible schema-16
build using the normal controlled update procedure; do not roll a schema-16 volume back to a
schema-15 image. Preserve diagnostics and the data volume. The identity cache is disposable and
does not require migration or a data reset.

After an approved deployment, compare the build fingerprint, arrivals/event mix, critical-lag
histograms, candidate losses, model publications, due evidence, active health and cleanup progress
over several busy intervals. A quiet snapshot is insufficient. These fixes cannot promise an Entry
Champion, profitable paper trading or issue-free operation over months.

**Assessment:** the implemented source changes are ready for review, with their isolated
regressions and broader checks passing. The approved deployment below passed its initial checks.
Comparable busy-period observations remain necessary before claiming the burst problem is resolved.
No additional code defect was established that justifies changing queue limits, learning rules,
Coach scheduling or cleanup policy in this patch.

## Approved live deployment and initial observation

The user authorised the live update after the read-only deployment check. At **19:47 UTC**, the
normal maintenance operation settled with zero unfilled orders to cancel. The replacement was
validated by **19:47:41 UTC**, about 23 seconds after maintenance preparation began. Only the
Signal Arcade service was replaced; its data volume and container environment were preserved.
The ignored local image selection now points to `signal-arcade:v1.10.7-burst-20260907` so a later
Compose start uses this build. The previous schema-16 image remains available for rollback.

- Image: `sha256:01d21afde7aa70ccf4cfafa14a24a5315ffe811d75e31d3a26105c4765cbd6b7`.
- Diagnostic build: `f867ff61462c00e8bad8a00094458d65e296c072f7e6fc1877aeac7a8047410c`.
- All installed backend source hashes match the reviewed repository. Only `database.py` and
  `intelligence/learning.py` differ from the preceding image. Runtime dependencies and frontend
  assets were verified identical; version 1.10.7 and schema 16 are unchanged.
- An isolated startup check passed without network access or production storage. Season 36,
  saved Champions, automatic support permission and both Coach permissions survived the update.
  Sizing and Exit resumed with their original active versions and healthy monitoring.

Six serial health observations from **19:48:09–19:53:10 UTC** recorded 35,925 additional processed
events, no shed or expired candidates, and all seven workers running. The final sampled queue was
102 and current critical lag was 0.238 seconds. Docker reported healthy, no restart and no OOM;
the bounded startup log contained only normal INFO messages.

Five retained intervals covering **19:47:29–19:52:48 UTC** recorded 36,657 processed events, zero
candidate losses, a peak queue of 534, peak overall lag of 3.62 seconds and peak critical lag of
1.63 seconds. The first is a partial startup interval; the following four complete intervals have
no recording-gap flags. Diagnostics continued in the same history database with a new boot/build
identity, zero detail drops and no writer error. Historical pre-update losses remain recorded.

A fresh snapshot generated at **19:53:35 UTC** confirmed two model publications after restart,
no training error, verified paper accounting and healthy Sizing/Exit monitoring. Coach research
and contribution permissions remain enabled, with a post-restart attempt and no reported error.
Entry remains unqualified at **40.8% operational coverage (408/1,000)**; its 70% requirement and
separate fitting and independent-proof checks remain intact. Cleanup continued, retiring 4,884
raw trades after restart, and reported storage within budget; the older retention backlog remains.

These are successful deployment and early recovery checks, not a matched burst benchmark. The
four complete new-build intervals admitted about **123 events/second**, versus about **252/second**
in the preceding five old-build intervals. Arrival mix and post-restart provider state differ, and
the old window overlapped image preparation. Cold/warming state and reset process counters also
limit comparisons. No end-to-end speedup, improved Entry coverage or long-term reliability claim
is justified by this short observation. No community push was performed.

## Subsequent staged follow-up

Later observations challenged the early healthy window. At **19:58:30–20:00:16 UTC**, the
19:47 build expired 726 candidates without capacity shedding. Recorded queue depth reached 3,719,
overall lag 19.56 seconds and critical lag 15.99 seconds. Four snapshots consumed 10.29 seconds;
16 heartbeat ticks consumed 18.09 seconds. This establishes concurrent expensive work, not that
the dashboard alone caused the losses. Another interval at **20:11:38–20:12:59 UTC** expired 565
candidates without a recorded snapshot, but overlapped an isolated profile on the same host and
is not a clean independent comparison. Workers remained running. Existing wall durations cannot
separate worker CPU, executor delay and database waiting.

The follow-up implements four bounded stages:

1. **Cancellation ownership.** Reproductions showed that cancelling heartbeat/market work, or
   cancelling a snapshot twice, could release the event boundary while its thread still ran.
   Submitted engine work now joins before cancellation escapes its owner; storage also signals
   its existing cooperative stop flag. Normal values and exceptions remain unchanged. Repeated
   cancellation, a worker failing during cancellation, context propagation and shutdown before
   database closure are covered. Cancellation can take longer because it must await submitted
   work; this does not make a stuck native operation interruptible.
2. **Fresh training admission.** A quiet check could become stale while waiting for the event
   lock. The trainer now checks again before taking a request or copying inputs. Tests inject
   queued/in-flight events, lag, storage, maintenance and shutdown during that wait. Deferred
   requests keep their original age and retry at the existing cadence. Training recipes,
   publication checks and existing pressure thresholds are unchanged.
3. **Dashboard work and bounded diagnostics.** A status response now computes the Discovery
   training population once and reuses only its count in the same response and exact cohort.
   Standalone requests remain fresh. Fixed aggregates distinguish selected worker CPU,
   executor/event-loop delay and completed event-lock waits; see
   [their precise interpretation](DIAGNOSTICS_HISTORY.md). They add no per-event history, live
   database query or authority. Worst-case diagnostic payload bounds remain tested.
4. **Active-health work.** An isolated 20-mint checkpoint profile identified repeated full Policy
   selection for each active skill. Each governance pass now shares its exact-cohort population
   locally. Health, receipts, dependencies and activation proof are still checked per skill.
   No population survives the pass, no outcomes are batched across governance boundaries, and
   suspension still stops immediately. Tests confirm that the next pass sees unavailable Exit
   receipts and harmful Sizing evidence and removes the affected support.

Stage suites passed **103, 105, 161 and 156 tests**, respectively; these counts overlap and must
not be added. The original cancellation, stale-admission, duplicate-status-selection and duplicate
health-selection reproductions failed before their corresponding fixes. Static checking uses the
project's existing pinned tools; no dependency upgrade was introduced.

### Isolated measurements and limits

All comparisons used temporary data, no production mount or network, and a one-CPU container.
The shared host still means live intervals overlapping validation are not standalone app samples.

| Paired operation | Previous median CPU | Updated median CPU | Evidence |
| --- | ---: | ---: | --- |
| Copied-data status response | 211.5 ms | 171.2 ms | Identical complete response; 3 measured samples per variant |
| Synthetic active-skill status response | 359.9 ms | 392.5 ms | Identical response; noisy result, no demonstrated speedup |
| Sizing + Exit health pass, 5,000 Policy episodes | 153.3 ms | 93.5 ms | 8 alternating measured samples per variant; identical evidence, health and active skills |

The health-pass result is about **39% less CPU for that operation**, not a whole-app throughput
claim. The checkpoint profiler itself added substantial overhead and its 6.54-second duration
must not be presented as a live tick benchmark. A 500-call no-op microbenchmark measured roughly
51 microseconds extra CPU per joined thread call and 90 microseconds including timing, compared
with a plain thread call. Those costs are nonzero and workload-dependent; the new aggregates are
used only for the selected phases. The optimization does not eliminate all full Policy scans or
prove that bursts can no longer expire candidates.

Policy identity retention, training/proof separation, chronology, route freshness, fees, unknown
outcomes, 70% coverage, Baseline approval and hard exits remain unchanged. No queue was enlarged,
no warning suppressed, and no learning or Coach work disabled. These fixes reduce avoidable work
and strengthen ownership; they cannot promise an Entry Champion or improved trading returns.

The complete backend suite passed **1,108 tests**, with zero failures, errors or skips in
**158.65 seconds**. Ruff and strict mypy checks passed. A dependency deprecation warning in
Starlette's test client remains unrelated to these changes. Tested source hashes were retained
and must match the packaged image. Frontend code is unchanged; its packaged assets are compared
with the preceding live image before deployment.

### Follow-up live deployment

The user authorised installation after validation. The updater waited for two recovered pipeline
samples before using the existing maintenance operation. Preparation began at **20:52:45 UTC**;
the updated service passed verification by **20:53:09 UTC**. No unfilled orders needed cancelling.
Only Signal Arcade was replaced. Its volume, container environment, season, saved Champion
records, active Sizing/Exit versions, support permission and Coach permissions were preserved.
Paper accounting remained verified.

- Local tag: `signal-arcade:v1.10.7-burst-stages-20260907`.
- Image: `sha256:81d0ff4a99212f155d44cecbe7eff083ebb7dc2450fac0a2ebc857e408890709`.
- Diagnostic build: `6ecad52a8361909233a56bdafbc91443810aedbb929cca6e53ba1d4aa9b09d68`.
- All 38 packaged backend files match the validated working source. Changes relative to the
  previous deployment are limited to `orchestrator.py`, `diagnostics.py` and
  `intelligence/learning.py`. Runtime dependencies and built frontend assets are identical.
- Isolated startup passed before deployment, without network or production storage. Version
  1.10.7 and schema 16 are unchanged. The ignored local Compose image selection was updated so
  a later start keeps this build. No GitHub or Docker Hub push was performed.

The preceding `signal-arcade:v1.10.7-burst-20260907` image remains available for a controlled
rollback on the same schema-16 volume. The caches in this follow-up are per-response/per-pass;
they require neither a migration nor a reset. Preserve the volume and diagnostic history.

Six serial health samples from **20:53:26–20:58:26 UTC** recorded **37,458 additional processed
events**, zero shed/expired candidates and all seven workers running. Five retained intervals
covering **20:52:57–20:58:13 UTC** independently recorded 37,765 processed events, zero losses,
a maximum sampled queue of 550, overall lag peaking at 6.24 seconds and critical lag at 3.14
seconds. The first interval is partial startup; the other four have no gap flags. At the final
**20:59:03 UTC** read, current critical lag was 0.188 seconds, queue depth 227, and there were no
degraded reasons, container restarts or OOM events. The bounded log had no worker exception;
one WebSocket connection was rejected and another accepted about one second later. That log
alone does not establish the rejected client's authentication/origin condition.

The final fresh snapshot and health read confirmed:

- Two model publications with no training error or discarded stale job. Reserve refresh had
  made 32 requests, accepted 141 routes and recorded 142 checkpoint updates, with no worker error.
  Invalid/unavailable routes and three responses discarded on context/pressure checks remain
  explicitly recorded. These counts use different units and are not an outcome failure rate.
- Sizing and Exit retained their original active versions and healthy monitoring. Their current
  health samples were 58/60 and 57/60 usable. Sizing's mean was slightly negative with an upper
  uncertainty bound above zero; healthy monitoring must not be described as proven improvement.
- Entry remained unqualified at **391/1,000 operational coverage (39.1%)**. Its independent proof
  and fitted-model coverage remain separate. The earlier 38.1% post-start value and this value
  are changing rolling populations, not evidence that the patch improved model quality.
- Coach's worker and both permissions remained enabled. It recorded a post-start attempt and
  reported waiting for outcomes with no error. Cleanup removed 2,663 raw trades after restart
  and remained within the configured budget, but its oldest retained trade was still roughly
  29.5 hours old against a 24-hour target; the retention backlog needs continued observation.
- Diagnostics used the new build/boot identity and retained the new CPU and wait aggregates,
  with no dropped records or writer error. There was one deferred collection check. Recorded
  heartbeat CPU totaled 9.75 seconds across 57 ticks, while 14 snapshots used 13.82 CPU seconds.
  Event persistence and learning also showed meaningful executor/event-loop delay; that is not
  evidence that all remaining wait time is SQLite contention.

These initial intervals admitted about **121.5 events/second**, materially less than the earlier
severe burst. They therefore establish successful deployment, continuing learning, recovery and
diagnostic continuity, **not resolution of every burst-performance problem**. The code has passed
its staged and full checks and is running for the requested observation before community push.
No further release-blocking regression was identified in these checks. Sustained busy periods,
checkpoint opportunities, Entry proof/coverage, Coach opportunities and cleanup backlog still need
comparison over longer periods; existing qualification and risk boundaries should remain intact.

### Additional edge-case check

A subsequent review added **10 regression cases** covering repeated cancellation while a worker
is queued behind an occupied executor, worker failure after queued cancellation, empty Policy
populations, and isolation by risk mode, null/empty configuration and Baseline contract. The
targeted suite passed **153 tests** in 18.21 seconds; Ruff passed. The earlier full 1,108-test result
remains the full-suite result for the deployed runtime. Only tests and these notes changed in this
recheck; all 38 backend hashes still match the deployed image. No further restart was needed.

At **21:05:33 UTC**, the live app had processed 101,770 events since startup with zero candidate
shedding or expiry. Queue depth was zero and current critical lag 0.105 seconds. All seven workers
were running, Sizing and Exit retained healthy active monitoring, three models had been published,
and reserve refresh had recorded 223 checkpoint updates without a worker error. Entry remained
unqualified at **389/1,000 operational coverage (38.9%)**. Coach was yielding to open-position
protection, with its worker running and no error. Storage remained within budget.

The extended history also captured a slowdown at **21:03:34–21:05:14 UTC**: maximum sampled queue
2,385, overall lag 14.32 seconds and critical lag 4.88 seconds, followed by recovery without losses.
The 100.30-second diagnostic interval carries `recording_gap`; intervals exceeding 90 seconds are
flagged even when the writer reports zero dropped records. This does not provide minute-level
detail or prove that every intermediate event was observed. Isolated checks ran on the same host
during this review, so these observations are not a controlled performance comparison. Continued
busy-period observation remains necessary; the burst-performance question is not closed.

The log contained rejected browser WebSocket attempts. A separate bounded, authenticated
same-origin WebSocket handshake succeeded against the LAN address. The unchanged authorization
and origin guards remain enforced; the rejected clients' credentials/origins were not available
to this review. Browser polling and bounded reconnection remain in place. No source change was
justified by those log lines alone.

## Held-position burst follow-up (deployed 8 September)

The later natural interval **21:28:31–21:30:32 UTC on 7 September** recorded 3,396 expired
candidate events, no queue shedding, a maximum sampled queue of 6,365, overall lag of 25.63 seconds
and critical lag of 17.30 seconds. The app recovered by 21:36:31 without restarting, but recovery
does not restore expired candidates. There were no dashboard calculations or model publications
inside that severe interval, so neither is a sufficient explanation of this incident.

That interval contained 2,401 broker updates and 4,111 persistence worker calls. A held token had
3,832 retained events between its buy and sell; retained rows and broker invocations are different
counts. The next interval admitted more events per second but had far fewer broker calls and less
critical lag. Workload composition matters, and total input rate alone is not a matched comparison.
Nested diagnostic durations cannot be added to attribute the entire delay to a single component.

### Changes justified by reproduction

- A held-position trade previously marked/saved its position, saved its exit assessment, then
  marked/saved the same position again during order processing. The combined market-update path
  now performs one mark and retains the assessment write. Independent order processing, heartbeat
  and watchdog paths still refresh marks. The private fill helper retains causal and execution
  guards; no timestamp cache or suppression of distinct market updates was introduced.
- Newly arriving urgent events were committed individually while interrupting a prefetched
  candidate batch. The first urgent arrival still commits alone; already-queued arrivals behind
  it use groups of at most 16, without waiting for more events. The original total urgent allowance
  remains bounded by one extra event batch. The existing initial batch size is unchanged.
- Buffered arrivals do not bypass an older prefetched event that becomes protected after an
  order is created. Priorities are checked between handlers. All durable evidence commits before
  fills; duplicate handling, per-token chronology, season boundaries and cancellation joins remain
  in force. A failed grouped write rolls back its entire group and records an integrity gap.

No model recipe, coverage denominator, 70% requirement, qualification rule, Champion/Coach
permission, health decision, checkpoint deadline, fee, hard exit, queue capacity or storage limit
changed. There is no new database schema or dependency. Broader heartbeat, dashboard, cleanup and
AI resource tuning was deferred because these two isolated changes do not establish a cause or a
safe fix for every remaining scheduling delay.

### Equivalent isolated comparisons

Preserved and changed functions alternated within the same process, with one warm-up pair excluded
and six measured runs per variant. Containers had one CPU, 1,800 MiB memory, disabled networking,
temporary SQLite databases and no production volume mounts. Timing remained subject to host
scheduling. These tests do not recreate the full provider, feature, training and disk workload.

For 800 held-position updates, median broker CPU time fell **515.7 to 380.5 ms (26.2%)** and wall
time fell 517.5 to 380.5 ms. Valuations fell 1,600 to 800 and position writes 2,400 to 1,600.
Final position, fill, cash, ledger and season-participation results had identical hashes. The
fixture includes blocked/recovered routes; executable exits and other risk cases are covered
separately by regression tests. Worst individual tick time did not show a consistent improvement.

The event-worker fixture isolates persistence and scheduling, using lightweight handlers rather
than model/provider work. Each workload starts with 250 prefetched candidates, then injects urgent
arrivals. Processing order was identical and no events were lost:

| Urgent arrivals | Transactions before → after | Median worker CPU before → after | Critical p95 before → after |
| --- | ---: | ---: | ---: |
| 1 | 1 → 1 | 10.3 → 8.9 ms | 1.08 → 1.40 ms |
| 32 | 32 → 3 | 27.4 → 13.3 ms | 20.1 → 4.6 ms |
| 320 | 251 → 18 | 172.1 → 51.2 ms | 174.5 → 38.8 ms |

Sparse traffic has no batching saving. The first-arrival medians were not uniformly lower:
1.08→1.40, 1.77→1.88 and 10.77→15.85 ms respectively. They include producer/event-loop scheduling;
the implementation adds no collection wait and commits that first arrival separately. The evidence
supports less burst write amplification and lower burst tail latency in this fixture, not a claim
that every event is faster. These percentages must not be combined into an app-wide speedup.

### Validation and deployment boundary

The broker/exit/route/season suite passed **154 tests**. The final urgent-persistence, interruption,
checkpoint and worker-pressure suite passed **114 tests**. New cases cover valid/stale/empty routes,
missing conversion, equal timestamps with different reserves, standalone marks, restart, failed
position writes, changing protection, duplicates, configured batch minima, transaction rollback,
repeated cancellation and parked next-season events. Ruff and strict mypy passed.

The complete backend suite passed **1,147 tests** in 138.19 seconds, with zero failures, errors or
skips. Source/test hashes remained unchanged through the full run; Ruff and strict mypy passed.
The sole warning was an upstream Starlette/AnyIO deprecation in the test client.

The packaged `signal-arcade:v1.10.7-held-burst-20260907` image has digest
`sha256:81fc10afd5645923124bbecbf2f3664b02fe9cbff0feb4dfcd42ce5563509704`.
All 38 installed backend files match the validated source; only `orchestrator.py` and
`paper/broker.py` differ from the preceding image. Installed dependencies and frontend artifacts
are identical, and schema 16 is unchanged. A network-disabled, disposable startup test passed
version, paper-only health and database initialization checks. No production volume was mounted.

The live application was updated from `v1.10.7-burst-stages-20260907` to the validated held-burst
image above at **06:47:49 UTC on 8 September**, following explicit user approval and a verified
backup. The existing season, data volume, settings and Champion/Coach permissions were preserved.
Both Sizing and Exit resumed with the same active identities and healthy monitoring. Compare several natural bursts
with similar held-position activity and due-checkpoint load after deployment. Observe critical lag,
candidate losses, recovery, checkpoint completion and training continuity; do not benchmark the
production database. Retention backlog and optional-worker opportunities still need observation.

The preceding schema-16 image is the scoped rollback target if these changes regress processing.
Do not roll back the current schema-16 database directly to v1.10.6/schema 15. Less wasted work can
help collection keep up, but cannot make an unavailable route executable or guarantee an Entry
Champion, higher coverage, profitable paper trading or issue-free long-term operation.

### Follow-up edge review

Five further cases exercise arrivals during a buffered write, a previously stored duplicate,
protection ending during persistence while due learning evidence remains protected, a handler
failure after a successful grouped commit, and future reserves reaching the combined broker path.
The expanded targeted suite passed **273 tests** in 32.36 seconds with no failures, errors or skips;
Ruff passed. No additional runtime defect was found. All 38 backend hashes still match the packaged
image above; only tests and these notes changed. The earlier 1,147-test full-suite result remains
the full-suite evidence for that runtime. No rebuild, deployment or live restart was performed in
this follow-up. Comparable natural-burst observation remains necessary after approved deployment.

### Approved deployment on 8 September

The user subsequently approved updating the live app. Before switching images, the app's upgrade
preparation completed and cancelled one unfilled paper order. The app was stopped at 06:40:36 UTC
while its data volume was archived from a read-only mount. The 2,936,271,704-byte compressed backup
passed a complete file-size and SHA-256 comparison, including the archive integrity check. This
backup and verification took approximately 410 seconds; collection was offline during the stop.
The private backup remains outside the repository.

Deployment validation completed at 06:47:49 UTC. The new container's image digest matches the
validated image above, schema remains 16, and its environment and data mount match the preceding
container. The local image pin was updated. The running preference, current season, risk profile,
automatic Champion permission and Coach research/contribution permissions were preserved. Sizing
and Exit resumed with the same active Policy identities and healthy monitoring; the paper execution
audit was verified. All seven core background workers were running. No source rebuild, settings
change, version increment or community push was performed as part of this deployment.

Six serial health observations from **06:48:05 to 06:53:05 UTC** were healthy, with all core workers
running, no degraded reasons and no candidate shedding or expiry. Processing advanced by 23,059
events. Five retained intervals from the new boot (06:47:37–06:52:49 UTC, including a partial
startup interval) recorded a maximum sampled queue of 296, overall lag of 4.79 seconds and critical
lag of 2.22 seconds. The container had no unexpected restart or OOM, and bounded startup logs
contained no worker exception.

At the final 06:54:01 UTC check, health and the paper audit remained healthy/verified. Reserve
refresh had completed 119 checkpoint updates without a worker error. The trainer was running and
idle, with four more usable outcomes required by its reported next-fit cadence; no new fit was
observed in this short window. Existing Linear and XGBoost artifacts were retained. Coach remained
enabled and healthy, yielding to market work. Storage cleanup was progressing within its budget.
Entry's operational rolling coverage was 584/1,000 (58.4%); it remained unqualified, with the 70%
requirement and independent/model-performance proof unchanged. The pre-stop rolling population
had 600/1,000 available outcomes; these are not matched cohorts and the intervening downtime must
not be treated as a controlled performance comparison.

This verifies deployment and short-run recovery. It does not establish improved training results,
Coach research throughput or sustained burst reliability. Compare naturally occurring workloads
with similar held-position activity and checkpoint demand before drawing those conclusions.
