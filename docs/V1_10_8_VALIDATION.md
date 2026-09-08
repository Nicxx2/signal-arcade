# v1.10.8 validation

This release addresses reproduced Coach lifecycle and fee-consistency defects and reduces
demonstrated repeated work. It retains schema 16 and all existing Baseline, permission,
coverage, chronology and independent-proof requirements.

## Scope and safeguards

- Verified zero fees remain zero in new learning evidence; unknown fees retain the fallback.
  Execution receipts identify the same fee source that their calculations used. Historical
  observations are not rewritten or retrospectively rescored.
- Coach workers remain owned until they finish, including repeated cancellation. Conditional
  database updates and individual cache merges preserve newer contribution transitions.
- An indexed 25-row page rotates through retained forward work independently of the 100-item
  recent display history. Exact-contract lookups find active studies and ready contributions
  outside that display window. One bounded contribution attempt remains separate from research;
  a persisted cursor gives waiting studies fair retries across restarts.
- Optional heartbeat contribution lookups defer when the shared reader is busy. SQLite busy/locked
  responses are retried later; unrelated database errors remain visible.
- Inference backoff skips history collection only when there is no forward study to monitor.
  Forward evaluation yields cooperatively under pressure, preserving complete saved evidence.
- Dashboard Policy selection is reused only within one response and thread. Tournament selection
  is reused only within one pass and is cleared following promotion. Health and qualification
  results are recomputed; no cache survives into the next response or tournament pass.
- A bounded 256-entry persistence memo skips unchanged skill state. Pending versions, Champion
  history and replay work still force required writes. Entries are recorded only after success,
  and publication boundaries clear the memo. Replay acknowledgements wait for transaction commit.

The dashboard's market lock, urgent-event ordering and protected-position scheduling rules remain
unchanged. This release does not increase queues, suppress loss reporting or lower the 70% gate.

## Isolated comparisons

Three alternating before/after pairs used the original methods from v1.10.7 and a deterministic
fixture of 1,000 Policy episodes, two tournaments and 20 resolved shared outcomes. Each run used
one CPU, a 2 GiB limit, no network and no production data mount. Each measured phase performed
six calls; timing excludes the warm-up call. Instrumented profiling calls are included in the
sample set, so these medians are component comparisons rather than a benchmark of live throughput.

| Component | v1.10.7 | v1.10.8 |
| --- | ---: | ---: |
| Tournament median wall time | 26.3 ms | 14.4 ms |
| Tournament median thread CPU | 21.4 ms | 14.4 ms |
| Tournament write-related SQL statements over six calls | 50 | 10 |
| Learning-status median wall time | 30.5 ms | 19.6 ms |
| Learning-status median thread CPU | 30.5 ms | 19.6 ms |

Tournament state digests and the compared coverage, evidence-lane, scorecard, qualification,
active-health and hold-validation fields were identical. The fixture demonstrates less repeated
work; it does not establish an app-wide speedup or prove that every natural burst will recover
faster. The older diagnostics also showed expiry intervals without dashboard activity.

## Regression checks

The staged checks cover verified/unknown/nonzero fees, buy/sell receipts, sizing trials, double
cancellation, worker exceptions, concurrent handoffs, rollback/retry, replay history, more than
100 retained studies, malformed rows, equal-time pagination, exact dependency identity, permission
boundaries, pressure recovery, cache eviction, restart, Policy identity and Linear/XGBoost separation.

Initial deployment validation passed **1,188 backend tests** and **355 frontend tests**, with no failed or skipped
tests. Ruff lint and exact formatting checks, strict mypy, frontend lint, TypeScript and the
production frontend build passed. Existing warnings concern a dependency deprecation, React fast
refresh exports and bundle size; they were not suppressed.

The production image contains the exact tested backend files and compiled frontend assets. Its
runtime dependencies match the backend test environment and the preceding live image; only the
application package version changes. Audits of those installed backend dependencies and the locked
production frontend dependencies reported no known vulnerabilities. Offline startup with disposable
data passed with all background workers running and the database healthy.

An intermediate full-suite rerun lacked temporary-disk headroom after repeated fixture retention.
After clearing only isolated test fixtures, the unchanged diagnostics-storage checks and complete
suite passed. A Docker-command timeout during the first startup probe was also retried with a
bounded startup allowance. Neither case required relaxing an application safeguard.

The final source review caught and reproduced a missing migration-table lookup that prevented
the Coach work index from being installed. The corrected migration passes fresh/reopen,
query-plan and legacy-without-Coach tests, plus 100 focused checks and the complete backend suite.

The first live attempt was rolled back when the startup window expired. The previous v1.10.7
image then also required about 3 minutes 46 seconds to restore the same retained dataset before
its HTTP service became ready; all seven workers recovered. The deployment check was shorter
than that observed baseline startup. A retry uses a bounded ten-minute startup allowance while
retaining the healthy-worker, accounting, settings and image-verification requirements. No
application health or qualification threshold was relaxed. The cost of restoring a large retained
dataset deserves separate measurement; this observation does not establish its exact cause.

The final image (`sha256:488da8a6788bf21b85c84e0000fbaa73abacd6e93fcb3565ca1bf8d41fcde9f8`)
was accepted at **13:02:47 UTC on 8 September 2026**. Both attempts used independently verified
stopped-volume backups, approximately 3.0 GB compressed each, outside the repository. A tested
compressed-output cap preserved host-disk headroom and would abort the upgrade if exceeded.
The season, risk profile, settings, permissions and data volume were preserved. The final image
and live Coach index/query plan were verified. No push or public deployment was performed.

From **13:03:24 to 13:08:24 UTC**, six serial health samples remained healthy. The app processed
48,676 events, received 49,302 and made 51 additional reserve-refresh checkpoint updates, with
zero candidate shedding or expiry. One training publication completed on the new build; retained
diagnostics contain its Linear and XGBoost generations. There were no training/refresh-worker
errors, container restarts or OOM events. Four complete retained intervals within this window
peaked at queue depth 298, overall lag 1.45 seconds and critical lag 0.35 seconds. The initial
partial startup interval had higher lag and is not included in those four-interval maxima.

A subsequent busier interval peaked at queue depth **2,460/10,000**, overall lag **10.89 seconds**
and critical lag up to **2.68 seconds** across the adjacent retained intervals. No events were
shed or expired. By 13:10:44 the queue was 22 and critical lag was 0.058 seconds. Further serial
samples remained healthy through 13:12:14, with zero losses. Snapshot and storage work overlapped
the rise; this observation does not isolate their causal contributions or prove that larger bursts
are solved. Live traffic and startup conditions are not equivalent to previous peak-load intervals.

The final learning assessment used a fresh snapshot (age 1.06 seconds), because an idle dashboard
cache can be older than the health response. Sizing and Exit remained active with healthy monitoring,
and paper accounting was verified. Entry remained unqualified at 409/1,000 available outcomes in
the current view; the latest fitted generations reported 39.4% availability. These are distinct
populations, and the 70% and independent-performance gates remain unchanged. Coach's worker and
permissions were intact, with no error; it was waiting for outcomes or yielding to market work.
This short check does not prove a completed Coach study or improved trading returns. Logs also
contained rejected WebSocket attempts alongside accepted connections; authentication/origin rules
were unchanged, and the rejected clients were not identified.

Host storage needs attention before extended unattended operation: the final check found roughly
1.3 GB free on C: and 9.4 GB on E:. Docker's reported filesystem capacity is not the host drive's
remaining physical capacity. Existing data and backups were retained; review host storage separately.

## Follow-up edge review, 8 September 2026

A further source review found two accidentally corrupted Unicode strings in the orchestrator:
the bullet-removal pattern for local explanations and the stopped-engine status message.
A new regression test reproduced the bullet failure before both strings were restored to their
v1.10.7 values. The review found no other newly corrupted strings in the changed tracked files.
These corrections do not change trading, qualification, fees, permissions or scheduling.

After the correction, **227 focused tests passed**, covering AI explanations, Coach recovery and
pressure, fee consistency, persistence rollback, Policy identity and cache scope, skill activation
health, market transactions and urgent persistence. Ruff lint, exact formatting and diff checks
passed. The earlier complete 1,188-test result refers to the preceding source; the only subsequent
Python changes are these two restored strings and three parametrized regression cases. Frontend
and dependency inputs remain unchanged. The live image listed above has not been restarted for
these local text corrections.

Longer observation found a further burst in the retained interval **13:14:55-13:16:31 UTC**:
29,162 events were enqueued, queue depth peaked at **7,126**, overall lag at **20.16 seconds** and
critical lag at **3.97 seconds**. There were **1,447 expired candidate events** and zero shed
events. All workers remained healthy and subsequent retained intervals through 13:21:06 recorded
no additional expiry. This burst preceded the focused test run, which began at 13:20:32, and the
burst interval recorded no dashboard snapshot work. These observations do not isolate its cause;
isolated tests still share the host and can affect concurrent performance measurements.

A fresh snapshot at **13:23:28 UTC** had age 2.10 seconds, verified paper accounting, healthy
active Sizing and Exit, and no Coach worker error. Entry remained unqualified at 409/1,000 current
available outcomes, with the 70% requirement intact. The following health response reported queue
depth 8, overall lag 0.23 seconds and critical lag 0.041 seconds, with the expiry total unchanged
at 1,447. No restart or OOM was observed. Recovery is demonstrated; sustained burst performance
is not cleared by this review, and no speculative performance change was made.

## Release-file check, 8 September 2026

The complete backend checks were rerun after the two text corrections: **1,191 tests passed**,
with no failures, errors or skips. Ruff lint, exact formatting and strict mypy passed. Source
hashes were unchanged during validation. Frontend inputs still match the previously tested
355-test build; frontend and dependency checks were not needlessly repeated.

Backend, Python packaging, both JavaScript packages, Docker metadata and the README agree on
**1.10.8**. All 35 local README file/image/anchor references resolve. Its Docker Hub Compose
example validates offline, pins the intended `nicxx2/signal-arcade:1.10.8` release and matches
the repository's service protections and defaults. The example intentionally omits source-build
and optional environment overrides; its host port uses Docker's default binding rather than
the source stack's explicit `0.0.0.0`. No image was pulled or service started by this check.

The README now explicitly describes remaining candidate expiry during bursts, host-disk
monitoring and compatible schema-16 code rollback. It no longer implies that all durable
storage has a fixed upper bound. Existing screenshots remain accurately labelled as v1.10.7
captures, and previous screenshot folders are preserved. No further runtime code was changed
in this release-file check, and no commit, push or deployment was performed.

At **13:31:05 UTC**, a fresh live snapshot (age 0.86 seconds) again showed verified paper
accounting, healthy active Sizing and Exit, and a running Coach worker without an error. Current
Entry availability was 418/1,000, still below the unchanged 70% requirement. Between the bounded
health readings at 13:26:13 and 13:31:05, the app received 85,956 additional events, completed two
more training publications and made 59 additional checkpoint updates. No additional candidate
expiry or shedding was recorded; the cumulative expiry count remained 1,447. The final queue
was 1,954 and critical lag 2.63 seconds. All workers were running, with no restart or OOM.
The test container was removed before the final snapshot, but tests shared the host during
part of this interval. This is continued-operation evidence, not a controlled performance
comparison or resolution of the earlier burst limitation.

## Diagnostics export follow-up

A retained v1.10.7 export on **2026-09-08 at 13:37:24 UTC** stopped after 2,200 minute rows
with `diagnostics_read_unavailable`. The preceding recorder status was healthy, with 2,621
minute and 54 hourly rows, no recorder error and no dropped diagnostic records. The download
ended after 5.47 seconds and 10,854,857 bytes, below its client limits. This establishes an export
failure, but the generic old trailer does not reveal its original SQLite or decoding exception.

Source inspection confirmed that a single detached read failure ended the export without retry.
The reader used a 20 ms SQLite lock wait and a 100 ms query deadline, while recording used its
own connection. An isolated exclusive WAL owner reproduced the exact zero-row generic failure
with `SQLITE_BUSY`; clearing that lock restored a complete export. Query-plan inspection used
the existing `interval_time` keyset index. No query, index, retention or recording change was needed.

The fix retains those read budgets and adds two asynchronous retries per page (50 ms and
150 ms backoff), capped at six retries per download. Only busy/locked errors and this reader's
own query deadline are retried. Connections close before decoding, streaming and backoff.
Cancellation retains the two-export concurrency slot until its actual read worker finishes.
Failure trailers now identify the stage, safe error category and retry count; successful trailers
also report retry count. There is no database migration or change to trading, learning,
Champion permissions, thresholds, evidence or recorder behaviour.

On the same isolated synthetic 3,000-interval database, both versions exported all **6,051 records**
(minutes, hours and events) without contention. Three normal runs took **0.272-0.302 seconds
before** and **0.268-0.292 seconds after**; this small sample does not establish a speedup.
With the same lock held for 50 ms, the old implementation stopped at zero rows after 0.022
seconds; the revised export retried once and completed all 6,051 rows in 0.404 seconds.
These are isolated container measurements, not live load or endurance results.

Regression coverage includes real WAL lock recovery, a pinned-reader checkpoint that cannot
truncate, thousands of rows, real query deadline interruption, permanent and extended SQLite
errors, filesystem failures, malformed/deeply nested payloads, unsupported schema, empty and
missing stores, later-page retries across all tiers, equal-timestamp cursors, fixed cutoff,
per-export retry exhaustion, repeated cancellation and cancellation during backoff. Failed
exports leave the main database and recorder unchanged and recording can continue afterward.
No live settings, database records, deployment or service restart were performed for this fix.

Final validation on **2026-09-08** passed **1,218 backend tests**, with zero failures, errors or
skips, including **27 new export regression cases**. Ruff lint, exact formatting and strict mypy
also passed. Source hashes stayed unchanged during validation. The first full run exposed a
test-fixture assumption about Python's JSON nesting limit; the corrected fixture and the complete
suite passed afterward. Existing backend files outside `api.py` and `diagnostics_store.py` match
the pre-task 1,191-test validation exactly. Frontend and dependencies were unchanged.

## Diagnostics capacity and retention edge checks

A further isolated review reproduced one reporting defect: removing the diagnostics file after
the first page made subsequent reads return an empty list, incorrectly producing
`export_complete` for the partial download. Exports now remember whether their store existed at
the start and require it throughout all tiers. Missing history advertised by recorder status
also produces `diagnostics_file_error`; an initially absent, unrecorded store still exports an
empty history. The existence probe runs off the event loop. No file is recreated or repaired.

The expanded focused suite passed **83 diagnostics tests**, including seven new cases for a
capacity pause, low free space, real retention deleting records between pages, and missing files
before or during paging, including an empty minute tier followed by retained hourly history.
Retention remains explicitly non-atomic: rows fetched before cleanup remain in the download;
later pages read the surviving history without repeating earlier rows.

A separate capacity run used isolated synthetic data at every configured row limit:
**43,200 minute rows + 8,760 hourly rows + 100,000 events = 151,960 records**. It physically
allocated a **402,644,992-byte SQLite file** (384 MiB minus 8 KiB), including reusable pages
representative of retention. All records exported successfully in 15.60 seconds. Adding
physically allocated regular padding took the owned directory to **536,870,912 bytes (512 MiB)**;
the recording guard entered `paused_storage`, and all 151,960 records still exported in 13.41
seconds, with zero retries. Padding exercised the byte guard; it was not extra diagnostic data
or a simulated WAL. Separate tests cover real WAL/checkpoint contention.

Each export contained 296,541,356 bytes of NDJSON and was consumed incrementally, without saving
the output or buffering the whole download. Peak Python process RSS was about 87 MiB; peak
container usage, including temporary data, was about 613 MiB. SQLite `quick_check` returned `ok`,
and export changed neither diagnostic nor main-database write counts. The container had one CPU,
a 2 GiB memory limit, no network, no live data mount and a temporary filesystem. Dataset creation,
both exports and checks took 39.63 seconds; the fixture was then removed. These measurements
cover these synthetic payloads and local streaming, not all payload distributions, browsers,
reverse proxies, physical-disk faults or long-term live conditions.

Only diagnostics reading/reporting changed in this follow-up. Storage budgets, cleanup,
recording and all trading/learning behaviour remain unchanged. No live deployment was performed.

Final backend validation passed **1,225 tests**, with zero failures, errors or skips, plus Ruff
lint, exact formatting and strict mypy. The validated source hashes stayed unchanged throughout
the run. Existing backend and test files outside the two export/read modules still match the
preceding validated source; the seven capacity/retention cases are in a new test module.

## Upgrade and remaining observation

### Suspended Champion recovery and Exit queue follow-up

The isolated reproduction confirmed that a health-suspended Sizing/Exit Champion could collect
new shadow evidence indefinitely without a path back to support. A separate reproduction showed
an identical native Exit fit replacing a different pending policy. Recovery now uses one durable,
preselected 60-entry trial per suspension; it cannot reuse earlier outcomes, pass on a favorable
prefix, slide after failure, or ignore unavailable observations. Existing coverage, harm and
advantage checks remain; Entry additionally retains its current activation gates. Structural or
unknown suspensions remain blocked. A changed upstream activation epoch invalidates recovery.

Restored authority, downstream removals and the recovery receipt commit together. Failed writes
leave the runtime and restarted learner suspended. The same immutable artifact and Champion
generation return; training and battle history are not rewritten. Recovery state uses a bounded
nested receipt in existing flexible JSON, keeping the strict schema-16 state model compatible.
Native deterministic Exit deduplication requires the full matching executable policy contract,
preserves ongoing battles and different queued/Coach contenders, and keeps every fit auditable.

Full backend verification passed **1,271 tests**, zero failures/errors/skips, with Ruff lint,
formatting and strict mypy (39 source files). This includes diagnostics capacity/export checks,
all four Coach skill recovery paths, native Entry gates, fixed-window coverage at 41/60 and 42/60,
pending and pruned evidence, restarts, immutable crowns, missing artifacts, revoked permissions,
legacy quarantine timestamps (including an already health-suspended legacy Champion), malformed
metadata and transactional failure. Frontend validation passed **359 tests** across 21 files,
plus lint, TypeScript and production build checks. Readout tests verify
that suspension details do not write state or expose Policy IDs. Validation artifacts and exact
source hashes are retained outside the repository in the local recovery audit folder.

The fixed trial deliberately does not retry a failed window. A newly qualified replacement is
then required; the change does not promise automatic recovery or a future Entry Champion.

A repeated full run initially exhausted the disposable test filesystem (211 MiB free), correctly
triggering the diagnostics recorder's 512 MiB free-space guard. Only that test container was
restarted to remove accumulated fixtures. The final clean run above passed without relaxing the
guard; the live volume was never mounted into the test containers.

Before the approved local update, the 2026-09-08 15:11:51 UTC snapshot showed healthy active
Sizing/Exit and unqualified Entry at 380/1,000 (38%) operational coverage. The previous build had
just recovered from a burst: 6,526 candidate expiries in its recent five-minute window, zero shed
candidates, and 7,973 cumulative expiries since that boot. All seven workers remained running.
This is retained as a pre-update baseline; zero counters after restart cannot demonstrate better
burst performance, and overlap with isolated validation/build work does not establish causation.

The first local deployment completed at 15:19:26 UTC after a verified 3,061,841,473-byte full
backup, preserving the season, settings and healthy Sizing/Exit authority. Four subsequent samples
over two minutes showed all seven workers running, queue depths 42/2/1/1, critical lag below 0.1 s,
and no candidate losses since that boot. The paper ledger audit remained verified. These are short
health observations, not an equivalent-load performance comparison or an endurance test.

That live check also found an incomplete diagnostics export: 9,777 rows (3,604 minute, 73 hour,
6,100 event) before `diagnostics_query_deadline` exhausted six retries. A bounded live EXPLAIN
confirmed the expected composite event index was used. An isolated one-CPU reproduction with
competing Python work increased median 100-row page time from about 3 ms to 130 ms and produced
the same deadline failure. Smaller pages completed without that failure in the five-sample trial;
this demonstrates a scheduling-sensitive read mechanism, not the exact attribution of live load.

The follow-up retains the 100 ms query budget, 20 ms lock timeout, two retries per page and six
per download. Deadline failures reduce pages from 100 to 50, then 25 for that download; complete
pages alone advance the cursor. A post-query budget check also covers reads too short to trigger
the periodic SQLite callback. Focused tests cover adaptive interval/event pages and equal-timestamp
ordering, alongside the existing capacity, WAL, cancellation and failure-isolation checks.

The 15:43:07 UTC local update of that adaptive-page build preserved settings and healthy
Sizing/Exit. It was not sufficient: a subsequent download stopped after 3,200 minute records
with six deadline retries. A small burst during observation expired 37 candidates; the queue
then recovered from 848 to 3 and 2, with critical lag returning below 0.05 s. Training published
one model, the paper ledger remained verified, and Coach was healthy waiting for outcomes.
These failures were retained rather than treating a healthy recorder as successful export proof.

The verified diagnostics-only backup reproduced the problem offline. With one CPU and no
competing work, all 14,707 records exported in 2.00 s. With a competing Python thread, the same
reader failed after 350 records in 2.32 s. A completed query/prefix was being discarded when
scheduling consumed its elapsed budget, repeatedly spending that budget on the same records.

The final reader checks the deadline between rows and treats the last fully fetched, decoded
row as a page boundary. A deadline interrupt may retain that ordered prefix; file errors,
unexpected interrupts and decode failures still reject the page. A deadline before any progress
still has the same bounded retry/backoff and smaller-page fallback. Connections close before
decoding or streaming, and no lock, query or retention limit is increased.

On the same offline backup, the revised reader exported all 14,707 records in 1.81 s without
contention and 30.25 s with contention (293 pages, one retry). These are bounded reproductions,
not a sustained-load benchmark or proof of the exact source of live scheduling pressure.
All **95 diagnostics tests** passed, including forced elapsed/SQLite deadline boundaries for
intervals and events, equal-timestamp cursor continuity without duplicates, real interrupts
before any progress, non-deadline errors, capacity, WAL contention and cancellation.

Final verification of that reader and the complete release passed **1,283 backend tests**
(zero failures, errors or skips), Ruff lint, exact formatting and strict mypy across 39 source
files. The previously validated frontend remains unchanged: **359 tests**, lint, TypeScript
and production build passed. Packaged backend and frontend hashes are checked against those
validation records before deployment; schema 16 and installed dependencies remain unchanged.

The final local image (`sha256:c37b6dffa191f86ec4104cadf18e3fb6cd0800e5e4bc7c189531ebf771d745fd`)
was deployed at **2026-09-08 16:03:35 UTC**, after a verified 10,961,874-byte diagnostics backup;
the earlier verified full data backup and prior compatible images remain available. Season,
settings, support/Coach permissions and Sizing/Exit versions were preserved. The father's remote
instance was not changed.

Four serial observations through 16:06:00 UTC showed all seven workers running. Startup queue
111 cleared to 0/0/1, with critical lag settling from 2.70 s to 0.011/0.026/0.024 s. There were no
shed or expired candidates since that boot during this window. The real HTTP diagnostics download
then completed with **14,762 records** (3,637 minute, 74 hour, 11,051 event), **27,989,780 bytes**,
one retry and an `export_complete` trailer in **50.97 seconds**. This was streamed and counted,
not buffered as one response. Recording remained healthy. The post-export queue was 201 with
critical lag 0.775 s and zero candidate losses; the export is still optional work under load.

The paper ledger remained verified, Sizing/Exit health remained healthy, and two model
publications completed during observation. Coach was healthy waiting for outcomes. Entry was
still unqualified at 358/1,000 (35.8%) operational coverage; its 70% requirement was unchanged.
The final container check at 16:07:29 UTC confirmed the exact validated image, healthy status,
zero automatic restarts, no OOM and no errors in the bounded startup log. These short observations
support the fixes but do not establish sustained peak-load capacity or month-long reliability.

A subsequent edge-case recheck passed **92 focused regression tests**. Additional isolated
checks interrupted real SQLite reads after 50 interval rows and 56 event rows; both resumed to
all 211 expected records without gaps, duplicates or database writes. No source fix was needed.

Live follow-up at 16:13:07-16:13:47 UTC caught another burst: candidate expiries reached 2,006
since this boot, while the queue recovered from 2,179 to 203 and 24. Sampled critical lag remained
below 0.1 s. The final 16:15:00-16:15:40 UTC readings added no further expiries, with queue depths
0/3/110 and critical lag 0.036/0.045/0.067 s. All workers were healthy, the ledger audit was
verified, Sizing/Exit remained healthy, recording continued and four model publications had
completed since startup. Entry remained unqualified at 370/1,000 (37%) operational coverage.
The live image still matched the validated source, with no restart, OOM or errors in bounded
logs. Candidate loss during bursts remains a documented capacity limit; healthy recovery does
not prove loss-free operation. No service restart or settings change was made for this recheck.

No evidence migration, model reset, permission change or new season is required from published
v1.10.7. The added Coach index and internal retry cursor are compatible with schema-16 rollback.
Use the previous verified schema-16 image and the same data volume if a code rollback is needed;
do not replace newer accumulated evidence with an older backup as a routine rollback step.
Older schema-15 images still require their matching pre-upgrade backup.

Entry must independently earn both coverage and model-performance proof. Coach's current
contribution path requires an existing Champion for the target skill. Better collection and
scheduling cannot make an unavailable market executable or guarantee a first Entry Champion,
profitable paper trading or issue-free operation for months. Sustained natural-burst behaviour,
provider availability, storage growth and Coach research opportunities require longer observation.

The independent final review found one remaining Coach scheduling regression: the durable
active-study lookup ran directly on the main async loop, as did status reads returned by the two
Coach control endpoints. A competing reader could therefore block market scheduling. An isolated
250 ms reader-lock reproduction delayed a scheduled heartbeat by about 235 ms; offloading the
lookup reduced that delay to about 11 ms. This identifies the blocking mechanism, not the cause
or expected improvement of a particular live market burst.

The correction uses the existing cancellation-safe worker helper for those three call paths.
After the monitor read returns, it rechecks research permission, market pressure and the exact
skill context before proceeding. Errors still propagate instead of looking like an empty study
population, and the normal control/maintenance serialization remains in place. Database writes,
study selection, Champion authority, model recipes and qualification requirements are unchanged.

The new monitor cases reproduced the original blocking call, and both control-response cases
failed against the original endpoints. After correction, **179 focused tests passed**, including
slow reads, concurrent responses, repeated cancellation, worker errors, revoked research,
changed dependencies, pressure arriving during the wait, active/absent studies, permissions and
existing Coach handoff/lifecycle behavior. The README, all 32 local link targets and the documented
Compose settings also passed the release check.

The complete corrected backend passed **1,297 tests** with zero failures, errors or skips,
plus Ruff lint, exact formatting and strict mypy across 39 source files. Hashes confirm that the
frontend inputs still match its previously successful **359-test** validation, lint, types and
production build. This last correction changes only `coach.py`, `api.py` and their regression
tests relative to the preceding validated backend; no other runtime source changed.

The follow-up image (`sha256:7bbc4b99b498d2d1a0bc3b290a9f790b3d4855999941d59411f098947a5c620f`)
passed the isolated startup check and was deployed locally at **2026-09-08 17:00:55 UTC** after
a verified 11,114,591-byte diagnostics backup. The previous verified full backup and compatible
image remain available. Packaged source/frontend hashes matched validation, installed dependencies
and schema 16 stayed unchanged, and the season, settings, Coach permissions and active Sizing/Exit
versions were preserved. No unfilled order needed cancellation during maintenance.

Before this update, cumulative candidate expiries had reached 14,976 since the previous boot;
the final pre-update sample had recovered to queue zero and critical lag 0.154 s. Isolated tests
and build work overlapped that runtime, so these counters do not establish the source of load
or a comparable before/after throughput improvement. Restarted counters must not be treated as
evidence that the known burst-capacity limit disappeared.

Five serial observations from **17:01:28 to 17:03:28 UTC** showed queue depths 0/0/0/18/0,
critical lag 0.015/0.007/0.017/0.024/0.063 s and no candidate shedding or expiry since restart.
All seven workers stayed healthy. The final snapshot verified the paper ledger, healthy active
Sizing/Exit, diagnostics recording and Coach waiting for outcomes with no error. Two training
publications completed. Entry remained unqualified at 360/1,000 (36%) operational coverage,
against the unchanged 70% requirement. Image/source hashes matched validation, with no automatic
restart, OOM or errors in the bounded log check. These short observations support release
readiness with the documented burst limitations; they do not establish long-term performance.
