# Local diagnostics history

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

Settings shows actual usage, retained coverage, queue/omission counts and recorder state. It
refreshes once a minute only while mounted. Recording continues with the page closed.

`GET /api/v1/diagnostics` returns the lightweight cached recorder status.
`GET /api/v1/diagnostics/export` downloads newline-delimited JSON with metadata, retained minute
and hourly rows, compact events and an `export_complete` trailer. Missing stores export no rows.
Both routes use the existing authentication. Exports are limited to two concurrent requests and
100 records per database read; read connections close before each page is sent. Concurrent
retention can remove old records during an export, so it is a paged review, not an atomic backup.
An interrupted read emits `export_incomplete`; a cancelled download may lack any trailer.

Set `SIGNAL_ARCADE_DIAGNOSTICS_ENABLED=false` and restart to disable recording. Existing diagnostic
history remains available for export. This switch and the fixed diagnostics allowance are
independent of the main storage controls. History starts when a recorder-enabled build first runs;
previous unsaved measurements cannot be recovered retroactively.

## Validation

Implementation and validation are recorded in `V1_10_5_DIAGNOSTICS_VALIDATION.md`. A long-running
observation period remains necessary before treating short controlled tests as endurance evidence.
