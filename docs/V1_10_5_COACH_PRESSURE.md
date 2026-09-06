# Market-processing pressure investigation — 5 September 2026

## Current outcome — 21:39 UTC

The verified fixes are live in v1.10.5 image `650a2a16c5f7…`: advisory-reader isolation,
dashboard scheduling, additive indexes, one valuation per sizing call, and batched immutable
training copies. This installation now uses a native Docker data volume. The original data
folder remains a verified recovery snapshot, and the conflicting Windows localhost relay was
removed with the user's administrator approval.

The final 20-sample observation passed all health/database/worker checks. At the final check,
84,414 events had been processed since this build started, with zero expired or shed events
and two successful fit publications. Nine complete post-startup intervals averaged 131 received
events/second, with measured histogram p95 bounds of 0.5 seconds overall and 0.25 seconds for
critical events. Full validation passed 596 backend tests; fixed-cohort model outputs remained
identical. README, changelog, backend and UI hashes match the deployed release.

This is an initial improvement check, not community release sign-off or proof of long-term
stability. The preceding native-volume boot developed a delayed expiry burst, documented below,
and the new window ran with entries halted by the season's drawdown rule. Keep Shadow enabled
for the next four-hour observation, including the automatic season boundary and resumed position
activity. Current Entry coverage is 41.1%, below the unchanged 70% requirement, and activation
remains unavailable. No profitable Champion or future qualification is implied.

## Finding

Live diagnostics showed recurring event/heartbeat/snapshot stalls with ongoing model fitting.
At the investigation baseline, the app had processed 703,383 events and dropped 21,807 candidate
events since its last restart. The worst recorded interval included a 17.7-second heartbeat,
23.4-second event batch and 12.8-second snapshot. These phases include time waiting on shared
resources; they must not all be counted as independent CPU work.

The Coach monitor loaded up to 5,000 complete learning observations every 30 seconds before
checking `can_run()`. Its query sorted full JSON records while holding `Database._reader_lock`,
which is also required by core broker/settings reads, heartbeat work, snapshots and storage
capacity checks. A background thread alone did not isolate that shared lock. The live Coach
reported `protecting_market_throughput`, but that check happened after the expensive read.

A copied-data profile reproduced 18.78 seconds for the first Coach history read and 5.94 seconds
warm, including 8.74/4.47 seconds executing SQLite's query. On that same isolated fixture,
expiring copied pending checkpoints took 77 ms, tournament advancement 17 ms, and history pruning
6 ms. This identifies a concrete source of shared-reader stalls; it does not rule out other
sources of processing pressure.

## Fix

- Apply Coach admission checks before history loading or experiment refresh; fitting also takes
  priority over Coach research.
- Use a separate read-only connection without either core database lock. Materialize/sort only
  row identifiers and timestamps, then fetch payloads in batches of 25. Preserve the full record
  contents and chronological order, including ties.
- Check pressure during SQL work and record decoding, use a 250 ms SQL work budget per chunk,
  and close the connection on deferral or cancellation. Interrupted evidence raises a distinct
  deferral; it is never substituted with an empty or partial cohort.
- Run candidate screening off the event loop and recheck pressure, research permission and
  configuration identity before inference. Existing checks after inference remain in place.

This first stage changed no learning algorithm, outcome label, qualification threshold, risk
setting or automatic activation permission. It required no index migration or history reset.
The later additive index stage is documented below; the main database remains schema 14
throughout, without manual Champion promotion or a forced new season.

## Verification

In a fixed three-read comparison on the same copied 5,000-record cohort, all ordered record
digests matched exactly before and after (`3349ccc3686d…`). Candidate outputs also matched;
this particular copied cohort produced no candidates, so non-empty candidate behavior is covered
separately by the existing Coach tests.

| Whole history read | Before | After |
| --- | ---: | ---: |
| Median elapsed time | 4.19 s | 2.62 s |
| Median CPU time | 3.67 s | 2.05 s |

These are small, profiled, isolated samples on one CPU, not a whole-app throughput guarantee.
The new query's SQLite execute step took about 8–10 ms in the first two comparison runs, with
77–91 ms in batched fetches. JSON validation still has a real cost; early admission, cancellation
and removal of the shared core lock are essential parts of the fix.

Regression coverage checks busy admission without any history read, unchanged tied-timestamp
cohorts, independence from both core locks, partial-read rejection and recovery, cancellation,
screening without blocking the event loop, and pause/context/pressure changes before inference.
The existing inference-time context-change test now changes context inside the fake inference
call, so it continues testing that boundary after adding an earlier context check.

The broad database/Coach/API/diagnostics/provider regression run passed 210 checks. The complete
backend suite then passed **558 tests** in 47 seconds, with one existing Starlette/AnyIO deprecation
warning. Mypy passed all 39 backend modules. Live deployment follow-up is recorded below.

## Deployment and observation

The Coach fix was deployed through maintenance on 5 September 2026. The existing season,
settings, ledger, UI assets and diagnostics history were preserved. Its image fingerprint is
`75805ad2726dc99766ee2da42a1607da37f17012d8b1de5fb5463739a28e96cb`.

Initial live samples were responsive, but a subsequent fresh interval recorded a 22.2-second
market batch, 27.3-second critical lag and expired candidate events. Thus this fixes a proven
bottleneck but does not by itself resolve all pressure. Training was idle during that incident.
Bounded operation timings were added to distinguish the remaining work within batches.
Each fixed phase stores only count, total duration and maximum duration; no payloads or I/O
are added to the decision path. Exceptions and cancellation still propagate unchanged.
Further live findings are recorded after qualification below.


### Detailed live finding and dashboard scheduling

The timing build (`85e2e1e321f799b249989f9abb5d667185559b77e3d1086eae42e08a278bc6d7`)
preserved the existing history and captured another slow interval. At about 218 admitted events
per second across six intervals, one minute spent 15.0 seconds generating seven dashboard
snapshots, 11.5 seconds persisting event batches, 9.4 seconds in heartbeat work and 4.6 seconds
in broker event work. Batch duration overlaps those boundary waits; these totals must not be
added as independent CPU time. Training was idle during that spike. The largest checkpoint
update in it was 0.37 seconds. Expired events were lower-priority candidates, not invented
learning outcomes; integrity windows continue to exclude incomplete evidence.

Profiling only learning status on the copied cohort reproduced 0.84 seconds initially and
0.69 seconds warm under cProfile. Repeated feature-completeness checks and evidence summaries
account for much of that cost. This identifies an avoidable read workload without changing
those proof calculations or introducing cached qualification results into trading.

Dashboard reuse now adapts between 5 and 12 seconds to its measured calculation cost, queued
market work and active training. The initial read and explicit invalidations still request a
fresh view; the single FIFO waiter survives request timeouts and cancellation. Twelve seconds
is the reuse admission cap, not a promise that a contended refresh always finishes within twelve
seconds. Actual snapshot age remains reported and the existing 15-second warning is unchanged.
The full backend suite passed 566 tests; mypy and scoped Ruff checks passed.

Post-deployment live comparison follows below. This is still a performance investigation and
soak validation, not evidence that a Champion will qualify or be profitable.


The maximum operational record test also passed with distinct timing values in every phase,
so the added fields fit the existing record cap without relying on identical-value compression.
An isolated 200,000-call timing check used 0.95 CPU seconds (about 4.7 microseconds per call),
with one retained phase and no I/O writer started. This is a microbenchmark, not an end-to-end
throughput result.


### Remaining reader and retention contention

The longer dashboard-only follow-up still recorded candidate-expiry bursts: the scheduling
change alone did not resolve pressure. A separate py-spy 0.4.1 tool sampled PID 8 for 30 seconds
at 20 Hz using nonblocking stack reads and no local variables. It captured 8,235 thread samples
and 50 read errors; idle-thread time is included and must not be interpreted as CPU percentages.
No profiler was installed into the app image or left running. The stack sample showed Local AI
qualification in `list_ai_assessments`, core callers waiting on reader/writer locks, and repeated
terminal-evidence retention scans.

Local AI's 5,000-record read had the same full-JSON sort pattern as the earlier Coach problem.
The fix uses a separate read-only connection and a chronological index. A covering retention
index avoids large evidence-row visits, with explicit descending row-id ordering retaining the
previous lane-index tie order. A lane/trajectory index supports the existing idempotency check.
These are additive schema-14 access paths, installed transactionally; rollback images remain
compatible and no rows or saved settings are rewritten by the index upgrade.

On the identical copied 4,717-record AI cohort, median elapsed time fell from 0.978 to 0.252
seconds and median CPU time from 0.969 to 0.252 seconds. All six ordered payload digests matched
(`88832b1944d76d2ad53afe68662bee70dfef47a7ce17f3d3e6bdfb9344f507a1`). The old plan scanned
and sorted JSON; the new plan uses `idx_ai_assessments_created`. These isolated measurements
support the query change, not a promise about market-wide performance.

The final index build passed **575 backend tests**, including identical full cohorts and tied
timestamps, reading while core locks are held, exact retention selections, preservation of
pending evidence, repeated migration, rollback after an injected migration error, refusal of
newer schemas, and the existing legacy season-only import case. That legacy case caught an
initial unconditional-index assumption; the corrected migration skips absent optional tables.
Mypy passed 37 source modules and scoped Ruff checks passed.

The index build was deployed through the app's maintenance workflow with fingerprint
`89fabcda04d0878f64e16124e509c0842c3bc67274937c405ff5932d3c2fa2b1`.
Backend source and README hashes matched the working repository; UI asset hashes were unchanged.
The data mount and season 31 were preserved, with Balanced, 400 USDC starting capital, 25% drawdown,
automatic seasons and Shadow learning. Read-only checks found zero ledger imbalances and zero
orphan fills. Live query plans selected the new AI chronological index and covering evidence
retention index. Identity lookup already selected the existing unique lane/trajectory index;
the additional trajectory index must not be credited with improving that live lookup.

At the first post-deployment snapshot, Entry activation remained unavailable: recent executable
coverage was 41.3% against 70%, and the latest model also failed return and conservative policy
value checks. Policy outcome coverage was 93.0%. These are different evidence populations.
The performance fixes do not remove unavailable outcomes from denominators, relax proof gates,
or establish that a profitable Champion will emerge. Longer live observation follows below.

### Sizing calculation work

The first 9.5-minute index-build observation processed 102,717 additional events and recorded
2,079 expired candidates. Two fits completed without errors. Another nonblocking 30-second
sample captured 8,205 thread samples with 52 read errors: repeated portfolio/settings/ledger
reads remained prominent, including several valuations inside each `plan_entry_size` call.
Core reads measured outside the shared Python lock were inexpensive when warm (about 0.5 ms
for a setting and 0.7 ms for the balance on 1,055 ledger rows). Thus a ledger index or a risk
threshold change was not justified by this probe.

Sizing now computes one current portfolio valuation per synchronous call and passes it through
the existing growth, realized-bankroll, exposure and cash calculations. No valuation is retained
between calls. The reference-size entry point remains fresh, and submission/fill gates retain
their separate current-state checks. On 315 synthetic before/after cases, every sizing output
matched exactly (`c8f161323be190dc2b1d5d31d211c8de2bdd2e5ec9caa10f165688deff155121`).
Cases cover all three risk modes, SOL/USDC books and missing conversion data, every integrity
state, profits/losses, executable/stale/blocked positions and pending cash reservations.
Total SQL reads fell from 4,347 to 1,260; measured CPU time fell from 0.192 to 0.068 seconds on
that synthetic fixture. Those timings are not a forecast of live throughput.

All **588 backend tests** passed. The added cases check that each subsequent sizing call sees
newly spent or reserved cash, and that submitting an earlier size still fails after cash becomes
unavailable. Uninitialized books and missing USDC conversion remain blocked at entry. Existing
fill-time integrity/size checks also passed. Mypy passed 37 modules; scoped Ruff checks passed.

### Windows storage overhead

The sizing build retained the same learning rules and improved its first observation, but a
longer sample still recorded candidate expiry. Inspection confirmed that `/data` was a Windows
NTFS bind mount on a healthy NVMe drive. A bounded standalone test compared identical small
SQLite databases with WAL and `synchronous=FULL`, without mounting any live app data:

| Median of three synthetic samples | Windows bind mount | Docker Linux volume |
| --- | ---: | ---: |
| 1,000 small indexed reads | 0.289 s | 0.009 s |
| 100 separate durable commits | 0.352 s | 0.192 s |

Every read digest matched. This demonstrates substantial filesystem overhead for this workload,
not a 32-fold whole-app speedup. It is consistent with Docker's
[WSL filesystem guidance](https://docs.docker.com/desktop/features/wsl/best-practices/).
The default Compose configuration already uses a named volume; this installation had explicitly
selected the Windows folder. No global Docker setting or model storage needs to change.

Docker's Linux data disk is already hosted on E:. The first full-folder copy preflight correctly
refused insufficient headroom: the directory includes about 23 GB of historical operator backups.
Those `backups/` archives are not runtime inputs and remain at the original host location.
The revised copy covers all other data, including the main database, provider configuration and
diagnostics history, while preserving the entire original folder. It leaves approximately 23 GB
of physical host headroom; the app's existing main database budget remains 16 GiB and diagnostics
remain separately bounded at 512 MiB.

The initial copy helper was exercised on disposable files: it preserves content, leaves archived
backups untouched, refuses an existing destination, and checks SQLite integrity. Two full-copy
attempts passed every file hash but exceeded their three- and ten-minute historical scan budgets.
Both refused cutover and restarted the original app with its original data and configuration.
Neither timeout reported corruption; neither established a completed integrity check.

The first unused destination was removed only after verifying its identity, lack of container
users, and continued use of the original app folder. Docker retained the freed allocation inside
its dynamic virtual disk. The second copy reused those Linux extents while checking real E: free
space, aborting below 13 GiB rather than trusting the virtual disk's larger reported capacity.
Its files were retained as an isolated provisional copy. A separate read-only process gave
the full historical scan a 256 MiB SQLite cache and thirty minutes while the original app ran.
These scans are maintenance diagnostics, not extra recurring work in the application.

The final synchronization helper requires that complete baseline check and exact destination
manifest before it can run. It is tested on fresh committed settings, growing/shrinking/new and
removed files, unchanged blocks, stale manifests, unsafe symlinks, and source/archive preservation.
It runs only after maintenance is ready and the source app is stopped, refreshes the provisional
copy with every newer source record, and verifies every resulting file hash. Fresh critical
tables and the complete diagnostics database are checked during that pause; the historical
market-event and decision tables are reserved for a full read-only scan of the frozen recovery
source after cutover. A per-table `quick_check` is explicitly not a full database integrity check.
The application user must open the new database before switching the local data source.

Only `SIGNAL_ARCADE_DATA_SOURCE` in ignored local `.env` changes at cutover. The app image, schema,
other settings, learning gates and provider configuration stay the same. The original folder is
a recovery snapshot at cutover; later restoration must account for newer records in the live
volume rather than silently restoring that older snapshot. Completion and live measurements
must be recorded separately after the synchronization and runtime checks succeed.

### Completed native-volume cutover

The provisional main database passed its full `quick_check` in 1,556 seconds, with schema 14
and no ledger imbalance. The separate diagnostics check initially could not open a cleanly
closed WAL database on a read-only mount because its WAL/SHM sidecars were absent. The local
verification helper now uses immutable reads only for a frozen file with no nonempty WAL or
rollback journal. Tests also verify that committed nonempty WAL data is still read and that a
nonempty recovery journal is never ignored. The diagnostics database then passed its full check.
This change is confined to migration verification, not the application's SQLite connections.

After a fresh maintenance pause, every byte of the stopped source was synchronized and verified.
The 13,925,756,957-byte runtime copy included all newer data: 31 seasons, 357 fills, 1 open position,
5,146 retained observations and 25 Champion events at that boundary. Both ledger imbalance and
orphan-fill counts were zero. The original backup archives stayed in the original folder.
Cutover completed at 20:19 UTC on 5 September under maintenance operation
`f82e6706e2f447b6b82df31306dae01e`.

The active `/data` mount is now Docker volume `solana-signal-arcade_signal-arcade-data`. The original
`E:/codex/paper-trading/solana-signal-arcade/data` folder is preserved as the cutover recovery
snapshot. Physical E: headroom was about 23.1 GB after cutover. Only the ignored local data-source
line changed. The deployed image remains `64afc62aac9f…` with build fingerprint `26901a7fb3ab…`;
all backend source, UI assets, README and changelog hashes matched the working v1.10.5 release.
Runtime checks retained season 31, Balanced, 400 USDC starting capital, 25% drawdown, automatic
seasons and Shadow learning. All learning-gate subject identities and execution-ledger checks
passed. The subsequent full read-only scan of the exact frozen source completed at 21:01 UTC.
Every source hash matched the final cutover copy. Full `quick_check` returned `ok` for both
the schema-14 main database (2,241 seconds) and schema-1 diagnostics database (0.063 seconds).
This completes the historical-table check separately from the already-passed full provisional
and fresh critical-table checks. The verification container exited; no recurring full scan was
added to the running app. Fifteen disposable synchronization/verifier cases passed, including
the WAL and journal boundaries described above.

### Separate Windows localhost relay fault

The first lightweight observer stopped after twelve successful samples because Windows reset
localhost HTTP connections. In-container requests and the machine's LAN address continued to
work. Inspection found Docker listening on `0.0.0.0:8765` and an older `wslrelay.exe` process,
started on 31 August, overriding `127.0.0.1:8765`. No HTTP proxy was configured. The alternate
loopback address also reached Docker successfully. This evidence localized the access fault
to the conflicting relay; a similar stale-listener symptom is recorded in the
[Microsoft WSL issue tracker](https://github.com/microsoft/WSL/issues/10601).

Windows required administrator permission to stop that process. With the user's explicit
approval, a guarded helper rechecked the exact executable, PID, creation time and sole listening
port before stopping only that relay at 20:40 UTC. Docker and the app stayed running, Docker's
PID was unchanged, and it became the sole listener on port 8765. Authenticated localhost access
then recovered. No WSL shutdown, Docker restart, firewall change or global networking setting
was used. Existing observer samples were preserved and observation resumed; the app's own
diagnostics retained intervening processing and training aggregates, with skipped intervals
still reported as gaps rather than reconstructed observations.

### Continued observation and batched training copies

The native-volume boot initially processed about 340,000 events without expiry or shedding,
but the subsequent observation caught 6,317 expired candidate events around 21:06–21:07 UTC.
The full recovery scan had already ended. Across the first three complete post-scan intervals,
received traffic averaged 155 events/second; maximum processing lag reached 31.3 seconds and
critical lag 27.5 seconds. Training preparation reached 20.4 seconds, and a later reconstruction
took 25.0 seconds. Storage wall timing overlapped the stall; the individual phase totals are
not additive CPU measurements. This observation failed: the earlier zero-expiry window was
not sufficient to declare the performance problem resolved.

All twenty HTTP health samples in that observation were healthy, including database and worker
checks. This demonstrates why HTTP health alone is insufficient for release acceptance. The
earlier resumed observer had one briefly failed health probe, with healthy workers and low
market lag, but did not retain the individual database/service flags; its cause is unconfirmed.
No error-level or warning-level runtime log entries accompanied those observations.

Two bounded nonblocking stack samples (60 and 120 seconds, 20 Hz, no local variables) captured
16,665/33,795 thread samples with 88/146 read errors. They showed ordinary event persistence,
reader activity and idle waits, but did not capture a full fit. They therefore do not establish
the cause of the 25-second reconstruction. Idle thread samples are not CPU percentages. Both
profilers exited. The second part of the twenty-sample observation overlapped these profilers;
it must not be presented as a wholly uninstrumented window.

A separate disposable copied cohort reproduced a 40,288,910-byte monolithic training input.
Its first serialization took 1.34 seconds and reconstruction 0.88 seconds under cProfile; later
copies were faster. The longest observed garbage collection on that fixture was 0.109 seconds,
so that isolated test does not reproduce or explain the live 25-second outlier. Nevertheless,
a native validation call over the whole cohort is a concrete source of thread blocking.

Training inputs now freeze all five ordered input categories in immutable batches of up to
32 rows per category. Reconstruction runs outside the market boundary and explicitly yields
between validation calls. The complete snapshot still belongs to one event boundary; there
is no sampling, omitted evidence, changed fit window, mixed-context input or partial publication.
Malformed later batches fail the entire job and leave one retry. The existing audit-only field
exclusions, Policy sizing trials, runtime/authority guards and stale-job limit are unchanged.

Six alternating old/new runs on the same fixture retained all 5,089 observations, 1,490 evidence
episodes, 1,000 models, 1,000 artifacts and 20 skill states. Every reconstructed cohort digest
was `ee7c2555e543ca69dd848f89439ca00d77dc3b3c7e1d3d24619d0e2ccda50701`; model outputs,
artifact metrics/parameters/qualification and serialized model payloads also matched. Existing
nonlinear equivalence tests additionally compare XGBoost payload bytes and proof cohorts.

| Median isolated measurement | Monolithic | Batched |
| --- | ---: | ---: |
| Freeze elapsed | 0.394 s | 0.283 s |
| Freeze heartbeat maximum gap | 0.045 s | 0.008 s |
| Reconstruct elapsed | 0.584 s | 0.965 s |
| Reconstruct heartbeat maximum gap | 0.553 s | 0.376 s |

This trades about 0.38 seconds of extra reconstruction CPU for better scheduling opportunities;
it is not a claim of faster total fitting or elimination of all Python pauses. Full backend
validation passed 596 tests. The final tuple type refinement then passed 38 targeted tests;
mypy passed all 39 backend modules, scoped Ruff and diff-whitespace checks passed. Chunk-boundary,
empty/uneven cohorts, mutation isolation, malformed-copy rejection, context changes and nonlinear
output equivalence are covered. Live deployment and observation follow separately.

The batched-copy build was deployed through maintenance operation
`26b573efd98d4814880b6fd4054c9211` at about 21:26 UTC. The image is `650a2a16c5f7…`, with
fingerprint `3e27384a6b2a…`. Only `intelligence/learning.py` and `intelligence/training_job.py`
differ from the preceding image's backend; UI hashes are identical. Live source, README and
changelog hashes match the repository. The native data mount, schema 14, season 31, 400 USDC
starting capital, Balanced risk, 25% drawdown setting and Shadow learning were preserved.
Post-startup ledger imbalance and orphan-fill counts were zero. The initial authenticated
verification was attempted before readiness and received a closed connection; it passed after
the bounded readiness wait completed. The Docker listener remained the only listener on 8765.

At the post-startup check, season equity was 298.270801 USDC, a 25.4323% drawdown. There were
no positions or pending orders, and `portfolio_drawdown_limit_reached` correctly halted entries.
Auto-season was in its configured one-hour countdown, with a displayed rollover target of
22:28 UTC. This is a strategy loss and active risk control, not evidence of profitable learning.
It also means this boot's early performance cannot be compared as equivalent to an earlier
window with active holdings and entries.

At 21:31 UTC, the first new fit had published successfully; recent usable Entry coverage was
403/1,000 (40.3%) against the unchanged 70% requirement. The evaluated model's own fitted cohort
had 36.7% coverage. These are distinct populations. Activation was unavailable, with 8/16
foundational gates passing; negative top-group return, insufficient current Policy cases,
winner-veto rate and conservative veto value also failed. No manual promotion, Active enable,
threshold relaxation or forced season change was performed.

### Final post-deployment measurements

Twenty lightweight health/diagnostics samples spanned 570 seconds, with no profiler, full scan,
copied-data fit or test container running during that observation. All sampled database,
service and worker flags were healthy. The final independent check saw 84,414 processed events,
zero candidate expiry, zero shedding and two fit publications with no training error or stale-job
discard. The latest reconstruction took 1.199 seconds, fitting 0.236 seconds and publication
0.119 seconds; preparation took 0.408 seconds separately. The reported job duration excludes
preparation, so these fields must not be mistaken for one identical duration measure.

The nine complete post-startup diagnostics intervals cover 541 seconds and 69,974 processed
events at 131 received events/second. Their p95 histogram bounds are 0.5 seconds for all processed
events and 0.25 seconds for critical events. Maximum lag was 2.058/1.557 seconds, maximum queue
depth 492, maximum heartbeat 0.232 seconds and maximum storage pass 0.132 seconds. These are
observed bounds for this workload, not throughput guarantees or a controlled before/after trial.

Diagnostics retained 221 minute records from earlier boots, including the failed window. The
current recorder had zero skips, an empty queue, no error or early eviction, and used 1.789 MB
against its separate 512 MiB budget. Physical E: headroom was 22.51 GB. No helper, test or profiler
containers remained, and Docker PID 7908 was still the sole port-8765 listener.

The auto-season countdown progressed from 3,533 to 2,947 seconds remaining, with the same
eligibility timestamp and 22:28 UTC target. It was progressing rather than restarting or stuck.
The paper drawdown stop remained active, with unchanged 298.270801 USDC equity and no positions
or pending orders. Recent Entry coverage reached 411/1,000 (41.1%); activation remained blocked.

### Next observation acceptance

The next four-hour Shadow observation should include actual fit publications, the automatic
season boundary and subsequent normal position activity. Review build/boot/configuration/season
identities together, not just uptime or a green HTTP health response. Compare traffic rates and
lag distributions as well as the worst intervals; retain any expiry/shedding bursts and gaps.
Check queue recovery, training failures or repeated stale jobs, provider/reserve-refresh failure
reasons, physical disk headroom and diagnostics-budget behavior. Verify the countdown advances
and the boundary's ledger/retained learning remain consistent. Entry must continue to satisfy
all model and forward-proof gates before activation can become available. A shorter clean
window cannot establish long-term stability, strategy improvement or future qualification.
