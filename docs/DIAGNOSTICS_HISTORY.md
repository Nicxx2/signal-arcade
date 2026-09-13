# Local diagnostics history

From v1.10.8, skill interval summaries also retain the current suspension reason/time and a
compact recovery status, enrolled/resolved/usable counts and restored time when available.
These describe the saved Champion's support lifecycle, separately from the latest fitted
candidate and battle. Recovery does not represent a new crown. Individual Policy IDs and the
full recovery evidence window remain outside the diagnostics export; missing older lifecycle
fields mean unavailable history, not that a skill was never suspended.

From v1.10.9, newly finished recovery trials also retain their failed check names. Older trials
remain unknown at that level of detail. Interval summaries cover up to all 12 supported
skill/family combinations (nine currently emitted native/Coach combinations), so a new Exit
family cannot hide Sizing. Contextual Exit summaries optionally include fixed-reference coverage
and conservative uplift. These are checkpoint comparisons, not measured live P/L gains. The
named optional fields stay readable by earlier schema-1 readers; all byte limits remain unchanged.

Diagnostics supports later operational reviews and comparisons between builds. It is separate
from the paper ledger, raw market history, learning observations and Champion proof. It is not a
complete event replay and cannot establish that a model change caused better returns.

## Storage and retention

The writer owns `data/diagnostics/history.sqlite3`, its WAL/SHM files and `writer.lock`. In the
container this is `/data/diagnostics/`, inside the existing persistent data mount. Ordinary
upgrades and paper-season resets preserve it. Deleting the data volume still deletes history;
this is not an independent backup.

The separate allowance is **512 MiB**, independent of Settings' main database budget. Both use
the same physical disk. Targets are 30 days of detail (43,200 intervals), 365 days of hourly
summaries (8,760 rows), and 90 days of events (100,000 rows). Compact events have a separate
768-byte compressed record bound, so model updates do not consume the larger interval allowance.
An oversized event is omitted explicitly without discarding its valid interval. A bounded registry prevents duplicate
intervals from being counted again after detail expiry. Time and row limits apply together.

Event retention also depends on frequency: 100,000 rows hold about 50 days at 2,000 events/day,
or the full 90-day target below about 1,111/day. This is substantially more than the initial
10,000-row proposal. The actual retained interval and event timestamps determine review coverage.

The main diagnostics file is limited to 384 MiB. Incremental detail cleanup reserves 8 MiB within
that limit and checks pages still in use; reusable pages do not cause repeated deletion. Cleanup
can reclaim old detail before an insertion reaches the page limit. Writes pause around 448 MiB
of owned files, leaving transaction/recovery headroom within
512 MiB; resumption uses 416 MiB hysteresis. Low physical free space (below 512 MiB) also pauses
recording. A long reader can prevent WAL reclamation, so a page limit alone is not relied upon.
Unrelated disk writers can still fill the disk. Nominal retention is a target, not a guarantee.

Corrupt, foreign or newer schemas are not silently replaced. Unsupported storage disables the
recorder and appears in Settings. No accumulating backups or automatic directory deletions are
created. There is no automatic recovery that overwrites an unreadable store.

## Recorded information

- A fresh boot identity, interval sequence, UTC bounds and monotonic elapsed duration.
- A fingerprint of the packaged backend and built UI, plus the application version. Configuration,
  season and artifact identities are hashed; risk mode, demo/mainnet and learning mode are explicit.
- Non-overlapping received, processed, expired, shed and reordered counts from the existing
  pipeline buckets. Histograms retain counts, including a separate critical-lane distribution,
  queue peak sampled during event processing and maximum lag. A queue peak between processing
  samples can be higher. No samples means unmeasured latency, not a zero-latency result.
- Bounded duration/count/max summaries for event batches, snapshots, heartbeat work, training
  preparation/publication and storage maintenance. These identify slow phases, not a full profiler.
- v1.10.7 burst follow-up: `snapshot_cpu`, `heartbeat_cpu`, `event_persist_cpu` and
  `event_learning_cpu` measure CPU time on the worker thread executing that operation. Matching
  `_wait` phases measure executor-dispatch plus event-loop resumption delay. They do not isolate
  database lock time; a worker's remaining elapsed time can include I/O, lock contention, GIL
  waiting or scheduling. Heartbeat CPU/wait covers its main tick; the existing heartbeat duration
  also includes the subsequent season check. `market_lock_wait`, `snapshot_lock_wait` and
  `heartbeat_lock_wait` record completed acquisitions of the shared event boundary. Cancelled
  lock waiters are not completed samples. Parent/child phases overlap and must not be summed as
  independent CPU costs. Old intervals without these fields are unmeasured, not zero. These are
  fixed aggregate counters, not per-event records or an additional live database query.
- Actual training and cleanup completion records. Readiness-only checks no longer erase the
  last actual fit timing. Publication counts are distinct from retained model counts.
- Latest per-skill/family sample counts, qualification flags, numeric proof metrics and identities
  of the observed Champion, active model and contender. Unknown metrics stay unknown. Numeric
  diagnostics are rounded to six decimal places; the authoritative learning artifacts keep their
  original values. Metric slots are decoded to their full names during export.
- Previously computed conservative paper-equity samples with their own timestamps, quote currency,
  minor-unit precision, realized/unrealized P/L and excluded-position counts. Diagnostics never
  requests another valuation. Samples can be old while trading is idle; check their timestamps.
- Available app CPU/RSS samples, provider reconnect counts, Local AI queue pressure, Coach state,
  storage sizes and the recorder's own omissions. Retained Coach counts are not lifetime totals.
- v1.10.7: bounded learning-refresh counters identify requests, selected/accepted routes,
  checkpoint updates, unavailable/discarded batches, invalid routes and worker errors. Deferrals
  distinguish pending sells, market boundaries, queue/lag pressure, unhealthy sources, maintenance
  and changed context. These are cumulative counters within a boot; hourly gauges retain their
  last value. A deferral counts a blocked guard check, not a failed token or missing outcome.
  Invalid-route counts and discarded-batch counts use different units and must not be combined
  into a per-request failure rate. Older intervals lacking these fields remain unknown.
  `unavailable_route_identities` is the current size of the bounded RPC identity cache, not a
  lifetime failure count. Identity repair re-enables acquisition without altering saved outcomes.

No wallet keys, provider URLs, passwords, raw settings dictionaries, log messages, feature
matrices, model weights or per-token market histories are copied. Nothing is sent to an external
telemetry service. This information never changes a decision, training target or qualification gate.

The Entry collection follow-up adds `kind: collection`, `version: 1` events, at most two every
five minutes while the learner has collected counters. Each event names one `lane`, its five
`horizons`, the `stages` column names, and a `counts` matrix (one row per horizon, one value per
stage). Counters accumulate within a learner `scope`, beginning at `since`; a newly constructed
learner or process has a new scope. Compare differences only within the same scope and use the
event's own `at` timestamp. No mint, episode identity or provider message is included.

The scope covers the learner's retained checkpoints across risk modes, configurations and seasons;
it is not a per-context cohort. A risk or season change does not reset these counters. Do not
attribute their aggregate totals to the current context shown by an interval or use their ratios
as fitted or activation coverage. Use the saved evidence for those exact-context measurements.

Optional `collection_expiry` version-1 events provide a `last_rpc` matrix using the same lane and
horizon layout, with their own `stages` columns. These count closed expirations by the last known
RPC stage, **not the cause of the expiry**. `no_rpc_selection` means tracking began at enrollment
and no RPC selection was observed; it does not rule out cached attempts or explain a deferral.
`unknown` covers restored records, evicted tracking and missing attribution. Internal tracking
uses separate observation/episode identities and horizons, is capped at 20,000 pending checkpoint
keys, and is removed on closure. These identities are never exported. Request-local identities
prevent another trajectory for the same mint from receiving an earlier request's attribution.
Late request telemetry cannot reopen closed tracking or evidence. No per-attempt database writes
are added and the counters are never qualification inputs.

Optional `heartbeat_work` version-1 events contain `seconds_since_boot`: fixed keys `positions`,
`cache`, `expiry`, `coach`, `ai`, `profile` and `season`, each holding [count, total wall seconds,
maximum wall seconds]. They distinguish heartbeat substeps without changing their execution
order. Worker-local timings are merged only after the worker joins; partial work ending in an
error/cancellation remains measurable. The event's `scope` is the process boot identity. These
wall times can include storage waits and CPU scheduling; they do not alone prove a root cause.
They overlap existing aggregate heartbeat timings and must not be added to them.

Each extra detail series emits at most once per five minutes, only when the existing event queue
has room after core/proof events. Deferral preserves cumulative counters. Restart creates a new
scope; absent older fields mean unmeasured history. Existing payload/retention limits still apply;
more event series can shorten event retention within its fixed row budget. Guard-check counts
can increase with the faster rechecks and must not be interpreted as more lost outcomes.

If an expiry matrix grows too large for the unchanged compressed event limit, it is split into
parts with disjoint `horizons` and matching `last_rpc` rows. No counts are rounded, capped further
or omitted to make it fit. Parts have independent bounded emission cadence and can resume after
queued proof takes priority. Reconstruct each lane/horizon from its named row and timestamp;
do not add a previous whole-matrix snapshot to its later parts. Scope changes still reset the
comparison. A larger number of parts shares the existing event retention allowance.

`cache_due`/`rpc_due` count eligible checkpoint considerations at scheduling passes, and
`*_selected` count the checkpoint targets attached to selected mints. Repeated consideration or
selection can count again. `rpc_requested` and subsequent stages refer to targets selected at
request start, not unique requests or final outcome denominators. A shared mint can serve several
Policy episodes and Discovery together. RPC stages distinguish accepted/rejected validation,
invalid identities, the address cap, provider unavailability, timeout, exceptions, cancellation
during the RPC await, and post-response context/pressure discards. An accepted route can still
produce an unavailable quote, or no new checkpoint if the stream already resolved it.

`usable`, `unavailable` and `expired` count newly closed checkpoints, once, through the normal
observation/expiry paths. Restored historical checkpoints are not recounted. These counters do
not establish why an individual old checkpoint expired; saved checkpoint reasons and equivalent
mature cohorts remain necessary. The Discovery event also includes coarse `rejections_since_boot`
for RPC rejection causes; these have the existing mixed route/batch units and a boot scope.

The Policy collection event also carries `dispatch_since_boot` (`due`, `not_due`) for market
events on pending learning mints. These count decisions to dispatch or skip checkpoint work,
not observations, unique tokens, successful worker completions or provider requests.
`wait_seconds_since_boot` separates cumulative `dispatch` delay (handoff to worker start) from
`resume` delay (worker completion to event-loop continuation). The existing interval
`event_learning_wait` remains their combined measurement; do not add it to these totals. Worker
execution and database contention are not classified by these two waits. Disabled diagnostics
do not collect wait timings. Counts saturate at 2^63-1 and wait totals at 10^12 seconds.
Both dictionaries are process-scoped: compare deltas only within the same enclosing boot, even
if the learner collection scope changes. They do not enlarge the core interval or trigger I/O
per dispatch. Their event shares the existing five-minute collection cadence and proof priority.

Collection events wait if fewer than two event slots are free, preserving queued training/proof
events. Their counters survive that deferral. They use the existing background diagnostics
writer and export, with no per-attempt database write or larger record/storage allowances. About
576 additional event rows/day are possible; they share the existing 100,000-row retention cap.
Unexported detail before a restart, skipped recording and records removed by retention remain
unavailable. Recording disabled has no effect on learning, trading or qualification.

The current refresh controls already allow batches of 1–20 routes (default 20), one bounded RPC
outside the market lock, at most 100 unique accounts and an eight-second request timeout. A
smaller configured batch may lose checkpoints under sustained arrivals. Change it only through
a controlled deployment and compare equivalent mature cohorts, request duration, quota pressure,
critical lag and every horizon in both lanes. More routes per call can add response/validation
cost. A synthetic capacity gain is not a live coverage or profitability forecast.

## Cadence, gaps and comparisons

The collector aims for one interval per minute. It takes only compact in-memory facts, waits
briefly for the event boundary and defers during training, storage work or market pressure. A
dedicated background I/O thread performs compression, SQLite commits and bounded cleanup.
It uses a separate connection and queue, outside the core executor, and checks pressure again
before writing. It receives only allowlisted diagnostic facts. Queues, message
sizes, proof slots, events and filesystem usage are bounded. Recorder failure cannot stop a core
worker. Unsent data, including the final partial interval at shutdown/crash, can be lost.

Counts are not reconstructed from overlapping five-minute or hourly status windows. Hourly
rows merge interval counts and histogram buckets and retain phase maxima. Gauges and skill proof
are the **last sample**, not hourly averages. Intervals are grouped by their completion hour;
`hour_boundary` flags identify intervals crossing UTC hours. Do not call these precise calendar-hour
rates without accounting for their actual time bounds.

Boot changes, skipped records, unavailable history, long intervals and clock jumps remain explicit.
Skipped diagnostics are separate from expired or shed market events. A collection attempt that
times out waiting for the core event boundary does not consume pipeline counters; a later
interval includes them while their bounded source buckets remain available. The v1.10.7 retry
fix records this as `collection_deferred` and retries at the next five-second poll without
incrementing `dropped`. Actual collector failures still count as omissions, and long delays still
mark recording gaps. A marked gap means intermediate proof, equity and phase timing cannot be
treated as minute-by-minute samples.
Retention advancement is conservative after time jumps; row and byte bounds still apply. Nothing
backfills offline time with healthy zeroes. Context is sampled at the interval end; observed
context changes mark mixed intervals. Brief changes that reverse between samples may not be seen.
Use the main ledger and immutable proof artifacts for exact decision attribution.

The in-memory event buffer retains eight compact events between collections. A cluster of training
publications can exceed that allowance: older diagnostic detail is counted as dropped and the
interval is marked, while the saved learning artifacts remain in the main database. This is distinct
from losing market events or model publications. The `snapshot_age` gauge is the age of the on-demand
UI snapshot cache; it can rise when nobody requests a snapshot. Assess engine health using worker,
queue, critical-lag and training evidence alongside that gauge.

Compare the same risk, quote, evidence cohort and configuration, and account for traffic and
missing evidence. Merge histogram counts before estimating a percentile; the last bucket means
**over 30 seconds**, not exactly 30. Sum matching numerators and denominators instead of averaging
coverage percentages. More fits or Champions alone do not establish profitable improvement.

Phase durations include wall-clock waiting and can overlap: an event batch includes its nested
phases, while storage can run concurrently. Do not sum them as CPU usage or attribute a burst to
the browser, Coach or an active skill from overlap alone. Compare arrival rate, event mix, critical
lag and losses over equivalent intervals, and separate isolated test load from live observations.
The [v1.10.7 burst review](V1_10_7_BURST_VALIDATION.md) illustrates these limits.

## Viewing and exporting

### Shared-account validation health

The live snapshot's `event_pipeline.reserve_validation` and the health endpoint's
`reserve_validation` report four fixed components: learning/Pump curve, learning/PumpSwap,
held-position watchdog/Pump curve and watchdog/PumpSwap. Only repeated `FeeConfig`, `Global`
or `GlobalConfig` layout/extension rejections trigger this particular issue. It does not diagnose
every provider failure, unsupported token or missing route.

Three failed batches spanning at least 30 monotonic seconds raise the issue; many affected routes
in one response count as one batch. A valid snapshot on the same component clears it. Other
venues, HTTP success, empty work, pressure deferrals and rejected stale/context-changed results
do not establish recovery. `verified` describes the last accepted account validation, not a promise
that a route remains executable or that its checkpoint was usable. Existing cumulative rejection
counts count attempts, not unique missing learning outcomes.

Disabled learning refresh, learning Off, demo mode and a watchdog with no held positions do not
raise active component warnings. Their retained in-process fault state is not relabelled as
recovered. A restart begins `not_observed`; it does not backfill proof of recovery. Core `/health`
`ok` remains process liveness, so this optional component issue cannot cause a Docker restart loop.

To preserve the existing interval and event budgets, the **Policy collection event** carries a
`reserve_validation` array of four integers in the component order above. It describes both
consumers; attaching it to Policy does not change that lane's evidence or qualification scope.
With no learning collection counters, a separate `kind: reserve_validation`, `version: 1` event
carries the same array. These events share the existing five-minute cadence and yield when proof
events need the queue. The full readable component details, counts and observation times remain
in the live API; no per-request database writes are added.

Each integer is `active * 64 + state * 16 + account * 4 + reason`:

| Field | Codes |
| --- | --- |
| active | 0 inactive, 1 enabled/applicable |
| state | 0 not observed, 1 verified, 2 checking, 3 blocked |
| account | 0 none, 1 FeeConfig, 2 Global, 3 GlobalConfig |
| reason | 0 none, 1 unreviewed account extension, 2 unsupported account layout |

For example, 117 means active/blocked/FeeConfig/unreviewed extension. A missing field in older
history means unavailable, not healthy. Use the enclosing event timestamp and boot/collection
scope; the compact sample is not a cumulative failure count or a coverage denominator.

Layout rejections may include a `layout` object in the live component status: `account_bytes`,
`sample_bytes` and `sample_sha256`, plus `reviewed_bytes` and `unreviewed_bytes` when the prefix
decoded. The digest covers at most the first 4,096 bytes; `sample_bytes` makes that limit explicit.
It identifies the sampled account contents, not a verified schema version. The known layout
length can exceed a truncated account's length; the rejection still stands. No account body,
RPC URL or credential is retained. Acceptance clears only that component's sample.

A separate optional `kind: reserve_layout`, `version: 1` event contains a four-element `layouts`
array in the same component order, with nulls where no layout sample exists, and the compact
`reserve_validation` array. At most one is emitted per five minutes per learner scope. It leaves
room for both collection events and yields to queued proof; a deferred sample can retry when
space becomes available. It preserves the existing 768-byte compressed event limit. Older
records without these fields do not establish that account validation succeeded.

Settings shows actual usage, retained coverage, queue/omission counts and recorder state. It
refreshes once a minute only while mounted. Recording continues with the page closed.

`GET /api/v1/diagnostics` returns the lightweight cached recorder status.
`GET /api/v1/diagnostics/export` downloads newline-delimited JSON with metadata, retained minute
and hourly rows, compact events and an `export_complete` trailer. An instance with no recorded
store exports no rows. If cached recording status says history exists but its file is missing,
or a store present at export start disappears during paging, the export reports a file error.
Both routes use the existing authentication. Exports are limited to two concurrent requests and
100 records per database read; read connections close before each page is sent. Concurrent
retention can remove old records during an export, so it is a paged review, not an atomic backup.
An interrupted read emits `export_incomplete`; a cancelled download may lack any trailer.

Healthy recording does not guarantee a complete download: the exporter uses its own short-lived,
read-only connections. Check the final trailer before relying on an export for a later review.
In v1.10.8, SQLite busy/locked responses and the reader's own query deadline allow up to two
retries per page, after 50 ms and 150 ms, with at most six retries across the entire export.
The 20 ms SQLite lock wait and 100 ms query budget remain unchanged. The reader checks elapsed
time between rows as well as through SQLite's progress callback. When the budget expires after
complete rows have been fetched, those rows form a smaller page; the next read resumes after
its last cursor. It does not throw away useful progress simply because scheduling was slow.
If no row was fetched, the deadline remains a retryable failure and reduces the requested page
size from 100 to 50, then 25 for that download. Only fully decoded, ordered rows advance the
cursor. File/decode errors and unexpected interrupts still fail; the retry limit is unchanged.
Smaller pages can require more reads but reduce each read's work.
Backoff is asynchronous,
without a database connection or engine lock held. A cancelled read retains its export slot until
its worker finishes; it cannot create extra detached reads beyond the two-export limit.

The trailer includes `read_retries`. Incomplete exports also identify `stage` (minute, hour or
event) and a safe `reason`: `diagnostics_sqlite_busy`, `diagnostics_sqlite_locked`,
`diagnostics_query_deadline`, `diagnostics_file_error`, `diagnostics_decode_error`,
`diagnostics_schema_unsupported`, `diagnostics_store_unsafe` or `diagnostics_sqlite_error`.
Non-transient failures are not retried or repaired by the export. Completed pages remain usable,
but a partial file must not be treated as complete history. Older builds report only
`diagnostics_read_unavailable`, which cannot retrospectively identify the underlying failure.
Retries do not recover records already removed by retention or never recorded. Exporting never
changes the recorder's state, writes application records or requests a database checkpoint.

Storage pressure pausing recording does not disable exports of retained history. Validation
covered all configured row limits (151,960 records), a SQLite file within 8 KiB of its 384 MiB
page ceiling, and total owned-file usage of 512 MiB. The latter used allocated fixture padding
to exercise the directory byte guard; a healthy writer pauses earlier to preserve WAL headroom.
The download is streamed, and expanded NDJSON size is separate from the compressed storage
allowance. Physical disk failures, browser/network failures and persistent contention can still
interrupt a download. Check its trailer rather than assuming reaching the end of a file means
the export completed.

Set `SIGNAL_ARCADE_DIAGNOSTICS_ENABLED=false` and restart to disable recording. Existing diagnostic
history remains available for export. This switch and the fixed diagnostics allowance are
independent of the main storage controls. History starts when a recorder-enabled build first runs;
previous unsaved measurements cannot be recovered retroactively.

## Validation

Implementation and validation are recorded in `V1_10_5_DIAGNOSTICS_VALIDATION.md`. A long-running
observation period remains necessary before treating short controlled tests as endurance evidence.
