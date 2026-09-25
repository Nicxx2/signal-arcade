# Local diagnostics history

The latest local v1.10.11 candidate adds a bounded optional `slow_work` sample with lane
`capacity`. Its phases include `lock_wait`, `setup`, `query`, `restore`, `dispatch`,
`worker`, `cpu`, `read` and `resume`. `stage` is 0 for the initial admission read and 1 for
the final read; an early deferral never reaches the latter. `admission_deferred`,
`lock_deferred`, `setup_deferred`, `sql_busy` and `sql_interrupted` are 0/1 outcome markers,
not durations. Admission/setup deferral can mean elapsed deadline or cancellation; it does
not prove a SQLite lock conflict. Query time includes read/stat work; worker time includes
these spans and descheduling. Do not add nested durations. The slowest coherent read is
retained until optional handoff, under the existing cadence, byte caps, eight-event capacity
and proof priority. The established storage sample is unchanged. Absolute deadlines, retry
pacing and pressure guards are unchanged; this is sampled detail, not a census of deferrals.

For large event batches, persistence serialization/SQL span counts now describe bounded
statements rather than individual rows; use the persisted-event counters for row volume.
Transaction exit still refers to the whole atomic batch. Fewer SQL calls do not establish a
hard deadline on filesystem I/O or COMMIT. Compare actual builds and workloads before drawing
performance conclusions; this instrumentation adds no provider requests or trading authority.

The later v1.10.11 update adds optional fitted-cohort counts to existing proof/skill
summaries: `coverage = [schema, resolved, usable, quote_liquidity, quote_fees, quote_other,
stale_route, window_elapsed, other_missing]`, with schema 1 and a maximum denominator of 1,000.
These counts describe the artifact's primary Discovery cohort, not operational or Policy coverage.
Missing, inconsistent or unsupported metadata is omitted. Quote failure subtypes require a saved
receipt; expiry reasons do not imply recoverability. The main immutable artifact remains the
authority if diagnostics lose an event. No extra event slot, raw receipt, provider request or
retention allocation is added. Existing input/compressed-size limits and explicit loss reporting
still apply, including an interval with many summaries. Older schema-1 readers retain the optional
array without changing the indexed proof-metric layout.

The same update separates `order_lock` admission and `order_lookup` SQL work inside the
existing broker detail. Both are nested within `order_save`; do not add them to the parent time.
The decision-expression index reduces rows visited while the writer lock is held, but additional
index maintenance has a cost. Isolated lookup results do not establish live burst capacity.
These additions were deployed locally on 18 September 2026; see the
[rollout record](V1_10_11_VALIDATION.md#coverage-and-order-lookup-live-rollout--18-september-2026)
before comparing boots. Old counters reset on restart, and old artifacts have no reconstructed
breakdown; neither absence proves healthy collection.

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

The 23 September follow-up adds a reduced collection fallback after 75 seconds when detailed
collection is blocked by queue, lag, storage or training pressure. It takes only an available
event boundary and a nonblocking pipeline-counter lock, performs no database reads/writes, and
does not traverse fitted artifacts or build a dashboard. Pending sells, upgrade preparation,
invalid lag, shutdown, a busy boundary and a full interval queue still prevent it. Admission is
checked again after lock acquisition. Writer pressure guards and every byte/queue bound remain
unchanged. This can preserve interval boundaries during a short deferral; it cannot guarantee
durability or uninterrupted observation during prolonged pressure.

Reduced records have `gauges.capture_mode="essential"`, `detail_omitted=true` and an empty
`skills` list. Missing rich fields are **unobserved**, not zero or evidence of no Champions.
Detailed records keep their existing shape. Pending publication groups still drain whole and FIFO,
with original timestamps and indices; handoff is not a durability acknowledgement. Long elapsed
intervals, cursor holes and reported losses retain the existing gap flags. Hourly records retain
the latest gauge/skill sample, so an hour ending with a reduced record also has reduced detail.

The optional `retention_sample` version-1 event carries boot scope, recording `at`, successful
`capacity_at` and nullable `history_at`, live/reclaimable/WAL bytes, `oldest_trade_at` and the
configured `retention_hours`. It reads cached measurements only. Missing history is unknown;
an old successful measurement does not become fresh because the event is new. The stream shares
the existing five-minute optional cadence, eight event slots and 768-byte compressed cap, and
yields to proof. A queued sample can coalesce to the latest measurements. Reduced intervals also
carry these fields under `gauges.storage_sample`; detailed intervals do not add them to their
already tight payload budget. Compare retained-age trends only at distinct successful measurement
times and account for clock changes.

Storage phases now include `history_setup_seconds`, `history_restore_seconds` and
`history_worker_cpu_seconds`. Setup/restoration describe connection guard handling; query elapsed
still includes SQL, commit/rollback and descheduling. Worker CPU excludes scheduling/I/O waits but
is nested within total worker elapsed. Do not sum overlapping measures or label all remaining
elapsed time as disk time. A deadline expiring during setup prevents even a short delete from
starting before its first SQLite progress callback. The original cooperative budget and normal
trading timeout restoration remain in force; filesystem stalls are not hard-interruptible.

The subsequent ownership follow-up applies the post-setup admission check to maintenance reads
as well. A deferred read keeps the original measurement and timestamp. Reader timeout restoration
and lock release still run if clearing its progress handler fails; a real error stays visible.

Optional `slow_work` adds the `enrichment` lane. Each sample describes one joined preparation,
metadata application or route-verification application, excluding the provider request itself.
`enrichment_lock_wait`, the present `enrichment_prepare`/`enrichment_metadata`/`enrichment_route`
field, and `enrichment_cpu`, `enrichment_worker`, `enrichment_dispatch`, `enrichment_resume` and
`enrichment_wait` belong to that same operation. Preparation and application hold the market
boundary until their worker finishes, even on cancellation. Provider I/O holds no such boundary.
Market samples similarly add `event_candidate_cpu`, `event_candidate_worker`,
`event_candidate_dispatch`, `event_candidate_resume` and `event_candidate_wait`. These are
optional sample fields, not additional interval counters. Wait is dispatch plus resume, and
worker elapsed includes descheduling; do not add nested timings as independent CPU costs.
Training events add `reconstruct_cpu_seconds` and `fit_cpu_seconds` beside their elapsed phases.
These CPU fields measure the owning thread, not total CPU across any native library worker threads.
The existing byte limits, proof priority, optional cadence and truthful loss accounting remain.
These measurements do not change model inputs, evidence eligibility or promotion requirements.

The 21 September community-polish candidate adds optional category detail to the existing
`storage` event's `history_work` object. `at`, `chunk_rows` and `category_offset` identify the
history pass that supplied the timings, before any later adaptive chunk adjustment. Offsets
0/1/2 start with raw trades/non-entry decisions/equity in the normal three-category controller.
The next admitted pass rotates its first category under the same absolute time budget.
`categories` contains fixed names with query/lock elapsed seconds, completed-query counts,
lock timeouts and query-budget interruptions. An empty category was not reached; it is not
proof that no cleanup work remained. A zero-row successful query still counts as completed.
Query elapsed time includes commit and descheduling, not just CPU work. These category timings
belong to the last pass; the event's `removed` counts still aggregate since the preceding storage
report. Do not divide those aggregate counts by the last pass's duration. The event retains its
existing cadence, compressed byte cap and proof-priority rules. These additions were deployed
locally through Settings preparation on 21 September; older records have no reconstructed category
detail. See the [rollout limits](V1_10_11_VALIDATION.md#maintenance-polish-live-rollout--21-september-2026).

The same update measures `counts_seconds`, `oldest_trade_seconds` and `other_seconds`
in storage phases. The residual subtracts only disjoint outer sections; nested history worker,
query and lock timings must not be added again. Optional counts run after required cleanup only
when market pressure allows. Large counts use an interruptible row scan; unfinished tables keep
their last completed values and timestamps, so large-table counts may stay old during pressure.
Each refresh resumes after the last attempted table, including an interrupted one, so one large
table cannot repeatedly prevent smaller counters from refreshing. The shared budget is unchanged.
Maintenance reader locks use the original deadline. SQLite interruption remains cooperative and
does not impose a hard timeout on filesystem I/O or descheduling. A failed capacity refresh is
reported as `capacity_unknown`, never as zero usage. `capacity_checked_at` and nullable
`history_checked_at` describe successful capacity and oldest-trade measurements independently.

The 19 September idle-recovery follow-up adds optional `collector_work` and `slow_work` version-1 events.
Each stream uses a five-minute reporting cadence within the same eight slots and byte limits.
Protected proof reports retain priority. No absence or handoff proves durable storage.
These additions were deployed locally on 19 September; compare only records from a build that
contains them. Their first saved live records are described in the
[rollout record](V1_10_11_VALIDATION.md#idle-recovery-and-audit-live-rollout--19-september-2026).

`collector_work` reports fixed, boot-scoped counters for due collection attempts, collection,
lock timeout, superseded collection, stopped work and errors. `before`, `after` and `writer`
count the primary blocking reason at their respective checks: maintenance, storage, queue,
lag, invalid lag or training. Multiple checks can concern one pending interval; these are not
unique lost intervals or outcomes. Existing `collection_deferred` still counts lock timeouts
only. `wake_seconds` contains count, sum and maximum monotonic lateness relative to the
collector's planned five-second polling wake, excluding the intentional sleep. It is distinct
from collection age and writer acknowledgement age; no catch-up intervals are invented.

`slow_work` retains the worst pending operation separately for storage, heartbeat and event
persistence. The subsequent local burst follow-up also adds `market` (one processing batch)
and `snapshot` (one dashboard refresh), deployed in the 19 September burst follow-up. Its boot, sample
number, wall timestamp, monotonic start/end, elapsed time,
outcome and phase values describe that same operation. A faster pass cannot overwrite it;
ties retain the earlier sample. A later worse operation may replace a pending sample, so this
is not a complete trace. Partial/error/cancelled phases can be absent. Samples clear only
after optional recorder handoff, which is not a durability acknowledgement. In the local burst
follow-up that handoff occurs when the sample is selected for an interval, rather than merely
accepted into the optional queue. Writer or encoding
loss remains subject to the existing omission counters. Runtime status labels pending samples
accordingly. Original sample time can precede the receiving interval; do not pair it with an
unrelated interval maximum. Cumulative summaries remain separate.

The local burst follow-up starts each optional stream's cooldown at interval selection. An
accepted sample evicted before selection can therefore retry. Admission favours streams not yet
collected in their scope, then those collected least recently; it never displaces protected
proof or enlarges queues. Cumulative summaries may refresh an existing same-scope queued entry.
A queued slow sample may be replaced only by a worse sample. Status `optional_coalesced` counts
these replacements separately from losses. Old-scope reports keep their original scope and
timestamps; they are not relabelled as current. Bounded overload, encoding failures, writer
rejection and process termination can still lose unsaved evidence and must remain visible.
Optional slow-sample admission validates elapsed time against the producer's finite numeric
range before comparing queued samples. Malformed values are counted as input losses without
interrupting collection of valid optional reports or queued proof.

The new `market` sample combines phases from the same processing batch, including AI worker
CPU and executor/resume waiting, existing persistence timings, market-lock waiting and broker/
decision detail. The `snapshot` sample pairs section timings with that refresh's CPU and waiting.
Nested elapsed times overlap and include descheduling; do not sum them as CPU time. Missing
phases are unavailable, not zero. These samples add no per-trade database writes and preserve
the existing core interval payload. `runtime_work.ai_dispatch_since_boot` and recorder status
distinguish `dispatch` decisions (including conservative in-flight/legacy-clock fallbacks) from
`not_due` skips. They count dispatch decisions, not unique outcomes, successful saves or losses.

The local release reliability follow-up changes the `event_candidate` timing boundary: it now
includes Baseline size, evaluation, provenance and entry-permission preparation in one joined
worker dispatch. Older builds measured only size/evaluation in that phase. Compare total batch
elapsed time and work counts across builds; do not treat this phase's changed scope as a regression
or add its nested time to the parent total. Original measurement timestamps stay unchanged.
Provider HTTP 413 recovery uses the existing bounded telemetry and configured fallback only;
the stream fallback reason is `primary_http_413`. A recovered connection does not fill an
observation gap or turn unavailable outcomes into valid proof.

The `persist` work-detail lane separates executor dispatch, worker elapsed, event-loop resumption,
serialization, database-lock acquisition, SQL and transaction exit. Transaction exit includes
commit or rollback, rather than implying a successful commit. Nested phase times overlap worker
elapsed time and can include descheduling; they must not be summed as CPU time. Instrumentation
preserves the lock, serialization, insert, cache invalidation and transaction-exit order. Worker
detail is transferred only after the owning worker joins, including cancellation cleanup.

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

v1.10.11 adds a low-priority `runtime_work` detail event, at most once per five minutes
when a slot is available. `seconds_since_boot` maps each named component to
`[count, total_seconds, maximum_seconds]`: `snapshot_portfolio`, `snapshot_history`,
`snapshot_tokens`, `snapshot_decisions`, `snapshot_learning`, `snapshot_advisory`, `snapshot_other`, `rpc_selection_wait`, `rpc_request`,
`rpc_result_wait` and `rpc_apply`. The v1.10.11 follow-up's `snapshot_other` measures remaining
snapshot-worker assembly time after subtracting the named sections. The activity follow-up
separates token snapshots and decision lookup/compaction into `snapshot_tokens` and
`snapshot_decisions`; earlier builds include those costs in `snapshot_other`. Do not compare
the residual across those builds as if its scope were unchanged. Serialization outside the
named sections remains in the residual. It excludes HTTP JSON transport and worker
dispatch/resume; older candidate builds lack this measurement. RPC apply includes worker
dispatch/resume time; it is not a CPU-only measurement. Aborted operations may contribute
completed timing.

The activity follow-up also timestamps dashboard capture before its worker starts, so displayed
snapshot age includes assembly/dispatch time. Reuse throttling still begins at completion;
coalescing, locking, cancellation joins and authoritative trading/learning reads are unchanged.
The decision-history index fixes a sparse-lane scan, not every source of snapshot contention.

`discarded_batches_since_boot` records nonzero post-fetch safety-rejection counts by
reason. Within this versioned event, omitted reasons are zero; an absent event in older
builds means unmeasured. The existing `deferred` guard-check counts include both pre-selection
blocks and post-fetch rejections. The new discard counts identify the post-fetch subset;
do not add them to `deferred` or label all deferrals as pre-selection losses. One request
can serve several routes/checkpoints, and neither count is a recoverable-outcome
estimate. The lightweight health response also exposes `discarded_by_reason` in learning
refresh status. Context changes and pressure still reject the result.

The v1.10.11 follow-up adds `maintenance_guards_since_boot` to runtime detail. Its fixed sources
are `upgrade`, `storage` and `unspecified` (for an unattributed guard). Each has `deferred` guard
checks and `discarded` post-fetch batches. Explicit upgrade preparation takes precedence if
both flags are set. These break down the existing maintenance totals; discarded counts remain
a subset and must not be added to deferrals. Absent sources in this field mean zero;
an absent field in an older build means unmeasured.

Storage detail keeps `history_seconds` as end-to-end elapsed time. It also reports
`history_worker_seconds`, `history_lock_wait_seconds`, `history_query_seconds` and
`history_dispatch_resume_seconds`. Query time includes transaction commit/rollback while
owning the writer; these are wall-clock durations, not CPU time. `history_work` describes
completed queries, lock timeouts and budget-exhausted query interrupts in that sampled pass.
It is not a minute aggregate. Removed-row counts retain their existing interval aggregation.
The cleanup controller uses query time, not total dispatch/lock/resume delay, and never resets
the absolute cleanup deadline after waiting for the writer.

The recorder's ordinary eight-event queue gives `training`, `training_error` and `proof` priority over
other detail. It first evicts the oldest optional event; when all slots hold proof/training,
an incoming optional event is rejected. A newer proof record can still displace the oldest
protected record if direct events overflow all eight slots. Model publications now use a separate,
bounded backlog described below. The main learning database remains authoritative; the diagnostic
disk, message and ordinary event-queue budgets remain unchanged.

### Publication report backlog

The 19 September follow-up retains up to four publication groups, each containing at most one
training summary and six proof summaries. Each detached input report is limited to 2,048 bytes:
at most 56 KiB of serialized protected input, plus bounded Python object overhead. Admission
performs no I/O, takes no new lock, and cannot delay model publication for a writer or collection.

Collection takes whole groups in FIFO order up to seven protected records, leaving at least one
of the unchanged eight writer slots for ordinary events. Ordinary training errors take priority
over optional detail in that remainder; unselected ordinary events remain in their bounded queue.
The regular cadence, early-collection conditions and pressure guards remain unchanged. This
absorbs short publication bursts, not unlimited sustained overload. A fifth pending group evicts
the oldest whole group and counts every displaced report by kind through `event_capacity`.
Malformed proof input leaves valid siblings intact and increments `event_input` for that proof.

Each new report has `publication: [group_id, zero_based_index, expected_count]`. Group IDs are
boot-scoped hashes, independent of model authority. Missing indices show an incomplete group.
The report's original `at` remains its creation time; `collected_at` is its eventual interval
collection time, **not** acknowledgement of a durable write. Event cursors and retention still
use the containing interval's end time. Paged consumers must use the cursor for traversal and
the original `at` for publication chronology. A report may describe an older configuration or
season than the interval that finally carries it; use its group-linked training context and
authoritative saved artifact for exact attribution. Do not infer its season from the later interval.

Recorder status includes `publication_backlog` with pending groups/events, capacity, monotonic
oldest age and `pending_collection`/`empty`. An empty backlog can mean reports were handed to the
bounded interval queue, not saved. Check writer state, queue/loss counters and persisted records;
acknowledgement time alone is insufficient because a rejected write is also acknowledged.
Interval encoding failures, writer rejection and compression omissions retain their separate
existing accounting. A process crash or shutdown may lose unsent reports; this buffer adds no
crash-durability guarantee and never reconstructs missing intervals as healthy observations.

### Admitted RPC selection samples

`collection_selection` events are optional latest-pass snapshots emitted separately for Discovery
and Policy through the existing five-minute detail cadence. They are sampled at most once per
monotonic minute, only while an existing RPC selection pass is admitted and diagnostics are
enabled. A new tracker scope can sample immediately. Selection events yield to the existing
loss and work-detail reports; a full queue defers them without displacing proof. There is no additional
scan while guards block selection, provider request, database query or identifier export.

`sampled_at` and scope-local `pass` identify the measurement, not every RPC pass; `at` is its later diagnostic
emission time. Samples can be old after pressure, and omitted samples are not evidence of an
empty backlog. `counts` has five horizon rows and named columns in `reasons`: `eligible`,
`fresh_cache`, `excluded_identity`, `missing_state`, `expired`. These are disjoint classifications
of unresolved checkpoints already due in that pass. Future and closed checkpoints are excluded.
Expired windows take precedence, then excluded identity, missing state and fresh cache. These
counts are repeated considerations, not unique historic losses or finalized outcomes.

`clock_unclassified` counts already-excluded pending trajectories with unresolved work whose
clock cannot be compared with the sampling time. This is a trajectory count, not a checkpoint
count or an expiry. It is separate from the due-checkpoint matrix: those clocks cannot honestly
be labelled due, expired or healthy. Future excluded clocks are safely recognized without adding
horizons to an extreme date. Sampling never repairs clocks, enrolls these rows or changes
selection. Older reports without this field did not measure it.

Join lane samples only when their `scope` and `pass` match. Queue pressure can defer one lane
until a newer sample is available; unmatched lanes must not be combined as a single pass.

`routes` contains eligible unique mints with <=5 seconds, (5,15] seconds and >15 seconds remaining,
followed by selected unique mints in that lane. Each lane uses its own earliest eligible clock;
a shared mint counts in both lane reports but is requested once. `budget` is the configured cap,
globally deduplicated eligible mints, and scheduler selections before account/address validation.
It is not the count of successful requests or usable outcomes. Existing request/result diagnostics
provide those later stages. Neither this telemetry nor a priority retry extends a deadline.

The local provider follow-up adds `selected_bands` and `unselected_bands`, each using the same
three deadline bands and original lane clocks as `routes`. Their elementwise sum equals that
lane's eligible bands for the same pass. A shared mint can occur in both lane reports and still
consume one request route. These are sampled opportunities, not unique lost or recoverable
outcomes. Missing/null fields in older or incomplete reports mean unmeasured. `guard_context`
is `preselection_passed` only when the caller checked its admission guards; `not_reported`
does not imply a pass. It does not describe guards at response/application time. Pair lanes only
with matching scope, pass **and sampled_at**, and keep post-fetch discards within guard deferrals.

### Bounded provider reports (local follow-up)

Optional `provider_health` events have `http` or `ws` lanes and a new random scope whenever that
provider is explicitly reconfigured. Counters describe the current configuration scope, not the
entire application lifetime. Already collected old-scope events remain historical; unsaved
in-flight detail from a replaced scope may be unavailable. No-operation providers emit no report.
Reports use the existing five-minute optional cadence, eight-event limit and 768-byte compressed
event cap. They yield to training/proof and can be delayed or absent under pressure. They add no
database calls, provider requests or training inputs. Older readers can ignore these additive events.

`counts` separates logical `batch` calls, endpoint `attempt`s, protocol `response`s, `transport`,
`http`, `rpc`, `malformed`, `cancelled`, `cooldown`, `quota`, `context_changed`, `subscription`,
`close` and `other`. Attempts can include primary and fallback within one batch. The fixed
`http_codes` breakdown is a subset of HTTP failures, not another loss total. `last_attempt` and
`last_response` contain timestamps with safe endpoint roles and operation categories. HTTP response
means a non-error JSON envelope with a successful HTTP status, and WS response
means both subscriptions acknowledged. Neither proves a validated mark, usable outcome or fresh
feed. Use collection acceptance/checkpoint and position validation evidence for those questions.

`last_failure` retains only a timestamp, finite category, bounded numeric code, primary/fallback
role (or unknown for cancellation/context changes before dispatch), allowlisted operation and
bounded retry seconds. Obsolete fallback responses retain their fallback role in the old scope;
they do not contaminate the replacement scope. A failure can remain older than a later success.
No exception prose, URLs (including hostname/path), headers, payloads or account identities are
saved. Unknown/malformed codes remain null. Counter saturation is 2^53−1. WS health/log error text
uses the same safe categories. A caught watchdog exception is described as a failed attempt,
not a confirmed recovery. Diagnostic reporting failure cannot change a provider result.
This follow-up was deployed locally through Settings preparation on 19 September; see the
[rollout record](V1_10_11_VALIDATION.md#provider-recovery-live-rollout--19-september-2026).

### Diagnostic loss detail

`loss_since_boot` in recorder status provides fixed counters. After a loss, a low-priority
`diagnostic_loss` detail event records the same `counts_since_boot` at most once per five minutes
when a slot is available, scoped to the process boot. Separate detail avoids enlarging the
already-tight interval payload. Its counters are `event_input` (encoding/size rejection),
`event_capacity` (input-event eviction/rejection), `interval_input` (whole-interval encoding/size
rejection), `interval_queue`
(whole-interval eviction), and `writer_intervals` (whole intervals rejected by the writer).
The post-burst candidate adds `collector_error` and `reporting_error` for failed collection or
reporting attempts. These exception counts are not exact missing-event counts: one interrupted
reporting attempt can omit several records. They use the same saturation and recording-gap rules.
`event_categories` breaks down only the two input-event counters into training, proof, storage
and other; do not add it to the reason totals. Counts are cumulative boot samples, not sums
across intervals. A loss during collection is reported in a subsequent successfully captured
sample. The recorder uses one captured writer-loss count for its gap flag, saved gauge and
comparison with the next interval, so a concurrent rejection cannot silently advance that
comparison without a gap flag.
The optional `other_event_kinds` map further breaks down `event_categories.other` into a fixed
allowlist: collection, collection_expiry, collection_selection, reserve_validation,
reserve_layout, diagnostic_loss, heartbeat_work, runtime_work, work_detail, collector_work,
slow_work, provider_health, and unknown. Only nonzero values are emitted; arbitrary identifiers and malformed
kinds map to unknown. Counters saturate independently at 2^53−1 and reset per boot. These are
input-event rejection/eviction counts, not additional losses, exact loss timestamps, unique
lost outcomes or compression omissions. Older records without this field have unmeasured
type detail, not a known zero. The map uses the existing status and optional diagnostic_loss
event; no new event series, interval fields, queue slots or recording cadence are introduced.
This breakdown was deployed locally with the 19 September learning presentation polish; see
the [build and rollout checks](V1_10_11_VALIDATION.md#learning-presentationdiagnostic-polish-live-rollout--19-september-2026).
The first short live sample had zero reported losses, so it did not exercise this breakdown
under live overload; controlled rejection/eviction checks are separate evidence.
Existing `dropped` is a mixed-unit legacy aggregate. Per-event compression omissions in an
otherwise accepted interval remain separate `omitted_events`/`event_omitted` values and are
not included in these recorder counters or `writer_intervals`. Neither a missing interval
nor a diagnostic gap is evidence of healthy operation.

Counts and timing reset with the process boot. Optional detail yields to queued proof and
collection events, retains cumulative values while deferred, and shares existing event
retention. During a continuous boot, five-minute spacing limits each detail series to 288 rows
per 24 hours; process restarts reset its cadence and can add initial emissions. Existing
interval phase, payload, queue and disk limits are unchanged; nothing backfills gaps
with healthy samples.

The collector aims for one interval per minute. It takes only compact in-memory facts, waits
briefly for the event boundary and normally defers during training, storage work or market pressure. A
dedicated background I/O thread performs compression, SQLite commits and bounded cleanup.
It uses a separate connection and queue, outside the core executor, and checks pressure again
before writing. It receives only allowlisted diagnostic facts. Queues, message
sizes, proof slots, events and filesystem usage are bounded. Recorder failure cannot stop a core
worker. Unsent data, including the final partial interval at shutdown/crash, can be lost.

The post-burst candidate also permits a compact collection immediately before an admitted valid
publication if its upcoming reports would displace protected events. It must be within five
seconds of the shared monotonic deadline or overdue, at least 55 and no more than 90 seconds
after the previous collection, with handoff space and a running writer in the recording state.
The ordinary queue/lag/storage checks still apply, and pending sells skip this extra work.
An early collection consumes the upcoming minute slot; late collections reset without catch-up
bursts. The regular loop rechecks both pressure and deadline after acquiring the event lock.
The publication then rechecks its own validity and admission. No disk operation is added inside
that boundary. A longer backlog remains the regular collector's responsibility.

This preserves the two observed repeated-publication timing patterns when admission permits;
the bounded publication backlog additionally absorbs short delays outside that admission window.
It does not guarantee lossless history. Sustained overload, unavailable writers,
encoding faults and full queues retain honest loss accounting. Preserving formerly lost proof
events consumes more of the existing event-row allowance, without increasing interval cadence.

### Local worker detail

`work_detail` events contain `lane` (`broker`, `decision` or `rpc`), process-boot `scope`, and
`seconds_since_boot`. Each fixed operation maps to `[call_count, total_seconds, maximum_seconds]`.
Aggregation occurs on the event-loop owner only after its worker finishes, including repeated
cancellation or failure. The worker's context is private and measurements never become model inputs.

| Lane | Measurements and scope |
|---|---|
| `broker` | Market-event broker updates and candidate submissions: `broker_mark`, `broker_assess`, `broker_orders`, `position_save`, `order_save`, `fill_save`, plus `broker_dispatch`/`broker_resume`. Other broker callers, including heartbeat work, are outside this detail series. |
| `decision` | Candidate decision writes: `decision_serialize`, `decision_lock` (acquisition), `decision_sql` (including strategy participation), `decision_commit` (transaction exit, including rollback/no-op exits), plus dispatch/resume. Serialization and cache publication retain their original transaction/lock boundaries. |
| `rpc` | Accepted result-application attempts: `rpc_validate`, `rpc_observe`, `checkpoint_persist`, `checkpoint_govern`, `checkpoint_prune`, plus dispatch/resume. Validation counts include rejected routes; observation counts include calls that produce no checkpoint. Persistence counts observation/Policy record saves, not distinct usable outcomes. |

Each series exports at most once per five minutes when optional event slots allow. Fields absent
before measurement started mean unmeasured, not zero. Durations include time the worker was
descheduled; they are not pure CPU costs or latency percentiles. Nested operations overlap:
position saves are inside broker work, and persistence/governance are inside RPC observation.
Do not add parent and child times together. Failed calls are included; whole-batch dispatch counts
have a different denominator from routes, database saves and checkpoint changes.

The three series can add up to 864 event rows/day during a continuous boot and share the existing
100,000-row event and 512 MiB disk budgets. They yield to proof and collection detail; retained
history is determined by its actual timestamps. Payload limits remain 2,048 bytes of event input
and 768 compressed bytes per event, with eight input events and four queued intervals. No
per-operation database writes, raw account identifiers, additional RPC requests or new trading
authority are introduced. A synthetic timing comparison does not establish live burst capacity.

### Interval aggregation and gaps

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

The ordinary in-memory event buffer retains eight compact events; the separate publication
backlog retains up to four bounded groups. Sustained pressure can still exceed those allowances:
older diagnostic detail is counted as dropped and the interval is marked, while the saved
learning artifacts remain in the main database. This is distinct
from losing market events or model publications. In the local community-polish candidate,
`snapshot_age` measures from the on-demand UI snapshot's capture time, including assembly,
matching the UI's age semantics. Earlier builds measured from cache completion, excluding assembly.
Invalidation does not rewrite the capture time; absent snapshots remain unavailable. The age can
rise when nobody requests a snapshot. Assess engine health using worker,
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

The final reliability follow-up keeps diagnostic byte limits and proof priority unchanged.
History cleanup reports `category_rows`, the per-category limits actually used, alongside the
existing pass ceiling `chunk_rows`. Its category timings include `query_busy` (SQLite contention)
and `query_budget_seconds` (cooperative time remaining when SQL began). Neither is a lost outcome.
Categories adjust independently; an exhausted late-admitted query does not automatically imply
its batch is oversized. Query elapsed time still includes commit and descheduling. The snapshot's
maintenance `history_chunk_rows` gives the next limits; match the saved pass's own timestamps and
limits when interpreting historical timings.

Optional `work_detail` lane `equity` contains cumulative `broker_equity`, `broker_snapshot`,
`setting_read_lock`, `ledger_read_lock`, `equity_save`, `equity_write_lock` and `equity_commit`
triples. They are collected only from an already joined broker worker, separately from its other
timings so worst-case values fit the existing event cap. An optional `slow_work` lane `broker`
keeps one worst pending joined operation with its own outcome, scope, clocks and component times.
This sample links equity and order work in the same operation; cumulative maxima alone cannot
establish that two slow measurements occurred together. Nested times overlap and include waits;
do not sum them as CPU usage. No extra valuation, database query or execution permission is added.
Collection remains guarded under pressure; recording gaps remain explicit rather than being
filled with zeros or hidden by a raised threshold. These additions do not prove burst recovery.

The enrollment-activity follow-up, deployed locally on 20 September, adds
`activity_capture_since_boot` to an existing optional collection event. It contains bounded
aggregate dimensions: `attempted`, `persisted_complete`, `persisted_partial`,
`persisted_unavailable`, `skipped_existing`, `invalid_capture`, `optional_sql_failed` and
`parent_failed` when observed. Persisted counts are acknowledged only after the parent transaction
commits. An unavailable record is an explicit failed measurement, not usable research evidence;
these are cumulative process counters, not a count of currently retained rows. Collection event
cadence, optional-event limits and reset-at-boot semantics remain unchanged. No event per lesson,
new publication group or per-token history is introduced. Existing diagnostic loss reporting still
applies; an unsaved counter snapshot is not durable evidence. See
[the enrollment contract](ACTIVITY_EVALUATION.md#durable-enrollment-evidence).

The configurable coverage setting adds `coverage_required_percent` and
`coverage_policy_revision` to interval gauges. These describe the current selection, not every
saved artifact's requirement. New policy-tagged proof events include `coverage_policy` with
`percent`, `revision` and `fresh_validation`; these belong to that exact fitted generation.
Older untagged artifacts retain the legacy 70% contract. Coach keeps its separate 70% requirement.
Missing diagnostic fields remain unavailable observations, never evidence that a threshold was
met. These additions use existing records and budgets and create no new polling or event type.
These fields were verified in saved intervals after the local 19 September deployment; see the
[rollout record](V1_10_11_VALIDATION.md#configurable-coverage-live-rollout--19-september-2026).

Implementation and validation are recorded in `V1_10_5_DIAGNOSTICS_VALIDATION.md`. A long-running
observation period remains necessary before treating short controlled tests as endurance evidence.

The contention follow-up adds two fixed optional `work_detail` lanes: `candidate` separates
reference sizing, policy evaluation, bounded sizing, entry permission, valuation and read costs;
`governance` separates model health, tournaments, retraining requests, skill governance, Policy
selection, skill health, join evidence and training-row selection. `ledger_read_sql` distinguishes
the account query from reader-lock admission. Candidate, event-learning and heartbeat workers
export only after joining; RPC workers split their governance detail into the same bounded lane.
Disabled diagnostics adds no query or retained timing map. Empty governance handoffs are omitted.
Nested elapsed totals overlap and include descheduling; they are not additive CPU time. Existing
optional collection caps, proof priority, pressure guards and honest loss reporting are unchanged.

The optional-cleanup follow-up adds `writer_wait` to recorder status and a separate optional
`collector_work` lane `writer`. Its fixed reasons are `admission`, `market_yield`, `storage`,
`maintenance`, `training` and the fallback `guard`. `episodes_since_boot` counts transitions into
a wait reason; `seconds_since_boot` includes the current unfinished wait, and
`reason_age_seconds` describes that reason's current episode. These are sampled writer-thread
waits, not lost outcomes, collector deferral counts, SQLite write time or additive CPU time.
The explanation is sampled after permission is denied, so a changing guard can produce `guard`;
it never grants write permission. A retained market-yield flag is reported without clearing it.
Status reads take a short in-memory lock and perform no database or provider I/O. The optional
saved lane shares existing cadence, byte limits and proof priority; unsaved waits remain unsaved.

Storage maintenance status adds `optional_history` with at most one latest attempt per category:
`incidents` and `ai_assessments`. Each reports attempt/completion timestamps, committed `removed`
rows, `completed`, `deferred`, `work_remaining` and lock/query/setup/restore/worker timings.
A deferred attempt is not a completed empty table. A full batch conservatively requests another
attempt. The cleanup retains the newest 2,000 resolved incidents and 5,000 resolved AI assessments
using the preceding ordering and tie behavior; unresolved records are excluded from deletion.
One transaction selects at most 50 deletions with a 50 ms cooperative budget beginning before
executor dispatch. Attempts are at least five seconds apart and rotate due categories; a completed
short batch is checked again after at least 60 seconds. Market pressure may defer them longer.
Quiet-stream optional retries yield to in-flight learning reserve requests and do not rerun
primary retention/capacity work. A yielded retry is not a new completed cleanup attempt.
Scheduling, filesystem I/O and rollback/restoration can exceed a cooperative budget; worker ownership is retained until
the worker exits. A partial resolved-incident index avoids a repeated sort; it has a small storage
and resolved-incident write cost and is built on startup. No learning/proof cohort or policy changes.

Coherent `slow_work` storage samples distinguish `optional_incidents_seconds` and
`optional_ai_assessments_seconds`, with nested `optional_lock_wait_seconds`,
`optional_query_seconds` and `optional_dispatch_resume_seconds`. Do not add these nested values
to `optional_history_seconds`. Ordinary optional attempts do not imply a primary cleanup completed.

The assessment/retention attribution follow-up adds optional coherent market measurements for
`event_features_cpu`, `event_assess` and `event_assess_cpu`. These are synchronous sections;
CPU uses the executing thread's clock. Existing interval phase fields and size limits remain
unchanged. Capacity reads distinguish dispatch, worker elapsed, worker CPU, the read callback
and event-loop resume delay, for both before/after reads. The callback includes SQL and filesystem
stat work; worker elapsed also includes reader admission/setup and descheduling. Neither is an
isolated disk-latency or fsync measurement.

Cleanup timing separates `execute_seconds`, `execute_cpu_seconds` and
`transaction_exit_seconds` within the existing `query_seconds`. Transaction exit may include
commit, rollback and descheduling. `committed_rows` increments only after successful exit.
Coherent storage samples retain these totals; a normal storage event uses compact
`history_work.cost_v1` rows in raw-trade, non-entry-decision, equity order. Each row contains
execution wall seconds, execution CPU seconds, transaction-exit seconds and committed rows,
and shares the original history attempt timestamp/scope. Optional detail can still be omitted
under pressure; missing fields are not zero-cost observations. These nested timings overlap and
must not be added as independent CPU time. No extra queries, provider calls or record capacity
are introduced for these measurements.
