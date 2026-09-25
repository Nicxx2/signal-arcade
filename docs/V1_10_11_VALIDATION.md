# v1.10.11 validation — 18–21 September 2026

Status as of **21 September 2026**: the release reliability and support-explanation follow-ups
have been deployed locally through Settings preparation; see the
[latest rollout checks](#release-reliability-live-rollout--21-september-2026).
The optional **55% coverage extension** remains deployed; see its
[rollout checks](#optional-55-coverage-live-rollout--20-september-2026) and
[validation and remaining evaluation](#optional-55-coverage--20-september-2026).
It includes the preceding provider recovery, learning presentation, configurable coverage and reliability work.
Earlier results apply only to their named builds. No public release was made by this work;
community publication remains on hold for longer live review. Burst reliability and limited
host disk headroom remain open concerns; the earlier 90 GB report is not the current baseline.

The community coverage default remains **70%**, with explicit prospective **65%, 60% and 55%** native
skill selections. The deployed build offers 70/65/60/55. The 55%-extension rollout
preserved the existing local selection of **60%, revision 1**;
the subsequent [read-only edge review](#post-rollout-edge-and-polish-review) observed a separate
selection of **55%, revision 2**, at 09:27 BST on 20 September. The 21 September reliability rollout
preserved that selection. Coach remains at 70%, and saved artifacts retain
their own contracts. The initial coverage-feature
rollout preserved 70%, revision 0. Earlier fixed-70% invariants below describe that preceding work;
they do not override the [current coverage scope and transition rules](LEARNING.md#configurable-skill-coverage-v11011).

## Baseline and invariants

- Clean starting checkout: published v1.10.10, commit
  `2ad309ec3cf84e8f32b1b610376b0d0f2fe4e32f`.
- Live baseline at 10:12 BST: healthy, all seven reported workers running, no trainer
  error; 2,417 fits published. Queue 112/10,000, current overall lag 0.344 s and
  critical lag 0.074 s. The preceding one-hour window had no shed or expired events.
  These are observations, not performance acceptance thresholds.
- Earlier read-only review found 211 retained route probes with only two open
  positions. Most of their approximately 388 KB JSON belonged to closed holdings.
- Live collection was configured for five routes per request and a ten-second
  interval. Increasing that setting remains conditional on collection and latency
  evidence. The existing default and maximum are twenty routes.
- Host free space was approximately 3.4 GiB on C: and 1.9 GiB on E:. Validation
  reuses installed runtime layers and temporary test databases, not a live database copy.
- The paused v1.11 twin-portfolio workspace is excluded.

Preserve schema 16, ledger and terminal evidence, real quote failures, fixed checkpoint
deadlines, all five horizons, three-Policy/one-Discovery scheduling, chronological
validation and embargoes, training/Policy separation, 70% coverage, Champion permission,
fresh activation proof and fixed failed recovery windows. Diagnostics remain observational.

## Stage gates

1. Probe retention: exercise both cleanup boundaries, closure with no future watchdog
   target, same-mint re-entry, late responses, unchanged active and saved proof, legacy
   unidentified probes and holdings whose sale has not committed. Then run terminal,
   season, profile-transition and reserve-validation regressions.
2. Dashboard: measure remaining work and optimise only with consistent input snapshots;
   retain coalesced refreshes, bounded cache reuse, cancellation ownership and stale timestamps.
3. Collection: retain post-fetch safety rejection; distinguish rejection reasons and
   request/lock/validation time before considering tuning. Compare slow providers,
   account limits, route changes, deadlines and both lanes, not only five-minute coverage.
4. Regression/release: complete relevant backend, frontend and static checks in isolation.
5. Rollout: verify exact runtime configuration and recoverability, deploy only the app,
   check startup and evidence continuity, and record any limits on sustained observation.

## Validation environment

The disposable test image adds pinned repository development tools to the existing
v1.10.10 runtime. Tests mount source read-only, replace `.env` with an empty test file,
have no network or live data mount, and use a one-CPU limit and temporary filesystems.
An initial runner attempt inherited the runtime's non-local bind default and failed
Settings validation. The runner now removes deployment-only environment defaults;
no production code was changed to accommodate that setup failure.

## Probe retention — passed

114 tests passed across probe retention, automatic seasons, profile transitions,
terminal evidence, checkpoint/watchdog reserve refresh and PumpSwap recovery.
Cleanup runs at existing heartbeat/watchdog boundaries, including with no remaining
holdings. Identified probes cannot survive same-mint re-entry, and late requests for
an old position cannot overwrite the new position's probe. Legacy unidentified probes
remain subject to the existing validator. The API structure and saved evidence are unchanged.

## Dashboard investigation

An isolated one-CPU synthetic snapshot with 1,001 Discovery observations and 1,000
Policy episodes took 0.188 s under cProfile; learning status accounted for most measured
work. This does not reproduce the live history or explain every earlier multi-second
snapshot. No lock removal or whole-learner copying is justified by this fixture.

Four bounded section timings distinguish portfolio, history, learning and advisory work.
The first diagnostics regression caught that adding these to interval phases exceeded
the existing compressed record budget. They were moved to a separate, low-priority
five-minute cumulative detail event. Existing payload, queue and retention limits remain.
Measurements are published on the event-loop owner only after its worker has joined,
including failure/cancellation; disabled diagnostics avoid section timing work.

The revised dashboard/diagnostics/cancellation group passed **116 tests**. No whole-snapshot
lock removal, longer cache lifetime or evidence-population cache was introduced.

## Collection — passed

**102 tests** passed across the new collection measurements, existing scheduler/capacity,
deadline/restart recovery, reserve-contract, enrichment-boundary and diagnostics checks.
Real mixed-venue batches of 5, 10 and 20 routes were exercised with response ages of 4.9 s,
5 s, 5.000001 s and 8.000001 s, five seconds before a checkpoint's original deadline.
The exact deadline remains inclusive; a later observation is unavailable and a response
older than eight seconds is rejected. Source feature state and the broker remain untouched.
All nine post-fetch guard reasons identify the fetched-batch subset of aggregate guard deferrals.
Complete runtime-detail events, including large counters, fit the existing event byte limit.

No live batch/interval tuning or fetched-result replay is included. The recent baseline
does not establish a live benefit sufficient to justify increasing work per request.
Existing rotation, Policy priority, quota/backoff, account limits and safety rejection remain.

## Full regression and release checks

- **1,860 backend tests passed**, including all skill promotion, chronology, fixed recovery,
  maintenance/restart, diagnostics and collection regressions. One existing Starlette/AnyIO
  deprecation warning remains. The tests used temporary databases and no network/live data mount.
- **413 frontend tests passed** across 22 files with two workers. TypeScript/Vite production
  build passed. ESLint had no errors and one existing EquityChart fast-refresh warning; the
  build retains its existing large-chunk warning.
- Ruff lint and formatting passed for backend/tests; mypy passed all 43 source files.
- `pnpm audit --prod --audit-level high` and the CI `pip-audit .` check found no known
  vulnerabilities. The disposable Python auditor needed an executable temporary directory
  and explicit temporary cache; production filesystem security was not changed.
- Final review verified that queued runtime detail owns copies of cumulative timing lists.
  The existing recorder already serialises/detaches event payloads; an explicit producer copy
  and regression make this ownership contract clear, rather than fixing a proven historic loss.
  Later measurements cannot mutate an already queued event.
  **28 snapshot/collection tests passed** after this final correction; formatting was then normalised.

During full validation, the still-running v1.10.10 encountered a burst. At 10:29 BST the
recent five-minute window recorded 5,397 expired candidate events and zero shed events;
the queue had already recovered to 49, overall lag 0.021 s and critical lag 0.005 s.
The isolated backend test container was briefly paused, then resumed at half a CPU after
the frontend/type-check jobs completed. By 10:35 BST the five-minute window had zero losses
and the degraded flag had cleared. A single burst cannot establish causation; this is not
evidence of v1.10.11 performance because the old build was still running.

## Packaged image and recoverability

The normal Dockerfile built the local `linux/amd64` image `signal-arcade:v1.10.11`:
`sha256:cfff2edb642e14a6b9b8c63d20811f1c811ffc4e210854aa5e70f014acbbf8a4`.
All 45 installed Python/resource files match the checkout after newline normalisation.
The exact old image remains available for a same-schema code rollback:
`sha256:aceb11e17787c7f95aa28af0a54315679ec225ed1026775e27fe3aa6a68723e8`.
No image or GitHub release was published.

An offline, non-root, read-only-root smoke container passed health, authentication,
snapshot, diagnostics, Champion history, Results/Seasons and compiled-asset checks,
plus preparation/cancellation of an upgrade against temporary demo data. It retained
schema 16, all five horizons and the 70% gate. `pip check` found no broken requirements.
Its initial 128 MiB data filesystem correctly triggered the existing diagnostics
low-space pause (512 MiB minimum); the normal-write check uses a 1 GiB temporary
filesystem. That run successfully persisted and decoded the new `runtime_work` event
with all four dashboard timings. Neither smoke run mounts production data or credentials.

The production dependency comparison found only `idna` resolving from 3.19 to 3.20,
besides the app version. A further full regression ran against the **installed release
package**, with pinned test helpers in RAM, no network and no replaced runtime dependencies:
**1,859 passed**, with the version-alignment check finding that the README omitted the
future public tag while explaining the unpublished release. The README now names that tag
without claiming publication, and the version check passed separately: **all 1,860 tests
passed across those runs**. This closes the gap between testing source on the old runtime
and testing the final package. The extra README sentence is documentation only; installed
code/resources are unchanged.

A separate backup completed at 10:54:39 BST on D:, containing a consistent 16,069,726,208-byte
schema-16 main database, a separate consistent diagnostics database, provider-settings
file and the pre-existing historical database backup. SQLite's backup API read the source
through a read-only mount/read transaction; running WAL files were not naively copied.
Main and diagnostics are separate snapshots, not one simultaneous volume snapshot.
The destination has restricted local-user/System access. File sizes and the main schema/table
metadata were readable and matched the backup manifest. A full read-only SQLite `quick_check`
on the copy exceeded its five-minute verification budget and was stopped; **full backup
integrity verification is incomplete**, not a reported corruption failure. Do not represent
this copy as restore-tested. The existing image/current-volume code rollback is independent
of restoring this older snapshot, which would discard later activity.

Before deployment, strictly bounded read-only checks of the backup's `settings`, `positions`,
`paper_seasons` and `challenger_skill_states` tables each returned `ok`; manifest file sizes
and schema 16 also matched. These are partial checks, not whole-database integrity or a restore test.

## Local live rollout

After the user's explicit deployment request, the app was replaced using the already-built
image; no further image pull, build or data-volume copy was required. E: began with approximately
1.9 GiB free and reached approximately 0.51 GiB after packaging. The 18 cache records created by
this build were removed by exact ID (about 1.15 GB); no older cache, image or excluded
workspace was pruned. Discarding the freed Docker filesystem blocks did not return
physical space to Windows. Both release/rollback images remain available. Live database
and WAL file sizes stayed stable during backup. Physical host space was a reliability concern
at this stage even though the Docker filesystem reported room; the later storage update below
resolves that observation. Broad cleanup or disk compaction was not performed by this upgrade.

The exact **Settings → Prepare for upgrade** API action reached **Ready** at 11:08:01 BST.
A snapshot generated after that boundary confirmed a stopped paper engine, no pending orders,
the existing held position and the saved season/authority state. Only the app container was
replaced, retaining the existing Compose project, data volume and configuration.

The first attempt did not pass Docker health: Compose returned `unhealthy` approximately
96 seconds after startup, before the requested 180-second wait limit. The process had not
exited itself. Automatic rollback restored the exact v1.10.10 image on the same current
volume; fresh checks confirmed all seven workers, position, cash, season and Sizing authority.
The failed container's application log was not retained, so its precise startup bottleneck
is unconfirmed. Slow cold startup/resource pressure is a hypothesis, not a demonstrated cause.

A single monitored retry used a new Settings preparation at **11:13:31 BST**, preserved startup
logs and allowed the full bounded 180-second window while retaining the unchanged health check.
The app server started at 11:13:52; Docker's first successful health sample was 11:14:15, and
the deployment observer confirmed it by about 51 seconds. No health check, resource protection,
schema or trading gate was weakened. The Settings operation reports **completed / restarted**
on **v1.10.11**, with normal freshness gates and the saved running preference restored.

Fresh post-upgrade checks at 11:14:39 BST confirmed:

- Season 57's identity and locked profile, the held position identity/units/entry receipt,
  cash of 308,306,966 lamports and starting bankroll of 400,000,000 lamports match preparation.
- Sizing Champion v8's exact artifact, consent and automatic participation remain unchanged.
  The existing drawdown halt remains in force. Entry and Manipulation are collecting proof;
  Exit v1 remains suspended, and Coach is inconclusive.
- All seven workers are running. Schema 16, all five horizons and the 70% requirement remain.
  Snapshot, diagnostics, Champion history, Results, Seasons and frontend assets return successfully;
  unauthenticated snapshot access still returns 401. The served JavaScript includes the new wording.
- The exact tested image ID is running as `arcade`, with a read-only root, the same tmpfs,
  dropped capabilities, security options, port and persistent data volume. Compose environment
  values match. Ollama was not replaced or restarted; its start time remains 10 September.
- Diagnostics are recording without errors. A bounded read of saved events decoded the new
  `runtime_work` record with all four dashboard and four RPC timings under the new boot identity.
  One held-position probe and zero retained closed-position probes are present. Restart itself
  empties the map, so this observation alone does not prove cleanup after future closures.

Eight serial health samples at 45-second intervals from **11:15:37 to 11:20:52 BST** all
reported healthy workers and no degraded state. Their recent five-minute windows recorded
zero shed and zero expired events. The final window received 49,057 events and processed
48,510, with lag p95 in the 0.5-second bucket; received and processed are separate window
counters and need not match. Sampled queue depth ranged from zero to five. These sampled
depths are not the maximum queue depth between requests and do not establish burst capacity.

The final fresh snapshot at **11:21:13 BST** still passed every continuity comparison. At the
final health check the queue was zero, current lag 0.013 s and critical lag 0.024 s. Collection
had accepted 118 routes/checkpoint updates from 39 requests with zero worker errors. Three
fetched batches were discarded by the unchanged maintenance guard. The four total maintenance
deferrals include those three post-fetch rejections and one pre-selection block; the counters
must not be added together. A second persisted `runtime_work`
event confirmed the cumulative timings and the first such discard under the same boot.
Diagnostics had no dropped records or errors, and the container had zero restarts and no
application warning/error in the bounded startup-to-check log.

The trainer remained healthy and had correctly skipped the startup fit-readiness check.
The fresh snapshot reported **four more eligible outcomes needed** before the next fit;
no new fit/publication occurred during this observation window. This validates readiness
reporting and resumed collection, not a completed live training cycle. Current operational
Entry coverage was **556/1,000 (55.6%)**, still below 70%; it is not fitted-model coverage.
No Champion was forced, and none of these short-term measurements prove a coverage gain.

Host free space at 11:21 BST was approximately 4.96 GiB on C:, 6.36 GiB on D: and
0.51 GiB on E:. The README and this record were updated after deployment; those final
documentation-only edits do not change the tested/installed application code.

At 11:00 BST the untouched live v1.10.10 still reported all seven workers healthy, no
trainer error and zero expired candidate events in its recent five-minute window. The
queue was zero, current overall lag 2.482 s and critical lag 0.026 s; these are separate
signals, not a claim that every event had low latency. Sizing v8 remained the saved active
Champion; Entry/Manipulation were collecting proof, Exit v1 stayed suspended after its
failed fixed recovery trial, and Coach was inconclusive. Stale idle snapshots were excluded
from claims about current coverage or performance.

The short live observation is separate from the isolated regression results. It cannot establish
sustained burst capacity, a coverage improvement or future Champion qualification. Full backup
integrity/restore verification remains outstanding operational work. The later storage update
below resolves the earlier E: headroom concern.
Larger collection batches, buffered responses and snapshot lock changes remain conditional
research ideas, not silently included optimisations.

## Additional edge-case recheck — 11:26 BST

Following the deployment, **198 focused tests passed** in the existing isolated test image,
using read-only source, no network or live data, temporary RAM-backed databases and a half-CPU
limit. They cover position closure/re-entry and late RPCs; snapshot failure/cancellation and
worker ownership; all nine post-fetch guards; exact deadlines and stale responses; duplicate,
cancelled, interrupted and failed upgrade preparation; diagnostics full-disk, read-only,
oversized-record and queue-pressure behavior; training/publication cancellation; and fixed
Champion recovery windows/permission guards. The existing Starlette/AnyIO deprecation warning
remains. Both temporary check containers exited and were removed.

A further deterministic 2,000-case payload check varied independent timing values and all nine
discard counters, including extreme counts. No payload exceeded 768 compressed bytes; maxima
were 552 bytes for the normal-count sample and 599 for the extreme-count sample. This supplements
the regression fixtures; it is not an exhaustive proof over every possible numeric combination.

The review found and corrected a **documentation interpretation error**, not a runtime counter
failure: `deferred` already includes both admission blocks and post-fetch rejections.
`discarded_by_reason` identifies the post-fetch subset. The earlier observation of four
maintenance deferrals therefore means three fetched-batch discards plus one pre-selection block,
not seven independent losses. README, diagnostics guidance and the earlier rollout paragraph
now state that relationship explicitly. No application code, live settings or image was changed.

The live trainer completed and published a new fit at **11:24:17 BST**, with no error; this closes
the earlier short-window limitation about not yet observing a complete live training cycle.
At **11:26 BST**, a fresh snapshot still matched position, bankroll, season/profile, Sizing v8,
consent and participation. All seven workers and Docker health were healthy, with zero container
restarts. Collection had recorded 184 checkpoint updates over 60 requests with zero worker errors.
Diagnostics were recording with zero dropped records, and the bounded application log contained
no warnings/errors. Operational Entry coverage remained 55.6%; no promotion requirement changed.

Latency was not uniformly near zero: a check during this period saw queue depth 153 and lag
1.705 s; the final check saw queue depth 2, lag 1.116 s and critical lag 0.198 s. The recent
five-minute window had zero shed/expired events, lag p95 in the 2-second bucket and no degraded
flag. These observations span natural traffic, a live fit and the limited isolated test load;
they do not identify the cause of a transient delay or establish improved burst capacity.
E: still had approximately 0.51 GiB free. Low physical host space and the unconfirmed first
startup bottleneck remain operational concerns; no live fault injection or further restart was used.

## Second edge-case recheck — 11:30 BST

Added 12 regression cases for previously uncovered combinations: actual disabled/demo/maintenance
and learner-identity changes while an RPC is in flight; repeated snapshot cancellation with a
queued successor and a late worker failure; cancellation of one browser sharing a refresh;
cancellation during RPC request/application, including an application worker that fails after its
temporary-data commit; non-finite timing values and saturated counters; and the exact 300-second
detail cadence boundary while proof events occupy every slot.

**46 tests passed** across the new cases and the adjacent probe, snapshot and collection suites.
Ruff lint and formatting passed for the new test file. Tests used the existing half-CPU isolated
tooling image, read-only source, temporary RAM-backed databases and no network/live-data mount.
No application code, live configuration, image or running service was changed. No new defect was
identified; the earlier counter-documentation correction remains the only correction from these
two post-rollout reviews.

At **11:30 BST**, a fresh snapshot again passed every recorded continuity comparison. All seven
workers and Docker health remained healthy with zero restarts. Three fits had completed and
published since boot, the latest at 11:28:36, with no training error. Collection had recorded
241 checkpoint updates over 80 requests without worker errors; diagnostics had no dropped records
or errors. The one held-position probe remained, with no obsolete probes.

The recent five-minute window had zero shed/expired events. Current queue depth was four,
overall lag 0.067 s and critical lag 0.185 s, but window p95 was in the **five-second bucket**.
Latency has not been proven uniformly low. Current operational coverage was 565/1,000 (56.5%);
this small moving-cohort change cannot be attributed to the upgrade. The 70% requirement and
all other qualification/permission checks remain intact. At this checkpoint, host space and
the first startup were still unresolved concerns; the storage update below supersedes the former.

## Storage and release-readiness update — 11:40 BST

After the user freed space, a fresh Windows filesystem check confirmed **91.28 GiB free on E:**.
The earlier 0.51 GiB readings remain historical rollout evidence and are no longer a current
release blocker. This does not establish the cause of the first unsuccessful startup.

Version declarations in the backend, Python/project/frontend metadata, Dockerfile and README
all identify v1.10.11. The implementation, regression results, edge-case checks and local
deployment are documented. Working-tree whitespace checks pass, and local credentials and
private test/rollout artifacts are ignored by Git.

This is a **tested release candidate**, with community publication intentionally delayed for
the scheduled live review. The changes are still local and uncommitted; HEAD/tag remain v1.10.10.
No v1.10.11 GitHub release or public container image has been published. The README consequently
still pins the available v1.10.10 public image in its Docker Hub quick start and clearly explains
how the local v1.10.11 build differs. Publication will require the final evidence review, any
justified corrections, the release commit/tag and public image validation/publication, followed
by updating the public quick-start tag and publication wording. Do not advertise a sustained
performance, coverage or trading improvement that the observation has not established.

## Final confidence audit — 11:47 BST

Re-read the complete implementation diff against v1.10.10 and checked the new regression
coverage. No new functional defect was identified. The optional runtime detail is appended
immediately before synchronous recorder collection under the existing event boundary;
there is no asynchronous gap in that path allowing it to displace a later proof event.
The diagnostics guide now qualifies its 288-row daily estimate: process restarts reset
the detail cadence and can add initial emissions. This is a documentation clarification,
not an application or retention-policy change.

A fresh read-only comparison of the running container matched all **45 packaged Python
and resource files** and all **nine frontend build files** to this checkout, with no
missing or differing files (backend text comparisons normalize Windows line endings).
Docker still reported healthy, zero restarts, and the same v1.10.11 image and boot.

At **11:44 BST**, the fresh live snapshot was 2.23 seconds old, all seven workers were
healthy, and every prepared-state continuity comparison passed. Seven training runs had
completed and published since boot, with no reported training or RPC worker error.
Diagnostics reported no errors or dropped records. The recent five-minute window had
zero shed/expired events, no degraded flag and lag p95 in the two-second bucket.
Operational Entry coverage was 568/1,000 (56.8%), still below the unchanged 70% requirement.
These checks support consistency and short-term health; sustained burst improvement,
new Champion qualification and profitable trading remain unproven. The first unsuccessful
startup's cause and a complete backup integrity/restore exercise remain unresolved.
Only documentation was amended during this final audit; the live app was unchanged.

## Natural-traffic follow-up implementation — 18 September 2026

This section supersedes the earlier checkout/live hash match: the running candidate has not
been redeployed with these later fixes. Version remains **1.10.11**, locally uncommitted and
unpublished. The initial deployed image and its rollback remain unchanged. No live settings,
database records, seasons, gates, permissions or services were changed during this work.

The 15:55–15:57 BST read-only review found continuing Discovery expiry, routine-storage RPC
guard collisions, diagnostic omissions and an 89-second-old dashboard response. These are
investigation evidence, not proof that every missed checkpoint is recoverable. Current cohort
coverage remained below 70%; Entry/Manipulation/Exit still needed valid performance proof.

### Stage decisions and edge checks

1. **Reproduce first.** Three isolated tests failed on the preceding candidate: a second
   optional storage event evicted a training summary; a writer-lock deferral halved the
   cleanup chunk from 50 to 25; requests during storage left no shared refresh queued.
   These fixtures establish those mechanisms, not the cause of every observed live spike.
2. **Diagnostics.** Give training/proof priority within eight slots and attribute losses
   with fixed counters. Two publications can still overflow; losses remain visible.
   The first gate passed **130 tests**, including export limits and pressure/failure handling.
   A later stronger high-counter/full-payload fixture caught insufficient interval headroom:
   loss counters were moved to optional `diagnostic_loss` events instead of enlarging intervals.
   A separate flag preserves recording-gap reporting even when counters saturate. Per-event
   compression omissions remain separate from input-event and whole-interval losses. The
   corrected diagnostics gate passed **70 tests**, including original full interval/hour
   payloads and high-counter optional detail. Arbitrary oversized legacy payloads can still
   be rejected under the existing fixed budget; no promise of lossless diagnostics is made.
3. **Cleanup/RPC coordination.** Measure query, writer-lock, worker and dispatch/resume time.
   Adapt chunk size from query work while retaining the original absolute deadline. Nonurgent
   cleanup can briefly defer for an admitted RPC, with recent capacity evidence and an
   eight-second bound. Unknown/urgent capacity and upgrade preparation bypass that deferral.
   Existing post-fetch safety checks remain intact. **210 tests passed**, then **three** extra
   deadline/attribution/payload cases passed. The controlled collision completed usable outcomes
   in both Discovery and Policy; cleanup resumes afterward. Urgent work, persistence ordering,
   cancellation, failures and continuous-stream cleanup remain covered. This is deterministic
   behavioral evidence, not a p95/p99 or live throughput comparison.
4. **Dashboard.** Retain one shared refresh waiter through storage work without owning the
   market lock while waiting. Keep current-state reads inside the existing boundary and report
   stale timestamps honestly. Measure residual assembly work as `snapshot_other`. **110 tests
   passed**, including multiple clients, cold cache, cancellation, storage/refresh errors,
   retry and context changes while waiting. No health, permission or activation cache was added.
5. **Collection capacity review.** Keep the current settings, deadlines, account limits and
   Policy/held-position priority. Existing 5/10/20-route boundary tests passed in stage 3.
   Additional timely collection in a controlled collision does not establish a benefit from
   increasing the live batch or creating a result buffer. Neither was implemented.
6. **Coach review.** Preserve all existing studies, enrollment rules and terminal outcomes.
   A new prospective multi-season design remains separate: strict serialized study models
   need an explicit forward/rollback contract and outcome-independent enrollment design.
   Do not reopen inconclusive studies or failed recovery windows to seek passing results.
7. **Final validation and release review.** See the final results below. The public quick-start
   remains on the published v1.10.10 image. No release commit/tag, push, container publication
   or live deployment is part of this follow-up.

Tests use the existing tooling image, half a CPU, bounded memory, read-only source, an empty
credential-file overlay, no network and no live-data volume. Temporary databases live in RAM.
These limits reduce test load on the shared host; they do not provide physical hardware isolation.
The initial diagnostics test process failed before Python startup with an allocation error;
its retry completed. A small follow-up container also exercised the real diagnostics free-space
guard because its temporary filesystem was below 512 MiB. The corrected diagnostics subset
passed with 1 GiB of temporary space. The complete run then reached 870 passes before the
large WAL/export fixture was refused by the store; cumulative temporary databases had exhausted
the usable test headroom. Full-suite validation was rerun with a 3 GiB temporary filesystem and
a 3.5 GiB memory cap, still limited to half a CPU and without network/live data. Production
free-space and byte limits were preserved; no application change was made for this harness issue.
After the formerly failing fixture passed, a bounded capacity check measured 523 MiB of
accumulated temporary data and 2,548 MiB free in the larger test filesystem.

Frontend validation used the already installed pinned tools directly because this checkout
lacked the Windows `vitest` launcher; sandboxed startup also blocked a required child process.
The permitted one-worker run passed **413 tests across 22 files**. TypeScript/production build
and ESLint passed; existing large-bundle and EquityChart fast-refresh warnings remain.

The final complete backend suite passed **1,902 tests in 441.74 seconds**, with the existing
Starlette/AnyIO deprecation warning. This includes all new regressions and the unchanged Coach,
skill lifecycle, recovery, chronology, provider and accounting suites. Ruff lint passed,
all **147 Python files** passed formatting checks, and strict mypy passed all **43 backend
source files**. `git diff --check` passed. Credentials, private validation logs and generated
frontend output remain ignored; no dependency lockfile, live configuration, learner contract
or permission change was introduced. Version declarations consistently remain **1.10.11**.

The selected local implementation and validation stages are complete. Tests establish the
controlled behaviors described above; they do not establish sustained live performance,
absence of every regression, 70% operational coverage or future Champion promotions.

At **16:26 BST**, serial bounded health/diagnostics GETs and Docker inspection confirmed the
unchanged image `sha256:cfff2edb642e14a6b9b8c63d20811f1c811ffc4e210854aa5e70f014acbbf8a4`,
the same 10:13:33 UTC boot, zero restarts, and all seven monitored workers running. E: retained
**91.28 GiB free**. The old build reported seven cumulative diagnostic drops, no recorder error,
and an 82.55-second acknowledgement age. Queue depth was 1,863 and the last processing-lag
sample was 0.275 seconds. These non-atomic samples establish liveness only; diagnostic delay
and prior gaps must not be interpreted as healthy latency observations. No fresh comparative
paper-performance claim was made during implementation.

Before any later deployment, repeat a current backup/restore-readiness check and use Settings
prepare-for-upgrade, retaining startup logs and exact rollback identity. The old first-start
failure and full backup restore exercise remain unresolved historical limitations. Natural
traffic validation must compare mature, comparable cohorts, including fees and drawdown.
This work does not demonstrate higher live coverage, better returns or new Champion eligibility.

## Additional boundary review — 18 September 2026

A further local edge review found one diagnostics race: the background writer can reject an
interval between the recorder's separate reads of its loss counter. The old sequence could
advance the comparison watermark without setting a recording-gap flag in either interval.
A deterministic interleaving test reproduced the problem. Collection now captures the count
once and uses that same value for its flag, saved gauge and next comparison. A rejection after
that capture is reported in the next successfully captured sample. This changes diagnostic
metadata only; no learning evidence, trading decision, queue limit or storage budget changes.

The review added **10 tests**, covering that race, the exact eight-second deferral limit,
capacity freshness at and beyond 60 seconds, future capacity timestamps, capacity at and above
the cleanup target, overlapping RPC cancellation, repeated refresh-waiter cancellation and
recovery, and SQLite failure cleanup. The SQLite test verifies that a failed delete releases
the writer lock and removes the progress handler before later database operations. Before the
fix, nine tests passed and the writer-counter race test failed; afterward, the focused backend
regression run passed **206 tests in 76.06 seconds**, including all ten new tests. The existing
Starlette/AnyIO deprecation warning remains. Ruff lint passed, all **148 Python files** passed
formatting checks, strict mypy passed all **43 backend source files**, and `git diff --check`
passed. The tests and static checks used isolated containers with no network or live-data access.

The complete **1,902-test** backend run and **413-test** frontend run above are the preceding
implementation baseline, not a new full-suite run after this diagnostics fix. No frontend
code changed in this review. The live app remains on the earlier deployed candidate; this
fix and the other natural-traffic follow-up changes remain local and unpublished. The 70%
gate, valid failures, chronological validation, training/proof separation, Champion permissions
and held-position/Policy priority remain unchanged. Passing these boundary checks does not
establish sustained live improvement or rule out every possible regression.

## Follow-up live rollout — 18 September 2026

The user authorized deployment of the reviewed follow-up and final diagnostics race fix.
This section supersedes the earlier local-only status. No application code changed during
rollout. The source remains uncommitted, and no public image, GitHub push or release was made.

- Built the repository Dockerfile with its frozen frontend lockfile. The 45 installed backend
  and resource files matched the checkout byte for byte. Installed Python dependency versions
  matched the previous live image. An isolated, network-disabled demo instance passed health,
  authentication, dashboard assets, learning/history pages, schema 16, the 70% gate and the
  Settings prepare/cancel smoke checks before replacement.
- Deployed image: `signal-arcade:v1.10.11-followup-20260918`,
  `sha256:99c249bd273e0de03b2a27a5de93cbab9ab0b78a9069a40007f62105efb98b6a`.
  Diagnostics build fingerprint:
  `82e3c3bbab7913f89581bc2f9e13ff69a3c490969e12492a15ab92b1a2bac58f`.
- Immediate rollback remains `signal-arcade:v1.10.11`,
  `sha256:cfff2edb642e14a6b9b8c63d20811f1c811ffc4e210854aa5e70f014acbbf8a4`,
  on the same current `solana-signal-arcade_signal-arcade-data` volume. The older v1.10.10
  rollback image was also retained. Ollama and the paused v1.11 workspace were untouched.
- Settings operation `a95f8e8c3ab34007b701fdbc4dfcf51e` reached **Ready at 17:03:47 BST**.
  The replacement container started at **17:04:02 BST**, application startup finished at
  **17:05:01 BST**, and the rollout observer saw the unchanged Docker health check pass after
  82 seconds. There were zero restarts and no rollback. Startup logs were retained privately.
  The operation reported `completed`, with the paper engine resumed using its freshness gates.

Fresh backup snapshots were taken through SQLite's backup API with the source mounted read-only.
The separate backup volume is `signal-arcade-v11011-followup-backup-20260918`; its host copy is
stored outside the repository in a private `v1.10.11-before-followup-20260918` directory. It contains the
16,069,726,208-byte main database, the 93,089,792-byte diagnostics database and provider settings.
Manifest sizes and schemas matched. The four critical-state tables (`settings`, `positions`,
`paper_seasons`, `challenger_skill_states`) and the full diagnostics database passed SQLite
`quick_check`. A full main-database check exceeded its 180-second budget and was interrupted;
full main integrity and a complete restore rehearsal remain **unverified**. A helper permission
refusal while copying provider settings was resolved by copying as the owning app user, without
changing live files or permissions. E: retained **61.94 GiB free** after the host copy.

The first post-start snapshot at **17:05:38 BST** was fresh. Season 58, its profile, both held
positions and quantities, 347,695,887 cash minor units, starting bankroll, active Sizing Champion,
consent, automatic participation and risk-halt state matched the settled Ready snapshot.
The initial string comparison of the profile flagged JSON property order; a structural comparison
confirmed identical values. The private checker was corrected; no app change was needed.
All seven workers were running, authenticated pages returned successfully, and unauthenticated
snapshot access still returned 401. Operational Entry coverage was **456/1,000 (45.6%)**;
the current fitted Linear/XGBoost generation reported **400/1,000 (40.0%)**, a different cohort.
These values do not show a deployment benefit or satisfy the unchanged 70% requirement.

The first six saved diagnostic intervals covered startup through **17:11:04 BST**. They had
no recording-gap flag (the first interval was correctly partial), no shed/expired pipeline
events, a maximum observed queue of 644, maximum overall lag of 3.70 seconds and maximum
critical lag of 1.43 seconds. No recorder or writer losses were reported. The new snapshot
section timings, `snapshot_other`, maintenance-source field and storage query/lock/dispatch
timings were present in saved events. An absent source within the maintenance-source field
means zero at that sample; later lightweight status had two maintenance deferrals and zero
post-fetch discards. These are separate, non-atomic samples, not contradictory counters.

The first scheduled cleanup period completed bounded passes and removed old raw events. At
17:11:34 its current chunk was 38 rows, with a last completed pass of 0.079 seconds; query work
was 0.038 seconds and writer-lock wait 0.012 seconds. This is a single pass, not a latency
distribution or proof that cleanup can always keep up. A dashboard request after several idle
minutes first returned a 353-second-old cached view and then a 2.62-second-old refreshed view
on the bounded retry. The stale response was not counted as healthy freshness.

The later cash balance changed because of a normal paper round trip. Its two fee-inclusive
receipts exactly reconciled the 3,015,247-minor-unit USDC cash change, and the execution audit
reported `verified` with no issues. One round trip does not establish better decisions,
profitability or a comparable before/after cohort.

At 17:11:34, collection had made 29 RPC requests and 88 checkpoint updates without an RPC
worker error or post-fetch discard. Operational coverage was 45.7%, while fitted coverage
remained 40.0%. The latest saved lane counters showed 37 usable Discovery checkpoints and
10 usable Policy checkpoints, with 17 Discovery expiries and zero Policy expiries. Sixteen
Discovery expiries had unknown pre-restart attempt history; the remaining one had a route
identity failure. These are checkpoint counts across horizons, not independent training rows,
and do not prove recoverability or a coverage improvement.

No new fit had published in the first six minutes of active runtime. The preserved five-minute
clean-stream requirement precedes enrolling fresh learner rows, whose primary outcome is
another five minutes later. The trainer had no pending job or reported error at that point.
The rollout therefore included a short additional observation window without forcing training
or relaxing warmup, chronology or proof requirements.

That additional check observed a natural fit/publication complete at **17:15:48 BST** in
6.71 seconds, without an error or stale-job discard. The next saved diagnostic interval
contained its training summary and all six proof records: Entry Linear/XGBoost, Manipulation,
Sizing, and deterministic/contextual Exit. Sizing v8 remained the active healthy Champion;
Entry/Manipulation still failed coverage and performance requirements, contextual Exit still
failed timing advantage, and the existing Exit suspension and inconclusive Coach study remained
intact. A qualifying fitted artifact is not itself permission or sufficient forward proof to
activate; the deterministic Exit proof record did not bypass that distinction.

The final bounded check at **17:16:39 BST** saw all workers running, the exact deployed build,
a 1.44-second-old dashboard and a 17.66-second diagnostics acknowledgement age. Eleven saved
intervals through 17:16:21 covered 99,868 processed events, zero shed/expired pipeline events,
maximum queue 1,020, maximum overall lag 4.07 seconds and maximum critical lag 2.66 seconds.
Only the initial partial-interval flag was present; no gap, compression-omission flag, recorder
loss or writer loss was reported in this sample. Collection had made 57 requests and 161
checkpoint updates, with zero worker errors or post-fetch discards. Six maintenance deferrals
remained valid guard checks. Operational Entry coverage was **458/1,000 (45.8%)**, and the newly
fitted Entry/Manipulation cohort had **401/1,000 (40.1%)** coverage. These different moving cohorts
must not be interpreted as a causal uplift from deployment.

Cleanup had removed 32,814 old raw events; its chunk varied and was 12 rows at the final snapshot.
The last sampled pass was about 0.008 seconds with 0.0048 seconds of query work. Retention still
had a backlog, so sustained catch-up capacity remains a follow-up question. All three retained
position probes belonged to current holdings. Paper execution audit remained verified. No
additional application fix was justified by this short rollout observation.

The app is left running for normal traffic. README and release notes reflect the deployed build,
and whitespace checks pass. Community publication remains deferred until longer observation
covers stronger bursts, cleanup catch-up, repeated publications and mature comparable cohorts.
This rollout confirms operational continuity and a real learning cycle; it does not establish
70% reachability under every market, future Champions, sustained efficiency gains or profitability.

## Post-burst local candidate — 18 September 2026

The user authorized staged implementation after the evening review and edge-case plan.
This section records the **pre-deployment candidate validation**. During that implementation
pass, the running image remained `signal-arcade:v1.10.11-followup-20260918`. No live
configuration, database, model permission, season, threshold or service was changed during this work.

### Evidence and selected scope

The completed review through approximately 20:26 BST inspected 167 overlapping saved intervals
from about 17:22 onward. A natural burst peaked at queue 6,807, overall lag 20.06 seconds and
critical lag 8.56 seconds, with 985 candidate expiries and no queue-capacity shedding. Fifteen
intervals carried recording-gap flags. The recorder counted 26 lost events since boot: two
training summaries, ten proof records and fourteen storage events, all at input-event capacity.
Durable learning publications still completed. A missing diagnostic proof event is not a missing
authoritative artifact. The precise cause of the market-processing spike was not established.

The eight-event queue cannot hold two complete seven-event publications. Saved interval 92
contained publications about 16.81 and 57.66 seconds after the previous collection; interval 170
had them about 29.82 and 68.62 seconds after collection. The corresponding next collections were
68.40 and 72.97 seconds after the previous boundary. Two new integration regressions failed on
the preserved baseline, confirming that these timings lose protected diagnostic reports.

The selected implementation:

- Shares a monotonic deadline between the regular collector and admitted publication boundaries.
  Collection may move up to five seconds early to prevent protected-report displacement, at
  least 55 seconds after the last collection, while consuming the same nominal minute slot.
  It requires queue headroom and a running/recording writer, yields to pending sells and ordinary
  collection pressure, and leaves gaps over 90 seconds to the regular collector. Job validity
  and market admission are checked again after collection. Terminal jobs do not wait for it.
- Rechecks the regular collector's pressure and deadline after waiting for the event lock.
  Attributes collector/reporting exceptions while preserving saturated counters and explicit gaps.
- Adds fixed, worker-local measurements for broker work, decision serialization/lock/SQL/commit,
  and RPC validation, checkpoint persistence, immediate governance and pruning. Aggregation waits
  for worker ownership to end, including repeated cancellation. The three optional detail series
  preserve event/interval byte bounds and the 512 MiB budget; their extra event rows can shorten
  event retention. Nested timings and differing count units are documented explicitly.

No database schema, coefficient-fitting contract, receipt ordering, durability setting, acquisition
priority, batch default, provider spacing, grace period, 70% gate or Champion permission changed.
The timing wrappers do not defer per-outcome governance across a batch. Existing cleanup and
held-position probe protections remain intact.

### Stage gates and edge cases

1. **Baseline/reproduction:** preserved a credential-free copy and hashes of the existing dirty
   checkout; the starting HEAD remains `2ad309ec3cf84e8f32b1b610376b0d0f2fe4e32f` (v1.10.10), with
   v1.10.11 changes still uncommitted. The selected baseline suite passed **153 tests**. Both new
   observed-timing regressions failed before the fix. Windows bind-directory reads intermittently
   returned `ENOMEM`; validation moved to a source archive unpacked into container-local temporary
   storage. The test image's production bind defaults were cleared. Those harness failures did
   not modify the app or indicate failing application tests after environment correction.
2. **Diagnostic scheduling:** its stage gate passed **117 tests**. Cases include exact early/due
   and 90-second limits, ordinary-loop races, full/dead/paused writers, insufficient event slots,
   pending sells, pressure arriving at the boundary, stale/context-changed jobs, repeated cadence,
   malformed events, saturation, serialization/store failures and writer-loss races. Further
   final regressions cover fewer artifacts, terminal jobs, a rapid third publication's honest
   residual loss, and persistence/reload of a real fit through the new boundary.
3. **Work attribution:** its focused gate passed **122 tests**, covering failed SQL/commit,
   cancellation, concurrent contexts, disabled measurements, reporter failure, unchanged marks
   and assessments, payload saturation, proof priority and identical checkpoint values.
4. **Throughput optimization:** deferred by the plan's evidence gate. The saved timings do not
   yet identify a specific live calculation/transaction to change safely. There is no speculative
   transaction batching, authority cache, lock release or governance deferral in this candidate.
5. **Discovery capacity:** expanded the real equal-cohort application experiment to 20 routes at
   sizes 5, 10 and 20, with instrumentation on/off and both ordering directions. All cases retain
   the same checkpoint values and leave market state untouched. Existing slow-reply, exact-deadline,
   route-rejection and post-fetch guard tests remain in the gate. Live capacity/selection changes,
   including more detailed exclusion scanning, remain deferred; `no_rpc_selection` still does
   not establish a recoverable missed outcome. The live/default batch size remains five.
6. **Learning and permissions:** the combined collection/learning gate passed **364 tests in
   113.38 seconds**, including Entry/nonlinear eligibility, independent participation, composition
   proof, contextual Exit, Coach lifecycle/recovery and coverage/permission behavior. Passing
   fixtures can progress through the existing rules; training alone still cannot authorize influence.
7. **Integration/release:** final candidate results and packaging are recorded below. No public
   push or live upgrade is part of this implementation pass.

All test containers use no network or live-data mounts, temporary databases, one CPU and bounded
memory. Source archives exclude ignored files, including live credentials and databases. The
paused v1.11 workspace and old paused steward were untouched.

### Timing evidence and remaining limits

A bounded collector probe with 1,000 retained artifacts and 95 buckets measured 200 calls: median
3.56 ms, p95 6.11 ms and maximum 8.65 ms. This synthetic probe establishes a modest local cost,
not a hard runtime deadline or proof that publication-time collection can never add latency.

An initial small timing comparison was inconsistent at batch ten. A counterbalanced repeat
alternated measurement order across 12 cohorts per variant (72 total 20-route runs). Median CPU
seconds per cohort, off/on respectively, were 0.0541/0.0463 at batch five, 0.0577/0.0449 at ten,
and 0.0403/0.0407 at twenty. This did not show a consistent CPU regression; it also does not
show a causal speedup. Wall-time maxima remained variable, and the test call includes worker
dispatch/resume and harness overhead. Temporary-database, host scheduling and one-CPU container
effects differ from a busy live database. Do not use this experiment to increase live batch size.

Closely spaced publications and unavailable writers can still lose diagnostic detail. The
recording limits, counter units and retention tradeoff are documented in `DIAGNOSTICS_HISTORY.md`.
Fresh natural-traffic evidence is required after any later authorized deployment before claiming
better burst performance or recoverable coverage. At the evening review, operational coverage
was 47.5%, fitted Entry/Manipulation coverage was 44.0%, and 125 matched closed paper trades lost
30.912303 USDC after already-included fees. Those different cohorts are not performance proof
for this undeployed candidate.

Full main-database integrity and an isolated full restore rehearsal remain unverified from the
earlier rollout. Complete those recovery checks before declaring community-release recovery
readiness. Neither additional training nor these diagnostics guarantee 70% coverage, Champions
or profits.

### Packaged candidate and final checks

The repository Dockerfile built the local candidate image
`signal-arcade:v1.10.11-postburst-candidate-20260918`, image ID
`sha256:35e8e4b6bf5aebc9389dfb6995606afca33cfa51ff9a60807db167e1109a3af5`.
Its diagnostic build is `295166056508c68573b36f62bd1c45144e5c22fe9c3f45ed92e46e33c9dc2b0a`.
All 46 installed backend/resource files matched the checkout and packaged source byte for byte.
Installed Python dependency versions matched the preceding deployed image; no live `.env` was
included. The official build retained its frozen-lockfile frontend build, using cached layers.
No frontend code changed in this pass, and the earlier frontend test results were not rerun.

An isolated packaged-app smoke passed with a disposable demo database, temporary filesystem,
test-only admin credential, no external network, no published host port and no live volumes.
It verified startup and worker health, v1.10.11, schema 16, unauthenticated snapshot rejection,
authenticated snapshot/diagnostics/Champion journey/leaderboard/seasons, the two packaged assets,
the 0.7 coverage gate, and Settings maintenance prepare-to-ready followed by cancel. This does
not constitute a live upgrade or a full backup restore rehearsal.

The first complete backend run returned 1,962 passes and one failure in an existing diagnostics
scheduling test. That test patched only the orchestrator clock, while the shared deadline now
also reads the recorder clock. All three scheduling fixtures now use one deterministic clock
for both modules; no production change was needed. The corrected scheduling/publication gate
passed **67 tests in 9.82 seconds**. Ruff lint and formatting checks passed for all 151 Python
files; mypy passed all 46 source files. The corrected scheduling file was formatted and linted
again after that test-only fix. `git diff --check` passed.

The final complete backend rerun passed **1,963 tests in 211.80 seconds**, with one
Starlette/AnyIO `BlockingPortal` alias deprecation warning and no failing tests. Private logs
are retained under `.test-run-v11011/post-burst-*.log`; the final suite is
`post-burst-final-backend.log`. The final manual comparison against the preserved pre-stage
source confirmed unchanged learning decisions, per-outcome governance order, transaction/cache
boundaries and cancellation ownership. Version identifiers in the Python package, Python project,
root package and frontend package all remain `1.10.11`. The final host disk check reported
66,080,100,352 bytes free on E: (approximately 61.54 GiB).

Read-only inspection after the packaged smoke confirmed that the live container still used
`signal-arcade:v1.10.11-followup-20260918`, image ID
`sha256:99c249bd273e0de03b2a27a5de93cbab9ab0b78a9069a40007f62105efb98b6a`, with its original
`2026-09-18T16:04:02.085345206Z` start, zero restarts and a healthy container health check.
That identity check is not a new sustained-traffic or skill-proof review. No live GETs, update,
restart, settings change or public push were performed in this implementation pass.

## Post-burst live rollout — 18 September 2026

The user subsequently authorized the live update. This rollout supersedes the candidate's
local-only status. No application code changed during deployment. The private image pin and
rollout documentation were updated; the source remains uncommitted and nothing was pushed or
published. The paused v1.11 workspace, old paused steward and Ollama service were untouched.

### Backup, identity and Settings boundary

- All 46 current backend/resource files still matched the tested source archive. The deployed
  image is `signal-arcade:v1.10.11-postburst-candidate-20260918`,
  `sha256:35e8e4b6bf5aebc9389dfb6995606afca33cfa51ff9a60807db167e1109a3af5`. Its diagnostic
  build is `295166056508c68573b36f62bd1c45144e5c22fe9c3f45ed92e46e33c9dc2b0a`, boot
  `50fad90e4ca84ce28640f988e787051a`. The tag contains `candidate`, but this exact tested image
  is now the running local deployment.
- The previous image remains available as `signal-arcade:v1.10.11-followup-20260918`,
  `sha256:99c249bd273e0de03b2a27a5de93cbab9ab0b78a9069a40007f62105efb98b6a`.
  Same-schema code rollback retains the current `solana-signal-arcade_signal-arcade-data`
  volume; it must not routinely replace newer evidence with an older backup.
- A fresh read-only-source SQLite backup completed at **21:43:42 BST**, retaining the
  16,069,726,208-byte main database, 94,801,920-byte diagnostics database and provider settings.
  The separate volume is `signal-arcade-v11011-postburst-backup-20260918`; the host copy is
  stored outside the repository in a private `v1.10.11-before-postburst-20260918` directory.
  Manifest sizes and schemas matched. The four critical main tables (`settings`, `positions`,
  `paper_seasons`, `challenger_skill_states`) and full diagnostics database passed `quick_check`.
  These bounded checks do not establish full main-database integrity or a complete restore
  rehearsal. E: retained 33,775,030,272 bytes free (about 31.46 GiB) after the host copy.
- Settings operation `7bb157c13b3940b7acbb87542565a269` reached **Ready at 21:50:29 BST**,
  with no pending orders or cancelled orders. The replacement container started at
  **21:50:37 BST**; application startup completed at **21:51:34 BST**. The unchanged Docker
  health check passed after 82 seconds, with zero restarts and no rollback. Settings reported
  `completed`, and the saved running preference resumed with normal freshness gates.

The fresh snapshot at **21:52:24 BST** was 2.20 seconds old when inspected. All 17 continuity
checks passed: exact build, fresh snapshot, season 58, season profile, risk mode, starting bankroll,
323,078,426 cash minor units, both positions and quantities, active skill versions, consent,
automatic participation, risk-halt state, the 70% gate, Settings operation identity/completion,
restored running preference and probes belonging only to current holdings. The paper execution
audit remained `verified` with no issues. Authenticated history/learning pages and both packaged
assets returned 200; an unauthenticated snapshot still returned 401. A case-insensitive variable
name collision in the private PowerShell page checker was corrected and the checks rerun; no
application change was needed.

One Solana WebSocket protocol-close warning occurred at **21:52:00 BST**. By the saved snapshot
at **21:52:24 BST**, the stream was connected again with fresh messages, one reconnect, no retained
error and no fallback. This observed provider interruption is not evidence that the new timing
code caused a regression. Separately, the old build's pre-upgrade five-minute health window
recorded 97 candidate expiries and zero shedding during the host-backup copy. Backup I/O and
natural traffic confound that sample; it is not a post-upgrade performance result.

### Natural-traffic checks and unresolved pressure

Eight serial health/diagnostics samples from **21:52:59 to 21:58:14 BST** showed all seven
workers running, no training/RPC worker error, no reported diagnostic loss and no pipeline loss
in those sample windows. They were point samples, not a complete burst trace. A bounded saved
history read returned seven intervals (sequences 0–6) and 18 events; neither the 20-interval nor
60-event page limit was reached. These intervals captured queue 2,895, overall lag 9.93 seconds
and critical lag 7.09 seconds, with no shedding/expiry and only the expected first partial interval.

The subsequent recovery check found a later, more substantial burst. Saved sequence 7 lasted
**96.89 seconds**, carried an honest `recording_gap` flag, and recorded queue **3,130**, overall
lag **20.04 seconds**, critical lag **9.05 seconds**, **171 expired candidate events** and **zero
capacity-shed events**. At **22:00:12 BST**, the queue was back to zero, current overall/critical
lag was **0.050/0.008 seconds**, and every worker remained running. The health warning
`recent_candidate_shedding` was still active because that label includes recent candidate
expiries. It must not be reported as fully healthy history merely because the queue recovered.
The next bounded read returned that one additional interval and five events; event-page overlap
was not counted twice. No interval sequence hole was seen, but the long interval is still a gap
in sampled proof/equity/phase detail. Recorder/writer drop counts remained zero.

The final dashboard was fresh at **2.19 seconds old** and the diagnostics acknowledgement was
**10.65 seconds old**. A saved 85-second dashboard-age gauge preceded the closing on-demand
refresh; the actual requested dashboard recovered, so this is not proof of a stuck refresh.
The Solana stream was connected with fresh messages, one reconnect and no current error/fallback.
The container was healthy, with the expected image, unchanged start time and zero restarts.

Collection completed **207 checkpoint updates from 44 requests** with zero worker errors. Three
post-fetch batches were discarded for processing lag; they are a subset of guard deferrals,
not three additional losses. The batch default remained five. The last saved collection cohort
at approximately **21:57:16 BST** had 55 Discovery expiries across horizons (3/12/16/24 at
300/600/900/1200 seconds) and one Policy expiry at 1200 seconds ending at `rpc_identity`.
Most Discovery expiry-stage details were `unknown` after the restart; they must not be relabelled
as `no_rpc_selection` or recoverable missed outcomes. Checkpoint counts are not independent
training samples, and valid unavailable outcomes and original deadlines were retained.

No new fit/publication completed during this rollout observation. Six readiness attempts were
skipped as not due, with no training error or discarded job. The current model still needed
eight eligible primary outcomes before retraining: the model's exact-cohort readiness count,
not the number of RPC checkpoint updates, determines that condition. Thus the new publication
boundary passed isolated tests but has not yet been exercised by a post-deployment publication
in this observation. Entry and Manipulation remained collecting proof; Sizing Champion v8 stayed
healthy and active; Exit remained suspended; Coach remained inconclusive. Operational Entry
coverage was **479/1,000 (47.9%)**, versus **42.1% fitted coverage** for the current Entry candidate.
They are different cohorts and neither establishes the 70% requirement or a deployment uplift.

The new `work_detail` records were saved for broker, decision and RPC lanes. In the latest saved
RPC detail, 175 observation calls took 28.55 cumulative elapsed seconds, including 22.83 seconds
in immediate governance; its largest measured governance call was 1.16 seconds. This makes
governance a useful investigation lead, not a proven cause of the whole burst. Nested timings
overlap, elapsed time includes descheduling, and a later interval separately contained a
7.76-second broker phase and 11.20-second event batch. Their maxima need correlation with
the corresponding detail series before selecting any optimization. No transaction, governance
priority, provider spacing or promotion rule was changed in response to this short sample.

Cleanup had removed **9,590 raw events**, remained within its storage budget, and yielded to
market pressure. Its last checked oldest raw event was about **29.17 minutes beyond** the
24-hour retention target at 21:59:41 BST, so catch-up is not established. There was no unheld
probe retention in the closing snapshot. E: had **33,772,433,408 bytes free (31.45 GiB)** after
the backups and observation.

**Outcome:** the requested update completed with preserved state and working instrumentation.
Burst lag, candidate expiry, delayed diagnostic sampling and retention catch-up remain confirmed
operational concerns. Their presence was also established on the preceding build; these short,
unmatched traffic cohorts do not establish either a regression or an improvement from the new
instrumentation. No new deployment-specific defect, corruption or worker crash was established,
so the verified image was left running without another restart or speculative fix. Longer
natural-traffic review should examine repeated publications and correlate slow broker/governance
detail with bursts before further implementation. No schedule was added and no public release
was made. Full main-database integrity and the full restore rehearsal remain unverified.

### Final review and first natural publication — 18 September 2026

A further read-only review at **22:02:45 BST** confirmed the same deployed image, diagnostic
build and boot, all seven workers running and zero restarts. The dashboard was **0.82 seconds
old**, with a diagnostics acknowledgement age of **2.15 seconds**. Queue depth was 106 and
current overall/critical lag was **0.338/0.062 seconds**. The recent candidate-loss warning was
still active; recovery at one instant does not erase the preceding burst.

The first post-deployment natural fit/publication completed at **22:02:40 BST** without a
training error or stale-job discard. Preparation, reconstruction and fitting took approximately
0.95, 2.91 and 5.09 seconds; publication waited 9.07 seconds for admission and took 0.27 seconds
to apply. Its training event and all six proof events were present in saved diagnostics: Entry
linear and XGBoost, Manipulation, Sizing, deterministic Exit and contextual Exit. This supersedes
the earlier observation that no publication had yet completed. It verifies a natural publication,
but does not establish that the near-deadline collection branch or repeated-publication overflow
handling has been exercised in live traffic.

Bounded primary-key reads through a read-only volume independently found the latest learning
model and the five unique candidates exposed by the snapshot, including both Entry families.
Their payload digests matched: inline parameters for linear artifacts and the separately saved
payload for XGBoost. The private checker initially assumed every digest required an external
payload; source inspection corrected that checker assumption before verification passed. No
application persistence change was required. This is a targeted durability check, not a full
database integrity scan or restore rehearsal.

The next saved diagnostic page contained two intervals and 12 events, below its limits of
20 intervals and 60 events. Sequence 8 crossed an hour boundary; sequence 9 lasted **97.60
seconds** with another `recording_gap`, queue **2,188**, overall lag **16.20 seconds** and critical
lag **3.50 seconds**. Neither interval recorded additional candidate expiry or shedding. The
observed total remained **171 expired candidates and zero capacity shedding**, with no reported
diagnostic record loss. Long collection intervals still leave gaps in sampled detail even when
the recorder reports no dropped records.

Collection had completed **248 checkpoint updates from 56 requests**, with seven post-fetch
processing-lag discards and zero worker errors. Those discards are included in aggregate guard
deferrals. Operational Entry coverage was **488/1,000 (48.8%)**, while fitted Entry/Manipulation
coverage was **42.5%** on a different cohort. Sizing Champion v8 remained active and healthy,
Entry/Manipulation were collecting proof, Exit remained suspended and Coach was inconclusive.
Neither new training nor these short coverage samples establish a performance improvement,
future qualification or profitable decisions.

The paper execution audit remained verified. Two new paper buys explain the exact **19,284,580
minor-unit** cash reduction since the preceding snapshot; this was expected trading, not lost
state. Season, profile, risk mode and active skill versions were unchanged. There were no unheld
probes. Raw-event cleanup remained about **28.55 minutes behind** its 24-hour target. E: had
approximately **31.45 GiB free**, rather than the earlier user-reported 90 GB before backup copies.

**Disposition:** leave this verified paper app running for normal observation. No new deployment
defect requiring a fix or restart was established, but burst lag, candidate expiry, delayed
sampling and retention catch-up remain open concerns. Production code and configuration were
unchanged in this final pass; README and CHANGELOG already describe the deployed scope and
community-publication hold correctly. The existing follow-up was rescheduled for one read-only
review at **01:10 BST on 19 September 2026**, using this baseline. The older paused steward was
left untouched. Community publication remains on hold, and no push was made.

### Fitted-coverage investigation and local candidate — 18 September 2026

The subsequent read-only investigation reconstructed the 22:10 BST paired generation's fixed
1,000-observation Discovery cohort and verified its evidence digest. It contained **430 usable**,
**305 insufficient-real-reserve quote failures**, **8 fee failures**, **251 stale-route expiries**
and **6 elapsed-window expiries**. Even recovering every one of those 257 expiries as usable would
give 68.7% for that fixed cohort if the 313 genuine quote failures stayed unchanged. This is a
conditional arithmetic example, not a permanent ceiling or proof that all expiries are recoverable.
Most observations predated the current boot; these are not comparable before/after performance
cohorts. The moving operational fraction is a separate measurement. Later candidates also failed
performance checks, so coverage alone would not authorize their promotion.

The supported implementation stages are local only:

1. Established order/evidence linkage, duplicate-history, restart and failed-write rollback
   contracts before optimizing. The pre-change isolated baseline passed 48 targeted tests.
2. Added an idempotent non-unique index over lane, extracted decision ID, trajectory and created
   time. The current writer makes its prior trajectory selection explicit; chronological readers
   keep insertion order for equal timestamps. The order and evidence link remain one transaction.
   No schema version, record JSON, season, permission or fee calculation changes. The combined
   lookup/database/measurement suite passed 63 tests. A 5,000-row isolated late/absent lookup fell
   from approximately 30,000 SQLite VM operations to fewer than 100; measured calls went from
   approximately 61/76 ms to 0.11/0.02 ms. Index creation/reopen took 66 ms on this small fixture.
   These measurements are not estimates for a large live database or a natural burst.
3. Added generation-bound optional numeric coverage metrics to Entry Linear/XGBoost and
   Manipulation, plus validated dashboard and compact diagnostic explanations. Freeze only quote
   classifications; keep bulky receipts excluded from training copies. Old or inconsistent reports
   are unavailable. A frozen 400-observation test retains all 392 usable outcomes, including losses,
   zero returns and embargoed rows, after the live objects change and after database restart.
   Paired fits with reporting enabled/disabled preserve coefficients, payload bytes/hashes, cohort
   digests, gates and authority (excluding the independent Manipulation creation timestamp).
4. Kept collection batch sizes, provider spacing, deadlines, post-fetch guards, held-position and
   Policy priority unchanged. The targeted fitting, diagnostics and collection contract suite
   passed 73 tests; the conditional collection-tuning stage is deferred until the lookup change
   is deployed and comparable natural traffic identifies the remaining bottleneck. Immediate
   governance must not be delayed merely to improve throughput.

The local source archive `.test-run-v11011/coverage-before.zip` contains pre-change source only,
not credentials or application data. All write-producing checks use disposable fixtures, with
no production volume mounted and no network in backend test containers. The initial harness
needed localhost binding and a temporary filesystem larger than the diagnostics 512 MiB free-space
reserve; those were test-environment corrections. The comparison test needed to exclude a separate
wall-clock creation timestamp; no fitting difference was found. Frontend checks use the existing
workspace tools directly because the local pnpm fallback does not expose their command shims.

This candidate still needs its separate Settings rollout and natural-traffic evaluation. No live
app, configuration, database, schedule, threshold or Champion permission was changed by this work.
The paused v1.11 work and paused steward remain untouched. Full main-database integrity and the
full real-data restore rehearsal are still unverified; isolated fixtures cannot establish those.

The isolated old-code → candidate → old-code rehearsal passed on a 5,000-episode fixture.
Evidence JSON retained the same SHA-256 across all stages; schema 16 and the stored active-skill,
mode and consent settings were unchanged. The previous code reopened the newly saved numeric
coverage metadata and external model-payload fixture, verified its digest, decoded the optional
diagnostic array and continued order linking. The small fixture's integrity check returned `ok`.
This checks compatible persistence, not a full live restore or live Champion eligibility.

In that rehearsal, 30 repeated late-match order transactions had a median duration of about
45.88 ms before and 0.258 ms after indexing. Sixty episode-save calls measured about 0.078 ms
before and 0.228 ms after; the rollback reader/writer, retaining the new index, measured 0.098 ms.
Thus index maintenance is not free, and process/cache/scheduling variation is visible. These
are synthetic measurements on a shared host, not a guarantee of faster collection or no tail
latency. Live validation must compare lookup/lock timing, critical lag and checkpoint completion
over comparable traffic and cohorts. E: had approximately 31.45 GiB free during local validation.

Final local checks:

- **1,988 backend tests passed**, in four sequential fresh containers: 483 + 440 + 560 + 505.
  The initial single-container run had 1,986 passes, one allocation failure while reading a
  bind-mounted IDL fixture and one missing package-manifest mount. The rerun included all source
  manifests and retained the same
  one-CPU/1.5 GiB limit; fresh containers released accumulated fixture memory between batches.
  No application change was used to conceal either harness failure.
- **423 frontend tests passed** across 22 files; TypeScript and the production Vite build passed.
  ESLint had no errors and retained the existing EquityChart fast-refresh warning; Vite retained
  the existing large scene-chunk warning.
  A final defensive fallback also keeps gates readable if an incomplete artifact omits its
  metrics object. All 28 EntryProof component checks passed afterward, including two new
  missing/null-metrics cases (425 distinct frontend tests across these runs). The candidate
  image was rebuilt afterward so its packaged UI includes this correction.
- Ruff lint/format checks passed, and mypy passed all 47 modules. Backend tests retained the
  existing dependency deprecation warning about `BlockingPortal`.
- Frozen-cohort accounting, paired-fit equivalence, legacy/partial/future reports, per-family
  rendering, nonpositive usable returns, restart persistence, and compressed diagnostic events
  passed. All four existing full-interval/proof-event byte-budget cases also passed with the
  new coverage arrays included for the native Entry and Manipulation families.

Source comparison against the pre-change archive confirmed that orchestration/scheduling,
training serialization exclusions, model schemas, Coach and quote arithmetic remain unchanged.

The final candidate was built with the repository Dockerfile as
`signal-arcade:v1.10.11-coverage-candidate-20260918`, image
`sha256:9320aea935092e4144a606902e210955919760f62c7b712e40ca3a2a69a03961`, diagnostic build
`df9bce7230b10e3fdbef8a2ae846dc4a8d5429c94deb6adcb4c66ce582656f69`.
Its networkless, non-root, disposable demo smoke passed health/all seven workers, enforced
authentication, snapshot/diagnostics/history routes, packaged UI assets (including the new
coverage fallback), schema/index checks, the 0.7 gate, five horizons, and Settings upgrade
prepare-to-ready followed by cancel. No production data or credentials were used for this smoke.

A final read-only Docker inspection confirmed that the live app still used
`signal-arcade:v1.10.11-postburst-candidate-20260918`, image
`sha256:35e8e4b6bf5aebc9389dfb6995606afca33cfa51ff9a60807db167e1109a3af5`, started at
20:50:37 UTC, with zero restarts and a healthy Docker health check. This verifies unchanged
deployment/liveness only; it is not a new burst-performance or learning-quality observation.

The fresh package resolved the existing transitive `idna` dependency to 3.20, versus 3.19 in the
test-tools image; the other compared runtime library versions matched. No requirement file was
changed. The affected API/security, configuration, HTTP-provider and provider-safety suites
passed **116 tests** using the candidate image's exact 3.20 library. Their first bind-mounted
run encountered five IDL file-read allocation errors before the relevant logic ran; rerunning
the same source from an internal disposable copy passed at the same one-CPU/1.5 GiB limit.
The final checks therefore retain the earlier harness failures explicitly, rather than counting
them as healthy observations or changing application logic to satisfy them.

**Disposition:** local implementation and validation complete; conditional collection tuning
awaits evidence from a separately authorized deployment. The running app and scheduled review
remain unchanged. No community push, forced promotion, threshold change or profit claim was made.

### Additional coverage edge review — 18 September 2026

The requested double-check added eight permanent boundary cases and strengthened the existing
diagnostic-size fixture to use different saved-generation counts, avoiding reliance on identical
arrays compressing together. **99 targeted backend checks passed** on disposable internal source
and data, with no network and the same one-CPU/1.5 GiB limit. Checks covered:

- Exact **69.9%, 70.0% and 70.1%** coverage after the normal 1,000-row tail selection. Recent
  wrong-risk/configuration/source rows, incomplete features, absent primary checkpoints and real
  Policy twins cannot displace eligible Discovery rows. The oldest eight eligible rows leave the
  window correctly. Both Entry families and Manipulation retain the same exact denominator;
  reaching 70% alone still cannot replace independent Policy proof.
- A busy SQLite writer rolls back without an orphan order or changed evidence, then retries
  successfully with measurements enabled. Quoted, Unicode, embedded-NUL and empty decision IDs
  retain correct parameterized lookup/update behavior; empty IDs do not create an order link.
- Denied index creation preserves schema, evidence and consent, and a subsequent open succeeds.
  The small disposable database's index-update integrity check passes. These are failure-injection
  fixtures, not a full live-database integrity scan or restore rehearsal.
- Frozen fits, old/malformed reports, publication context changes, diagnostic priority and the
  compressed full-interval/proof-event budgets continue to pass with differing cohort reports.

The first three new boundary assertions used an aggregate-report gate name against the
family-specific report. Correcting the test to `entry_outcome_availability` resolved that test
assumption; no application logic changed. All 47 backend source/resource files match the
already-built candidate archive. Only tests and this validation record changed in this review;
the candidate image/build, live app, settings and scheduled review remain unchanged.

### Coverage and order-lookup live rollout — 18 September 2026

The user subsequently authorized deployment. The tested image
`signal-arcade:v1.10.11-coverage-candidate-20260918` is now running locally, image
`sha256:9320aea935092e4144a606902e210955919760f62c7b712e40ca3a2a69a03961`, diagnostic build
`df9bce7230b10e3fdbef8a2ae846dc4a8d5429c94deb6adcb4c66ce582656f69`, boot
`637a2fc216b64a4081ad2859b1973896`. The container started at **22:11:21 UTC / 23:11:21 BST**.
All 47 packaged backend files and all 30 embedded application frontend sources matched the
local source. Windows and Linux frontend output filenames differed, so source-map contents were
compared directly; this was not treated as an unexplained stale-source mismatch.

The old boot's 23:05 BST preflight was process-healthy but degraded by recent candidate loss.
It had **1,194 shed and 29,258 expired candidates**, including 724 expiries in its recent
five-minute window, and **nine dropped diagnostic events** (one training, five proof, three
storage). Operational coverage was 448/1,000. These are pre-update observations; resetting
counters at deployment is not evidence that burst capacity or fitted coverage improved.

A fresh consistent SQLite backup completed at **23:10:37 BST** in the separate Docker volume
`signal-arcade-v11011-coverage-backup-20260918`: main database 16,069,726,208 bytes, diagnostics
95,268,864 bytes, plus provider settings. Manifest sizes, schemas, bounded quick checks of
settings/positions/paper_seasons/challenger_skill_states, and the small diagnostics database
passed. Full main-database integrity and full real-backup restore remain unverified. The first
Windows-folder copy was stopped because it was too slow; only that attempt's incomplete files
were removed after checking its exact path and contents. Previous completed backups remain.
Only one fresh large copy was retained, leaving **15.70 GiB free on E:**, which needs ongoing
host-space monitoring; Docker's larger virtual free-space figure is not a substitute.

Settings upgrade preparation `9cad39c579ef4cebaba02ecf4731a253` reached Ready at 23:11:06 BST
with no pending-order cancellation or interrupted model download. Four holdings and season 58
were recorded after preparation settled. Compose replaced only the app, without rebuilding,
pulling or touching Ollama, and retained the same data volume. Only the private image pin
changed; other environment values were compared without displaying secrets. The previous
post-burst image remains available for code rollback against the current schema-16 volume.
The deployment script included rollback on failed startup; rollback was not needed.

Docker/HTTP health passed approximately **51 seconds** after replacement, with zero restarts
or OOM kills. Settings recorded completion and restored the previous running preference.
The initial fresh dashboard, history/leaderboard/seasons pages and packaged assets returned
success; unauthenticated snapshot access remained 401. Fifteen of the seventeen immediate
continuity comparisons matched directly. Cash and position count differed because normal
post-resume trading sold one holding at 22:12:11 UTC for its existing stop-loss rule. A bounded
read-only check verified the exact saved fill and balanced ledger: **2,760,163 account minor
units** explained the entire cash increase, and the sold **873,471,017,271 token units** explained
the removed position. Remaining holdings matched exactly. The paper execution audit was verified.
These differences were reconciled, not silently accepted or rolled back to an older ledger.

Season/profile, risk mode, starting bankroll, active skills, consent, automatic participation,
risk-halt state and the **70% gate** were preserved. The new non-unique lookup index exists;
`EXPLAIN QUERY PLAN` uses it for the order-to-Policy lookup. Schema remains 16. Production source
was unchanged during deployment. The paused v1.11 workspace, old steward and existing scheduled
review were untouched; no public push, force-fit or promotion occurred.

#### Initial natural-traffic observation

At **23:18:57 BST**, health was not degraded, all seven workers were running, and the dashboard
was **2.17 seconds old**. The boot had processed **75,408 events**, with **zero pipeline candidate
shedding or expiry**, and completed **three training/publication cycles**. There were no training
or RPC worker errors; 36 RPC requests produced 171 checkpoint updates. Two fetched batches were
discarded by existing guards (one maintenance, one processing lag). These are a subset of guard
deferrals, not extra losses to add to them. The final bounded container logs contained startup
information only, and Docker remained healthy with zero restarts or OOM kills.

The read-only diagnostic query returned six saved intervals and 30 events, below its 20/60
limits. They cover **384.69 seconds**, starting with an explicitly partial startup interval.
There were no gaps between consecutive saved boundaries, and the longest interval was
**70.23 seconds**. Saved intervals peaked at queue **926**, overall lag **6.11 seconds**, and
critical lag **3.72 seconds**, with no saved pipeline loss. Recording reported no event or
interval loss, no writer error or early eviction; the final acknowledgement age was **46.67
seconds**. These are short saved samples and point-in-time checks, not a sustained-burst test.

The first saved worker detail showed two order saves, at most 2.93 ms, but no decision-linked
`order_lookup` measurement yet. That is insufficient for a live before/after lookup-speed claim.
The same early detail recorded nine RPC applications, at most 0.924 seconds, and request time
at most 0.649 seconds. Later guard discards are visible in the live counters even though that
earlier low-frequency detail predates them. Nested worker timings are not summed with parents.
Checkpoint expiry still occurs: the early cumulative expiry sample had 124 Discovery and two
Policy expiries, of which 121 Discovery expiries had unknown RPC attribution after restart. This
cannot establish that the new build caused those losses or could have recovered valid quotes.
Cleanup removed 7,150 raw trades; its retained oldest trade was still about 44 minutes behind
the 24-hour target at the last history check. No obsolete unheld probes remained in the final
snapshot. These remain observations for the scheduled review, not solved-throughput claims.

The saved latest learning model and all five unique displayed skill artifacts were found in the
database; inline/external payload digests verified. New Linear Entry and Manipulation artifacts
and saved diagnostic summaries carry matching, valid fitted counts: **375/1,000 usable (37.5%)**,
280 real-reserve quote failures, 13 fee failures, 326 stale routes, five elapsed windows and one
other missing outcome. Operational coverage was separately **446/1,000 (44.6%)**. Neither is a
post-deployment-only cohort, so neither supports a coverage improvement or regression claim.

The retained XGBoost artifact is older, at **39.4%**, and correctly has no new breakdown. The first
new Linear fit had 233 eligible training rows and the latest had 232, below XGBoost's unchanged
250-row minimum; the lack of a fresh XGBoost fit is therefore expected, not lost proof. Its saved
performance gates also fail. Sizing Champion v8 remains active/healthy; Entry and Manipulation
are collecting proof, Exit remains suspended, and Coach remains inconclusive. No Champion or
profit improvement has been established.

Two local verification-helper mistakes were corrected without touching application state: a
PowerShell summary syntax error prevented the final snapshot file from being written, and its
dependent read-only helper consequently received an empty bind-mount directory. The exact empty
local directory was checked and removed, the snapshot was obtained, and the artifact verification
then passed. Neither failed attempt is counted as a successful application check.

**Disposition:** the latest v1.10.11 changes are deployed and ready for normal unattended traffic
and the existing scheduled review. No deployment regression was found in this bounded check.
README, CHANGELOG and learning/diagnostic documentation now describe the deployed scope. E:
still has **15.70 GiB free** after the single fresh backup; keep that host constraint in subsequent
checks. Broader burst efficiency, retention catch-up, 70% coverage and Champion qualification
still need comparable natural evidence. Community publication remains on hold. Private evidence
is retained in `.test-run-v11011/coverage-*`; credentials were not displayed.

#### Final edge and polish check — later on 18 September 2026

A fresh check at **23:20 BST** confirmed the same deployed image/build and boot, healthy Docker
status, zero restarts/OOM kills, and all seven workers. Backend files and embedded frontend
application sources again matched the deployed image exactly (47 and 30 files respectively).
The original configuration remains preserved except for the intended image pin. Authenticated
pages and packaged assets returned success; unauthenticated snapshot access remained 401.
Settings preparation was completed, the dashboard was 2.41 seconds old, the paper execution
audit was verified, season 58 and participation preferences remained intact, and the 70% gate
and five horizons were unchanged. No unheld probes were retained.

This later check **does supersede the earlier clean sample as an all-clear for burst behavior**:
a natural burst expired **765 candidate events**, with zero capacity shedding, queue peak
**3,837**, overall lag **20.03 seconds** and critical lag **2.61 seconds**. Its saved interval
lasted **90.87 seconds** and correctly carried `recording_gap`, despite zero reported diagnostic
event/interval drops. That gap is not a healthy observation. The next saved interval recorded
no further loss and recovered to peaks of 3.93 seconds overall and 1.72 seconds critical lag.
At the live check the queue was 51, with current lag 0.384 seconds and critical lag 0.057 seconds;
the recent-loss warning remained correctly visible. These targeted reads returned two intervals
and 13 events, below their 20/60 limits; they do not establish sustained recovery.

Natural order-linked work now exercises the index: eight lookups took **1.39 ms in total**,
at most **0.98 ms** each. Ten enclosing order saves peaked at **27.86 ms**. These nested values
must not be added together. This small sample supports that the new lookup is functioning,
while remaining insufficient for a causal claim about total burst throughput. The burst's
event-batch maximum was 8.91 seconds; its other overlapping phase timings and sparse detail
do not isolate a new defect or justify speculative changes to scheduling or proof.

Reviewed edge contracts include exact 69.9/70/70.1% boundaries, frozen cohorts and negative
outcomes, old/malformed/cross-family coverage reports, duplicate and unusual decision IDs,
transaction rollback/retry, denied index creation, and diagnostic size/priority limits.
The prior 99-test boundary run remains applicable to the verified unchanged production source;
it was not reported as a new test execution. Bounded live reads again verified the current model
and five displayed skill artifacts, including payload digests and valid saved coverage counts.
No new learning, authority, persistence or UI defect was established. The existing burst loss,
diagnostic gaps, retention lag and low fitted coverage still require investigation under longer
comparable traffic; process liveness alone does not resolve them.

Only this validation record was polished in this pass. No production code, settings, data,
services, schedules or thresholds were changed. The app can continue running for the scheduled
review, with those explicit limitations; this is not approval for community publication or a
claim that all performance issues are fixed. E: still had 15.70 GiB free.

The final read at **23:22:41 BST** found queue **2**, current overall/critical lag
**0.017/0.156 seconds**, all seven workers running, and no additional expiry (still 765) or
capacity shedding. The recent-loss warning remained visible. The snapshot was 2.22 seconds old,
diagnostic acknowledgement age was 18.72 seconds, and no training/RPC worker or recorder error
was reported. Host free space was 15.69 GiB. Monitoring stopped after this bounded check.

## Publication retention and selection follow-up — 19 September 2026

This follow-up implements the subsequent reviewed plan locally. The paused v1.11 workspace,
live service, configuration, database records and schedules are untouched. Version remains
**1.10.11**, schema remains **16**, and no build, push, restart or deployment was performed.

### Evidence motivating the scope

The preceding read-only review at **03:05 BST** verified the coverage candidate image
`signal-arcade:v1.10.11-coverage-candidate-20260918`, diagnostic build
`df9bce7230b10e3fdbef8a2ae846dc4a8d5429c94deb6adcb4c66ce582656f69` and boot
`637a2fc216b64a4081ad2859b1973896`. That review found all seven workers, 105 completed
publications, zero restarts and no additional pipeline expiry beyond the earlier 765. These
are prior observations, not a new live health check for the changes below.

Saved interval 131 lasted **101.24 seconds**. Two six-report publications exceeded the old
eight-event buffer, losing one training and three proof summaries. The affected learning
artifacts were nevertheless persisted; bounded payload verification distinguished diagnostic
loss from learning loss. The existing early-collection path intentionally refuses a collector
age above 90 seconds, so it cannot absorb every observed publication cluster.

Collection was close to its configured five-route capacity: 583 additional requests selected
2,914 of a possible 2,915 routes. But RPC application reached **5.852 seconds**, and nested
governance timings include overlapping elapsed time and descheduling. They do not prove that
governance CPU work caused the burst. Blindly increasing the batch could hold the event boundary
longer; no such increase is included here. The source default remains 20, while this live app's
configured batch remains five.

A bounded 400-completed-Discovery sample contained 208 usable outcomes, 134 liquidity failures,
four fee failures, 53 stale-route outcomes and one elapsed window. Even hypothetical recovery
of all 54 missing outcomes would yield **65.5% in that sample**, not a prediction for future
or fitted coverage. Valid liquidity/fee failures cannot be erased to make 70% pass. The fitted
model cohort, operational window and this diagnostic sample are separate populations.

### Staged changes and edge checks

1. **Publication retention.** A separate four-group backlog retains up to seven compact reports
   per publication, without I/O or writer waits at admission. Collection drains whole FIFO
   groups within the existing eight-event interval cap, leaving room for ordinary diagnostics.
   Original report timestamps, group IDs, indices and expected counts survive; `collected_at`
   is collection time, not durable-write acknowledgement. Pending counts/age are explicit.
   Overflow evicts the oldest whole group with exact report-category losses. A malformed proof
   summary leaves its siblings intact and an explicit missing index instead of discarding the
   rest of the publication. Interval and writer failures retain their original accounting units.

   The stage gate passed **123 tests**. Cases cover 101-second collection delays, closely spaced
   publications, fifth-group overflow, disabled/full/dead writers, malformed and oversized input,
   error priority, no input aliasing, original/cursor timestamps, repeated store append, bounded
   compression, terminal jobs, pressure changes and collection/publication admission rechecks.
   The later malformed-summary isolation regression is also included in the final combined gate.
   A crash can still lose unsent diagnostics; neither an empty backlog nor a writer acknowledgement
   alone proves every report was saved.

2. **Selection visibility.** Optional measurements use the admitted RPC pass's existing pending
   trajectories, at most once per monotonic minute. Two small lane events report disjoint
   due-checkpoint eligibility categories,
   remaining deadline buckets and the deduplicated route budget. They retain sampled timestamps
   and pass IDs, contain no account identifiers and use the existing optional five-minute cadence.
   These are sampled considerations, not unique losses or a causal explanation of expiry.

   The stage gate passed **163 tests**. Instrumented and uninstrumented paths retain identical
   selections, rotations and clocks across zero/one/five/twenty route limits and both channels.
   Tests include shared mints with separate lane clocks, exact five/fifteen-second boundaries,
   closed/future work, missing state, excluded identities, saturated counters, privacy and the
   existing input/compressed payload limits. Provider/account rejection remains a later stage.

   A later cost check found that sampling every admitted pass added repeated horizon work:
   with 2,400 pending synthetic trajectories, median thread CPU time was 19.11 ms without the
   new sample versus 46.34 ms with it on every pass. The implementation therefore limits
   measurement to once per minute; it never consumes the slot on blocked, cached or disabled
   passes. Another **112-test gate passed** after this refinement, including exact monotonic
   boundaries, wall-clock changes and a fresh tracker scope. The instrumented/control selections
   and rotations remained identical across 32 simulated ten-second passes, with six samples.
   In that separate run, mean thread CPU time was 14.39 ms without sampling and 18.16 ms with
   the cadence cap; median wall time was 13.35/16.04 ms and the instrumented maximum 43.29 ms.
   Host scheduling differs between runs: these are isolated costs, not a live latency guarantee.
   A final pressure check places the new optional samples behind existing loss/work-detail
   reports. A full queue preserves proof, then retries the sample without consuming its emission
   cadence until it is actually admitted. No extra history scan is triggered by that retry.

3. **Measured proof-selection work.** Filter ineligible records before sorting Policy evidence.
   The order key, identity-reservation checks, earliest eligible record per mint and latest
   1,000-row window are unchanged. Missing/negative outcomes remain in proof. Immediate governance
   stays at each original outcome boundary; no outcome-spanning cache or deferred suspension was
   introduced.

   An isolated 3,000-record mixed-history fixture selected the identical 1,000 records. Across
   12 runs per variant, median selection wall time was **25.78 ms before / 16.19 ms after**;
   median thread CPU time was **25.79 / 16.21 ms**. This narrow fixture establishes reduced sorting
   work, not total application latency or live burst capacity. The stage gate passed **192 tests**,
   including mixed cohorts, insertion order, equal instants with different timezone offsets,
   naive timestamps, missing/negative outcomes, identity reservations, skill recovery, activation,
   chronological fitting, Exit lifecycle and coverage boundaries.

4. **Conditional scheduling experiments.** No batch, priority, deadline, grace, quota or provider
   setting changes were adopted. The earlier deadline-ordering example improved completions
   with one-second processing but worsened them at five seconds. Existing 5/10/20-route,
   freshness, post-fetch guard and deadline tests remain in the regression gate. A larger live
   batch or new ordering needs representative timing evidence, held-position/Policy protection
   and demonstrated benefit before implementation.

### Combined acceptance and rollout boundary

**All 2,031 backend tests passed** across the isolated groups: 675, 483 plus the separately
rerun release-version test, 422, and 450. The first group was rerun after the final sampling
cadence and optional-report priority refinements. Strict mypy passed for **47 source files**;
Ruff lint, formatting (**158 files**) and `git diff --check` passed. The existing Starlette/AnyIO
`BlockingPortal` deprecation warning remains; no application regression was found in these
checks. Version declarations, documentation link targets and the new validation anchor agree.

Tests used fresh disposable containers with no network or live-data mounts, capped at one
CPU and 1.5 GiB, with temporary test databases. The initial harness omitted a loopback bind
override and rejected test Settings; the override was corrected without touching the app.
Two initial test assumptions about the old buffer and store context-manager support were also
corrected. Those failed attempts are not counted as passing validation.
The sampling-cost helper initially treated a dataclass as a Pydantic model; its fixture was
corrected before measurements. A mistyped focused-test path collected no tests and was rerun
using the actual file. Neither harness error required an application change.
The full-suite archive initially omitted release metadata used by the version check. Its 483
other tests passed; after including the package manifests, Dockerfile and CHANGELOG, the version
test passed separately. These archive omissions did not change application source or versions.

README, CHANGELOG, learning and diagnostic documentation distinguish this local follow-up from
the previously deployed candidate. No frontend behaviour changed in this follow-up. The 70%
gate, valid failures, training/proof separation, chronological validation, Champion permissions,
held-position priority and Policy scheduling remain intact.

Live rollout is a separate step through Settings upgrade preparation. Before it, recheck disk,
the exact build and backup readiness. Afterward verify boot/build, bounded backlog/drain and
writer losses, natural publication persistence, selection samples and matched traffic/lag
without forcing training or promotions. Full main-database integrity and a complete backup
restore rehearsal remain unverified. These fixes do not guarantee 70% coverage, Champions,
profits or the elimination of burst loss.

The host-only disk check during validation found **15.36 GiB free on E:**. No live API, live
database scan or service mutation was performed in this implementation pass, so prior runtime
observations must not be presented as fresh validation of the new source.

**Disposition:** this local v1.10.11 follow-up is ready for the separate rollout checks above.
No new source defect remains from the staged checks. Community publication stays on hold for
deployment verification and comparable natural-traffic evidence. Private `retention-*` test
inputs and the validation manifest retain the local reproduction details; they are not release
assets and contain no live credential.

### Additional edge review — 19 September 2026

The follow-up double-check verified the prior eight recorded source/test hashes before making
any edits. It then reproduced a local diagnostic isolation defect: the new optional eligibility
sample inspected clocks on records that the selector would otherwise skip. A timezone-naive
clock on a missing-state record raised `TypeError`, failing that admitted selection pass only
when the optional measurement was enabled. Extreme future dates could also overflow horizon
addition in this newly inspected path. This candidate has not been deployed; no such runtime
incident is claimed from the live app.

The correction keeps already-excluded records outside the core selection loop. Their optional
classification uses elapsed durations, avoiding future-date addition overflow, and records
incomparable clocks as a separate `clock_unclassified` trajectory count. It does not repair
timestamps, enrol records, change evidence or relax the core selector's existing validation.
Closed horizons remain excluded; future horizons remain not due. The new field is optional
diagnostic metadata within the same payload limits and is never a qualification input.

**38 new boundary cases** cover both lanes, missing state, excluded identities, fresh cached
routes, naive/extreme future clocks, closed work, all five horizons immediately before/at due
and at/after expiry, and repeated mixed-size publication overflows. Further cases confirm that
interval-queue losses keep interval units and create a saved gap, while writer compression
omissions preserve original group indices and an explicit omission count.

The initial two failing reproductions passed after correction. A first **125-test gate passed**,
followed by the expanded **191-test gate**, including existing selection, checkpoint, post-fetch
guard, publication pressure, diagnostics priority, real application-cost and coverage cases.
These overlap and must not be summed. The earlier 2,031-test full run remains the preceding
baseline; it is not presented as a fresh full-suite execution after this correction.

The isolated 2,400-trajectory cost check again selected identical routes with identical rotation
across 32 simulated ten-second passes and six measurements. Mean thread CPU time was
15.38 ms without the optional sample / 21.04 ms with it; median wall time was 14.44/18.61 ms,
with an instrumented maximum of 60.47 ms. These small fixture timings include host variability
and do not establish live latency or a causal comparison with the earlier profiling run.

Lint, formatting (159 files), whitespace checks and strict mypy (47 source files) passed.
No further defect was found in this focused review. README and diagnostic semantics describe unclassifiable
clocks and warn against joining lane reports from different sample passes. Live rollout,
Settings preparation, services, data, seasons, permissions and the 70% requirement remain
untouched; the prior rollout/backup and natural-traffic limitations still apply.

## Publication retention live rollout — 19 September 2026

The user authorized the live update after the additional edge review. This supersedes the
earlier local-only disposition for the publication backlog, selection visibility and Policy
proof sorting. The version remains **1.10.11**, schema **16**; no public image or GitHub push
was performed.

- Local image: `signal-arcade:v1.10.11-retention-candidate-20260919`.
- Image ID: `sha256:f1b6da446c5b35109789aa7b1e19cd547172f321a50df996c4639acbbf4fd15c`.
- Diagnostic build: `13819757152fe780e12ebb420e809844dc9cc3f2bb6c2a4cdac56e8abaef2f3d`.
- Boot: `fb6f50bcbf71467b8f2e272c844b21a2`.
- Container start: **03:14:11 UTC / 04:14:11 BST**, 19 September; application startup
  completed at **03:14:42 UTC**.
- Rollback image retained:
  `sha256:9320aea935092e4144a606902e210955919760f62c7b712e40ca3a2a69a03961`.

### Packaged checks and backup

All **47 backend files (45 Python files and two IDL resources)** matched both the installed
package and image source against the checkout. Runtime dependency versions matched the previous
image. An isolated candidate with
no network or live-data mount passed health/worker, authentication, frontend asset, key-page,
schema/index, 70% gate, five-horizon and Settings prepare/cancel checks. The new bounded
publication status was present. This supplements the staged test gates above; it is not another
execution of the full backend suite.

E: had **15.33 GiB** free before rollout, insufficient for a prudent additional uncompressed
copy of the approximately 16.07 GB main SQLite file. After Settings preparation reached Ready,
the app alone was stopped. The complete stopped data volume was archived with its original
file metadata, including the main database, diagnostics, provider-secret file and legacy backup.
All five files were read back and matched their original SHA-256 digests; gzip CRC validation
also passed. The archive is **4,074,539,351 bytes (3.79 GiB)**. Existing backups, the original
image, Ollama and the data volume were preserved. No database restore or migration was needed.
Backup artifacts and environment rollback copies are private and must not be published.

Two private rollout-helper issues were corrected transparently. The first stop guard rejected
the normal SIGTERM exit code 143 despite the explicit shutdown-complete log; its recovery
resumed the original app and verified health before retry. The revised guard requires a
stopped, non-OOM container, no Docker error, an accepted exit status and a shutdown-complete log.
During backup, a default SIGALRM disposition did not enforce the intended eight-minute bound
for container PID 1. Copy plus read-back verification completed successfully in **515.97 seconds**.
The helper now installs an explicit timeout handler, verified in a disposable PID-1 container
alongside corruption, size-limit and unsafe-path checks. These were deployment-helper issues,
not application-source fixes; neither failed check was counted as successful validation.

The intentional stopped period ran from **03:05:32 UTC** until the new application's
**03:14:42 UTC** startup, in addition to the earlier brief retry interruption. This is a
maintenance observation gap, not healthy traffic coverage. Outcomes spanning this pause must
not be used as an unqualified before/after performance comparison.

### Startup and continuity

Settings recorded the same upgrade operation as completed after restart. All **17 continuity
checks passed** on the first fresh post-start snapshot: exact build, freshness, season/profile,
risk mode, starting balance, cash, positions, active skill versions, consent, auto-participation,
risk halt, 70% gate, operation identity/completion, running preference and held-only probes.
Season **58**, all **three positions** and cash **354,597,917 minor units** were preserved.
The paper execution audit reported verified with no issues. Authentication rejected an
unauthenticated snapshot; root, Champion journey, leaderboard and seasons pages returned 200.
All seven workers were running, Docker reported healthy and zero restarts, and bounded startup
logs contained no application error.

Bounded primary-key reads verified the authoritative learning model and five observed unique
skill artifacts, including inline parameter and external XGBoost payload digests. Historical
artifacts retain their original fitted coverage and creation times. Sizing Champion v8 remained
active and healthy; Entry and Manipulation were collecting proof, Exit remained suspended and
Coach remained inconclusive. No permissions, scheduling settings, fixed deadlines, valid failures,
chronology or qualification thresholds were changed.

After the backup, host free space was **11.54 GiB on E:** and **1.66 GiB on C:**. This is limited
headroom, not the previously reported 90 GB. No older backup was deleted. Full main-database
integrity and a complete backup restore rehearsal remain unverified; archive verification
must not be described as either. Sustained burst performance, improved fitted coverage and
Champion qualification still require natural-traffic evidence. Community publication remains
on hold for that review.

### Short natural-traffic observation

At **04:19:48 BST**, the fresh snapshot was **2.21 seconds** old and the diagnostic
acknowledgement **11.64 seconds** old. All seven workers were running, the trainer/RPC error
fields were clear, the publication backlog was empty and no new diagnostic loss was reported.
All 17 continuity checks passed again. The two protected frontend assets returned 200 and
contained the expected coverage explanations; an initial unauthenticated root request correctly
returned 401 and was repeated with authentication. Only the local image pin changed in `.env`.

A bounded read returned **five consecutive intervals (sequence 0–4)** covering **311.02 seconds**
and **ten saved events**, below the 30-interval/100-event limits. The initial partial interval was
marked; no recording-gap flag or sequence hole appeared. The longest interval was **65.11 seconds**.
Saved maxima were queue **590**, overall lag **5.41 seconds** and critical lag **2.71 seconds**,
with **zero shed or expired pipeline events**. The final live queue was zero and overall/critical
lag **0.005/0.149 seconds**. These are a short startup sample, not sustained burst validation or
a matched comparison against the previous boot's 976 expired events and seven diagnostic losses.

Both new lane-selection reports persisted with the same scope, sample timestamp and pass ID.
That sampled pass showed 19 eligible unique routes against the unchanged configured budget of
five, including one Policy route; it is not a count of unique lost outcomes. Unclassified clocks
were zero in that sample. RPC had made **27 requests** and applied **99 checkpoint updates**.
One post-fetch processing-lag discard was included within the three aggregate processing-lag
deferrals; it is not an additional loss to add to them. Guard enforcement remained active.

No natural fit/publication had completed in this new boot by the final check. The worker was
healthy and its initial readiness checks reported not due; the dashboard still required **four
more outcomes**. Thus persisted artifacts were verified, but live publication-group draining,
repeated-publication retention and overload behavior remain unexercised in this rollout sample.
The isolated regression tests cover those cases; they must not be presented as live observations.
No training or promotion was forced.

Operational Entry coverage was **460/1,000 (46.0%)**. The saved fitted Entry/Manipulation cohort
was **42.4%**, with its pre-rollout artifact timestamp; these are distinct cohorts. The fitted
breakdown retained 424 usable outcomes, 374 valid quote failures and 202 missing checkpoints.
The maintenance gap and cohort changes prevent a clean before/after comparison. The rollout
does not demonstrate a coverage improvement, better trading decisions, a new Champion or profits.

**Disposition:** the updated app passed the rollout and continuity checks and is running for
normal observation. No new application fault was found in this short check. Limited host disk
space, the unexercised natural publication path, longer burst/coverage evidence and the full
database/restore limitations above remain explicit follow-up items. No schedule was created.

### Post-rollout edge and documentation check — 19 September 2026

A further check at **04:27:56 BST** found the same deployed build and boot, all seven workers
running, Docker healthy with zero restarts/OOM events, no trainer/RPC errors and no warning/error
severity lines in the bounded runtime log. The live queue was zero, overall/critical lag
**0.023/0.041 seconds**, and diagnostic acknowledgement age **15.71 seconds**. Application source
still matched the verified image; no application change, restart or additional deployment was needed.

The initially stationary retraining counter was investigated rather than assumed healthy or
broken. Indexed, read-only queries inspected at most 12 pending observations per query. Fresh
rows were being saved, with usable one-minute checkpoints. The earliest inspected post-start
row was created at **04:19:44.488 BST**, after the five-minute continuity safeguard, so its primary
five-minute outcome was not due until **04:24:44.488 BST**. Existing continuity/reconnect,
malformed-clock, horizon-boundary, optional-priority, publication-overflow and chronological
selection code/tests were reviewed against this behavior. The previous isolated test results
remain their validation record; this pass did not rerun the full suite.

**Two natural training/publication cycles then completed**, at approximately **04:25:03** and
**04:26:51 BST**. The first publication was observed with one pending group/seven events, then
an empty backlog after collection. Bounded stored diagnostics verified **both complete groups**:
one training report plus six proof reports each, original indices 0–6, consistent expected
counts and original timestamps. Their maximum collection delays were **37.26** and **49.37 seconds**.
The authoritative first new learning model and five observed unique native skill artifacts were
also read by primary key; inline and external XGBoost payload digests matched. This now verifies
normal sequential publication retention live. It does not exercise a four-group overflow,
crash durability or sustained pressure with multiple groups waiting simultaneously.

The final bounded diagnostic read contained **13 consecutive intervals (0–12)** spanning
**794.75 seconds**, and **50 events**, below the 30/100 limits. The initial partial interval was
labelled; there were no recording-gap flags or sequence holes, no shed/expired pipeline events
and no reported diagnostic losses. Saved maxima were queue **1,155**, overall lag **5.41 seconds**
and critical lag **3.47 seconds**. Both selection lanes had saved samples. This
short post-start period still does not establish comparative burst capacity.

After normal trading resumed, a strict equality check correctly flagged that cash and positions
no longer equalled the frozen pre-upgrade snapshot. Read-only primary-key and indexed ledger
queries reconciled **12 natural fills (seven buys, five sells)** through **04:26:16 BST**. Every
transaction balanced; cash changed by exactly **−7,082,698 USDC minor units**, matching the
fee-inclusive cash movements, and reconstructed holdings matched all five current positions.
The three original positions retained their identities. The other 15 continuity checks and the
paper execution audit passed. No older ledger was restored. The private reconciliation helper
was corrected to compare equivalent UTC timestamps by instant rather than `Z`/offset formatting;
that was a checking-script issue, not an application-data error.

Operational coverage at that snapshot was **46.5%**; the first newly fitted cohort's coverage
was **41.2%**. Its 1,000-row denominator included 412 usable outcomes, 363 valid quote failures
and 225 missing checkpoints. These are different populations, and the maintenance gap remains
a confounder. Neither the new fits nor the short paper results establish better decisions,
70% coverage or future Champion qualification. Sizing v8 remained active/healthy in the checked
snapshot; Entry/Manipulation continued collecting proof, Exit was suspended and Coach inconclusive.

README and learning documentation now explain the continuity window followed by each new row's
own outcome horizon, so a healthy trainer waiting for evidence is not mistaken for a stalled fit.
Documentation links and the repository whitespace check passed. The existing verified backup's
manifest and archive size still matched; the full archive was not reread unnecessarily.
Host headroom was **11.53 GiB on E:** and **1.62 GiB on C:**. Disk space, longer pressure evidence,
full main-database integrity and a full restore rehearsal remain limitations. No new application
defect was identified, and no settings, gates, permissions, evidence or services were changed.

## Idle recovery and audit follow-up — 19 September 2026

This section records the **local candidate validation**, before the live rollout recorded below.
It was separate from the preceding deployed retention build. Implementation
started from a private, credential-free source snapshot, preserving the earlier uncommitted
v1.10.11 work. Live settings, services, seasons, permissions and data were not changed. The paused
v1.11 workspace and scheduled review were left untouched. Version remains 1.10.11 and schema 16.

The stages retained their own regression gates:

- Diagnostic idle recovery: **174 tests passed**. A finite lag sample from a completed event
  cannot indefinitely block collection after admitted work has drained. Queue producers,
  dequeued receipts, batches in flight and season boundaries remain distinguished from idle.
- Attribution and persistence timing: **200 tests passed**. Fixed collector counters and coherent
  worst-operation samples retain original times and partial/error outcomes. Existing proof
  priority, eight event slots, byte limits, cooldowns and loss accounting remain in force.
  Worker data is merged after joining, including repeated cancellation. Duplicate batches,
  SQL/serialization/commit failures and disabled/failed reporting preserve persistence behavior.
- Fee provenance: **153 tests passed**, including 34 dedicated provenance cases. Both venues,
  buy/sell, SOL/USDC, aggregate and component rounding, zero/repeated components and the LP
  liquidity boundary replay from saved inputs. Optional metadata is tolerant on read and strict
  in the pure arithmetic audit; malformed or missing metadata cannot hide core receipts.
- Local learning recovery: **242 tests passed** before the final nonfinite-current-clock checks.
  Recovery requires five quiet monotonic seconds after a successful batch, and no admitted work.
  Failed/cancelled batches cannot establish it. A dequeued-event handoff cannot admit publication;
  urgent arrivals, context and the existing 120-second job lifetime are rechecked after collection.
  RPC freshness, optional AI pressure, valid failures and all proof/permission gates are unchanged.

The new-reader/old-image compatibility rehearsal used only a synthetic database with a new
receipt and a held position. The currently deployed retention image reopened a copy and retained
identical cash, positions, ledger, chronology and raw receipt bytes. This verifies that optional
outer receipt metadata does not break that rollback reader. It is **not** a full live-database
integrity check or backup restore rehearsal; those remain unverified.

The isolated persistence overhead check used 18 counterbalanced rounds of 64-event transactions
per variant, omitting two warmup rounds. Median baseline time was **1.440 ms**, with instrumentation
**2.081 ms**, and disabled instrumentation **1.678 ms**. The added **0.641 ms** met the predeclared
budget of an extra maximum of 10% or 2 ms per transaction. It is roughly 45% of this tiny baseline,
so this is an accepted measurement cost, not a speed improvement. Exact inserted IDs and 3,456
saved rows were checked. This fixture does not establish live burst capacity or tail latency.

At **07:07 BST**, an indexed, read-only, two-second-bounded query inspected at most 60 completed
observations created before a fixed cutoff. The sample had 37 usable outcomes and 23 recorded
failed quotes. Saved quote inputs reproduced all 23 failures: **20 insufficient-liquidity and
three fees-exceeding-proceeds failures**, with no disagreement or unknown input in this sample.
This complete-row sample does not cover the whole fitted cohort or unresolved checkpoints.
The earlier fixed 1,000-row cohort had 515 usable, 392 quote failures and 93 missing outcomes;
recovering every missing outcome would yield only **60.8%** for that cohort while retaining its
recorded failures. Neither that bound nor another generation's percentage is a universal ceiling.
No coverage denominator, admission population, quote failure, batch size or threshold was altered.

Broader performance optimization and trading-policy changes remain evidence-dependent. The new
coherent timings have not yet been observed live and do not justify larger RPC batches, relaxed
freshness, deferred governance, less durability or a new entry/exit filter. Strategy research needs
untouched chronological and forward evidence after costs. These changes cannot promise 70%,
a Champion or profit.

Final integration completed at approximately **07:24 BST**:

- **2,177 backend tests passed** on the final application/test source, in four serial, one-CPU,
  networkless containers (460 + 529 + 461 + 727). Tests used temporary databases and no live mount.
- Ruff lint and formatting passed for 165 files; strict mypy reported no issues in 49 source files.
- **425 frontend tests passed** across 22 files. ESLint, TypeScript and production build passed.
  The existing EquityChart fast-refresh lint warning, large scene-chunk advisory and backend
  Starlette/AnyIO deprecation warning remain; none is a new failure from this change.
- The repository Dockerfile built `signal-arcade:v1.10.11-safety-candidate-20260919`, image
  `sha256:9496a080c3cb6d3f79a8d75f7269958cb925dcb3255a511ed2518ee63721aeee`.
  All **49 installed backend source/resource files** and **30 embedded frontend sources** matched
  the tested source. The checking helper initially counted only Python files while expecting the
  total including two resources; correcting that helper verified the complete package inventory.
- An isolated, networkless, one-CPU demo container passed worker startup, authentication,
  snapshot/learning/diagnostics routes, served assets, schema 16, the unchanged 70% gate and
  Settings prepare/cancel. New runtime evidence was readable with no reporting errors. Its
  diagnostic build was `2dd5d2a72987382f17dfc7c61cfd84c6fc52bba16a4fe399225d4221d410a165`.
  This exercised disposable data only. Runtime dependencies matched those used for the backend
  checks, including the test runner's idna 3.20 overlay. Dependency manifests were unchanged;
  remote vulnerability audits were not repeated in this implementation pass.
- Source comparison confirmed no deletion of starting files and no changes to dependency
  manifests, learning/proof formulas or quote arithmetic. README, changelog, learning and
  diagnostics documentation now describe the candidate and its limitations. Whitespace checks passed.

At **07:24 BST**, read-only Docker inspection confirmed the live app still ran the earlier
retention image `sha256:f1b6da446c5b35109789aa7b1e19cd547172f321a50df996c4639acbbf4fd15c`,
started at **03:14:11 UTC**, healthy with zero restarts. That is a container observation, not a
new learning/performance review or evidence that this candidate is deployed. E: had **11.22 GiB**
free and C: **1.60 GiB**. No live restart, upgrade, push, forced training or promotion occurred.

Before deployment, repeat the Settings preparation and recoverability checks with current disk
headroom and compare state at equivalent maintenance boundaries. The isolated old-reader check
does not replace a real backup/restore rehearsal. After a separately authorized rollout, validate
actual image/build/boot, quiet recovery, natural bursts, retained training/proof groups, diagnostic
gaps and resource costs. Sustained performance and learning quality remain unproven by local tests.

### Additional edge review — 19 September 2026

The follow-up review added **18 interaction cases** and passed **210 targeted tests** covering
idle recovery, publication pressure/backlogs, diagnostic limits, receipt compatibility, source
boundaries and coverage gates. These checks verified:

- Urgent work, stop, storage activity or a changed clock while training waits for the market
  lock prevents preparation after acquisition; the lock is released correctly.
- A source switch can discard queued/parked records without forgetting a dequeued receipt.
  Its stale source event remains fenced; learning remains blocked until that receipt completes.
- Collection immediately before publication does not extend the original 120-second lifetime,
  including the exact deadline and a value just beyond it.
- Optional slow-work reporting failures cannot replace the storage result or its original error,
  and storage ownership is released on both paths.
- Eight missing, malformed or unknown fee-provenance forms survive a complete disposable database
  close/reopen without changing held-position access, cash, ledger, chronology or raw receipt bytes.
  The arithmetic audit reports unavailable/invalid inputs rather than inventing successful proof.

No application-code defect was reproduced and no runtime code, configuration or live service was
changed. Only tests and this validation record were added to. The 2,177-test full integration run,
425 frontend tests and packaged-image checks above still apply to the unchanged application source;
the 18 new cases add coverage. This review is not a new live performance observation or deployment.

## Idle recovery and audit live rollout — 19 September 2026

The user authorized deployment after the checks above. The tested application was deployed
through the existing Settings preparation path, replacing only the app service. Version remains
**1.10.11**, schema **16**; the same named data volume and Ollama service were retained.

- Image: `signal-arcade:v1.10.11-safety-candidate-20260919`.
- Image ID: `sha256:9496a080c3cb6d3f79a8d75f7269958cb925dcb3255a511ed2518ee63721aeee`.
- Diagnostic build: `2dd5d2a72987382f17dfc7c61cfd84c6fc52bba16a4fe399225d4221d410a165`.
- Boot: `dd09d54cd1d948fdabc28ee043c5f497`; container start **06:39:24 UTC / 07:39:24 BST**.
- Settings preparation started **07:31:31 BST**, reached ready at **07:31:48 BST**, and
  recorded completion after restart at **07:39:40 BST**. Application startup completed at
  **07:39:47 BST**. The stopped/maintenance period is a collection gap, not healthy coverage.

After clean shutdown, a complete stopped-volume archive was created and read back. All five
files matched their SHA256 hashes and gzip CRC verification passed. The compressed archive was
**4,078,952,938 bytes (3.80 GiB)**; backup and verification took **447.94 seconds**. The previous
image and private configuration copy were retained. An exact comparison confirmed the only
configuration change was the image pin. No earlier ledger was restored. Archive verification and
the synthetic old-reader check do **not** replace a full database integrity scan or a full real
backup restore rehearsal; both remain unverified.

The first live snapshot passed 15 unchanged-state checks, including season 58, profile, risk,
permissions, Champion state, the 70% gate, maintenance completion and held-only probes. Strict
cash/position equality correctly failed because normal paper trading resumed: one sell at
**07:39:57 BST** increased cash by **4,591,607 USDC minor units** and reduced four holdings to
three. Bounded primary-key and ledger reads reconciled both differences exactly. Its ledger
balanced, surviving holding identities matched, and the new optional fee provenance replayed
exactly. This cash movement is not a profit or learning-improvement claim. The execution audit
was verified with no issues. Authentication was enforced and the checked app/API pages returned
successful responses.

Read-only primary-key checks verified the existing latest learning record and all five observed
unique native skill artifacts, including inline parameters and the external XGBoost payload
hashes. These were historical pre-restart artifacts, not new training on this boot. Sizing v8
remained active and healthy; Entry and Manipulation collected proof, Exit remained suspended,
and Coach remained inconclusive. These legitimate gates and lifecycle states were preserved.

At **07:43 BST**, three consecutive saved intervals (0–2) spanned **186.17 seconds**, with the
initial partial interval labelled and no recording-gap flags or sequence holes. Fourteen events
were read, below the 30-interval/100-event bounds. New `collector_work` and coherent heartbeat
and persistence `slow_work` records were saved. Their original sample times and phase timings
were retained; nested elapsed phases must not be added as CPU time. There were no shed/expired
pipeline events or reported diagnostic losses. Saved maxima were queue **333**, overall lag
**5.09 seconds** and critical lag **4.30 seconds**. Current queue was zero and overall/critical
lag **0.029/0.013 seconds**. The fresh dashboard was **2.21 seconds** old and diagnostic writer
acknowledgement **21.81 seconds** old. All seven workers were running with no restarts or reported
trainer/RPC errors. These are short startup observations, not sustained burst validation.

The old boot's **1,462 expired candidate events** are not losses from this new boot. Likewise,
new zero counters do not prove improvement. Operational coverage moved from **61.6%** before
maintenance to **59.1%** afterward, while the existing fitted cohorts remained **57.4%**. These
are different populations, affected by the maintenance gap; neither movement establishes a
learning regression or improvement. Valid quote and performance failures remain in the evidence.
No training, promotion, outcome repair, threshold or permission change was forced.

The closing snapshot at **07:45:33 BST** was **2.17 seconds** old, with a **48.27-second**
diagnostic acknowledgement age, no reported diagnostic losses, all seven workers running and
no degraded reasons. Queue was zero; overall/critical lag was **0.014/0.148 seconds**. There
were **29 RPC requests and 96 checkpoint updates**, no RPC worker errors or post-fetch discards,
and two pre-request market-health deferrals. Discards remain a subset of aggregate deferrals.
Cash and holdings still matched the reconciliation. Routine cleanup had resumed and removed
**4,911 old raw events**; its last completed chunk took **0.078 seconds**. The reported oldest
trade timestamp was sampled at **07:44:50 BST** and was roughly **17 minutes** behind the
24-hour retention target, so catch-up remained outstanding. A coherent storage sample was
available in memory; pending optional samples are not counted as saved records.

The final bounded saved read available at **07:45:05 BST** contained **five consecutive intervals
(0–4)** spanning **307.29 seconds**, with the same maxima and zero shed/expired events. Its 14
events were below both page limits; no recording-gap flag or sequence hole was observed. A new
fit/publication had not yet completed on this boot. The trainer reported no error and skipped
not-due work; post-restart continuity admission and subsequent outcome maturation still apply.
Natural training/publication, repeated pressure and idle recovery after a substantial burst
remain to be observed on this exact build. No performance or learning-quality claim follows
from this startup check.

The application/source comparison still matched all 238 recorded baseline file hashes except
the intentionally updated README; the additional edge-test file remains as recorded above.
The rollout documentation was updated separately. All 56 local documentation file targets and
the new rollout heading resolved, and the whitespace check passed. Host headroom was about
**7.40 GiB on E:** and **1.61 GiB on C:** after retaining the verified backup. Low host headroom,
the outstanding full integrity/restore rehearsals and longer live evidence remain limitations.
No new deployment defect was found in this bounded review. No public image or GitHub push,
new schedule, forced training, season change or modification to the paused v1.11 work occurred.

### Post-deployment edge review — 19 September, 07:49 BST

A further read-only review found no new application defect. The running image/build/boot were
unchanged, with healthy Docker status, zero restarts and no new bounded-log errors. All 238
recorded tested-source hashes still matched except the intentionally updated README. Existing
full integration and additional interaction tests therefore still cover the application source;
they were reviewed rather than unnecessarily rerun against the unchanged build.

Code review rechecked dequeued-but-unfinished work, producer admission, source/season boundaries,
urgent arrivals after lock waits, the five-second quiet boundary, failed/cancelled batches,
publication expiry after diagnostic collection, optional reporting failures, transaction/duplicate
semantics and malformed optional fee metadata. The pre-change source comparison confirmed that
the persistence addition instruments the existing SQL/transaction, while the broker addition
stores optional provenance without changing quote arithmetic. Learning formulas and proof gates
remain unchanged. The previously measured instrumentation overhead remains a cost, not evidence
of faster operation.

At **07:49:05 BST**, all seven workers were running, no degraded reason was reported, the dashboard
was **1.61 seconds** old and diagnostic acknowledgement age was **58.49 seconds**. Queue was zero,
overall/critical lag **0.338/0.046 seconds**, with **47 RPC requests and 134 checkpoint updates**.
There were no RPC errors, post-fetch discards or reported diagnostic losses. Seven pre-request
maintenance deferrals and two market-health deferrals were reported; they are not additional
discarded batches. Cash and three holdings still matched the preceding reconciliation, and the
paper execution audit remained verified.

A bounded saved read at **07:49:23 BST** contained **nine consecutive intervals (0–8)** spanning
**568.63 seconds**, with **34 events**, below both page limits. Only the initial partial interval
was flagged; no recording-gap flags, sequence holes or shed/expired pipeline events were observed.
The longest interval was **71.16 seconds**, so sampling was not an exact minute. Saved maxima
remained queue **333**, overall lag **5.09 seconds** and critical lag **4.30 seconds**. Collector
deferrals and all three slow-work lanes, including storage, were now saved. This confirms useful
new evidence and continued recording, not comparative burst capacity.

A two-second-bounded indexed read of at most 12 recent pending observations verified post-restart
enrollment and one-minute checkpoint progress: four usable outcomes and three recorded quote
failures in the inspected records; the other five had no checkpoint yet. None of this is a
five-minute fitted-cohort coverage estimate. An initial review projection used non-model field
names; checking `LearningCheckpoint.observed_at` and `net_return` corrected the private inspection,
without changing application data. The trainer reported four more outcomes needed, no error and
no new fit/publication yet. Its maturity/readiness contract remains applicable.

Cleanup had removed **28,905 raw events**; its timestamped oldest-trade sample was roughly
**12.2 minutes** behind the retention target, improved from the earlier **17 minutes**, while
catch-up remained incomplete. Operational/fitted coverage remained separate at **59.1%/57.4%**;
the fitted artifacts were still pre-restart. Host headroom remained **7.40 GiB on E:** and about
**1.60 GiB on C:**. Longer natural training/publication, burst recovery, performance and learning
quality remain unverified; no new application change or live mutation was made in this review.

## Configurable skill coverage — local implementation, 19 September 2026

Implemented the approved optional **70% (default), 65%, 60%** requirement under the collapsed
Settings → Learning requirements section. Version remains **1.10.11**, schema remains **16**.
At this implementation stage, the feature had **not been deployed or pushed**. No live requests, configuration changes,
service changes, forced training, promotions, season changes or database resets were performed
for this implementation. The paused v1.11 workspace and paused steward were not touched.

### Scope and stage checks

1. **Persisted policy and authority boundary.** A strict, versioned setting is separate from
   configuration and evidence identity. The existing authenticated, same-origin mutation path
   serializes it with upgrade preparation and the event boundary. Stale revision saves fail;
   no-op saves do not increment revisions. Settings and required authority revocations commit
   together before memory changes. Failure injection verified rollback and restart consistency;
   automatic-support and consent preferences are preserved.
2. **Fitting and proof.** New native Entry Linear/XGBoost, Manipulation, Sizing and Exit use the
   selected applicable coverage gates, including contextual Exit's reference comparison. New
   generations need a validation cutoff after the setting change; changing back cannot publish
   an old in-flight job. Two real-fit comparisons at 60% and 65% retained the same rows, feature
   parameters, metrics, cohort digests, payload bytes and predictions as the 70% run. Their 210
   fee failures out of 600 observations stayed unavailable (65% coverage), and missing separate
   Policy proof still blocked qualification. Historical proof is not reclassified.
3. **Lifecycle.** All four native skills were exercised at exactly 60/65/70% and one usable
   outcome below each threshold, with fixed sample minima. Active health, raising a requirement,
   persistence failure, restart, closed recovery, repeated toggles and fresh battle boundaries
   were checked. Battles retain the existing 120-usable/172-resolved budgets. A 172-resolved,
   zero-usable battle still closed inconclusively at 60%. Coach-derived support and mixed
   Coach/native battles retain 70%; legacy timing fallback and Champion-impact reporting retain
   their separate fixed requirement. Raising may remove authority; it does not trigger a sale.
4. **Presentation and diagnostics.** Saved artifacts, battle/recovery receipts and current
   selection are labelled separately. A stricter current eligibility gate does not rewrite
   historical fitted checks. Unknown policy metadata cannot produce an infinite JSON threshold
   or an invented passed gate. Interval gauges and compact existing proof events expose the
   selected/saved revision without new requests, polling or event types. Browser checks used an
   isolated fixture and the app's real component/styles: collapsed/expanded states, a simulated
   save, desktop/phone presentation and tablet grid bounds were checked. At 390 and 1,024 px,
   the document width equalled the viewport; tablet header and actions did not overlap. Temporary
   preview tabs, viewport overrides and the development server were closed afterward.

### Validation results

- Full backend regression: **2,274 passed**, in four serial offline Docker shards
  (**476 + 559 + 500 + 739**). Final malformed-recovery hardening added one regression case;
  **131 targeted backend tests passed afterward**, including coverage policy/lifecycle/API/real
  fitting, recovery, persistence and legacy Exit evidence. These totals overlap.
- Full frontend regression: **436 passed in 23 files**. Final app/proof/recovery/arena rerun:
  **373 passed in 14 files**. These totals overlap.
- Strict backend type check: **48 source files passed**. Frontend TypeScript and production
  build passed. Ruff lint and formatting passed across **171 Python files**; Git whitespace
  checks passed. ESLint had no errors and retained the pre-existing `EquityChart.tsx` Fast
  Refresh warning. The existing optional 3D scene bundle remains above Vite's 500 kB warning.
- Broader testing caught a legacy synthetic battle fixture without timestamps. The new
  timestamp filter now runs only for versioned prospective battles; unchanged legacy battles
  retain their original behavior. A separate test excludes observations one microsecond before
  a new battle's start and accepts the boundary itself. Final malformed recovery checks refuse
  qualification while preserving the corrupt receipt for inspection, without serializing infinity.
- Initial full-suite runner attempts lacked fixture/IDL files and used a 512 MiB temporary
  filesystem, correctly tripping the recorder's 512 MiB free-space guard. The isolated runner
  was corrected (fixtures included, 1 GiB tmpfs, 1 CPU and 1.5 GiB memory limit), and all four
  shards then passed. No application storage guard was weakened to make tests pass.
- README, Learning, diagnostics and changelog descriptions were updated. Existing uncommitted
  reliability changes remain present. Private evidence and source archives remain ignored.

### Limits and rollout requirements

This is local functional validation, not evidence of improved learning, throughput, profits or
future Champions. A lower requirement accepts less complete evidence; it does not raise the
measured coverage or repair valid quote failures. All other sample, chronology, fee, performance,
complexity, harm and permission gates still apply. Existing 70% artifacts keep that contract;
the new setting does not immediately promote an older blocked generation. Natural retraining
readiness and fresh validation may take time.

Leave the live app at its existing setting until a separate rollout through Settings preparation.
After rollout, verify default/selected policy persistence, actual build and timestamps, natural
fresh fits, immutable proof, worker/queue/diagnostic continuity and execution-ledger continuity.
Compare economic outcomes only across comparable fee-inclusive cohorts with sufficient samples.
Rollback requires the matching pre-upgrade data and image together; an old image does not
understand lower-threshold proof metadata. No old-image/current-data rollback was attempted.
Host headroom during this task was about **7.38 GiB on E:** and **1.59 GiB on C:**; deployment
backup capacity still needs its own check. No live performance improvement is claimed here.

### Second coverage-setting edge review — 19 September 2026, local only

The additional review reproduced and corrected two local edge cases before deployment:

- A native artifact fitted under 65% could activate under 70%, then have its ongoing health
  requirement fall back to 65% after a later setting change. Health now retains the stricter
  saved activation contract, and recovery inherits it. Manual native-skill activation also
  saves this contract once the setting has been versioned; unchanged default legacy receipts
  retain their existing format. Checks cover Entry, Manipulation, Sizing and Exit.
- Malformed coverage metadata in a native Entry activation receipt could bypass its early
  proof check. Such receipts now block authority, including manual-mode restoration after a
  restart, and cannot enroll a recovery trial. Unknown requirements never become a permissive
  fallback or a nonfinite dashboard value.

Twelve regression cases were added. The final selected backend run passed **341 tests** across
coverage policy/lifecycle/API/real fitting, learning, independent participation, progression,
recovery, persistence, Coach lifecycle, legacy Exit evidence and battle replay. This overlaps
the preceding full-suite counts; it is not another full-suite run. It also verifies that a
threshold increase preserves Champions whose fitted and activation proof already satisfy it,
and that a Coach challenger against a native Champion freezes both sides at 70%.

An initial manual-mode test omitted the required Entry authority and correctly failed restart
restoration. The fixture was corrected to include Entry; that existing application guard was
preserved. Separate failing tests reproduced the two defects before their fixes. The final
run retained only the existing Starlette/AnyIO deprecation warning.

Strict mypy passed for **48 backend source files**; Ruff lint and formatting passed across
**171 Python files**, and the repository's normal Git whitespace check passed. Frontend code
was unchanged in this review, so its preceding validation results were not counted again.

Learning documentation now explains the stricter saved activation contract. The dropdown,
default, fitting recipes, evidence denominators, sample minima and remaining proof gates are
unchanged. This review did not access or change live settings, data or services, deploy, push,
or claim improved learning performance. The feature and corrections had not yet been deployed
at the end of this review; the subsequent rollout is recorded below.

## Configurable coverage live rollout — 19 September 2026

The user requested the live update through Settings and explicitly chose to skip new backups.
No data-volume backup or extra environment backup was created. The same named data volume and
runtime settings were retained; only the local image pin changed. Nothing was pushed or published.

- Image: `signal-arcade:v1.10.11-coverage-settings-20260919`.
- Image ID: `sha256:e9b4cdc3f4185000296f0c145e617dfe1ab74fed240ebbc396e05327c5320931`.
- Diagnostic build: `3668c0b5e40cf33c5fd8adf0d3e9129e4d4e15102eae2921ccf678d3838feb07`.
- Boot: `72f8a9d451724580a1fcbd0f819c9a24`; schema remains **16**, version **1.10.11**.

Before replacement, the packaged image matched all **50 installed backend files** and **31
embedded frontend sources**, including the new Settings component. All **30 installed runtime
package versions** matched the preceding image. An isolated, networkless smoke test with no
live volume verified authentication, main API/pages, the 70/65/60 choices, stale-save rejection,
unchanged permissions and upgrade preparation/cancellation.

Settings preparation reached Ready at **09:44:22 BST** with no pending orders to cancel. The
old app shut down cleanly at **08:44:27 UTC**; the replacement container started at
**08:44:28 UTC**, and application startup completed at **08:44:51 UTC**. Its unchanged Docker
health check passed and the same Settings operation completed. This pause is an observation gap.
The rollout retained **70%, revision 0**; no live coverage-setting mutation was made by the agent.

Post-upgrade reconciliation preserved season **59**, its profile, risk mode, bankroll, all
three held position identities, exact cash, active Sizing Champion v8, consent and automatic
participation. No fills occurred in the initial reconciliation window, and the execution audit
was verified without issues. Held-only probes, authenticated pages and the live Settings assets
also passed. All seven workers were running, with zero Docker restarts or OOM events.

One natural fit/publication completed at **09:45:30 BST** from retained evidence. Its saved
publication group contained the training event and all six proof events, indices 0–6, with a
maximum collection delay of **17.15 seconds**. The model and five unique native skill artifacts
were verified with bounded primary-key reads; inline and XGBoost payload digests matched.
An initial private verifier incorrectly hashed all Entry parameters: its actual digest includes
feature names and fitted coefficients/scales/means, excluding separate Policy cohort metadata.
The verifier was corrected to match the implementation; no app or data change was needed.

The bounded saved diagnostic read contained **four consecutive intervals (0–3)** and **21
events**, spanning **247.58 seconds**, below its 30/100 read limits. Only the first interval was
marked partial; no recording gap or sequence hole was observed. Peak queue was **410**, overall
lag **3.52 seconds**, critical lag **2.54 seconds**, with zero shed or expired pipeline events.
All four intervals saved coverage **70%, revision 0**. At **09:48:25 BST**, the snapshot age was
**1.23 seconds**, diagnostic acknowledgement age **36.65 seconds**, publication backlog empty,
trainer/RPC worker errors zero and execution audit verified. Three post-fetch processing-lag
discards were observed, within aggregate guard deferrals, not extra losses. The four startup log
lines were INFO from the `uvicorn.error` logger; its name is not an ERROR severity. Host free
space was about **6.97 GiB on E:** and **1.55 GiB on C:**.

### Resume verification after the interrupted response

At **16:27 BST**, a fresh bounded check confirmed the same image, build and boot still healthy,
with zero restarts or OOM, all seven workers running, **151 completed training/publication
cycles**, no trainer error, an empty publication backlog, and a verified execution audit.
Snapshot age was **2.25 seconds**, diagnostic acknowledgement age **59.67 seconds**, current
queue **4**, overall/critical lag **0.010/0.099 seconds**, with no cumulative pipeline shedding,
expiry or reported diagnostic record loss. This check did not paginate the intervening history,
so those counters are not proof of uninterrupted diagnostic sampling over the whole period.

The setting had independently been saved as **60%, revision 1**, effective **10:44:33 BST**.
The agent left it unchanged. Recent native generations report 60%; legacy Sizing Champion v8
remains healthy under its saved requirement. Entry/Manipulation remain collecting proof, and
Exit remains suspended. Other performance and fresh-validation gates still apply; new Sizing
and Exit generations were correctly blocked where their validation began before the change.

One historical RPC-worker error was recorded; `last_error` was clear, the worker was unblocked
and had completed subsequent requests (**2,152 requests / 9,517 checkpoint updates** at this
snapshot). The bounded boot log contained eight warnings and no ERROR/CRITICAL lines or
tracebacks. Its exact transient cause was not established by this check. Host headroom was
about **6.91 GiB on E:** and **1.29 GiB on C:**. No further app, service or setting changes were
made during resume verification; only documentation deployment status was completed.

These observations verify deployment and current operation, not profitable decisions or
guaranteed Champions. Full main-database integrity and full backup restore rehearsal remain
unverified. After a lower requirement has been saved, an older image must not be pointed at
the current data; rollback still requires compatible code and matching data. No rollback was
needed or attempted.

## Community presentation and diagnostic polish — 19 September 2026

This section first records local validation; the subsequent Settings rollout is recorded below.
Version remains **1.10.11**, schema remains **16**. No live settings, data, services, permissions,
seasons or Champion states were changed during the initial local checks. The saved 60% selection,
Coach's fixed 70% and historical proof contracts are outside this patch. The paused v1.11 work
and steward remain untouched. The changes are now deployed locally; community push is pending.

### Changes and stage boundaries

- **Entry checklist correction:** reproduced the duplicated coverage-freshness row for both
  families, then separated finite-value sanitization from adding the freshness check. Family
  lists now include the check once. Tests inspect the full list before dictionary conversion,
  cover 60/65/70%, legacy and malformed metadata, and assert unchanged artifact serialization
  and qualification. Stage-one proof, coverage, lifecycle and fitting checks: **125 passed**.
- **Saved learning details:** expose each artifact's already-persisted schema and evidence dates
  in its summary. The UI distinguishes actual training/validation/chronology counts, usable
  Discovery periods, Sizing target exclusions, contextual Exit's shared cohort, and Coach's
  independent study populations. Missing or invalid dates/counts remain unavailable. No cohort
  is reconstructed from current rows, and no new query, polling, fitting or persistence path is
  introduced. Stage-two checks: **29 backend** and **49 frontend** tests passed; TypeScript passed.
- **Optional diagnostic attribution:** a fixed `other_event_kinds` breakdown counts lost input
  events within the existing `other` category. Unknown names become `unknown`; counters detach,
  saturate and reset per boot. Input and compressed payload limits, eight-event priority,
  four-group publication backlog, interval cadence and recording-gap behavior are preserved.
  Stage-three diagnostic/publication/runtime checks: **131 passed**, including a populated
  high-counter payload. These targeted totals overlap; they are not additive suite totals.
- **Burst investigation:** correlated retained samples with the same boot and time ranges in
  the preceding 387-interval/2,401-event review. One gap included 3.05 seconds of heartbeat
  expiry elapsed time; another busy interval included 2.41 seconds of cache elapsed time. The
  worst 113.89-second gap had no matching retained slow-operation sample. Five-minute cumulative
  detail brackets wider periods, and elapsed timings include waits/descheduling. No single
  reproducible application cause was established, so no hot-path, collection, queue, cleanup,
  RPC-batch or governance optimization was added. The known pressure remains an open limitation.
- **Window experiment decision:** retain the 1,000 limit. The preceding 72 comparisons across
  1,000/2,000/3,000 windows did not justify a blanket increase; larger fits did not resolve the
  observed coverage problem. Sizing/contextual Exit may merit separate experiments, using new
  unseen periods and fixed predeclared alternatives. The already-inspected confirmation period
  must not be reused as a fresh holdout. No experimental model was published.

A structural comparison against the immutable deployed coverage-settings image verified that
the entire `LearningEngine` class and module constants are identical. Only the artifact-summary
and checklist functions differ, with one new finite-value helper. Thus this patch does not
change fit recipes, evidence selection, outcome-time embargoes, promotion rules or permissions.
This comparison is code evidence, not a claim of better trading decisions or future Champions.

### Final edge-case and regression checks

The complete backend suite covered **2,315 distinct tests**, all passing after correcting an
offline-runner packaging omission: the initial archive omitted `CHANGELOG.md`, so its version
test could not read that file. Adding the unchanged changelog to the isolated archive resolved
that test; no release/version code was changed. Ruff passed, all **172** checked Python files
were already formatted, and mypy reported no issues in **50** source files.

The frontend run covered **454 tests in 24 files**. At a half-CPU limit, 452 passed and two
existing Arena tests exceeded timing assumptions. The exhaustive motion test passed unchanged
when run serially with one CPU. The cold lazy-loading focus test still exceeded its default
one-second query wait; its readiness wait is now bounded at three seconds, retaining every
skill-switching, Escape, focus-return and body-scroll assertion. All 11 tests in that file then
passed. Thus every test passed across the complete run and targeted reruns; the original run
was not entirely green. No runtime Arena, animation or loading behavior changed.

TypeScript and the production frontend build passed with the pinned dependency versions
verified against the existing isolated test image. ESLint completed with zero errors and its
existing `EquityChart` Fast Refresh warning; Vite retained the existing lazy 3D-scene chunk-size
warning. `git diff --check` passed. Private bundles include the new source/tests and exclude
credentials, live data and local evidence; their output remains ignored by Git and Docker.

The new Learning details were visually checked with synthetic saved artifacts and real app
components/styles at phone and desktop widths. At 390 and 1,024 CSS pixels, no new content
clipping or horizontal overflow was detected, and the browser reported no warnings/errors.
Missing fields, invalid/reversed dates, legacy schemas, per-family count meanings and long
identifiers were covered. At 320 pixels with a classic desktop scrollbar, the existing global
320-pixel body minimum still causes a 15-pixel viewport overflow; no new detail text clipped.
The local preview was stopped and its browser tab closed after inspection.

### Read-only live close and additional burst evidence

At **17:30:45 BST**, the live app still used the coverage-settings image/build/boot recorded
above; this local polish had not been deployed. Docker was healthy, with zero restarts or OOM,
all seven workers running, **176 completed training/publication cycles**, no trainer error and
an empty publication backlog. The authenticated snapshot first returned a 2,027-second-old
cache; one bounded retry obtained a **1.83-second-old** snapshot. This is refresh recovery,
not continuous dashboard freshness. Diagnostic acknowledgement age was **58.97 seconds**.
Current queue was **20**, overall/critical lag **0.003/0.033 seconds**, and the paper execution
audit was verified without issues. The saved 60%, revision 1 remained unchanged.

However, cumulative low-priority candidate expiry had risen from zero at **16:56:58 BST** to
**8,042**, with no capacity shedding. A fixed-end read-only review of that intervening window
retrieved **28 consecutive intervals (411–438)** and **204 events**. Both paginations reached
an empty page, using two interval pages and four event pages within caps of two/eight pages,
100 rows per page and a 30-second total query budget. The saved intervals span **16:57:00 to
17:29:46 BST**; the beginning and final minute are not fully represented by completed intervals.
Event inclusion follows its saved cursor; delayed samples can describe earlier work.

- Expiry was **409 / 2,413 / 5,220** in intervals 430 / 434 / 438. These are pipeline events,
  not counts of unique missed outcomes or recoverable trades.
- Peak queue was **9,042**, overall lag **20.85 seconds**, and critical lag **8.89 seconds**.
  Four recording gaps lasted **101.39 / 97.47 / 110.76 / 115.52 seconds**. There were no sequence
  holes, but consecutive sequence numbers do not make these long intervals healthy coverage.
- All **13** saved publication groups contained one training event and six proof events,
  indices 0–6, with maximum collection delay **52.19 seconds**. Reported training, proof and
  storage event losses remained zero; optional capacity losses rose from two to **three** at
  the close snapshot. The six retained loss summaries still reported two, so the extra loss
  cannot be assigned to a saved event kind. This deployed build lacks the new kind breakdown.
- A same-boot heartbeat sample within interval 434 recorded **7.08 seconds** in expiry out
  of **7.82 seconds** total elapsed. Other samples showed database-query and dispatch/resume
  delays. These are selected elapsed measurements, with overlapping phases and descheduling;
  they do not identify one CPU bottleneck or establish that expiry caused the whole burst.

The offline checks were isolated from live data/network and CPU/memory bounded, but shared the
Docker host. Their possible contribution to host scheduling or I/O pressure is unresolved;
this window is not an uncontaminated performance comparison. The local patch cannot explain
the live change through deployed code because it was not running there. No speculative hot-path
change was added in response. Before claiming community load readiness, collect comparable
natural-burst evidence without concurrent local test/build jobs, then reproduce any suspected
bottleneck offline. Any optimization must preserve expiry validity, held-position/Policy
priority, proof accounting and bounded work, and pass the same regression checks.

A final serial read at **17:37:26 BST**, after all offline check containers had exited, confirmed
the same live build/boot, all seven workers, **178** completed publications, no trainer error,
an empty publication backlog and a verified execution audit. Queue was **43**, overall/critical
lag **0.101/0.101 seconds**, and acknowledgement age **14.65 seconds**. A cached snapshot aged
399.69 seconds refreshed on one retry to **0.003 seconds** old. Cumulative expiry had increased
further to **10,518**, still with zero shedding and three optional diagnostic losses. The
additional 2,476 expiries were not separately paginated; this closing snapshot does not establish
when they occurred or whether pressure has stopped. Docker exposed eight CPUs; the live app had
no container CPU cap. Offline checks had used limited fractions of that shared capacity, which
does not eliminate host interference. No further polling or live mutation was performed.

### Remaining release limits

The latest close above carries **10,518 candidate expiries** and **three optional diagnostic
losses**. Saved histories contain long recording gaps; an earlier review also recorded one
recovered RPC-worker error. More precise reporting does not repair or recover past missing
evidence. Full main-database integrity, complete restore and
abrupt-crash durability remain unverified; no heavy live operations were run for this patch.
Host headroom at the start was about **6.85 GiB on E:** and **1.31 GiB on C:**. Existing test
images and bounded temporary files were used rather than new images, dependencies or backups.
The later headroom check was **6.85 GiB on E:** and **1.26 GiB on C:**; this remains limited.
Recheck capacity before a later Settings rollout. Private experiment, snapshot and log files
remain excluded from Git and Docker contexts. Community publication remains pending.

### Additional edge-case review — 19 September 2026

Before this follow-up, all **243** source/test files compared against the preceding isolated
validation bundles matched. The review checked saved count/date construction across Entry,
Manipulation, Sizing, deterministic/contextual Exit and Coach, the single Entry freshness row,
legacy/malformed proof handling and the new optional diagnostic loss breakdown. No fitting,
qualification, execution or diagnostic-priority change was needed.

One presentation defect was reproduced: JavaScript silently normalized an impossible saved
date such as `2026-02-30T12:00:00Z` to March 2. The new evidence panel now rejects impossible
calendar/time fields before parsing. Missing timezone, zero year, invalid month/day, non-leap
February 29 and 24:00 stay unavailable. Valid leap days, fractional seconds, timezone offsets,
equal instants across different dates and Unix epoch zero remain displayable. This validation
affects explanatory UI dates only; it never changes a stored timestamp or learning cutoff.

Both affected UI suites passed: **60 tests**, including **29** saved-evidence tests. An initial
type check identified potentially undefined array indices in the new helper; the implementation
now uses explicit numeric captures and a guarded month lookup. A disposable Linux runner also
needed LF line endings before it could run; that was a private harness issue. The 60 tests
passed again after these corrections. The broad backend/frontend suites were not rerun.
Final TypeScript compilation and focused ESLint checks passed with zero errors or warnings;
`git diff --check` also passed. The earlier production build was not repeated for this small
date-display correction. All isolated check containers exited; no checks remain running.

A separate bounded in-memory check round-tripped **256** synthetic diagnostic loss reports
with varied large counters, boot IDs and every allowed optional kind. Largest raw/compressed
sizes were **914/550 bytes**, below the existing **2,048/768-byte** limits. These sampled cases
supplement the previous rejection, eviction, saturation and boot-reset tests; they do not
change queue capacities or add a second loss count. Direct date checks also rejected 14 malformed
inputs and preserved 56 valid timestamp cases. No live request, service change, deployment or
push was made during this additional review. Previously observed burst/disk limits remain open.

### Learning presentation/diagnostic polish live rollout — 19 September 2026

The user subsequently requested deployment. The final checkout, including the calendar-date
correction, was built with the normal Dockerfile and frozen frontend lockfile. No backup was
created, following the user's earlier preference. The compatible preceding coverage-settings
image was retained for rollback; unlike the older pre-setting images, it understands the saved
60%, revision 1 policy. The database schema, fitting/authority code and permissions are unchanged.

| Identity | Deployed value |
| --- | --- |
| Image | `signal-arcade:v1.10.11-learning-polish-20260919` |
| Image ID | `sha256:46fe3db110625a0d345c5c00500f6f461299ff73f1b93da3cdf87eb56886a178` |
| Diagnostic build | `9a8a597945a6346de173dbd702387c10c62c7536e21d2320f02152990e4fccad` |
| Boot | `7dcc8981816a4a9fa2b0509bd910fe9d` |
| Container start | 19 September, 16:50:05 UTC |
| Application startup complete | 19 September, 16:50:33 UTC |

Installed-source verification matched all **50 backend files** and **32 embedded frontend
sources**, including the new saved-evidence component. All **30 runtime dependency versions**
matched the preceding deployed image. An initial private PowerShell property-count comparison
reported a mismatch; an exact dictionary comparison confirmed no dependency differences.
Only the two reviewed backend files differed from the prior image. No application workaround
or dependency change was needed. The normal production build passed with its existing lazy
3D-scene chunk-size warning.

Before touching live state, a disposable networkless container with temporary data passed
startup, authentication, bounded page/asset reads, Settings prepare/cancel, coverage choices
and stale-revision rejection, unique Entry checklist IDs, saved evidence metadata and the new
diagnostic loss field. Neither live data nor host credentials were mounted into that container.

The live app then reached **Ready at 17:50:00 BST** through the same Settings maintenance endpoint
used by the UI. Preparation cancelled **one pending paper order** through the normal maintenance
path, leaving no pending orders and preserving both held positions. The previous service shut
down cleanly at **16:50:04 UTC**, and the replacement passed its unchanged Docker health check
with zero restarts or OOM. The same Settings operation completed and normal running resumed.
This deliberate shutdown/startup is an observation gap. Only the local image pin changed in
deployment configuration; the named data volume and runtime environment were preserved. No
rollback, forced training, promotion, season reset or community push occurred.

Fresh post-upgrade checks against the settled Ready snapshot preserved **season 60**, profile/risk
mode, bankroll, exact cash and both position identities/units, active Sizing Champion v8, consent, automatic participation,
learning mode and Coach contribution permission. Skill coverage remained **60%, revision 1**,
effective **10:44:33 BST**, Coach remained **70%**, and the Entry window remained **1,000**.
The paper execution audit was verified with no issues, and probes were held-position-only.
Authentication remained enforced; served JavaScript contained the new evidence panel, and
bounded Champion journey, leaderboard, season and maintenance reads all succeeded.

One natural fit/publication completed at **17:52:24 BST**. The latest learning model and seven
retained unique skill artifacts were read by primary key with a five-second query deadline;
payload digests and snapshot correspondence matched. These included five newly created native
artifacts and the two retained Champions. New Entry/Manipulation generations carried the saved
60% policy with fresh validation. New Sizing/contextual Exit generations correctly remained
unqualified where their validation window still began before the requirement change. Existing
Champions retained their own historical 70% contract. No gate was relaxed to manufacture proof.

At the fixed closing snapshot **17:52:48 BST**, all seven workers were running, no trainer or RPC error
was reported and the publication backlog was empty. Snapshot age was **2.20 seconds** after one
retry refreshed a 93.44-second-old cache; diagnostic acknowledgement age was **23.46 seconds**.
Queue was **189**, overall/critical lag **0.068/0.068 seconds**, and new-boot shedding, expiry and
reported diagnostic losses were zero. The bounded startup log contained only four INFO lines;
`uvicorn.error` is the logger name, not their severity.

The fixed-end saved-history read returned **two consecutive intervals (0–1)** and **16 events**,
below its 30/100 limits, covering **125.22 seconds**. The first interval was labelled partial;
there was no recording gap or sequence hole in this small sample. Longest interval was **63.72
seconds**, peak queue **1,091**, overall lag **2.97 seconds**, and critical lag **1.37 seconds**.
The first publication group retained indices **0–6**, one training event and six proof events,
with maximum collection delay **0.21 seconds**. No overflow/crash-durability or sustained-burst
claim follows from these startup observations.

Operational Entry coverage was **551/1,000 (55.1%)**; fitted Linear/XGBoost coverage was
**532/1,000 (53.2%)**, a different cohort. Entry/Manipulation were collecting proof, Sizing v8
was active/healthy, Exit remained suspended and Coach inconclusive. These observations do not
establish improved decisions, profit or readiness for new Champions.

The preceding boot had reached **11,577 candidate expiries** at the deployment preflight. Its
counter reset at restart; the new zeros do not erase or solve that pressure. Burst reliability
remains open for comparable normal-traffic evidence without concurrent build/test work. Free
space after the build was about **6.47 GiB on E:** and **1.28 GiB on C:**, still limited. Full
main-database integrity and complete restore rehearsal remain unverified. The app is updated and
passed the bounded rollout checks; an unconditional community load-readiness claim is not made.

### Post-rollout read-only edge review — 19 September 2026

The follow-up closed at **17:58:48 BST (16:58:48 UTC)** on the same image, build and boot listed
above. This is a saved observation, not a claim about subsequent traffic. The container was
healthy with zero restarts or OOM, all seven workers were running, and trainer/RPC error counts
were zero. Two natural training/publication cycles had completed and the publication backlog
was empty. No new deployment defect was supported by this bounded review.

- The dashboard first returned a **193.59-second-old** cached snapshot. One bounded retry
  returned a snapshot **2.17 seconds** old; diagnostic acknowledgement age was **49.10 seconds**.
  The old response was not treated as a healthy current observation.
- Current queue was **187**, overall lag **1.63 seconds** and critical lag **0.19 seconds**.
  New-boot pipeline expiry, shedding and reported diagnostic losses remained zero.
- Saved history contained **seven consecutive intervals (0–6)** and **45 events**, below the
  30-interval/100-event read limits, covering **459.62 seconds**. The first interval was partial.
  There were no sequence holes or `recording_gap` flags, but the longest interval was **80.82
  seconds**: late sampling still limits visibility. Peaks were queue **1,148**, overall lag
  **4.55 seconds** and critical lag **2.61 seconds**. This is not a sustained burst test.
- Both publication groups retained one training event and six proof events, indices **0–6**,
  with maximum collection delays of **0.21** and **12.72 seconds**. Sequential natural publication
  does not verify simultaneous waiting groups, overflow handling or crash durability.
- RPC recorded **44 requests** and **210 checkpoint updates**. Two post-fetch batches were
  discarded by safety guards, one for queue pressure and one for processing lag. These are a
  subset of aggregate guard deferrals, not additional losses or counts of unique missed outcomes.
- Entry checklist identifiers were unique and coverage freshness appeared once per family.
  The selected **60%, revision 1** requirement, Coach's **70%** and the **1,000-observation** Entry
  window were unchanged. The paper execution audit reported no issues and probes were held-only.

Free host space was approximately **6.46 GiB on E:** and **1.28 GiB on C:**. The previous boot's
11,577 candidate expiries remain unresolved evidence; a restart resets counters, not historical
losses. Full main-database integrity and a complete restore rehearsal remain unverified. No app,
configuration, service or live data was changed during this review. Longer comparable traffic is
still needed to assess learning outcomes and burst reliability; these checks do not establish
new Champion readiness or profitable decisions.

### Burst diagnostics and AI dispatch follow-up — 19 September 2026

At this stage, the **locally validated follow-up awaited deployment**, still version 1.10.11. It did
not supersede the preceding live build/boot observations. No live settings, services, data,
seasons, permissions, thresholds or dependency versions were changed, and nothing was pushed.

The work followed three separately checked stages:

1. Optional diagnostic cooldowns now begin when an event is selected for an interval. An
   accepted event evicted before collection can retry. A finite kind/lane/horizon-part registry
   bounds cadence state across repeated scope changes. Admission favours uncollected and then
   least-recently-collected streams without displacing proof. Same-scope cumulative reports can
   refresh queued values; worse slow samples can replace earlier samples. Original scope/time,
   honest loss counters, whole publication groups, queue sizes, writer cadence and byte limits
   are preserved. Collected remains distinct from durably saved. **179 focused tests passed.**
2. Coherent `slow_work` samples now cover a market-processing batch and a dashboard refresh.
   Parts belong to that operation, including available worker CPU, dispatch/resume waiting and
   existing database/section detail. Nested elapsed times overlap and are not additive CPU.
   Task-local contexts restore after failure/cancellation, and reporting cannot abandon worker
   ownership. The worst-case interval test caught an initial attempt to add AI CPU/wait fields
   to every interval; those fields were moved to optional slow samples instead. The unchanged
   core interval and event budgets then passed. **219 focused tests passed.**
3. Local AI outcome dispatch now skips only provable pre-horizon no-ops using the original
   observation timestamp. A separate predicate preserves pending-token retention, critical
   event priority and enqueue deduplication. In-flight same-token work and incomparable legacy
   clocks conservatively keep the existing handler. A zero-delay yield preserves cooperative
   scheduling when a skipped executor call was the tick's only await. Deadline/grace edges,
   stale/unexecutable routes, original fees, negative outcomes, save failures, mode changes,
   restart and concurrent registration were checked. **203 focused tests passed** before the
   final combined review; its scheduling-fairness addition passed the wider suite below.

Final validation covered **2,352 distinct backend tests** across six serial, resource-limited,
networkless container batches and targeted edge reruns. One existing fixture claimed pending
AI work without supplying a saved assessment or due clock; it was corrected to provide a due
assessment, preserving its assertions for AI, broker and separate Discovery/Policy updates.
The corrected fixture and final scope/counter/encoding checks passed together (**86 tests**).
That rerun overlaps the full suite and is not an additional 86 distinct cases. Earlier setup
attempts also exposed test-container bind and temporary-space constraints; only the disposable
runner was adjusted. No production workaround was made for these fixture/environment failures.

Ruff checking and formatting cover all backend/test Python files. Mypy passed for **51 source
files**. The existing dependency deprecation warning remains. There are no frontend changes in
this follow-up; frontend tests/builds were not repeated. Byte comparisons against the starting
workspace verified that learning recipes, Coach, broker, quote math, database, API, models and
project version/dependency declarations are unchanged. Existing chronology, training/proof
separation, selected coverage policy and authority rules remain in force.

A small isolated synthetic comparison measured active-thread CPU per phase observation at
about **1.25 microseconds before / 2.55 after** coherent sampling. For a future-only AI outcome,
median wall time was about **328 / 16 microseconds per tick** across three 1,000-tick trials,
with the new path retaining its event-loop yield. These measurements concern instrumentation
and no-op dispatch only: they exclude real quotes, trading, database contention and matched
market traffic, and cannot predict overall throughput or recovered outcomes. An integration
check separately verified 100 skipped future calls and the first exact-due dispatch in each AI
mode, without changing event priority.

The final read-only container inspection still showed the prior learning-presentation deployment
running and healthy with zero restarts. At that checkpoint this follow-up had not run live. Further database-write
offloading or changes to shared-lock ownership remain conditional on the new timing evidence;
they were not bundled into this patch. The rollout validation requires checking actual build,
boot and fresh timestamps, then compare several natural bursts with comparable traffic and
training/cleanup activity. Track critical lag, expiry, checkpoint completion, optional-report
age, complete publication groups, resource headroom and genuine diagnostic gaps. Full database
integrity and restore rehearsal remain outside these checks. No sustained-burst, Champion or
profitability improvement is claimed.

#### Additional edge review of the local burst follow-up

A subsequent review reproduced a defensive input-validation gap: malformed `slow_work.elapsed`
values could raise during queued-sample comparison, before proof collection. Current producers
already emit bounded numeric values; this was an isolated test finding, not an observed live
failure. Optional identity/admission now rejects values outside that numeric contract before
comparison and counts rejected incoming reports as input losses. A malformed event submitted
through the generic JSON-only API cannot poison comparison with a valid optional sample.

The initial regression run reproduced nine failures. After the correction, **350 focused tests
passed**, including **13 new cases** for malformed elapsed values, valid numeric boundaries and
queued proof continuity. Related tests covered optional eviction/retry and fairness, scope
changes, publication retention, encoding limits, AI deadline/grace and fee semantics, worker
joining, cancellation and snapshot timing ownership. This focused rerun overlaps the preceding
full-suite validation; it is not a new full-suite run. The existing dependency deprecation
warning remains. No live rollout or live performance comparison was performed in this review.

After expressing the numeric guard so the pinned type checker can narrow its type, all **24
optional-admission tests passed again**. Whole-backend/test Ruff lint and formatting checks
passed (176 Python files), as did focused mypy checking of the changed source module and the
repository's normal `git diff --check`. No learning, execution or deadline logic changed in
this additional correction.

### Burst follow-up live rollout — 19 September 2026

The authorised rollout used the same **Settings → Maintenance & updates → Prepare for upgrade**
operation as the UI. Preparation reached Ready at **19:52:35 BST**, with one open position in
season **60**, no pending orders cancelled and no interrupted model downloads. The app shut
down cleanly and the replacement completed startup at **19:53:05 BST**. Settings reported the
same operation completed and restored the paper engine's previous running state. This intentional
preparation/restart period is an observation gap, not healthy market evidence.

- Image: `signal-arcade:v1.10.11-burst-candidate-20260919`.
- Image ID: `sha256:7f03adcd4e32d2ad19b4e536af9f4716107045a85aa39510b2471f9cb30c4646`.
- Diagnostic build: `10c01f4c59ea49ac2cd0e0d50fdc0606bbe42600621d2f6ca6df27d5ec78ca86`.
- Boot: `c002a5f8b6474e2d85c4718abf5c895c`; version **1.10.11**, schema **16**.

Before replacement, all **51 packaged backend files** and **32 frontend sources** matched the
checkout. Runtime dependency versions matched the preceding image. Only the five reviewed
backend files differed; learning recipes, database schema, quote math and authority code were
unchanged. Packaged authentication, UI routes, coverage settings, upgrade prepare/cancel,
coherent timings, malformed optional input isolation and AI deadline checks passed in a
networkless disposable demo container with no live data mounted. The existing data volume and
compatible preceding image were retained. No new backup was made, following the user's saved
preference; a full database integrity scan and restore rehearsal remain unverified.

The first fresh live snapshot passed **26 continuity checks**, including season, risk profile,
bankroll, current Champion support, consent, automatic participation, Coach permission, the
**60%, revision 1** skill requirement, Coach's **70%** requirement and the **1,000-observation**
window. Cash and the original position matched the prepared snapshot exactly. AI remained in
Shadow mode. Through **19:58:57 BST**, one subsequent natural paper buy reconciled to cash,
positions and a balanced ledger, and its fee quote replay matched. The execution audit remained
verified. Natural trading changes are not deployment discrepancies.

The closing read at **19:59:51 BST** showed all seven workers running, no trainer or RPC worker
error, no reported diagnostic loss, and an empty publication backlog. Docker was healthy with
zero restarts or OOM. Bounded logs showed normal startup and no subsequent errors. The dashboard
recovered from a cached response to **2.17 seconds** old; diagnostic acknowledgement age was
**27.10 seconds**. Authentication and the served UI, Champion journey, leaderboard, seasons
and maintenance routes passed bounded read-only checks.

Saved diagnostics contained **six consecutive intervals (0–5)** and **34 events**, covering
**383.13 seconds**, below the fixed **30-interval/100-event** read limits. There were no sequence
holes or recording-gap flags; the initial interval was partial and the longest interval was
**70.03 seconds**, which still limits temporal resolution. Peaks were queue **2,425**, overall
lag **9.13 seconds** and critical lag **3.28 seconds**, with **zero shed or expired pipeline
events**. At closing, queue depth was **277** and both reported lags were **0.250 seconds**.
This short, unmatched traffic cohort does not establish sustained burst improvement.

Two natural training/publication cycles completed. Both groups retained their training event
and all six proof events, indices **0–6**, with maximum collection delays of **20.87** and
**42.02 seconds**. The first new learning model and five observed unique skill artifacts were
verified with bounded primary-key reads and payload digests, including the separate XGBoost
payload. This verifies normal sequential publication, not overflow or crash durability. Saved
market-batch and dashboard slow samples contained coherent operation timings. Runtime counters
recorded **390 future-only AI dispatches skipped** and **one dispatch retained**; these are calls,
not distinct successful outcomes. Three optional queued summaries were coalesced without loss.

Pressure remains visible: RPC recorded **35 requests**, **164 checkpoint updates** and **two
post-fetch processing-lag discards**, a subset of aggregate guard deferrals. Cleanup removed
**2,126 raw events** and continued yielding to market work. Its last checked raw-event boundary
was about **27.8 minutes** behind the 24-hour target. Host free space remained limited at about
**5.99 GiB on the data drive** and **1.27 GiB on the system drive**. No files, backups or images
were deleted to create headroom.

Operational Entry coverage was **519/1,000 (51.9%)**; the latest fitted Entry families showed
**46.4%**, a different cohort. Sizing Champion v8 remained active and healthy; Entry and
Manipulation were collecting proof, Exit remained suspended and Coach inconclusive. Existing
valid failures and permissions were preserved. The preceding boot's **8,847 candidate expiries**
and **675 capacity-shed events** remain historical pressure evidence; reset counters do not
erase them. More comparable natural traffic is needed before claiming better learning, fewer
burst losses, new Champion readiness or better trading results. No community push was performed.


### Provider recovery and Discovery follow-up — local validation

This follow-up implements the bounded provider corrections and collection visibility from the
read-only investigation. It is **local only, not deployed or pushed**. The preceding burst image
and its live evidence remain the deployment baseline; the tests below do not establish improved
live coverage, trading results or long-term burst capacity.

The starting checkout's public-source digests and diff were retained privately before edits.
Pre-existing v1.10.11 work was preserved. No runtime data, provider settings, learning requirement,
season, permissions, database schema, dependency version or paused workspace was changed.

**Implemented stages**

1. Bounded provider diagnostics now distinguish handled HTTP/transport/protocol failures,
   cancellations, quota/cooldown skips and configuration changes. Safe numeric status codes
   include HTTP 413 without broadening its retry/fallback treatment. Redirects are HTTP failures,
   not successful protocol responses. No arbitrary exception text, URL component, header, body
   or account identity is retained. Optional reports keep existing limits and proof priority.
   A protocol response is not a validated mark or usable learning outcome.
2. HTTP configuration generations prevent old responses from setting or clearing a replacement
   endpoint's cooldown. Checks cover quota admission, primary/fallback completion and the later
   market-lock boundary for learning, held-position and candidate-safety results. Settings changes
   serialize with threaded application and recheck profile-transition restrictions after waiting.
   Learning context discards remain within guard deferrals, not failed quotes or usable outcomes.
3. Ordinary WebSocket backoff resets only after both valid subscription acknowledgements and
   a matching, structurally valid notification at least 60 monotonic seconds later. Duplicate,
   missing or invalid acknowledgements and quiet connections do not qualify. Rate-limit handling,
   fallback triggers and the separate five-minute clean-stream enrollment window remain intact.
   Shutdown and explicit reconfiguration interrupt retry waiting; old connections cannot qualify
   or hand off further decoded events after their configuration changes. Work already handed to
   the event handler keeps its existing queue and cancellation semantics.
4. Existing admitted selection samples now distinguish selected and unselected deadline bands
   using each lane's original clock, with scope/pass/sample time and preselection guard context.
   No selection priority, extra history scan, provider request or training input was introduced.

**Discovery experiment and conditional capacity decision**

Two alternatives were tested only in memory: earliest-deadline ordering inside the urgent band,
and an extra ten-second urgency band. Both preserve the small cache, deadline, rotation and lane
share checks, yet fail the declared failure/latency safeguards:

| Synthetic six-route case | Existing | Earliest deadline | Extra urgency band |
| --- | ---: | ---: | ---: |
| Recoverable route with 4s left, five others with 14s left | 5 usable | 6 | 6 |
| Repeated validation failure with 4s left, five good routes with 5s left | 5 usable | 4 | 5 |
| Repeated validation failure with 4s left, five good routes with 11s left | 5 usable | 4 | 4 |

Each attempt costs one second followed by the unchanged ten-second wait. These failures reject
both alternatives; a coverage gain in the first example cannot excuse the later regressions.

A separate bounded replay compared all three selectors on identical synthetic manifests with
48 or 72 Discovery trajectories, shared mints and two independently timed Policy episodes for
each third mint. It retained all five horizons, valid unavailable outcomes, repeated per-route
validation failures, provider outages, repaired routes, 1/3/5-second request/application costs,
33-second pressure periods, an in-flight context change and a clock jump. All cohorts were closed
before comparison. It recorded per-lane/horizon usable, unavailable and expired counts, request
counts, repeated-attempt distributions, CPU time and bounded scheduler-state size. Each alternative
used the same request count in each scenario: 144, 99, 85 and 98. Primary Discovery usable counts
were identical within each scenario (34/48, 32/72, 30/72 and 27/72). Earliest-deadline ordering
avoided one Policy expiry in one scenario; it did not remove the hard counterexamples.

These are small synthetic scheduling checks, not a calibrated market/fee replay, model validation,
capacity benchmark or estimate of attainable coverage. CPU timings from one capped run are not
comparative performance proof. **Neither alternative ships.** Original 3:1 Policy/Discovery
rotation, borrowing, shared-mint deduplication, 90-second grace, attempt spacing and batch limits
remain unchanged. Valid unavailable outcomes are retained and never converted into usable ones.

Capacity changes also remain deferred. The historical 97-interval investigation included a
97.21-second recording gap with 1,223 candidate expiries, queue 6,811, 21.54-second overall lag
and 7.39-second critical lag. Its coherent 16.37-second market sample included persistence,
market-lock wait and candidate work; these nested elapsed measurements are not additive CPU
cost. They do not justify increasing RPC batch size or moving work across safety boundaries.
This implementation does not claim that burst pressure or Discovery coverage is solved.

**Rollout gate**

A later authorized rollout should use Settings preparation and verify deployed file/build/boot
identity and unchanged settings, season and permissions. Observe natural traffic without concurrent
local test/build work, including several bursts, provider recovery, checkpoint completion/expiry
by lane and horizon, fresh timestamps and diagnostic continuity, saved complete proof groups,
position marks and paper-ledger reconciliation. A drained queue, more fits or a short profitable
period is insufficient. Provider-limit causes, sustained capacity, full database integrity and
backup restore rehearsal remain unverified. Private evidence and source snapshots stay ignored.


**Local checks completed**

- Stage gates passed before proceeding: 176 provider/optional-report tests, 210 configuration/
  collection/safety tests, 171 reconnect/provider tests, and 126 selection/collection tests.
  These groups overlap and are not additive counts.
- The complete backend suite passed **2,456 tests**, run in seven serial, networkless disposable
  containers capped at one CPU and 1,536 MiB, with no live database or volume mounted.
- Final review corrections were followed by **809 passing focused regression tests** covering
  providers, diagnostics, saved proof, collection, coverage, account validation and positions.
  These include persisted provider reports alongside a complete seven-event publication group,
  redirects, empty stale responses and a profile transition starting during a settings-lock wait.
- All **29 reconnect tests** then passed, including explicit wall-clock jumps, stability not
  leaking into the next short flap, rejected subscriptions, exact 60-second boundaries, malformed
  and quiet traffic, rate limits, configuration changes and cancellation. The final focused runs
  overlap the full suite; they are not another complete full-suite run.
- Strict mypy passed for all **52 source files**. Ruff lint and formatting passed across the
  backend and tests (**180 Python files**), and `git diff --check` passed. The existing dependency
  deprecation warning about AnyIO's BlockingPortal alias remains; no dependency was changed.
- Additive reports fit the existing compressed event budget even with varied saturated counters.
  Optional-admission checks cover full queues, fair service, scope changes, repeated complete
  publication groups and the existing explicit overflow/loss accounting. Missing report detail
  is not interpreted as a healthy zero.
- The public-source comparison found no missing pre-existing files or unrelated changes.
  Package versions remain **1.10.11**. Frontend sources, database schema, execution math, model
  recipes, coverage policy and dependency versions were preserved. No frontend rebuild was needed
  for these optional diagnostic records. Documentation additions were checked for obvious credential
  patterns; private source snapshots and experiment evidence remain ignored.

The two initial plans for Discovery ordering were rejected, not silently substituted with a new
untested policy. Further capacity optimization is still evidence-gated. No live update, live
load test, forced fit/promotion, backup/database rewrite, threshold change or community push was
performed during this implementation. These checks found no regression in the tested contracts;
they do not establish zero risk or improved live trading performance.

**Additional provider boundary review — local only**

Three isolated failing cases reproduced two edge cases: a single WebSocket notification could
continue handing off decoded events after shutdown or reconfiguration during a yielding handler,
and an obsolete fallback HTTP response was labelled as primary in the old diagnostic scope.
These are reproduced boundary defects, not observed live incidents.

The stream now checks shutdown and configuration before each decoded-event handoff. The change
does not roll back already handed-off work, and uninterrupted multi-event batches still complete.
Obsolete HTTP results retain the actual endpoint role; cancellation or a context change before
dispatch uses unknown. Request ordering, retries, cooldown policy, collection priorities and
learning requirements are unchanged.

Eight new regression cases cover shutdown, reconfiguration, uninterrupted batches, obsolete
fallback success/HTTP failure/transport failure, and pre-dispatch cancellation/context changes.
All **350 focused tests** passed across provider recovery and safety, optional diagnostics,
publication retention, checkpoint scheduling and collection contracts. This overlaps earlier
checks and is not another complete full-suite run. Strict mypy passed for all **52 source files**;
Ruff lint/format checks passed for **181 Python files**, and `git diff --check` passed. The live
app was not queried or changed.

### Provider recovery live rollout — 19 September 2026

The provider/collection-visibility follow-up and the two additional boundary corrections above
were deployed through **Settings → Maintenance & updates → Prepare for upgrade**. The earlier
local-only sections describe their state at validation time; this section records the later
authorized deployment. Community publication remains pending.

- Image: `signal-arcade:v1.10.11-provider-candidate-20260919`.
- Image ID: `sha256:f703db9c0c1d9088ea8c0793ca8327611b73a226c474afb1e01f3e0cc93c4068`.
- Diagnostic build: `c5d5e9e6f435cc02cfd9cd5cb7a384557a3601e82ea3ce3d5f22ef0530b16efc`.
- Boot: `b42ff8a42a2c4e51a8d395a0c8b096b9`.
- Container started at 21:24:45 UTC; application startup completed at 21:25:08 UTC.

Before preparation, the current image matched the preceding burst rollout. A stale initial
dashboard response refreshed to 2.21 seconds old; stale reads were not treated as fresh evidence.
All seven workers were running, the ledger audit passed, and 62 training/publication cycles had
completed. The old boot retained 1,223 candidate expiries, no shedding, 35 post-fetch discards,
eight historical RPC worker errors and one dropped optional collection-selection report; no
training/proof diagnostic loss was reported. Those cumulative figures are not erased by a new
boot and are not comparable rates for this short rollout window.

The release image matched all 52 backend files and 32 mapped frontend sources; a separate read
inside the running container verified the installed backend digests. Dependencies and schema 16
were unchanged. The preceding image remains available as a compatible rollback. Packaged checks
used a disposable networkless demo container with temporary data, exercising startup, protected
routes, frontend assets, Settings prepare/cancel, coverage revisions and provider telemetry.
An initial smoke harness directory-ownership error was corrected before the passing run; it did
not touch live data or require an application change.

Settings reached Ready, the preceding process shut down cleanly, and the same preparation
operation reported Completed after restart. The first fresh snapshot passed 26 continuity checks:
season 60, profile, bankroll, permissions, active skills, risk state, coverage 60% revision 1,
Coach 70% and the 1,000-observation training window were preserved. The two prepared position
identities and cash matched exactly. Authentication and bounded API/asset checks passed.
The intentional shutdown/startup interval is an observation gap, not healthy traffic.

No backup copy was requested; no existing backup, paused workspace or data volume was removed.
Private rollout evidence stays ignored. Full database integrity and restore rehearsal remain
unverified. This deployment does not establish improved coverage, Champions, profits or sustained
burst capacity; Discovery ordering and RPC batch size remain unchanged.

**Post-rollout observation through 22:30:30 BST**

- All seven workers remained running. At the closing container check there were zero restarts,
  OOM events, warning-level log entries or error-level log entries. The fresh dashboard was
  2.13 seconds old after its cached response refreshed; diagnostic acknowledgement age was
  29.66 seconds. Current queue was one, overall lag 0.061 seconds and critical lag 0.040 seconds.
- Five consecutive saved intervals (sequence 0–4) covered 302.19 seconds with no recording-gap
  flag or sequence hole. The longest interval was 61.78 seconds; the first carries the expected
  partial-interval flag. Peak queue was 1,141, overall lag 5.783 seconds and critical lag
  2.093 seconds. There were no shed/expired pipeline events or reported diagnostic record losses.
  The fixed-end read returned 32 events within the limits of 30 intervals and 100 events; neither
  limit was reached. These are short unmatched traffic cohorts, not sustained burst validation.
- Two natural fits/publications completed. Each retained its training event and six proof events
  with indices 0–6 of seven; maximum collection delays were 30.79 and 0.49 seconds. The backlog
  was empty. Both observed learning models and their five unique current skill artifacts passed
  bounded primary-key persistence and payload-digest checks. This does not exercise simultaneous
  waiting groups, overflow, crash recovery or proof under sustained pressure.
- Both new HTTP and WebSocket provider-health reports were saved, with safe endpoint roles,
  fixed counters and no provider-controlled prose. Matching Discovery/Policy selection samples
  retained pass/scope/timestamp, selected/unselected deadline bands and preselection guard context.
  No reconnect or provider reconfiguration occurred during this sample, so their failure/recovery
  boundaries retain isolated-test coverage rather than live-exercised proof.
- Learning RPC completed 28 requests and 143 checkpoint updates, with zero worker errors or
  post-fetch discards. Guard deferrals included four queue-pressure, five processing-lag and one
  startup market-health deferral. Discards remain a subset of deferrals. Live batch size stayed five.
- Operational Entry coverage was 515/1,000 (51.5%). The first post-rollout fitted Entry cohort was
  460/1,000 (46.0%), including 330 valid quote failures and 210 missing outcomes. These distinct
  cohorts do not demonstrate an improvement caused by this deployment. Sizing Champion v8 remained
  healthy, Entry/Manipulation were collecting proof, Exit remained suspended and Coach inconclusive.
  Existing valid performance failures still prevent qualification; no gate or permission was relaxed.
- Routine cleanup resumed and had removed 1,556 raw events by the closing sample. Its retained-oldest
  timestamp was approximately 11 minutes behind the 24-hour target at its recorded history check.
  There were no unheld probes. Cash and both positions reconciled through the closing snapshot;
  no natural fills occurred in that comparison window, and the paper execution audit passed.
- Host headroom at 22:31 BST was about **5.72 GiB on E:** and **1.91 GiB on C:**. This is limited
  headroom, not a long-term storage clearance. No files were deleted or storage settings changed.

No new deployment regression was found in these checks. The runtime source remains identical to
the verified image; only rollout documentation was updated afterward. Natural traffic must still
establish longer-term provider recovery, diagnostic continuity, burst capacity and learning quality.

## Optional 55% coverage — 20 September 2026

At this implementation checkpoint, the extension was **local-only**. It was subsequently
[deployed through Settings preparation](#optional-55-coverage-live-rollout--20-september-2026),
without selecting 55% on the live app. It adds 55%
as the lowest explicit choice alongside 70% (default), 65% and 60%. Existing saved settings keep
their value and revision. No model recipe, schema migration, collection budget, fee calculation,
position handling, season or execution permission changed. Backend production changes are limited
to the accepted percentage in the existing policy/API and the associated validation messages.

The existing versioned native contract also governs applicable new activation, battle, health
and recovery proof. Older artifacts and activation receipts keep stricter saved requirements.
Coach-derived support and mixed Coach battles remain at 70%. Native Entry keeps its existing
fitted-proof plus operational-coverage activation path; other native skills retain their separate
composition-proof checks. Enabling an option is not an automatic promotion or a settings save.

Settings uses the server's advertised choices, restricted to the supported four values. Duplicate,
unknown or malformed capabilities cannot offer a lower percentage. A draft or confirmed value
that becomes unsupported remains visible as unavailable and cannot be silently saved or replaced.
Successful saves remain distinguishable from failed dashboard refreshes, and stale revisions
cannot overwrite a concurrent setting change.

### Completed isolated checks

- **212 focused backend tests passed**, covering policy/API persistence, exact fitted boundaries,
  all native skill lifecycles, paired fitting identity, nonlinear artifacts, bounded waiting
  candidates and battle replay. A further **302 existing learning regressions passed** across
  Entry, contextual Exit, Coach, participation, recovery, persistence and work budgets:
  **514 backend tests across 20 explicitly selected files**, not another full backend-suite run.
- **475 frontend tests passed across all 24 files**, including Settings, fitted-generation proof,
  recovery and battle requirements. The Settings cases also exercise a server losing advertised
  capabilities after a successful save. No test contacts the live application.
- Strict backend type checking passed for **50 Python source files**. Ruff lint passed and all
  **182 backend/test Python files** passed formatting checks.
- Frontend TypeScript checking and the production Vite build passed. ESLint reported no errors
  and the existing `EquityChart.tsx` fast-refresh warning. The existing large scene-chunk build
  warning remains; this change does not alter the scene or its loading strategy.
- Paired fits retained identical coefficients, XGBoost payloads, predictions, sample counts and
  evidence digests. The 549/550/551-of-1,000 boundary was checked without removing valid quote
  failures or changing the evidence population. Missing separate Policy proof still blocked
  qualification at 55%.
- Native health and fixed recovery exercised **32 versus 33 usable outcomes out of 60**.
  The sample minimum stayed at 30; insufficient coverage failed, while sufficient coverage
  still required advantage and acceptable harm. Restarts retained failed/restored recovery
  results. Raising 55% to 60% withdrew insufficient support; returning to 55% did not revive it.
- Repeated eligible Entry/Manipulation generations retained the active trial and only the latest
  waiting generation of that family. Waiting candidates generated no per-observation predictions
  or hidden forward proof. Existing bounded queues, caches and trial budgets were retained;
  this is a functional bound check, not a sustained-load benchmark.
- Setting-save failures, stale requests, freshness boundaries, in-flight jobs after toggling
  requirements, stricter activation receipts and Coach's 70% floor retained their protections.
  The tests used a networkless, resource-bounded container with temporary synthetic databases,
  an empty test environment file and no live data mount. Frontend APIs were mocked.

### Compatibility and remaining evaluation

No stored artifact is requalified retroactively. Selecting 55% requires a new policy revision
and validation beginning at or after its effective timestamp. Installing this code alone does
not change an existing 60% selection or its permissions. Existing artifacts and proof remain
immutable, including proof that failed under an earlier requirement.

After 55% appears in saved settings or proof, a rollback reader must recognize it. Readers that
accept only 70/65/60 reject 55% records; they must not reinterpret them or have historical records
rewritten to bypass that restriction. Raising the current setting does not remove this history.
Use a compatible build or the documented matching image/data restoration procedure.

The preceding retrospective investigation found additional statistical qualifiers at 55%, but
their later outcomes were limited and mixed. More qualifying generations, many with overlapping
cohorts, do not establish better Champions, profitable trading or optimal coverage. The extra
option deliberately permits less complete evidence, including in applicable new native health
checks; the other gates do not eliminate that uncertainty.

Practical validation remains a separate forward review after an explicit rollout/selection:
verify the actual build and saved revision, freeze the comparison before outcomes, distinguish
fitted Discovery from independent Policy evidence, and compare comparable traffic periods with
sample size, fees, harm, winner vetoes and uncertainty retained. Track candidate/publication work,
queue and critical lag, proof loss and diagnostic continuity. No forced promotion, load test,
threshold selection, deployment or new schedule was performed by this implementation.

### Read-only live boundary check

At **09:12:58 BST on 20 September**, serial read-only checks confirmed the same provider-recovery
build and boot, with **60%, revision 1**, Coach at 70%, and only the deployed 70/65/60 choices.
All seven workers were running, 253 natural training/publication runs were recorded, the publication
backlog was empty, and reported pipeline shedding/expiry and diagnostic-loss counters were zero.
The first dashboard response was cached and 2,245.70 seconds old; the bounded retry refreshed to
2.71 seconds old. Diagnostic acknowledgement age was 61.49 seconds, so that diagnostic record was
not a simultaneous observation of every health field. This confirms the implementation did not
deploy or select 55%; it is not live validation of the new option or sustained performance.

### Second edge-case pass

The follow-up review required no production-code correction. **164 backend tests passed** across
the 55% edge cases, policy, lifecycle and contextual Exit files, including eight additional cases.
The new cases check each native fitted coverage field independently when raising saved 55% proof
to 60%, including Entry/Manipulation's separate Policy coverage and contextual Exit's reference
coverage. A sufficient companion cohort cannot conceal a missing, below-threshold, non-finite,
boolean, string or out-of-range value. Damaged or incomplete 55% policy metadata cannot fall back
to legacy authority. These checks preserve historical proof rather than requalifying it.

All **14 Settings tests passed**, including an additional temporary capability-loss/recovery case:
the unsaved 55% draft remains visible, cannot save while unsupported, and still requires an
explicit save after support returns. Frontend TypeScript checking, targeted ESLint, Python lint
and formatting, and the tracked diff whitespace check passed. These selected reruns overlap the
earlier counts; they are not additional full-suite runs. Only regression tests and this validation
note changed during the follow-up. The live app and its selected requirement were untouched.

## Optional 55% coverage live rollout — 20 September 2026

The user subsequently authorized deployment. The app completed Settings → Prepare for upgrade,
stopped cleanly at 08:22:18 UTC, and completed startup at 08:22:42 UTC. This interruption is an
observation gap, not healthy market history. Only the app container was replaced; the existing
volume, provider configuration, execution permissions and selected **60%, revision 1** remained.
No new backup was made, following the user's existing preference. No data restoration was needed.

- Image: `signal-arcade:v1.10.11-coverage55-candidate-20260920`.
- Image ID: `sha256:e609fbcb7c75f44b5014a09bc245db743425a1d034775c6cc97af48e02c18426`.
- Diagnostic build: `2f6218ccf6f2dee788c1e90e67ae5aed257fe0c821ef788f20b15d9a867f3f28`.
- Boot: `e789c980be57486aa472ee3f33215542`; version 1.10.11 and schema 16.

The packaged image matched all 52 backend/resource files and 32 bundled frontend sources.
Runtime dependencies matched the preceding image. Only the expected three backend files differed:
API/policy accepted values and the coverage validation messages. Networkless packaged smoke checks
passed authentication, served routes/assets, upgrade preparation/cancellation, all four choices,
invalid inputs and stale-save rejection, with temporary synthetic data and unchanged permissions.

At 09:23:28 BST, the live build matched the candidate. All seven workers were running, Docker was
healthy with zero restarts/OOM, and Settings reported the same upgrade operation completed. The
fresh dashboard preserved season 61, risk profile, cash, zero open positions, learning mode,
consent, participation, active Sizing Champion v8, Coach permission and the 1,000-observation window.
The paper execution audit passed. The API advertised all four choices with 60% still selected,
Coach at 70%, and the original setting timestamp/revision retained. Protected routes rejected
unauthenticated access; bounded route and asset reads succeeded.

Initial queue depth was zero, overall/critical lag was 0.010/0.013 seconds, and pipeline
shedding/expiry and reported diagnostic losses were zero. The provider was connected with no
reported error. RPC had made five requests and applied 23 checkpoints, with no worker errors or
post-fetch discards. Diagnostic acknowledgement age was 46.30 seconds, so the first status record
was not a simultaneous measurement of every health field. No post-restart fit had completed at
this early sample; normal continuity/outcome requirements still apply. These startup checks do
not establish sustained burst performance, new qualification or better trading.

### Closing rollout checks

At **09:25:08 BST**, one natural post-restart fit/publication had completed. The saved publication
retained its training event and all six proof events, indices 0–6 of seven, with a maximum collection
delay of 1.88 seconds. Bounded primary-key reads verified the new learning model and five unique
native skill artifacts, including the external XGBoost payload. Earlier retained artifacts also
passed payload checks. This does not exercise publication overflow or establish forward advantage.

The fixed-end diagnostic read contained two consecutive intervals, sequences 0–1, and 16 events
within limits of 30 intervals and 100 events; neither limit was reached. They covered 123.37 seconds,
with one initial partial interval, no recording-gap flags or sequence holes, and a longest interval
of 62.55 seconds. Peak queue was 596, overall lag 4.32 seconds and critical lag 2.97 seconds, with
zero pipeline shedding/expiry. This is a short startup sample, not sustained burst validation.

The first closing dashboard response was 97.84 seconds old; a bounded retry refreshed it to 2.26
seconds old. Diagnostic acknowledgement age was 28.23 seconds. Closing queue depth was zero,
overall/critical lag 0.016/0.132 seconds, all seven workers were running, no degraded reasons were
reported, and the publication backlog was empty. RPC recorded 14 requests and 45 checkpoint
updates, with zero worker errors or post-fetch discards. A startup market-health deferral and two
unavailable route identities were retained as valid guards, not removed or treated as successes.
All reported diagnostic-loss counters were zero, and bounded startup/runtime logs contained no
error-severity entries. Docker remained healthy with zero restarts/OOM at 09:25:37 BST.

Sizing v8 remained active; Entry/Manipulation were collecting proof and Exit remained suspended.
Operational Entry coverage was 576/1,000 (57.6%), distinct from any fitted cohort. **60% remained
selected and 55% was not exercised on live data.** No paper-accounting issue was reported. Cleanup
had not yet completed a new scheduled pass in this short window, so retention progress was not
validated by this rollout check. Host free space was approximately 5.35 GiB on E: and 1.81 GiB on C:;
that existing storage constraint remains unresolved. No cleanup, full integrity scan or restore
rehearsal was performed. Only deployment documentation changed after the verified image build;
runtime source stayed unchanged. No new automated schedule or community publication was created.

### Post-rollout edge and polish review

At **09:28:04 BST**, the same image, diagnostic build and boot remained active. All seven workers
were running, no degraded reasons were reported, the publication backlog was empty, and reported
pipeline shedding/expiry and diagnostic loss remained zero. The closing dashboard was 4.79 seconds
old and diagnostic acknowledgement age was 22.90 seconds. Queue depth was 64 and overall/critical
lag 0.061/0.080 seconds. The provider remained connected with no reported error; RPC had completed
30 requests and 89 checkpoint updates with no worker error or post-fetch discard. These are
short-window observations, not a performance comparison against the preceding release.

The fixed-end diagnostic query returned five consecutive intervals (0–4), covering 304.87 seconds,
and 23 events within the 30-interval/100-event limits. There were no sequence holes or recording-gap
flags; the initial partial interval remained identified. Peak queue/overall lag/critical lag stayed
596/4.32 seconds/2.97 seconds. The first publication's training event and all six proof events
remained saved. No new training cycle under the later 55% selection had completed at this cutoff.

A separate settings save at **09:27:10 BST** selected **55%, revision 2**. The review itself used
only read-only live requests and did not make that selection. Bounded primary-key reads verified
the new setting's persistence and confirmed that all five inspected older native artifacts retained
their 60%, revision 1 contracts, qualification, metrics, counts and payload digests. Active skills,
consent and participation were unchanged; Coach retained 70%. Operational coverage was 576/1,000,
which met the new operational floor but did not retroactively qualify those fitted artifacts.
Entry/Manipulation remained collecting proof, Sizing healthy and Exit suspended. A natural paper
buy reconciled exactly to the cash debit, fee totals and new position; it was not treated as a
deployment discrepancy or evidence of better trading.

All 52 local backend/resource hashes still matched the verified image. SHA-256 comparisons of the
live page's JavaScript and CSS matched that image exactly. No application-code correction or
redeployment was needed. Existing isolated coverage transition/UI checks remain applicable; they
were not rerun without a new code change. Documentation and the tracked diff whitespace check
were reviewed. Routine cleanup resumed, removing 1,820 raw trades by the closing snapshot, while
retaining its guard for in-flight learning RPC. Host free space remained about 5.35 GiB on E: and
1.81 GiB on C:. This storage limitation and longer-term forward evaluation remain open. Only this
validation note and private review evidence were written; live configuration, data and services
were untouched by the review.

## Activity evidence and bounded dashboard reads — 20 September 2026

At this implementation stage, the follow-up was **local only**, with no deployment or push. Live
services, data, settings, coverage selection, permissions and the paused development workspace
were unchanged. The later authorized [activity rollout](#activity-evidence-live-rollout--20-september-2026)
below records its own image/build identifiers; preceding deployments do not identify this patch.

### Scope and evidence boundary

Saved burst evidence showed snapshot work overlapping a long market-lock wait, with both learning
status and residual dashboard assembly contributing wall time. Inspection found that the positive
decision lane could search a much larger PASS/ABSTAIN journal. An action/time index and bounded
per-action merge now avoid that search while retaining one SQLite read snapshot, original time
ordering and rowid ties. The optional index follows current-season rotation and rollback. Minimal
legacy imports without a decisions table are supported; the index is created only when that table
exists. Schema 16 and stored decision records remain unchanged.

Optional snapshot timings now separate token assembly and decision lookup/compaction. The old
`snapshot_other` residual therefore has a different scope. Snapshot capture age starts before the
worker, includes assembly time and is not reset to zero on completion. Cache throttling still uses
completion time. The shared refresh, event lock, worker joins, old-cache recovery and authority
boundaries remain in place. This fixes a bounded query cost and freshness reporting; it does not
establish that all burst pressure is solved.

New full decision snapshots record seven descriptive activity fields. They distinguish buy-count
share, buy-volume share, signed flow, individual trades meeting a 0.01 SOL cutoff and wallet counts.
The calculation is lazy and shares the existing one-second window; compact token cards and position
marks skip it. Complete observed amounts are required for numeric value/count fields, and complete
wallet identities for wallet counts. Empty/unsupported evidence remains unknown. The UI preserves
the distinction between quantity coverage and stream continuity. Old records are not reconstructed.

Baseline v1.1–v1.5, all three risk modes, integrity and sizing semantics, learned feature vectors,
coverage contracts, Policy identity, hold/exit rules and Champion permissions are unchanged. The
earlier absolute flow feature is not reinterpreted as signed flow. Position wording now says hold
score and explains that it is a heuristic, not a profit probability or integrity verdict.

The two motivating holdings do not establish that a new rejection, recovery cooldown or faster
exit improves outcomes. Those ideas remain conditional on prospective evaluation. The required
cohorts, chronology, counterexamples and evidence limits are documented in
[ACTIVITY_EVALUATION.md](ACTIVITY_EVALUATION.md).

### Staged validation and practical limits

- Initial query/snapshot checks: **123 passed**, covering bounded selection, timestamp ties,
  duplicates/empty actions, season rotation/reopen/rollback, cancellation, failed refresh recovery
  and diagnostics ownership. Later checks add dense positive lanes and legacy imports.
- Activity/trading checks: **100 passed**, including dust mixed with large sells, repeated wallet
  loops, unknown amounts/identities, exact amount/time boundaries, future trades, venue changes,
  cache timestamps, truncation and expiry. Comparisons across all 15 Baseline-version/risk-mode
  combinations preserved decisions, integrity/sizing assessments, nonempty learning vectors and
  exit assessments. The initial synthetic fixture was corrected to contain valid price-path data;
  the application's missing-evidence guard was retained.
- The broad backend run was split after accumulated test databases filled its 1 GiB temporary
  filesystem and activated the real diagnostics low-space guard. It was not a valid all-green run.
  Fresh diagnostics/query/snapshot checks passed **172 tests**, confirming that environment cause.
  The later legacy-import edge exposed and corrected the index guard, including index creation on
  fresh databases. Release-version checks also required the package/README/Docker files in the
  disposable source bundle. No application disk safeguard was relaxed.
- The closing provider, migration, database, snapshot, diagnostics and version batch passed
  **218 tests** after those corrections. Other backend batches exercised training/publication,
  coverage, recovery, accounting, fees, safety, retention and seasonal boundaries; the final lazy
  activity refinement is checked separately below.
- Final lazy-collection review: **204 checks passed** in the broad focused batch; its one failing
  new test used an incomplete fake clock. After correcting that fixture, all **35 activity,
  feature-budget and snapshot checks passed**, including skipped dashboard/mark work, one
  calculation per cached window and preservation of the original one-minute cutoff/time. No
  application clock or evidence rule was relaxed. Backend module coverage was completed across
  the isolated runs and corrective rechecks, not one uninterrupted full-suite pass.
- Frontend verification: **151 existing app tests and 15 new activity tests passed**. The new
  test file uses the repository's explicit DOM cleanup between cases. TypeScript, ESLint, backend
  Ruff and backend mypy checks passed. The production frontend build passed; the existing large
  dynamically loaded 3D scene chunk still generates its size advisory.

All backend execution used networkless disposable containers, synthetic/temporary data and bounded
CPU/memory. No production volume was mounted. A small synthetic CPU-cost check showed that the new
evidence is not free; this motivated skipping unused calculations on dashboard/position paths.
Measurements were noisy and are not a live throughput or trading comparison. Optional JSON fields
and the index also have a storage/write cost. Comparable natural traffic, diagnostic continuity,
retention/headroom and prospective trading evidence still need review after a separately authorized
deployment. No claim of improved profit, 55% qualification or new Champions follows from these tests.

### Follow-up edge-case review — 20 September 2026

The read-through found one remaining unnecessary calculation: held/pending market updates used
the full snapshot method even when no new entry decision was being evaluated. The local correction
lets those callers omit the descriptive activity fields. Pending-order heartbeats, resume checks
and conversion-price lookups do the same. New entry decisions still collect and persist the
breakdown. The original core values, flags, confidence, integrity handling and exit evidence remain
unchanged; a cached activity result cannot leak optional fields into a priority snapshot.

The closing focused batch passed **80 tests**, including actual market dispatch for active/paused
holdings, pending orders and new candidates; lazy-cache timestamps; bounded history reads; an
active reader overlapping season rotation; failed refresh recovery and cancellation. A separate
fresh container passed **173 tests** covering provider safety, broker work, probe retention, market
bursts, exit policy, AI dispatch, risk profiles and database behavior. Both used the existing
networkless, resource-limited disposable harness with synthetic data and no production volume.
Backend Ruff, the whitespace/diff check and mypy across **51 source files** also passed.
No further defect was found in these checks. These are targeted regression results, not evidence
that every possible failure or live burst has been exercised. This edge-case review was local only;
the live app, settings, saved learning evidence and services were not changed during that review.

## Activity evidence live rollout — 20 September 2026

The user subsequently authorized deployment. The app reached Ready through the same maintenance
endpoint used by **Settings → Prepare for upgrade**, shut down cleanly at **10:57:28 UTC**, and
completed startup at **10:58:12 UTC**. This interruption is an observation gap. Only the app
container was replaced, retaining the existing data volume and runtime configuration. No new
backup was made, following the user's existing preference; no reset or restoration was performed.

- Image: `signal-arcade:v1.10.11-activity-candidate-20260920`.
- Image ID: `sha256:fd3059b2a8021cfbb26bf25748d824f68f6fb4a8b044adbb85485c44570a5e7d`.
- Diagnostic build: `4b3c7ab3d9291be26c8a0516c98815dc58f9dda95ed29f863fe8c56bea260a26`.
- Boot: `fe8b5f1c56494a2ea6526df235d42644`; version 1.10.11 and schema 16.

Before replacement, the packaged image matched **53 backend/resource files** and **33 bundled
frontend sources**. Runtime dependencies matched the preceding image. Networkless packaged
checks passed startup, authentication, served routes/assets, Settings prepare/cancel, coverage
choices and stale/invalid-save rejection, signed activity arithmetic, omitted priority-path
activity work and the action/time index. The preceding compatible image was retained for fallback.

At **10:58:44 UTC**, Docker was healthy with zero restarts/OOM, all seven workers were running,
and the original Settings preparation operation had completed. The fresh snapshot preserved
season 61, profile, risk mode, bankroll, cash, zero positions, selected **55%, revision 2**, the
original selection timestamp, the 1,000-observation window, consent, participation, Coach
permission and the active Sizing Champion v8. Coach's requirement remained 70%. The earlier
55%-extension rollout preserved 60%; 55% had been selected before this deployment. No
coverage setting was changed by this rollout. The paper execution audit remained verified.

Authenticated bounded page/asset reads served the new activity panel and hold-score wording;
unauthenticated access remained rejected. A bounded read of five naturally saved new decisions
verified all seven activity fields and their timestamps. The database retained schema 16 and one
action/time index on the current decision table. These startup decisions were ABSTAIN, consistent
with existing evidence requirements; no learning continuity or trading guard was bypassed.

One natural training/publication completed. Bounded primary-key reads verified the learning model
and five unique native skill artifacts, including inline and external XGBoost payload hashes.
At the **10:59:59 UTC** fixed end, one saved initial partial interval and eight events contained
the training event and all six proof events, original publication indices 0–6 of seven. Maximum
collection delay was **45.66 seconds**, and the publication backlog had drained. The interval
covered **66.45 seconds**, with peak queue **496**, overall lag **7.41 seconds**, critical lag
**3.92 seconds**, zero shed/expired events and no recording-gap flag. The bounded read limits
were 30 intervals and 100 events; neither was reached. A single initial interval is not sustained
burst or multi-interval continuity validation.

At that fixed end, queue was zero, overall/critical lag **0.013/0.012 seconds**, snapshot age
**8.96 seconds** and diagnostics acknowledgement age **51.23 seconds**. Initial stale cache age
had recovered from 27.90 to 3.00 seconds on the bounded retry. RPC recorded ten requests and
46 checkpoint updates, with zero worker errors or post-fetch discards. Five startup market-health
deferrals and four unavailable route identities remained valid guards. Reported diagnostic losses
and new-boot pipeline shedding/expiry were zero, with no degraded reasons or error/warning lines
in the bounded startup log. The new token and decision timings appeared in pending optional
snapshot evidence; pending samples alone do not prove durable recording.

Entry and Manipulation were collecting proof, Sizing v8 was healthy, Exit remained suspended and
Coach inconclusive. Operational Entry coverage was 608/1,000 (60.8%), distinct from fitted coverage.
No promotion was forced, and these checks do not establish better trading, coverage or profit.
The preceding boot's **4,001 expired candidate events** remain historical pressure evidence;
zero counters after a restart do not erase that limitation. Host free space after the build was
approximately **5.12 GiB and 0.92 GiB** on the two checked volumes, an unresolved operational
constraint. Cleanup had not yet completed its first new scheduled pass. No full database integrity
scan, restore rehearsal or load test was performed. Community publication remains pending.

### Closing activity rollout check

At **11:01:22 UTC (12:01:22 BST)**, the same image/build/boot remained healthy with all seven
workers running, zero restarts/OOM, no degraded reasons, no trainer/RPC errors and an empty
publication backlog. Two natural publication groups retained their training event plus six proof
events each, with indices 0–6 and maximum collection delays of **45.66 and 4.80 seconds**. Three
consecutive saved intervals (sequences 0–2) covered **197.35 seconds**, with no sequence holes or
recording-gap flags. Initial-partial and hour-boundary flags were present. The longest interval
was **70.68 seconds**, peak queue **699**, overall/critical lag **7.41/3.92 seconds**; pipeline
shedding/expiry and reported diagnostic losses remained zero. All 24 events and three intervals
were below the 100-event/30-interval limits. This remains a short startup sample.

The final dashboard refreshed from **26.77 to 3.03 seconds** old on the bounded retry; diagnostic
acknowledgement age was **3.40 seconds**. Queue was zero and overall/critical lag **0.003/0.046
seconds**. Saved runtime-work evidence now contains both new snapshot section timings, so their
durable collection is verified. RPC had made 16 requests and applied 77 checkpoints, with no
post-fetch discards. One queue-pressure, four processing-lag and five startup health deferrals
remained explicit. Three Discovery 1,200-second checkpoints expired with the last recorded stage
`rpc_identity`; this is distinct from pipeline-event expiry and does not establish a new rollout
defect. The bounded runtime log had no error/warning lines. The execution audit remained verified.

Runtime source hashes still matched the deployed image; only rollout documentation changed after
the build. The selected 55% policy and its revision were unchanged. Host space remained about
**5.12 GiB and 0.90 GiB** on the checked volumes. The app is ready for normal-traffic observation,
with storage headroom and sustained burst behavior still requiring attention. No GitHub push,
new schedule, forced promotion or policy change was performed.

## Durable enrollment activity follow-up — 20 September 2026

**Local implementation and validation; not deployed.** This follows the read-only entry-activity
investigation. It prepares better original-decision evidence and an offline research screen;
it does not establish a better buying policy. Baseline/feature/evidence versions, models,
coverage selection, native proof, Champion permissions, order execution and exits remain unchanged.
Comparison against source extracted from the preceding deployed image found only the intended
database/enrollment/diagnostic integration and two new activity modules in the Python runtime.

Stage 1 defined and tested the fixed `activity-evidence-v1` projection, original clocks, signed
values, null reasons, exact parent context and 4 KiB limit. Stage 2 added optional companion tables,
initial-transaction insertion, immutable first evidence, indexed parent deletion and commit-aware
counters. Parent JSON and training-copy bytes remain unchanged. An edge review found that a
legitimate raw integrity operand can retain a numeric value together with a low-coverage reason;
the companion now preserves both and marks that record partial. It does not clamp that value or
misrepresent its warning. Contradictory new activity values or mismatched cached clocks remain
unavailable. None of this changes the older integrity calculation or learner feature vector.

Local validation included:

- Contract/activity tests passed first, followed by transaction/identity regressions. The broader
  database, migration, season and diagnostics batch passed **203 tests**, trading/skill/Coach/
  coverage/training batch **449 tests**, and final activity/publication/retention/work-budget batch
  **195 tests**. These batches overlap; their sum is not a unique test count. Ruff passed across
  backend and tests, and final strict type checking passed for all **53 backend source files**.
  Frontend files and typed API response models are unchanged; optional diagnostic payloads gain
  the documented counters. No frontend build was needed for this evidence-only follow-up.
- Tests cover unknowns, malformed/signed/count boundaries, original failed attempts versus later
  fills, separate Discovery/Policy decision times, duplicate persistence, checkpoint updates,
  no historical backfill, restart, pending retention, season decision rotation and FK cascades.
  Recoverable optional SQL failure preserves the parent; transaction rollback, commit failure,
  disk-full, corruption, I/O error, interruption and cancellation produce no false durable count.
  Aggregate diagnostics fit the existing event byte cap with large synthetic counters.
- The preceding activity image's actual Python reader opened a disposable new database containing
  55% coverage and an active Champion-state fixture, read/updated parents, deleted parents and
  cascaded their companions. Reopening with the new reader preserved remaining records, coverage
  and exact Champion state. This tests that reader, not arbitrary historical downgrade support,
  live corruption recovery or a full production backup restore.
- Three bounded local resource rounds used **768 saves per path**, comparing ordinary parent
  saves with optional capture. Prespecified incremental limits were median **+1 ms**, p95 **+3 ms**,
  and live-page storage **+6,144 bytes/parent**, with the fixed **4,096-byte payload cap**. Repeated
  runs passed. The final run measured approximately **0.21/0.66 ms** ordinary/capture medians and
  **0.43/2.07 ms** p95 values, **4,672** extra live-page bytes/parent and maximum payload **2,277
  bytes**. WAL reached about **4.17 MB**, below the isolated 8 MiB screen. A separate 5,001-parent
  synthetic retention fixture pruned to 5,000 with indexed cascade in about **1.23 ms**. These are
  elapsed local measurements with scheduling variability, not CPU totals or a live burst SLA.

Stage 4 tooling is prepared, with a fixed weak-demand hypothesis, prespecified context/period
contract, exact production independent-Policy selection, matched fee-aware outcomes and input
digests. Tests preserve profitable missed winners, negative outcomes, failed quotes, pending
observations and unknown-feature Baseline fallback. Possible study-period truncation by the
selection cap is inconclusive; a cap confined to older pre-study rows is reported separately.
The report has no independent manipulation truth labels and never authorizes activation. No live
study period has been started and no fresh companion cohort yet exists on the deployed app.
Consequently **Stage 4 prospective validation and Stage 5 strategy/model activation remain
pending**. Synthetic correctness tests cannot pass that evidence gate.

A bounded serial read-only check at **12:15:58 UTC** confirmed the preceding build/boot still
running, all seven workers present, 28 natural publications, no trainer error and an empty
publication backlog. Queue was zero, overall/critical lag about **0.018/0.016 seconds**. The
dashboard first returned a **589-second-old** cached response, then refreshed to **2.95 seconds**;
diagnostic acknowledgement age was **14.93 seconds**. The same boot had **417 expired candidate
events**, zero capacity shedding and no reported diagnostic-record loss. This is a point check,
not a full interval-history review: pressure and stale cached responses remain limitations, and
the new local patch cannot yet be credited with live improvements. Selected coverage remained
55% revision 2, Coach 70%, and the paper execution audit reported verified with no issues.

Storage headroom remained constrained (about **5.08 GiB and 0.60 GiB** on the two checked volumes).
No service, live database, settings, seasons, thresholds or permissions changed. No image build,
deployment, push, forced training/promotion or new schedule was performed. Rollout, natural
capture/publication and sustained performance validation remain necessary before community
readiness or improved trading can be claimed.

### Additional enrollment/research edge review

A second local review reproduced two offline evaluation gaps before correcting them: later
traffic could displace a fixed study's selected opportunities, and a malformed primary checkpoint
could count as a usable five-minute outcome. The evaluator now excludes post-period/future
entries before rolling selection, preserves pre-study first identities, and distinguishes caps
that truncate the study from caps that only remove older history. Usable primary outcomes must
declare the 300-second horizon and fall within its inclusive 300–390-second observation window.
Expired unknown outcomes remain missing in the denominator.

Additional checks bind companions to their parent's original Policy entry time and route, treat
extreme malformed numbers as unavailable, limit individual SQLite values before materialization,
and avoid loading oversized optional payloads into the report. These changes affect evidence
validation and the offline research tool, not native training, Baseline scores, execution or
Champion authority. The focused regression batch passed **158 tests**, including original
identity selection, capture/storage failures, activity dispatch, learning and frozen training
inputs. Ruff and strict type checking of all **53 backend source files** passed. No live
deployment, setting change or strategy activation was performed;
prospective validation remains pending.

### Enrollment evidence live rollout — 20 September 2026

The user authorized deploying the evidence-only follow-up for normal-traffic observation.
Storage initially failed the deployment preflight; the constrained system volume subsequently
had about **2.62 GiB** available. After building the candidate, the data volume had about
**4.74 GiB** free. No files were deleted to obtain that space. Storage remains a limitation,
not a long-term capacity guarantee.

The packaged image matched all **55 backend files** and **33 frontend source-map entries**
against the reviewed source. Installed dependency versions matched the preceding image.
A network-isolated, disposable-database smoke check verified initial Discovery/Policy capture,
unchanged training-copy bytes, immutable companions after parent updates and reopening,
schema 16, foreign keys and preserved 55% coverage. Its synthetic payloads were 2,535/2,562 bytes.
The first smoke attempt correctly rejected the fixture's inherited public bind without an admin
credential; explicitly binding that isolated fixture to localhost resolved the test setup.
No production authentication setting changed.

The Settings upgrade operation reached Ready, with zero held positions and pending orders,
then the preceding app stopped cleanly. The container was replaced using the same data volume
and configuration apart from its image pin. Settings recorded the completed restart and restored
the running state. The preceding compatible image remains available; no database restore or
new backup was performed.

- Image: `signal-arcade:v1.10.11-enrollment-candidate-20260920`.
- Image ID: `sha256:412a3629dbefc6aee57ff1509dbc94a105a6e238d47ccd63c1c4d185dfdf7813`.
- Diagnostic build: `1d4c9a4cdc9d45b1618ca95de0cee7c09f1aae33979ccce288974e6079f725a1`.
- Boot: `7dc4fcf641dd418ab0dab116750504a1`.
- Container started **12:40:43 UTC**; application startup completed **12:41:14 UTC**.

The first fresh check at **12:41:46 UTC** passed all continuity checks: season 61, profile,
risk mode, cash, positions, initial bankroll, active skills, learning/Coach permissions,
coverage revision/effective time and the 1,000-observation training window. Selected native
coverage remained **55% revision 2**, with Coach **70%**. All seven workers were running,
Docker was healthy with zero restarts or OOM, and the paper execution audit was verified.
Snapshot age was **0.75 seconds**, diagnostic acknowledgement age **32.31 seconds**, queue zero
and overall/critical lag **0.030/0.033 seconds**. No pipeline loss, trainer error or reported
diagnostic loss had occurred in this short startup sample; no training cycle was yet expected.

Served frontend assets and bounded learning, leaderboard, season and maintenance reads passed;
unauthenticated snapshot access still returned 401. A bounded read-only database sample verified
the additive tables, schema and cascade definitions, with no backfill on 60 sampled older
parents. New enrollment requires the normal clean-stream warm-up. The deployment does not
start a prospective study, change Baseline/model decisions, or clear Stages 4 or 5. Sustained
burst behavior, future-cohort completeness and any trading benefit remain unproven.

#### Natural capture and final rollout check

After normal warm-up, the first bounded sample contained **19 new Discovery parents and one new
Policy parent**, each with a valid complete companion of **2,596–2,937 bytes**. A subsequent
sample validated 20 new Discovery companions and one Policy companion. Primary-key rereads of
all 20 original companions found identical payload digests; **18 parents had gained natural
60-second checkpoints** without replacing the original evidence. No sampled older parent had
been backfilled. These are bounded samples, not a complete population audit or a claim that the
underlying markets are legitimate.

By **12:48:58 UTC**, two natural training/publication cycles had completed, with an empty backlog
and no trainer error. Both saved publication groups contained the training event and all six
proof events, indices 0–6; maximum collection delays were **47.18 and 1.56 seconds**. These early
fits can use retained pre-upgrade lessons. They do not demonstrate better trading or evaluate
five-minute outcomes for the newly enrolled activity cohort.

The bounded diagnostic read contained **six consecutive intervals, sequence 0–5, and 42 events**,
below the 30-interval/100-event limits. Saved intervals covered **409.77 seconds**, with the
initial partial interval explicitly flagged, no sequence hole or recording-gap flag, and a
longest interval of **82.44 seconds**. This is slower than nominal minute cadence, even without
a recording-gap flag. Peak queue was **1,517**, overall lag **6.43 seconds** and critical lag
**2.97 seconds**. Pipeline shedding/expiry and reported diagnostic-record loss were zero.
Eleven retained Discovery checkpoint expiries were reported in the first collection summary,
with unknown preceding RPC stages; these are distinct from pipeline-event loss and cannot be
attributed to the new companion capture from this sample.

The next saved collection event recorded **29 attempts and 29 committed complete companions**,
with no reported partial/unavailable capture or capture-error counters. This confirms that the
new counters reached durable diagnostics; they are cumulative boot counts, not retention counts.
The final snapshot refreshed from **75.66 to 3.17 seconds** old on retry, diagnostic acknowledgement
age was **57.79 seconds**, queue zero, and overall/critical lag **0.048/0.020 seconds**. All seven
workers remained running, Docker healthy with zero restarts/OOM, and the execution audit verified.
The bounded runtime log contained no warning/error-severity records. Space was about **2.65 GiB**
on the system volume and **4.74 GiB** on the data volume.

No deployment regression was demonstrated by these checks. The app is ready for continued
normal-traffic observation, with constrained storage, cached-dashboard freshness, longer sampling
intervals and sustained burst performance still requiring attention. No prospective study period
has been frozen or started, and no Stage 5 buying/model rule was activated. The first study must
declare a future period and context before its outcomes exist and respect retained-cohort limits.
Runtime source hashes still match the deployed image; subsequent edits document this rollout.
No push, new schedule, forced training or promotion was performed.

#### Post-rollout edge and polish review

A further read-only check at **12:51–12:52 UTC** confirmed the same deployed image/build/boot,
healthy Docker state, all seven workers and no restarts/OOM. Source hashes still matched the
reviewed image, so the previously passed 158-test edge batch and strict type check remain
applicable; no runtime edit or repeated load-producing test was needed.

All **24 sampled new companions** validated, with payloads of **2,571–2,838 bytes** and no missing
companions in that sample. The original 20 records retained identical digests after all 20
parents gained 60-second checkpoints and 18 gained 300-second checkpoints. The latter count
means recorded checkpoints, not necessarily usable quote outcomes. Older sampled parents still
had no backfill. Indexed FK cascades and original parent/context matching remained intact.

Saved diagnostics contained **nine consecutive intervals, sequence 0–8, and 55 events**, covering
**600.22 seconds**, below the 30/100 read limits. There were no sequence holes, recording-gap flags,
pipeline losses or reported diagnostic losses; the initial partial interval remained explicit.
Peak lag/queue and longest interval were unchanged from the preceding check. Two complete
publication groups remained saved, with no backlog. RPC reported **54 requests, 230 checkpoint
updates and zero worker errors**. Pressure-related guard activity remained visible; this short
sample does not establish sustained burst safety.

The fresh dashboard was **3.11 seconds** old after retry, diagnostics acknowledgement age
**29.81 seconds**, and overall/critical lag approximately **0.074/0.072 seconds**. Learning
permissions, active skills, season/profile, coverage policy and training-window continuity
checks passed. Five natural fills reconciled exactly to the account-currency cash change, and
the remaining position matched its entry fill. A changed cash balance or position count after
natural trading is not a deployment discrepancy; the execution audit also remained verified.

Cleanup reported within budget and approximately **nine minutes** behind the 24-hour raw-event
target. Storage inventory included the new tables. Host space remained constrained at about
**2.65 GiB/4.73 GiB** on the checked system/data volumes. No new application defect requiring a
fix was identified. The app was left running for observation; Stages 4 and 5 remain pending.

### Bounded study reader and prospective freeze — 20 September 2026

The read-only design review confirmed a tooling limitation: the old research reader loaded up
to 5,000 retained Policy parents before filtering the requested period. A mature database can
retain 5,000 terminal parents plus pending records, exhausting that budget on unrelated history.
The follow-up changes only standalone research tooling, its tests and documentation. It does
not change the live collector, Baseline, features, trainer, native selector, coverage policy,
Champion permissions or exits. No deployment or restart was needed.

The reader now uses one bounded read transaction and the existing time index to select period
metadata before loading parent JSON. Original identity receipts preserve first opportunities;
mixed offsets, exact boundaries and ties are resolved using aware instants. Native selection
still precedes the study's fee/profile/venue filters. Missing identities, missing original parents
within the period, possible retention overlap and the native cap prevent a positive screen.
The lexical pruning watermark receives a conservative two-day offset allowance. This is a
bounded consistency check, not proof that unrecorded deletions or arbitrary corrupt timestamps
never occurred.

Compact private export uses digest checks, a byte limit, disk headroom checks and exclusive
atomic publication. Failed writes cannot expose a partial final dataset or overwrite another
file. Replay needs no database. Reports distinguish recorded companion status from usable inputs
and identify first failing input reasons; a complete stale record remains unusable. Zero matching
patterns and insufficient changed outcomes are explicit blockers. Hypothesis thresholds and
research minima are unchanged.

Stage checks passed in the network-isolated disposable test environment:

- Initial extraction/export stage: **22 tests passed**, including 5,001 irrelevant older parents,
  concurrent checkpoint writes, mixed offsets, microsecond boundaries, busy/interrupted reads,
  row/byte/time limits, low disk, partial output, output races and source-sidecar protection.
- Selection/retention integration: **68 tests passed**, preserving first opportunities, missing
  outcomes, tied timestamps, cross-season identity, context-filter order and the native cap.
- Integrated evidence/research suite: **127 tests passed**, including valid quote failures,
  unknown/stale inputs, missed winners, zero matches, no positive outcomes and CLI export/replay.
- Strict mypy passed for **54 backend source files**; changed Python files passed Ruff. A final
  filesystem-path comparison polish passed **38 dataset tests**. Repository whitespace checks passed.

A resource-limited, network-isolated process read the live data volume through a read-only mount
at **15:24:40 UTC**. Its retrospective tooling smoke covered **12:50–15:00 UTC**, not a prospective
experiment. It extracted **104 Policy parents**, 3,264,617 parent bytes, into a **4,357,291-byte**
private bundle. Replaying the bundle without the live volume produced an identical report.
There were no reported identity/retention completeness issues within the bounded contract.
The exact primary context contained **80 opportunities**, **77 usable activity inputs**,
**79 usable primary outcomes** and one valid quote failure; 24 other-context records stayed
excluded. Two complete records were stale and one was partial. There were **zero pattern matches**,
so this pilot provides no evidence for activating a buying rule. It is explicitly labelled
retrospective and is excluded from the future trial.

The post-check at **15:27:25 UTC** retained the same enrollment image/build/boot, all seven workers,
unchanged coverage revision/profile, verified execution audit and an empty publication backlog.
The dashboard refreshed from a cached 205-second response to **3.43 seconds** old; diagnostic
acknowledgement age was **19.46 seconds**. Queue depth was two, overall/critical lag **0.132/0.013
seconds**, pipeline shedding/expiry zero and trainer errors absent. The existing one optional
`slow_work` diagnostic capacity drop remained; training/proof loss counters remained zero. A
bounded ten-minute Docker log read returned no lines, which is not independent proof of health.
These checks show no immediate regression from the bounded research read, not sustained burst
safety or better trading. Storage remains constrained; no full database copy was made.

One prospective specification was frozen at **15:26:54 UTC**, before enrollment begins:

- Enrollment: **15:45–21:45 UTC** on 20 September (**16:45–22:45 BST**).
- Final outcome read: **after 22:00 UTC / 23:00 BST**, allowing 15 minutes after enrollment ends.
- Fixed primary context: balanced, Baseline v1.5, original matching profile/configuration,
  Pump curve with native SOL quote, 125 bps venue fee and 30,000-lamport network fee; selected
  native coverage 55% revision 2. Other routes are not pooled to reach the sample minimum.
- Fixed minima: 200 independent opportunities, 30 changed usable outcomes and 90% usable inputs,
  alongside the declared outcome coverage and unchanged preliminary economic screen.
- Canonical specification SHA-256:
  `359339fcc0a74efa8772d5a9eda39ff7ffe75914f00727eb156638d4d5a6b9ce`.

The specification, manifest and datasets remain private and ignored by Git. Their digest and
four tool/native-contract source digests were verified. The manifest requires diagnostic/build/
context continuity review; gaps or changes cannot be presented as an unqualified positive result.
No new scheduler was created. Stage 4 outcome review remains pending. Six hours may still produce
insufficient matches; that result is inconclusive, not a reason to tune thresholds or extend the
trial until it passes. Stage 5 remains disabled pending stronger prospective evidence, independent
integrity review, opportunity-cost analysis, robustness and native proof/permissions. This entry
trial does not evaluate deterioration during a later hold.

#### Follow-up timezone edge check

Before the prospective window began, a further review reproduced a standalone-reader omission:
Python accepts offsets such as UTC+15/UTC-15 and UTC+23/UTC-23 that SQLite's date parser rejects.
Passing those study boundaries directly to SQLite returned an empty cohort despite valid rows.
Normalizing only the query boundary parameters to UTC corrected all four regression cases.
The integrated activity/research suite then passed **131 tests**; the reader passed strict type
checking and Ruff, and repository whitespace checks passed.

The frozen study already uses UTC, so its period, hypothesis, population rules and specification
digest are unchanged. A separately dated private reader-hash addendum records this correction
before enrollment; the original specification and manifest were preserved. No running-app code,
configuration, data, trading rule or service state was changed, and no deployment was needed.

### Entry support explanations and freshness — local follow-up, 20 September

This follow-up is **implemented locally, not deployed**. The frozen six-hour activity study keeps
its original running build, specification and archived evaluator. Its source hashes and the
unchanged specification file digest were rechecked. The study's final outcome read remains due
after **22:00 UTC / 23:00 BST**; neither this work nor the earlier losing fallback examples qualify
a buying rule. Stage 4 review and conditional Stage 5 activation are not claimed complete.

Implemented and checked in stages:

- Correct saved activity and decision evidence ages to subtract original measurement clocks from
  the decision clock. Cached `freshness_seconds` describes snapshot-time freshness and could
  understate decision-time age after queueing or intervening work. Missing, naive, invalid or
  future clocks stay explicit; no measurement, decision time or eligibility window is changed.
- Add bounded scalar support explanations to new Entry/Manipulation/Sizing receipts. Preserve
  inclusive support boundaries and the scale floor; record the first failing feature and total
  failure count. Separate invalid model parameters, unavailable verified XGBoost payloads and
  Coach support failures. Explanation makes no additional model load or provider request.
- Link active decision receipts to a known cached original Policy identity with its timestamp.
  Preserve original opportunities across retries, restarts and pruning; ambiguous same-time
  attempts and missing origins remain explicit. No per-decision history scan or database query,
  migration, new worker, new timer, sticky veto or model authority is introduced.
- Show applied versus unapplied skill influence alongside the original integrity/activity
  evidence. A proposed veto outside support is not displayed as an executed veto. Neither a
  decision receipt nor a modeled positive outcome is claimed to prove a fill or legitimate trading.
- Document the separate prospective support-fallback investigation and its decision boundary.
  New recovery requirements need a future specification, opportunity-cost analysis and fresh
  proof; they cannot inherit a pass from the existing count/value activity study.

Validation used disposable, resource-limited offline containers without live data mounts and
local frontend tests. The integrated backend run passed **275 tests** covering learning, broker,
features, activity capture/research/reading and Policy selection. An expanded final run passed
**45 tests**, including 35 receipt edge cases plus priority dispatch and Policy ordering; these
overlap the integrated run. The application and evidence UI run passed **183 tests**, followed
by **32 focused checks** after the final missing-receipt guard. TypeScript, frontend lint, Ruff,
strict mypy (**56 source files**), production frontend build and repository whitespace checks
passed. The build retained its existing large-scene-chunk warning. The first backend fixture run
needed missing cohort fields, and TypeScript caught a potentially absent receipt; both were
corrected before final verification.

The edge checks cover exact/just-outside support, small-scale normalization, non-finite and
malformed parameters, missing payloads, legacy receipts, same-time/future identity clocks,
cross-configuration isolation, restart, parent-ID reuse after pruning and ordinary later recovery.
Action, prediction, blockers and size remain identical with and without the new annotations.
New metadata leaves frozen training-copy bytes and model artifacts unchanged. Existing pending
fill validation, economic signs, valid failures, proof selection, coverage and permission tests
remain passing. No trading improvement or sustained-burst performance result is inferred.

A bounded serial read-only live check at **20:23:58 UTC / 21:23:58 BST** confirmed the original
enrollment image/build/boot, Docker healthy with zero restarts/OOM and all seven workers running.
Snapshot age was 6.13 seconds, diagnostic acknowledgement age 6.53 seconds and publication backlog
empty. Queue depth was four, overall lag 0.014 seconds and critical lag 0.032 seconds at the sample.
However, the recent five-minute window recorded **6,465 expired candidate events**, zero capacity
shedding and the recent-candidate-loss warning. Four optional diagnostic capacity losses had been
reported since boot; training/proof/storage loss counters were zero. This is a recovered instant
after pressure, not an all-clear or evidence that the undeployed changes helped. It does not replace
the full-window continuity and outcome review. Local source remains v1.10.11; no restart, deployment,
setting change, forced training, promotion or GitHub push was performed.

#### Follow-up display edge review

The next review reproduced and corrected display-only gaps before deployment. Native JavaScript
date parsing truncated microseconds (hiding tiny future-clock differences) and normalized invalid
calendar dates. Saved evidence ages now validate the original aware ISO calendar/time and compare
microseconds exactly before rounding for display. Leap days, offset equivalence, second rollover,
invalid offsets and absent clocks are covered; unsupported formats remain unavailable.

Unknown applied actions could previously receive a generic sizing-success label. The panel now
requires consistent skill/support/actionability fields and recognizes the existing Entry,
Manipulation and Sizing actions explicitly. Unsupported receipt versions do not supply detailed
support explanations. Valid applied sizing and Entry support remain visible. Retry wording says
the attempt is linked to the first opportunity, without implying the original proof payload is
still retained; the long internal identifier is available as a title instead of widening the card.

The regression run reproduced ten failing cases before these corrections. The final application,
activity, receipt and timestamp suite passed **206 tests**. TypeScript, focused lint, production
build and repository whitespace checks passed; the existing scene chunk-size warning remains.
Backend learning/trading code was reviewed but unchanged in this follow-up, so its previous
backend validation still applies. The frozen study archive and specification digests were verified
again. No live requests, deployment, service change or trading-rule activation occurred in this
display review; the previously observed burst limitations remain unresolved.

### Completed prospective study review — 20 September 2026

The frozen 15:45–21:45 UTC enrollment window and 22:00 UTC outcome cutoff were reviewed after
maturity. The bounded reader returned 348 Policy parents: 273 independent exact-context
opportunities, 74 other-context exclusions and one ineligible record. Of the 273, 261 had usable
300-second after-fee outcomes and 12 had valid quote failures. Fresh usable inputs were available
for 205 (75.1%), below the fixed 90% minimum; all 68 unavailable cases had stale input clocks.
No opportunity matched all four fixed pattern conditions, leaving zero changed usable outcomes.
The original specification, source archive and private dataset were preserved. A separate scalar
cross-check agreed with the counts. A subsequent full replay failed allocation in its constrained
container; a successful independent full replay is not claimed.

**Stage 4 review is complete and inconclusive. Stage 5 experimental buying activation stays off.**
The 95.6% usable-outcome coverage in this narrow Policy cohort is not Entry's fitted Discovery
coverage or proof of manipulation detection. Missing inputs are not repaired by positive paper
outcomes, and the 70 positive versus 191 nonpositive modeled outcomes do not establish actual
portfolio profit. A new hypothesis requires a new prospective specification and opportunity-cost
review; neither extending this window nor selecting thresholds after seeing its outcomes qualifies.

Serial bounded diagnostic pages used a fixed end, deduplication and empty terminal pages:
330 intervals and 2,519 events across the complete read, with 295 intervals and 2,235 events through
the outcome cutoff. One boot and no sequence holes were observed, but the outcome-window records
contained **52 recording gaps**, up to **208.56 seconds**. Observed interval peaks reached queue
10,000, overall lag 23.45 seconds and critical lag 15.47 seconds. Their counters reported 467 shed
and 44,724 expired candidate events; intervals straddling the study boundaries and differing
populations prevent treating these as unique missing study outcomes. All 135 publication groups
in that outcome-window read were complete; this does not turn the diagnostic gaps into coverage.
The whole read contained 151 complete groups. Provider HTTP 413 failures recovered, but their
cause was not established. Raw-event retention remained behind target. These are reasons for
bounded reliability work, not grounds for activating an unqualified buying rule.

### Release reliability follow-up — 21 September 2026

Before the subsequent rollout recorded below, this follow-up was **local and not deployed or published**. A pre-change public-source archive and
hash manifest isolate it from earlier v1.10.11 work. The completed study's specification and
archived evaluator hashes remain unchanged. Work proceeded in stages with targeted regressions
before integration:

1. **Cleanup pacing.** A reproduced error marked a completed core retention/budget pass as
   deferred merely because optional housekeeping yielded to a busy market. It therefore used
   the two-second deferral delay instead of the existing bounded catch-up cadence. Only that
   incorrect label is removed. Actual pressure deferrals, urgent admission, transaction deadlines,
   chunk limits, cancellation and protected ledger/proof records remain unchanged. Cleanup,
   coordination and database edge groups passed **88 tests**.
2. **Provider 413 recovery.** HTTP RPC and stream-handshake 413 failures can use an already
   configured fallback, once, with bounded cooldown/backoff and Retry-After handling. No provider
   is added and no account batch is split. Unavailable endpoints still yield unknown results;
   route pairs, slot fences, quota priority, generation isolation and subscription acknowledgement
   remain required. Tests cover missing/both-failed fallbacks, critical requests, invalid/non-finite
   retry headers, unrelated errors and configuration changes. The integrated provider suite
   passed **212 tests**.
3. **Entry preparation.** Size, Baseline evaluation, provenance and entry-permission checks now
   share one joined executor dispatch. A regression reproduced the previous three dispatches.
   Tests preserve the real decisions across five supported Baseline versions, all three risk modes
   and normal/dust/missing-input cases. Original clocks, pre-veto enrollment, non-entry behavior,
   repeated cancellation and worker-error ownership remain covered. The integrated entry/activity/
   evidence/burst-boundary group passed **174 tests**. The `event_candidate` diagnostic phase now
   includes provenance/actionability; its old and new phase totals have different scopes.

These targeted counts overlap the full release suite and must not be added to it. No Baseline
formula, learned feature, fitted artifact, support bound, fee, selected coverage, Coach requirement,
permission or experimental entry rule was changed. The earlier local support-explanation and
timestamp-display follow-ups remain part of the release candidate, not the running build.

The complete backend suite passed **2,816 tests across all 140 test files**, run in 24 serial,
resource-limited disposable batches without live data mounts or provider access. The full frontend
suite passed **531 tests in 27 files** with one low-priority worker. TypeScript project checks,
strict mypy (**56 source files**), frontend lint, Ruff lint/format checks and the production
frontend build passed. Existing warnings
remain for the 3D scene chunk, the chart module's React-refresh export and a dependency's deprecated
test-client alias. Production dependency audits found no known vulnerabilities; the backend audit
resolved all 28 production dependencies in a clean environment without the test-only import path.

Initial integration failures exposed missing version-check files in the private test package and
accumulated fixtures exhausting the temporary filesystem's diagnostic free-space allowance.
Including the required files and splitting batches corrected both failures without relaxing the
application's disk guard. Audit execution also required an executable temporary mount inside its
disposable container. Formatting-only normalization of pre-existing mixed-format files was checked
for unchanged Python syntax trees. Public-file checks found no private evidence/database/archive
paths or matching credential patterns, and local documentation file links resolved. These checks
do not include a newly built application image or a complete restore rehearsal.

A serial read-only live check at **02:58:39 UTC / 03:58:39 BST on 21 September** confirmed the
original enrollment build/boot, all seven workers running, unchanged 55% native/70% Coach
requirements and a verified paper execution audit. The dashboard refreshed from 26.65 seconds
old to 4.14 seconds old; diagnostic acknowledgement age was 7.41 seconds and publication backlog
was empty. Queue depth was one, overall lag 0.026 seconds and critical lag 0.065 seconds, but
the recent five-minute counters still reported **1,487 expired candidate events**. Since boot,
seven diagnostic capacity losses were reported (two storage, five other; zero training/proof).
This recovered snapshot is not sustained burst validation or evidence for these undeployed fixes.

The closing read at **03:18:34 UTC / 04:18:34 BST** still showed the same image/build/boot,
Docker healthy with zero restarts/OOM, all workers running and a verified paper ledger. Snapshot
age refreshed from 33.06 to 3.47 seconds; diagnostic acknowledgement age was 55.64 seconds.
Queue depth was 2,040, overall lag 3.23 seconds and critical lag 0.028 seconds. The recent five-minute
window reported **1,052 shed and 10,077 expired candidate events**. Diagnostic capacity loss had
risen to 11 (three storage, eight other; zero training/proof), with no pending publication backlog.
These are continuing pressure observations on the old build. Local validation shared the host,
although its workers were bounded; host contention and unmatched traffic prevent attributing the
snapshot difference to one cause. No claim of healthy diagnostic continuity or solved bursts follows.

At this check, deployment and an image build were blocked by insufficient host disk headroom. No files were
deleted to make room, no new full database copy was made, and no live setting, service, season,
permission or trading rule was changed. After space is restored, use Settings upgrade preparation,
verify the exact image/build and preserved state, then compare natural-traffic intervals, retention
progress, provider recovery and original-input freshness. Keep diagnostic gaps and candidate loss
visible. Full backup restore and main-database integrity rehearsal remain unverified; no community
push or claim of sustained improvement is made by this local check.

#### Follow-up edge review

A further review added seven regression cases without changing production code. The focused
suite passed **198 tests**, overlapping the earlier full suite. Checks cover cleanup above target
when only protected evidence remains (no catch-up spin), the actual WebSocket handshake exception
for HTTP 413, rejection just before cooldown expiry and recovery exactly at expiry, failures in
each entry-preparation phase, and an exposure-blocked Baseline opportunity retaining its original
decision while remaining ineligible for actionable proof or optional AI influence. Existing
reconfiguration, cancellation, subscription and retention boundaries passed in the same run.

The production-source hashes and frozen study specification still match the prior validated
state. Ruff and whitespace checks passed. No additional production defect was identified in this
review; only regression tests and this record changed. The live app was not upgraded, and limited
host disk space and unverified post-rollout burst performance remain the release blockers.

### Release reliability live rollout — 21 September 2026

The preceding reliability and support-explanation changes were deployed locally through Settings
preparation. Before building, the 56 backend files matched the previously tested package and the
changed production files matched the final validation hashes. The full release suite and additional
198-test edge run above were not repeated. The normal image build passed, including TypeScript and
the frontend production build; the existing scene chunk-size warning remains.

Candidate `signal-arcade:v1.10.11-reliability-candidate-20260921` has image ID
`sha256:d43ba8926b6d6adf84e20668d788fbb79a26f0b956ca2456c38592ec6ad2d873` and diagnostic build
`a9fcf8fb443ac4b076e66b73bf9d2522243e7bd2a010e41e8a405fa6156eb0d0`.
All 56 packaged backend files and 35 frontend source-map entries matched local source. Runtime
dependencies, database definitions, saved model definitions and coverage-policy definitions match
the preceding enrollment image, which remains available as the compatible fallback. No database
copy or restore was performed. Older backup database copies were removed at the user's request,
restoring about 15 GiB of headroom while three later backups and verification records were retained.
Full database integrity and full restore rehearsal remain unverified.

Two network-isolated disposable checks passed: evidence capture, immutable payloads and restart
with schema 16/55% coverage; and actual API coverage choices, invalid/stale save rejection and
unchanged authority. Neither check mounted live data or contacted providers.

Settings preparation began at **08:52:03 UTC / 09:52:03 BST**, reached Ready at 08:52:20 UTC,
and the old app completed clean shutdown at 08:52:25 UTC. The replacement container started at
08:52:27 UTC and application startup completed at **08:53:47 UTC**. Initialization took about
80 seconds, causing temporary Docker health failures while HTTP was not listening. It recovered
to healthy within the unchanged deployment timeout, with zero restarts or OOM. The shutdown and
initialization period is an observation gap, not healthy traffic. Boot is
`0466617e2d744e3cb10caf180c4d52dd`.

At **08:54:43 UTC / 09:54:43 BST**, all seven workers were running, snapshot age was 1.00 second
and diagnostic acknowledgement age was 35.40 seconds. The Settings operation was completed.
Cash and all three position identities matched the settled prepared snapshot exactly. Season 61,
profile, risk mode, bankroll, learning mode, permissions, active Manipulation v1, retained Sizing
v8 and suspended Exit v1 were preserved, as were native 55% revision 2 and Coach 70%. The paper
execution audit was verified with no issues. Authentication still required credentials; served
JavaScript/CSS hashes matched the verified image and the updated receipt explanations were present.

One natural training/publication cycle had completed using eligible retained evidence. Its model
and five unique native skill artifacts were present in bounded primary-key reads; inline and
external payload hashes verified. This does not mean new post-start enrollment bypassed its clean
stream or outcome-maturity requirements. Publication backlog and diagnostic loss counters were
zero at this initial check. Queue depth was 75, overall/critical lag 0.574 seconds and observed
post-start candidate shedding/expiry zero. These short observations do not establish sustained
burst improvement or long-term retention progress. The first scheduled cleanup pass was still due.

No Baseline formula, native learning/proof requirement, selected coverage, permission or experimental
buying rule was changed by deployment. Stage 4's completed prospective study remains inconclusive;
Stage 5's experimental buying filter remains off. No community push was performed.

The closing check at **08:59:20 UTC / 09:59:20 BST** still showed the exact new build/boot, all
seven workers running, Docker healthy with zero restarts/OOM, no trainer/RPC errors and a verified
paper audit. An old on-demand cached snapshot (275.94 seconds) refreshed to 2.17 seconds; the old
response is not a healthy freshness observation. Diagnostic acknowledgement age was 6.89 seconds.
Queue depth was 20, overall lag 0.102 seconds and critical lag 0.027 seconds. RPC had made 29
requests and applied 142 checkpoints, with one post-fetch processing-lag discard within aggregate
guard deferrals; batch size remained five. All three retained probes belonged to held positions.

The first scheduled cleanup passes had removed 526 raw events and 487 non-entry decisions.
The sampled completed core pass correctly had no deferral reason, duration 0.139 seconds and
history query time 0.045 seconds. Cleanup was still requested, its chunk was three rows, and the
24-hour retention target remained about 6 hours 13 minutes behind. This verifies execution of
the corrected path, not enough catch-up throughput or a resolved storage backlog. Available host
space was about 14.66 GiB on the data drive and 1.50 GiB on the system drive.

A fixed-end, deduplicated read returned six saved intervals (sequence 0–5) and 35 events, with
empty terminal pages, no sequence holes, no recording-gap flags and one initial partial interval.
The longest saved interval was 62.46 seconds; peaks were queue 853, overall lag 5.95 seconds and
critical lag 3.14 seconds, with zero reported candidate shedding/expiry. The final 46.73 seconds
were not yet saved and are not claimed as covered. Both natural publications retained their
training event and all six proof events, indices 0–6, with maximum collection delays of 10.47
and 43.46 seconds. Publication backlog and loss counters remained zero. The bounded startup log
contained no ERROR/CRITICAL or traceback entries; `uvicorn.error` is a logger name, not an error
severity. Longer comparable traffic, retention recovery and provider-failure recovery remain
unverified. No further service changes, forced training, promotions or schedules were made.

#### Final deployed edge and polish review

At **09:01:53 UTC / 10:01:53 BST**, the image/build/boot still matched the verified candidate.
All seven workers were running, Docker was healthy with zero restarts/OOM, trainer/RPC errors
remained zero and the paper audit remained verified. Cash and the three holdings were unchanged
since the settled rollout check. The cached first snapshot refreshed from 153.09 to 2.97 seconds
old; diagnostic acknowledgement age was 22.78 seconds. Current queue was zero and overall/critical
lag was 0.088/0.113 seconds. Native 55% revision 2, Coach 70% and skill authority were unchanged.

Cleanup had removed 7,749 raw events and 1,036 non-entry decisions. Its chunk adapted from three
to 35 rows, the latest completed pass had no deferral reason and the database file size was
unchanged between the two checks. Retention was still about 6 hours 13 minutes behind target.
Seven maintenance-related fetched batches had been discarded, within aggregate guard deferrals;
the earlier processing-lag discard remained. Catch-up versus collection pressure still needs
longer observation, and this short comparison does not prove sustained improvement.

The bounded new-boot read contained eight intervals and 51 events, no sequence holes or
recording-gap flags, an initial partial interval and one hour boundary. The longest interval
was 75.34 seconds and the unsaved tail about 25 seconds. Both publication groups remained complete;
reported candidate shedding/expiry and diagnostic loss were zero. Production source hashes still
matched the verified image (56 backend files and 35 frontend sources). Existing cancellation,
partial-worker-failure, protected-retention, fallback/cooldown and stale-setting edge coverage was
reviewed; the unchanged tests were not rerun. Documentation links and whitespace checks passed,
and private evidence/backups were not tracked. No new production defect or required code fix was
identified; no app, settings or service changes were made in this final review.

## Champion selectivity and collection handoff — local candidate, 21 September 2026

This is a **local candidate, not a live rollout**. Baseline, native learning/proof, broker,
model schemas, coverage settings and Champion permissions retain their previous contracts.
The engineering and research boundaries are in [SUPPORT_EVALUATION.md](SUPPORT_EVALUATION.md).
The earlier activity-pattern study remains inconclusive and its archived evaluator is preserved.

Stage 1 adds passive original-opportunity action counts and a separate sample of actual entries.
The sample is capped at 30 recent fills, uses exact indexed provenance and attributes only matching
season/profile/configuration/Champion receipts after activation. Checks cover duplicate fills,
ambiguous parent buys and full closes, partial/open/missing closes, currency/quantity mismatch,
future receipts, context replacement and restart. Negative realized results remain negative;
unapplied proposals receive no Champion credit. No persisted model/learning JSON field was added.

Stage 2 gives one fetched learning batch up to 0.5 seconds of scheduled lock-free waiting for a
storage chunk. Tests cover cancellation, stop, upgrade, learner/provider/route replacement, held
sell priority, lag, a stale idle event and a continuously busy store. Existing request clocks,
checkpoint deadlines, expiry, duplicate-outcome protection and Policy priority remain authoritative.
Cleanup is neither paused nor given a new admission delay by this handoff.

The first broad run exposed an interval-size compatibility issue when new counters were added to
the core report. Those counters were removed from the fixed interval payload before rollout.
A further high-entropy counter test exposed oversized optional runtime detail. Large reports now
split into finite optional lanes, preserving exact counters, original scope/time, the existing
byte limit and proof priority. Rechecks cover storage readback and fair admission while repeated
complete proof groups leave only one optional slot. No failing candidate was deployed.

Validation completed:

- **2,881 backend tests passed** in the complete isolated suite. The final diagnostic split,
  additional payload/parent edge cases and all new behavior then passed **167 targeted tests**.
- **533 frontend tests passed** across 27 files. TypeScript, ESLint (zero errors), Ruff and
  strict mypy (58 source files) passed; the production frontend build succeeded.
- Existing warnings remain: React Fast Refresh export style, a large frontend scene chunk and
  the test client's upstream deprecation warning. They are not newly introduced failures.
- The initial full test container exhausted its 768 MiB temporary fixture filesystem. It was
  discarded and the successful run used pytest's failed-only temporary retention, one CPU,
  a read-only root filesystem and no network/live volume. This was a test-environment limit.
- Core training/proof, models, Baseline and broker sources matched the before-change manifest.
  Private evidence, source rollback archive and study inputs remain ignored by Git/Docker.

Stage 3 prepares separate prospective research. The selectivity recipe compares one fixed shadow
hypothesis with incumbent, Baseline and cash; it never activates a strategy. The private specification,
verified immutable artifact and evaluator archive were frozen before a **12:00–18:00 UTC
(13:00–19:00 BST) enrollment period on 21 September**, with outcome cutoff **18:15 UTC / 19:15 BST**.
The current app already records the original Policy receipts used by this offline study; freezing
the files did not change the app or create a scheduled task. Changes of season, profile, fees,
configuration or Champion composition are excluded/reported rather than silently pooled. Review
boot/deployment and diagnostic gaps alongside the eventual dataset. Too few samples, incomplete
evidence or unfavorable comparisons remain inconclusive/unfavorable; do not extend until passing.

The separately frozen fallback-transition specification is **feasibility only**. Later-attempt
fixed-horizon efficacy still requires its own reviewed shadow quote/outcome capture. Original
Policy prices cannot substitute, and matched actual fills do not establish the outcome of a delayed
unexecuted trade. Conditional evidence review and trading activation are therefore **not complete**.
There is no new buying rule, forced promotion or claimed profit/selectivity improvement.

A bounded read-only live check at **10:32:17 UTC / 11:32:17 BST** confirmed the previous verified
build/boot and all seven workers running. Current queue was 13, overall/critical lag 0.493/0.263
seconds, and the returned five-minute counters reported zero pipeline loss. An initially cached
snapshot aged 2,545.66 seconds refreshed to 2.99 seconds; the stale response was not counted as a
healthy observation. Diagnostics acknowledgement age was 25.22 seconds, publication backlog empty,
and the existing single optional collection-record loss remained visible. Native 55% revision 2,
Coach 70%, active Manipulation v1, inactive retained Sizing v8, suspended Exit v1 and verified paper
audit were preserved. This limited check does not establish sustained burst or trading improvement.
No live settings, data, services, seasons or permissions were changed; no restart, push or schedule
was performed. Settings rollout and natural-traffic performance validation remain separate steps.

The closing read at **10:50:12 UTC / 11:50:12 BST** still showed the same live build/boot and all
seven workers running, queue zero, overall/critical lag 0.009/0.033 seconds and verified paper
execution. The snapshot refreshed from 1,075.94 to 3.19 seconds old; diagnostic acknowledgement
age was 56.76 seconds. The returned five-minute window now included **one expired candidate
event out of 57,862 received**, zero capacity shedding, and the recent-candidate-loss warning.
One additional storage diagnostic record was lost to event capacity; total reported loss was two
(one storage, one collection), with zero reported training/proof losses and an empty publication
backlog. These are remaining pressure observations, not a clean sustained-validation result.
The new candidate was not deployed, and concurrent host/provider load was not controlled, so
this sample cannot attribute the change in live pressure to a code improvement or regression.

### Additional local edge review, 21 September 2026

**88 focused tests passed**, including six added boundary checks. A real post-fetch storage
handoff was exercised at and immediately beyond both the eight-second response-freshness limit
and the 300-second checkpoint's 90-second grace limit. Waiting uses the original request clock;
late data did not create a usable outcome, and neither lane changed the market state or broker.
A shared storage-release signal woke both dashboard and RPC waiters without holding the market
lock. Compact → split → compact runtime reports retained exact counters, scope and timestamps
through storage encoding, while complete seven-event publication groups kept priority. Cadence
identities remained bounded and no diagnostic loss was recorded in these fixtures.

The focused run also repeated actual-entry attribution and prospective-study boundary checks.
Ruff passed for the added tests. All four frozen study files and all 56 archived backend source
digests still matched; core training/proof, model, Baseline and broker sources also matched the
before-change manifest. No additional application defect or required behavior change was found.
Only regression tests and this validation note were added during the review. The local candidate
remains undeployed, the live pressure observations above remain unresolved, and the prospective
study and conditional activation stages are still pending. These checks do not establish improved
trading, sustained burst performance or unattended reliability.

### Settings rollout of the selectivity engineering changes, 21 September 2026

The user authorized deployment after the additional edge review. Settings preparation reached
Ready at **11:01:41 UTC / 12:01:41 BST**, with no pending orders, followed by a clean shutdown
and replacement of only the app container. Application startup completed at **11:02:26 UTC**;
the same Settings operation completed and restored the previous running state. The shutdown and
startup period is an observation gap, not healthy traffic. No backup copy, data restore, season
reset, coverage adjustment, forced training or Champion promotion was performed.

- Image: `signal-arcade:v1.10.11-support-candidate-20260921`.
- Image ID: `sha256:69ed233222e4926dbf03c8adbf89523c7d2b0d4bfc0de48c3690cbb706a57f28`.
- Diagnostic build: `cae0ab01ca520cfd0b52e05e6326e7c0da2f88c861fdb0918746ffda77f7e8e4`.
- Boot: `83b0a9cf1d834244ac47241a44f905b0`; schema remains 16.

All 58 installed backend files and 35 frontend sources matched the reviewed candidate; served
JS/CSS hashes matched the image. Disposable networkless checks passed startup, authenticated
routes, Settings prepare/cancel, coverage validation and persistence across restart. The standard
rebuild initially resolved an unrelated `watchfiles` update. The release image restored the
preceding `1.2.0` version, and the complete installed runtime dependency map then matched the
previous image. The previous compatible image was retained; rollback was not needed.

The first fresh post-rollout snapshot preserved Season 61, risk/profile, cash, all three position
identities and quantities, learning mode, consent, automatic participation and Coach permission.
Native coverage stayed 55% revision 2 and Coach stayed 70%. Manipulation v1 remained active,
Sizing v8 retained but awaiting support qualification, Entry collecting proof and Exit v1
suspended. The paper execution audit was verified without issues. The new passive panel showed
60 original supported vetoes and separately attributed 13 matched fallback trades; none received
Champion entry credit. These descriptive results do not establish selective or better trading.

At **11:04:04 UTC / 12:04:04 BST**, all seven workers were running, Docker was healthy with zero
restarts/OOM, queue was 177 and overall/critical lag 1.504/0.275 seconds. A cached snapshot aged
66.15 seconds refreshed to 3.25 seconds; diagnostic acknowledgement age was 47.02 seconds.
The short new-boot window reported no pipeline shedding/expiry or diagnostic loss. One natural
publication had drained: its training event and all six proof events were saved, indices 0–6,
with maximum collection delay 40.14 seconds. Bounded primary-key reads verified the saved learning
model and five observed unique skill artifacts, including inline and external payload digests.
RPC reported nine requests, 47 checkpoint updates, no post-fetch discards and zero worker errors.

The first bounded saved-history read contained one initial partial interval covering 65.56 seconds
and eight events within 30-interval/100-event limits, with no recording-gap flag or sequence hole.
Its peak queue was 597, overall lag 4.362 seconds and critical lag 3.190 seconds. This is startup
validation, not sustained burst evidence. Before deployment, the preceding image recorded 2,814
expired candidate events in a five-minute window while the build also used host resources; these
unmatched traffic periods cannot establish improvement or regression. Storage remained above its
configured database budget, and retention catch-up still requires observation.

The frozen artifact and all four study files were unchanged. Season/profile, active Champion map
and selected coverage still matched the fixed specification. Deployment completed before the
13:00–19:00 BST enrollment window; its 19:15 BST outcome cutoff was not moved. Research and
conditional trading activation remain pending. Only the reviewed engineering changes are live.

The closing check at **11:07:32 UTC / 12:07:32 BST** confirmed the same image/build/boot,
all seven workers, queue zero and overall/critical lag 0.007/0.028 seconds. The five-minute
window reported 47,119 received events with no shedding/expiry. A cached snapshot refreshed
from 209.00 to 3.19 seconds old; acknowledgement age was 46.86 seconds, publication backlog
empty and all diagnostic-loss counters zero. Scheduled cleanup completed a 0.298-second pass,
removing 50 raw events and requesting further bounded catch-up. Retention was still about
6 hours 18 minutes behind the 24-hour target; the database remained over its configured budget.
RPC had made 27 requests and 139 checkpoint updates with no post-fetch discards or worker errors.

The final fixed-end read contained four consecutive saved intervals (0–3), covering 273.84 seconds,
and 32 events; neither read limit was reached. No recording-gap flag or sequence hole was observed;
the longest interval was 76.21 seconds, with peak queue 1,036 and overall/critical lag 7.024/4.592
seconds. The unsaved tail and initial partial interval limit coverage. Three natural publication
groups each retained their training event and all six proofs, with maximum delays 40.14, 4.16 and
16.94 seconds. Saved runtime detail included the new handoff counters, all zero in that pre-cleanup
sample: actual fetched-batch/storage overlap is not yet established by live evidence.

The running 58 backend source hashes matched the verified image. Bounded startup/runtime logs
contained no ERROR/CRITICAL severity, traceback or warning entries (`uvicorn.error` is an INFO
logger name in the startup lines). Remaining host headroom was approximately 14.28 GiB on the
workspace drive and 1.27 GiB on the system drive. Documentation links and whitespace checks passed.
No new deployment defect was identified. This completes the rollout check; sustained pressure,
retention recovery and prospective trading effects remain open observations, with no further
restart, forced experiment or scheduled polling created.


## Community polish candidate — 21 September 2026

This is a **local, undeployed candidate** built after the user's staged implementation request.
It does not replace the deployed selectivity build recorded above. No live settings, data,
permissions, thresholds, services or frozen study files were changed during this work.

### Evidence and scope

A fixed-end, bounded read ending at **15:32 UTC / 16:32 BST** contained 45 saved intervals and
337 events over the preceding hour. Pagination completed for the saved window with no sequence
holes, but seven long recording intervals and an approximately 93-second unsaved tail remained
observation gaps. The longest interval was 173.21 seconds. The saved window recorded 1,954
expired candidate events, no capacity shedding, peak queue 6,963 and overall/critical lag
22.59/11.73 seconds. Twenty-one publication groups were complete according to their own declared
counts; maximum collection delay was 76.06 seconds. This is evidence of pressure, not a clean
bill of health or a controlled comparison with v1.10.10.

The actual-entry heading inherited the footer-help control's absolute positioning. Serial,
bounded Results requests returned the requested server order correctly; delays were not evidence
that ranking was wrong. Cleanup was still roughly six hours behind its raw-event retention
target, with its adaptive chunk at one row. Existing aggregate SQL/lock timings did not identify
which category was limiting catch-up. A deterministic partial-pass reproduction demonstrated
that always starting with raw trades could leave non-entry decisions and equity unvisited.

### Implemented stages and edge checks

1. **Champion-impact layout:** give the actual-entry disclosure its own flow layout and visible
   keyboard focus. The footer help retains its separate placement. Component checks and browser
   checks covered open/closed disclosures, both open together, keyboard activation, absent active
   comparisons, desktop, 390px and 320px widths, and 200% CSS zoom. The browser zoom keyboard
   shortcut did not change the in-app browser's zoom; CSS zoom was the enlargement check.
2. **Results feedback:** show loading and retry state beside the sort controls and label the
   retained table's actual order, including an accessible table name and polite status. Keep
   server-side ranking, cancellation, sequential retry cadence and the last successful rows.
   Tests cover retained rows on failure, rapid sort changes, late superseded responses and empty
   results. Browser checks cover delayed responses, retry recovery, narrow layouts and switching
   to Seasons while a Results request is pending. Preview requests used local fixtures only.
3. **Retention fairness:** rotate the first category in admitted history passes. The reproduction
   allows just one query per pass: fixed ordering services only raw trades, while rotation gives
   all three categories a turn. Keep the same absolute deadline, row caps, lock timeout, adaptive
   controller, urgent-budget handling and protected evidence. Checks include cancellation,
   omitted optional categories, invalid rotation input, zero-row queries and reused timing maps.
   Rotation is a fairness fix; it does not establish faster raw-event catch-up or solve the
   observed one-row chunk limit. Categories compete within the existing shared budget.
4. **Burst-path review:** recheck candidate preparation, held-position/Policy priority, reserve
   result ownership, provider/context changes, original freshness clocks and cancellation.
   The timing evidence contains overlapping elapsed work and host descheduling. It did not
   establish a further safe optimization to immediate governance or checkpoint processing, so
   those algorithms, queue limits, deadlines and RPC batch size were not changed speculatively.
5. **Diagnostics:** retain per-category query/lock work in the existing storage event, with the
   original pass timestamp, rotation offset and chunk used before adaptation. Check real and
   varied payloads against the existing 768-byte compressed event limit. Preserve proof priority,
   honest omission counts, original publication timestamps and finite queues. No new per-trade
   query, event stream, retention allocation or recorder cadence was added.
6. **Manipulation research:** the artifact, specification, evaluator archive, feasibility file
   and manifest still match the frozen hashes. Enrollment ends at 19:00 BST and the outcome
   cutoff remains **19:15 BST**; this stage is pending. No screening result, recipe activation,
   replacement Champion or improved profitability is claimed. Even a positive result requires
   a separately versioned candidate and fresh qualification/common-forward proof.
7. **Release validation:** frontend tests, browser checks, static checks and a disposable restart
   rehearsal are recorded below. README, changelog and diagnostics documentation identify this
   follow-up as undeployed. Community publication and live rollout remain separate steps.

The focused cleanup/database checks passed **97 tests**; the subsequent cross-boundary suite
passed **244 tests**, including cleanup diagnostics payloads, stale RPC/application guards,
publication overflow/loss, study boundaries and candidate preparation. The full frontend suite
passed **534 tests**. TypeScript and the production frontend build passed. ESLint reported no
errors and the existing `EquityChart.tsx` hot-reload warning. The build retains the existing
large optional 3D-scene chunk warning. Ruff passed; mypy passed for all **58 source files**.
The full backend run passed **2,902 tests**; its release-version check failed because the
disposable source archive omitted the package manifests. The archive was corrected without
changing application code. The separate final run of that version check and the 15 cleanup
rotation/admission cases passed **16 tests**, completing validation of all **2,903 backend tests**.
The existing Starlette/AnyIO deprecation warning remains.

A network-disabled disposable runtime used the current deployed image's dependencies, a tiny
synthetic database and the newly built UI. It passed startup/authenticated reads, all Results
sorts, Settings prepare-to-Ready, source upgrade, prepare/cancel and another restart. Schema 16,
55% selection/revision, stopped trading state, protected CREATE evidence, ledger, orders, fills
and positions were preserved. This was a source-overlay rehearsal, not a newly packaged release
image, a full-size live database migration, a full backup restore or a live deployment.

A scan of the actual Git-tracked/unignored release set found no private data/backup/evidence
paths and no common token/private-key patterns. Private fixtures and test artifacts remain
ignored. This bounded pattern scan is not a claim that any scanner can prove absence of secrets.
Learning, Baseline and broker source hashes were unchanged from the start of this follow-up.

### Live observations during validation and remaining limits

At **16:04:33 UTC / 17:04:33 BST**, a serial read-only check confirmed the same deployed build
and boot, all seven workers, the same active Manipulation Champion and selected coverage,
an empty publication backlog and a verified paper execution audit. Current queue was 36,
overall/critical lag 0.239/0.589 seconds and diagnostic acknowledgement age 9.63 seconds.
However, the preceding five-minute window recorded **8,623 shed and 19,183 expired candidate
events**. Two dashboard responses were 13.80 and 18.04 seconds old, so refresh recovery was not
established by this check. Four optional diagnostic events had been lost since boot (three slow
samples and one selection sample); training/proof loss counters remained zero. These live totals
are not measurements of the undeployed fixes.

This window overlaps local validation on the same host. The disposable tests initially had a
one-CPU ceiling, subsequently reduced to half a CPU; other completed build/static/restart checks
also used host resources. Host contention and natural traffic therefore confound attribution.
No load test was run against the live app. A quiet current queue does not erase the recorded loss.
Sustained burst recovery, retention progress, fresh dashboard/diagnostic continuity and the
prospective study remain required observations. This candidate must not be described as proven
unattended reliability or as evidence that every remaining problem has been fixed.


The closing read at **16:08:57 UTC / 17:08:57 BST**, after the test processes ended, confirmed
Docker healthy with zero restarts/OOM and the same live image/build/boot. All seven workers and
the paper audit remained valid; coverage and active skills were unchanged. A cached dashboard
refreshed from 19.03 to 2.95 seconds old. Pressure still existed: queue 2,495, overall/critical
lag 12.63/0.44 seconds and 2,849 expired candidates with no capacity shedding in the preceding
five-minute window. Diagnostic acknowledgement age was **121.15 seconds**, so continuity was
not healthy merely because the recorder was running. Publication backlog was empty and loss
counters had not increased. This short, overlapping window is not sustained recovery evidence.
Disk headroom was about 12.61 GiB on the workspace drive and 1.16 GiB on the system drive.
No further live polling, deployment, forced learning or scheduling was performed.

## Final maintenance-read and diagnostics candidate — 21 September 2026

This follow-up was validated as a **local v1.10.11 candidate** before the rollout below.
It follows the community-polish
candidate above and preserves its Results feedback, disclosure layout and cleanup rotation.
It does not change Baseline decisions, learning features, training windows, coverage selection,
proof gates, Champion permissions, held-position/Policy priority or the frozen Manipulation study.

### Evidence and scope

A further bounded read-only review at approximately 17:17 BST confirmed the existing support
deployment and boot with all seven workers running and no reported trainer/RPC worker errors.
The diagnostic acknowledgement was nevertheless about 323 seconds old, with two publication
groups pending. Pending reports are not durable proof. In a preceding bounded 30-minute saved
window, nine of eleven intervals had recording gaps; the longest lasted 267.83 seconds and
the unsaved tail was 226.75 seconds. There were 9,144 shed and 30,875 expired candidates in that
saved window. These observations overlap natural traffic and local validation on the same host;
they do not isolate app changes from host contention and do not measure this undeployed candidate.

One saved storage pass took 84.956 seconds while its previously named sections accounted for
less than one second. The missing optional-count/oldest-trade sections and unbounded shared-reader
admission were concrete investigative leads. Read-only SQLite query-plan inspection confirmed
that `COUNT(*)` uses a single Count opcode: the progress callback need not run during its B-tree
walk. This establishes a cancellation gap, not proof that every slow live pass has that cause.
Cleanup remained hours behind retention and the last measured live-data size exceeded its target.

The initial regression reproductions failed for blocked capacity reads, non-interruptible counts
and optional counts running before market-pressure admission. The implementation now:

- Uses the original absolute deadline for maintenance reader admission and cooperative SQL work,
  including capacity and retired-table catalog reads. It restores the reader's busy timeout and
  progress handler, keeps the executing worker joined, and leaves the writer connection alone.
- Stops before maintenance reads during upgrade preparation. Deferral keeps committed deletion
  counts and the last real capacity measurement; unknown capacity is explicitly labelled and
  retried rather than presented as zero or as a successful fresh measurement.
- Runs optional counts after required cleanup when pressure allows. `COUNT(1)` offers progress
  callbacks during large scans. Only complete counts receive fresh timestamps. Attempts resume
  after the last attempted table so an interrupted large table cannot starve smaller counters;
  the same shared budget remains in force. Large counts can still remain stale.
- Records counts, oldest-trade reads and residual storage elapsed time. The residual subtracts
  only disjoint outer phases, never overlapping worker/query/lock details. Successful capacity
  and oldest-trade measurements have independent timestamps; an unknown oldest timestamp is null.
- Measures saved snapshot age from the actual capture timestamp, including assembly time, in
  agreement with the dashboard. Invalidating a cache does not rewrite the age of its contents.
- Adds Results timeout/retry/navigation regression coverage and an honest Settings message for
  unavailable capacity. Existing sorting, cancellation and retained-table order remain intact.

SQLite interruption remains cooperative. Neither these changes nor the tests establish a hard
deadline on filesystem I/O, OS descheduling or executor starvation. No queue limit, retention
allocation, recorder cadence, RPC batch size or trading rule was relaxed to hide pressure.

### Staged checks

The focused cross-boundary suite passed **181 tests**, including reader contention/cancellation,
committed work after a deferred final read, unknown-capacity recovery, upgrade admission,
retention rotation, RPC ownership, snapshot age, diagnostic payload size and publication priority.
Two isolated-harness issues were corrected: the disposable filesystem must expose more than the
app's existing 512 MiB reserve guard, and the adaptive-controller fixture must supply its own
reader admission when modelling SQL time. Neither correction loosened production checks.

All **537 frontend tests** passed. TypeScript and the production build passed; ESLint had zero
errors and the existing `EquityChart.tsx` hot-reload warning. The existing optional 3D-scene chunk
size warning remains. Ruff passed for the changed backend/tests and mypy passed for 56 backend
source files.

The full backend run completed with **2,913 passes and four fixture failures**. Those four cases
froze only the orchestrator clock at an artificial value; carrying the new absolute deadline to
the database correctly made it appear already expired against the real clock. The fixture now
uses the same clock on both sides. Production deadlines were not relaxed. The final focused run
passed **113 tests**, including those four cases, the counter-rotation starvation check, database
retention, maintenance coordination and snapshot boundaries. This completes coverage of all
**2,917 backend cases** across the full and focused runs; it is not a claim that the original full
run had no failures. Counter rotation was finalized after the broad run and checked in the focused
run. Ruff passed again on the final changed backend/test files.
Mypy also passed again on all 56 backend source files.

### Packaged runtime and release boundary

An isolated candidate image was built as
`signal-arcade:v1.10.11-maintenance-final-20260921`, image ID
`sha256:ab7f397889867f611cdf476a3862fda104b3ffcb9505e393ace41382e328ed44`.
It installs the new project wheel and built frontend over the current support runtime. Public
build tools were downloaded only in the disposable wheel builder; the final image build and
runtime rehearsal had networking disabled. All runtime dependency names/versions matched the
support image. This is an installed-package check using the existing runtime dependencies, not
a claim that a fresh upstream base/dependency rebuild has been rehearsed.

Hashes matched for all 58 installed backend package files, the corresponding source files and
all nine built frontend files. The packaged CLI passed startup, all-worker health, authentication,
all three Results sort endpoints, the new built UI status text, Settings prepare-to-Ready,
prepare/cancel and two subsequent restarts. The fixture retained schema 16, the selected 55%
policy/revision, stopped trading, protected CREATE evidence and its original journal hashes.
Orders, fills and positions were empty synthetic fixture tables; this does not establish a
full-size live migration, protection of every real holding, backup restore or sustained load.
The container had no live data mount, exposed host port or source-overlay import path.

A scan of 467 tracked/unignored release files found no private data/backup/evidence paths and
no matches for the common credential/private-key patterns checked. This bounded scan cannot prove
absence of every possible secret. Generated packages, fixtures and logs remain ignored. At the
end of validation, drive headroom was approximately 1.17 GiB on the system drive and 12.29 GiB on
the workspace drive. No backup or user data was deleted. Host resource headroom remains a
separate operational constraint and the tests are not live capacity benchmarks.

The learning/Baseline/broker source hashes and all five frozen-study artifact hashes match the
preceding local candidate. The study remains frozen and inconclusive; maintenance validation
does not authorize a Manipulation rule change. Local tests use disposable synthetic data and
bounded resources. The validation stage performed no live restart, deployment, setting change,
forced training or push. The separately authorized rollout and its remaining limits follow.

## Maintenance polish live rollout — 21 September 2026

The user authorized deployment after the final edge review. Eleven additional installed-package
checks passed, including cancellation before opening SQLite, cursor wraparound, retaining a
completed count before a later interruption, retrying interrupted counts, restoring a non-default
reader timeout after a real SQL error, and retired-catalog reader contention. No further app-code
change was needed. All 467 release files matched the validated manifest before deployment.

The Settings **Prepare for upgrade** path reached **Ready**. The app stopped cleanly, only its
container was replaced, and the existing named data volume was retained. The preceding image
remains available; schema 16 and runtime dependency versions are unchanged. No new backup was
requested, no user data was deleted, and no image or code was pushed publicly. The local image pin
now selects `signal-arcade:v1.10.11-maintenance-final-20260921`:

- Image: `sha256:ab7f397889867f611cdf476a3862fda104b3ffcb9505e393ace41382e328ed44`.
- Diagnostic build: `559821f8df15212f79cadc720a7376b9409f6f850cf9e985dec402fcfdb71520`.
- Boot: `69e0226d6fad47e9b83ac8fde193df0c`.
- Container start: **16:59:41 UTC / 17:59:41 BST**; application startup completed at
  **17:00:55 UTC / 18:00:55 BST**. Docker health passed around 112 seconds after container start.

Startup briefly exhausted the health-check grace period and showed unhealthy before recovering.
There was no restart, OOM or rollback. The preparation/startup period is an observation gap, not
healthy market coverage. This larger-database startup was materially slower than the tiny fixture
rehearsal; these timings do not isolate cold reads, host contention or other startup work.

Fresh post-startup checks verified the same season 61, cash, all three position identities/token
amounts, bankroll, risk/profile settings, learning mode, permissions and active Manipulation
Champion. The 55% coverage selection/revision/effective time, 70% Coach requirement and 1,000-row
training window were preserved. Settings completed the same operation and restored the prior
running state. Paper execution audit was verified without issues. The served JavaScript/CSS
matched the validated hashes, authentication remained enforced, and all three bounded Results
sort routes plus Champion-journey and maintenance reads returned successfully.

One natural training/publication cycle completed at **18:03:29 BST**, before new post-startup
observations could finish their own primary horizon; retained evidence can progress sooner.
Its training event and **all five expected proof events** formed a complete six-event group.
Maximum diagnostic collection delay was 47.40 seconds. Bounded primary-key reads verified the
new learning-model digest and five observed skill-artifact payloads, including the external
XGBoost payload. This is one successful cycle, not long-term publication/overflow validation or
evidence of improved trading returns. Entry remained collecting proof, Manipulation active,
Sizing testing its candidate and Exit suspended. No training or RPC worker error was reported.

Cleanup began naturally after the existing five-minute startup grace. By **18:09:38 BST**, it
had removed 1,420 raw trades, 1,387 non-entry decisions and 96 equity rows. The first saved storage
event contained category admission detail plus count, oldest-trade and residual timings. Smaller
counter timestamps refreshed while the interrupted large counts correctly retained older ages.
A busy-reader capacity deferral displayed `capacity_unknown`, then recovered to a fresh
measurement and `cleanup_needed`. The adaptive chunk reached one row and later recovered to six;
the fixes do not establish adequate catch-up throughput. Raw retention was still about **7.52
hours behind** its 24-hour target; live database pages were **21.47 GiB** against a **16 GiB** budget.

The bounded diagnostic review used a fixed end of **17:09:38 UTC / 18:09:38 BST** and read to an
empty page within the limits: seven intervals, 40 events, sequences 0–6 without holes. It included
one startup partial interval and one **170.62-second recording gap**. Peaks were queue **2,390**,
overall lag **17.94 seconds** and critical lag **9.26 seconds**. No candidate shedding/expiry or
diagnostic record loss was reported. Guard counters showed queue/lag deferrals; zero record-loss
counters do not make the long sampling interval healthy. The unsaved tail was 25.56 seconds.

At the recovery read, queue was 2, overall/critical lag 0.162/0.101 seconds and acknowledgement age
23.37 seconds. A stale dashboard refreshed from 28.52 to 2.21 seconds old. RPC had updated 200
checkpoints and recorded three post-fetch discards (two maintenance, one lag); these are a subset
of guard deferrals, not additional losses. At **18:10:26 BST**, Docker remained healthy with zero
restarts/OOM; the bounded startup/runtime log contained no warnings or errors. Free space was
about 1.06 GiB on the system drive and 12.22 GiB on the workspace drive.

The rollout and preservation checks passed. **Burst pressure, diagnostic sampling gaps, slow
retention catch-up and tight disk headroom remain operational limitations.** A short successful
recovery does not establish a regression-free comparison with the preceding build, sustained
reliability, community-release readiness, new Champions or profits. The frozen Manipulation
study and its cutoff were not changed. Full database integrity and full restore rehearsal remain
unverified. No further polling or schedule was created as part of this rollout.

## Final community readiness review — 21 September 2026

A bounded follow-up used a fixed end of **18:12:33 BST** on the same deployed image, build and
boot. All seven workers were running; dashboard and diagnostic acknowledgement ages were 4.17
and 2.78 seconds. Three natural training/publication cycles had completed without a reported
trainer error. All three publication groups were saved with their training event and all five
expected proof events, with no pending publication backlog or reported diagnostic record loss.
The paper execution audit remained verified; coverage policy, permissions and Champion state
were unchanged.

Serial diagnostic pagination reached an empty page within its bounded budget: ten intervals
and 64 events, sequences 0–9 without holes, and a 4.55-second unsaved tail. The window still
included the earlier **170.62-second recording gap**, peak overall/critical lag of **17.94/9.26
seconds**, and peak queue 2,390. No pipeline candidate shedding or expiry was reported. These
pipeline counters do not mean that every learning checkpoint completed: checkpoint expiry and
valid unavailable outcomes remain separate evidence. The quiet closing snapshot does not erase
the gap or establish performance improvement against a comparable traffic cohort.

Raw-trade cleanup had removed 2,044 rows since startup but was still about **7.56 hours behind**
its target. Capacity was again temporarily unknown due to reader contention, with its previous
measurement and timestamp retained honestly. The last measured live pages remained about 21.50
GiB against the 16 GiB budget. Catch-up throughput remains unproven.

All four source version declarations agree on 1.10.11, and all 93 local documentation link
targets checked exist. The release files initially matched the deployed manifest. The final
review additionally ran the exact repository-wide Ruff checks: lint passed, but formatting
identified 13 files. The pinned Ruff 0.16.4 formatter corrected those files locally. Every
changed file retained an identical parsed Python syntax tree; lint and formatting checks then
passed across all 202 Python files. No trading or learning behaviour was changed. Earlier
functional validation remains recorded above; the full suites were not rerun for formatting.

This final formatting/documentation polish is **local only**. The live image remains the
maintenance rollout recorded above, with equivalent Python logic but different source bytes
for the seven formatted backend files. No further restart or deployment was performed merely
for whitespace. A future community image should be built from the final formatted checkout.
Fresh upstream dependency audits and a complete clean Dockerfile rebuild were not repeated in
this review; the installed-package rehearsal is not a substitute for those release CI jobs.

No additional functional defect was established by this review. Nevertheless, diagnostic gaps,
retention catch-up and host disk headroom still prevent an unconditional claim of readiness for
unattended long-term use. The frozen Manipulation study was not changed or prematurely evaluated.
No public commit, push, promotion, setting change or additional schedule was made.

The closing bounded log read found three provider warnings: a stream close followed by two HTTP
413 rejections. At **18:18:14 BST**, a final serial read confirmed automatic recovery: the provider
was connected with fresh messages, three reconnects, no current error and no pending retry. All
seven workers remained running. The first cached dashboard was 182.16 seconds old and refreshed
to 3.17 seconds; diagnostic acknowledgement age was 27.92 seconds. Queue was seven, overall/
critical lag 0.021/0.045 seconds, and the recent five-minute pipeline counters reported no shedding
or expiry. These recovery observations do not treat the stale response or provider interruption
as healthy coverage. The trainer reported six publications and no error; only the first three
groups were independently read from saved diagnostic history in this final review. Docker was
healthy with zero restarts/OOM; free space remained about 1.05 GiB on the system drive and 12.22
GiB on the workspace drive. INFO messages from the `uvicorn.error` logger are not error-level
events; the bounded log contained no ERROR/CRITICAL event or traceback.

## Final cleanup reliability follow-up — 21 September 2026

The later read-only window, **17:59:41–20:41:13 BST**, reached the end of saved history within
bounded serial pagination: 132 intervals and 969 events, with no sequence holes and an 11.19-second
unsaved tail. It still contained **20 recording gaps**, **2,146 expired candidate events**, zero
capacity shedding, peak queue 6,104 and peak overall/critical lag of **22.05/13.35 seconds**. All
61 publication groups were complete; one low-priority heartbeat detail was lost, with no reported
training/proof loss. These are unmatched natural traffic observations, not a controlled comparison
against v1.10.10 or the preceding build.

Retention lateness grew from 7.56 hours at 18:12 to 8.74 hours at 20:41 and nearly nine hours at
21:04. Live pages exceeded the configured 16 GiB budget. Category samples and source inspection
showed that aggregate cleanup cost could reduce every history category to a single row; read-only
query plans also identified repeated preserved-boundary work. A disposable reproduction of the
actual maintenance method showed a 20 ms cooperative deadline waiting about 205 ms behind a
200 ms SQLite busy timeout. This established a lock-budget edge case, not its occurrence live.

The local fix makes bounded maintenance yield on SQLite contention and restore ordinary writer
settings on every exit; cooperative deadlines include worker dispatch. Each history category now
adjusts independently, and budget cleanup alternates raw/decision admission. Indexed raw boundary
selection preserves the same exact newest cohort, including timestamp ties, inside one statement;
it introduces no cached watermark, new index migration, schema bump or protected-evidence deletion.
On a disposable 25,000-row fixture preserving 20,000 rows, both queries deleted the same 50 rows.
The distinct-timestamp case used approximately 462,700 versus 122,700 SQLite VM steps; the all-tied
case used 791,400 versus 786,400. This is an isolated work comparison, not a live latency guarantee.

Targeted stages passed **67** maintenance admission/rollback tests, **155** cleanup/database
regressions, **129** diagnostic/broker/publication checks and **90** coherent-operation checks.
A worst-case diagnostic payload test caught an oversized combined broker record during development;
the added equity counters now have a separate bounded optional lane, retaining the existing record
cap and proof priority. One controller fixture was isolated from unrelated reader-admission timing;
real contention/deadline behavior remains covered separately. The broker sample now contains parts
from one joined operation. No speculative broker execution or diagnostic-pressure guard rewrite was
made: its remaining live cost needs attribution after deployment.

Frontend validation passed **537 tests across 27 files**; lint had zero errors and the existing
EquityChart fast-refresh warning. Backend type checking passed across 58 files. A clean repository
Dockerfile build succeeded. Its dependency resolution changed only `watchfiles` from 1.2.0 to 1.3.0
relative to the previous runtime inventory; final package checks must use that exact environment.
Current production frontend and exact runtime dependency audits reported no known vulnerabilities
in their audited packages. Full backend-suite completion, final packaging and rollout evidence are
recorded separately when complete; these stage results do not yet establish release acceptance.

The fixed Manipulation selectivity study is now concluded, with insufficient changed decisions
and no positive economic screen; see [the recorded result](SUPPORT_EVALUATION.md#completed-fixed-window-result--21-september-2026).
Its specification/evaluator and trading rule remain unchanged. Selected coverage, Coach's separate
requirement, the training window, chronology, negative outcomes, Champion permissions and
held-position/Policy priority are preserved. Disk headroom, a full restore rehearsal and sustained
natural-traffic validation remain independent release concerns.

Final local validation completed: the full backend run passed **2,965 cases** and exposed two
controller-test assumptions that a real worker would always be admitted within 50 ms. Both fixtures
now control admission explicitly; the reporting test also covers a genuine deferred outcome.
The final affected run passed **161 checks**, covering both corrected failures and their neighboring
deadline, contention, cleanup, broker and diagnostic contracts. Across the completed full run and
the final affected run, all **2,968 current backend cases** are covered. No application code changed
after the full run. An earlier isolated test attempt exhausted its 768 MiB temporary filesystem;
the subsequent run removed successful temporary fixtures instead of weakening the diagnostics
low-disk safeguard. Final Ruff lint and formatting passed across all 205 Python files.

The final installed image matches all **58 backend** and **nine built frontend** file digests,
the README, version 1.10.11 and its diagnostic fingerprint. Its exact audited dependencies match
the package inventory. Disposable startup, authentication, Results sorting, Settings preparation,
cancel and restart checks passed while preserving the synthetic ledger and schema 16. This is not
a full restore rehearsal of the main database. The release/privacy review includes 470 files;
no new finding group, actual credential match or private publish path was found. Existing security
fixtures and public project references remain intentional; Git/Docker exclusions are unchanged.

Before deployment, the six-hour runtime gate was recorded with load-band comparisons against the
preceding build, retention and live-page trends, complete durable proof groups, diagnostic gaps,
freshness recovery, worker/ledger checks and projected disk headroom. These are release-review
criteria, not altered trading or recording thresholds. A quiet startup cannot satisfy this gate.

The reviewed image was deployed through Settings preparation on **21 September**, with application
startup complete at **21:49:24 BST**. Initialization took approximately 78 seconds; Docker health
passed by the rollout's 112-second poll, within its existing 180-second guard. No restart or OOM
occurred. The prepared cash, three position identities, season 61, active skill, learning mode,
consent, automatic participation, Coach permission and selected coverage/revision were preserved.
The first read at 21:50:28 had all seven workers running, snapshot age **0.69 seconds**, queue zero,
overall/critical lag **0.010/0.006 seconds**, and no reported pipeline or diagnostic loss. Authenticated
served assets matched the verified image; unauthenticated snapshot access remained rejected.

One natural publication already had its training event and all six proof events durably saved,
with a 3.78-second maximum collection delay. The new linear model and observed native artifact
payloads verified by bounded primary-key reads; the latest XGBoost payload also verified but was
from an earlier fit, not a new post-upgrade family refit. The first saved partial interval includes
startup: it is not a steady-traffic sample. At that initial read, scheduled cleanup had not yet
reached its existing five-minute startup interval. Workspace/system free space was approximately
9.72/1.42 GiB, still limited. The six-hour read-only review is scheduled separately; no GitHub push
or unconditional long-term readiness claim is made by these immediate checks.

At **21:56:33 BST**, the requested dashboard recovered from its idle cached response to a
**3.29-second-old** snapshot. All seven workers remained running, with no restart/OOM, trainer/RPC
worker error, reported diagnostic loss or pipeline expiry/shedding. Two natural publication groups
were complete, with a 27.97-second maximum collection delay and an empty backlog. Seven saved
intervals contained 47,472 enqueued events, no sequence holes/recording gaps, a longest interval of
75.29 seconds and peak queue/overall/critical lag of **929 / 6.64 / 3.90 seconds**. The first interval
is partial and includes initialization; the fixed-end read has a **37.80-second unsaved tail**.
This remains a small, relatively quiet sample, not a matched burst comparison.

Cleanup began on schedule, initially completed a pass, then deferred a slow capacity read before
resuming. By the closing read it had removed **10,144 raw events, 2,510 non-entry decisions and 82
equity points**. Fresh live-page measurements fell from 22.869 to 22.825 GiB between 21:54 and
21:56; retention lateness improved by approximately 2.6 minutes but remained about **9.55 hours**.
The independently adjusted row limits and new per-category query/busy/budget fields were saved in
durable storage events. This verifies operation and initial progress, not sustained catch-up.
No coherent broker/equity sample had yet been saved in this short window; that path remains to be
observed under natural applicable work. RPC recorded two post-fetch processing-lag discards, a
subset of eight processing-lag deferrals. Limited disk space and the six-hour acceptance gate remain
open; the single read-only follow-up is scheduled for **03:55 BST on 22 September**.

## Final evidence and continuity review — 23 September 2026

The subsequent fixed six-hour read-only review did **not** satisfy the declared sustained-runtime
gate. Across 209 complete saved intervals, 5,856,610 enqueued events included 56,616 expiries and
5,482 shed events (1.06% combined per enqueued event, not per learning opportunity). There were
101 recording-gap intervals, a longest interval of 443.79 seconds and peak critical lag of
20.64 seconds. All 103 observed publication groups were complete, without reported training/proof
loss. The current build remained healthy with seven workers and no restart/OOM, but that does not
make the missing observations healthy traffic. Retention was approximately 5.5 hours late and live
pages grew in each two-hour block. Limited host headroom remained a separate concern.

Coherent slow-broker samples and bounded query plans supported a specific evidence-read fix:
buy-side chronological lookup could scan a lane despite an existing decision index, while sell-side
entry-fill lookup lacked a targeted access path. The final candidate explicitly uses the decision
index and adds a non-unique partial execution-fill index. Duplicate selection, chronological ties,
writer linkage and transaction atomicity are preserved. The execution index includes the preceding
build's traversal order so a compatible rollback also preserves duplicate selection. Schema 16 and
saved authority records are unchanged; index creation still has a one-time startup cost.

Cleanup now rechecks its original deadline after connection setup, before even a short statement
can finish without invoking SQLite's progress callback. Timings separate setup/restoration and
worker CPU from elapsed query/commit and dispatch/resume time. This fixes an admission edge and
improves attribution; it does not establish that unidentified worker delay is caused by disk I/O,
or justify larger cleanup transactions or weaker market guards.

Reduced in-memory diagnostics can preserve a due interval during short detail deferrals, subject
to a free boundary, no pending sell and available bounded queue capacity. Existing writer guards
are unchanged. Reduced detail is explicit, complete publication groups remain FIFO, and pressure
can still cause unsaved tails or long intervals. Retention measurements retain their actual sample
times in a separate bounded optional event. A worst-case test caught interval overflow when these
fields were initially placed in full intervals; the final design keeps that existing payload
unchanged rather than increasing its limit.

Targeted validation passed 91 database/broker/linkage checks, 149 maintenance/runtime cases across
the initial run and corrected-fixture rerun, 179 initial diagnostic/publication checks and 142
final diagnostic-boundary/payload checks. A controller fixture now isolates RPC admission policy
from unrelated executor delays; real contention and deadline tests remain. An isolated test attempt
failed on a Docker host bind-read allocation error before running tests; later checks stream a
small immutable source archive into the network-isolated disposable container instead.

The conditional support review passed 136 learning/coverage/selection checks, including six
reproductions of rare upstream admission. Thirty older supported opportunities fall to ten, then
zero as newer vetoed rows displace them from the 1,000-row independent Policy population. Both
positive and negative vetoed outcomes give the same selection. This confirms a recency limitation,
not evidence that saved proof was lost. No retrospective proof-window extension, altered minimum,
requalification bypass or Manipulation rule activation was made. A future window-policy study must
define its population before observing outcomes and cover activation, health, restart and recovery.

Final package, full-suite and rollout results follow only after those checks complete. The existing
six-hour runtime gate remains unchanged; isolated checks and quiet startup cannot certify sustained
burst capacity, retention catch-up, improved decisions or profitable trading. Full main-database
integrity and a full backup restore rehearsal remain unverified.

The broader regression run exposed an optional-report priority edge: a retention sample could
occupy the last available slot before a loss report. Retention now follows the existing detail
reports and retries through the same fair bounded admission. Proof preservation and loss-report
priority remain required. Packaging also exposed a newly resolved transitive Starlette version;
the release explicitly pins the previously deployed and tested 1.6.0 version. A fresh audit of
the preserved runtime dependency inventory reported no known vulnerabilities.

The complete backend run executed 2,999 cases: 2,994 passed initially. Its five failures were
the report-priority defect above, three assertions that needed to account for the additional
optional retention event, and an isolated test archive missing release metadata. Corrected
publication/version and additional-edge runs passed 58 and 71 cases respectively; the affected
broader diagnostics run also passed 195 cases before the publication assertions were updated.
All five original failures are covered by the passing reruns. The fixture changes still require
every training/proof report, original publication indices, exact cadence boundaries and retries.
Static checks passed for 207 Python files, with strict typing passing for 56 Python source files.

The final standard wheel was checked byte-for-byte against all 58 expected backend/resource
files. To limit temporary disk use, it was installed without dependency resolution over the
verified candidate runtime and unchanged frontend layers. Installed and source payloads, nine
built frontend files and the exact audited runtime dependency inventory matched. The packaged
application passed isolated first startup, Settings prepare/restart and prepare/cancel/restart
checks, including authentication and unchanged synthetic ledger records. No live data was used
in that rehearsal, and it does not establish a complete live-database restore.

The final clean frontend run passed all 537 tests. ESLint had no errors, TypeScript and the
production build passed, and all nine independently rebuilt asset hashes matched the packaged
frontend. The existing Fast Refresh export warning and large lazy-loaded 3D chunk warning remain.
Earlier isolated frontend attempts had dependency-path/native-loading and CPU timing failures;
the final runner uses one coherent temporary dependency tree. The focus-restoration test now
preloads its lazy module so compilation is separate from behavior, retaining its bounded wait.
No frontend application behavior changed in this review. The final release-file privacy review
found no local-credential matches, private publish paths or new finding groups; existing public
publisher references and security-test fixtures remain documented exceptions.

The Settings upgrade on **23 September** first exceeded the existing 180-second startup guard.
Automatic rollback restored the preceding image, which itself took approximately 148 seconds
to reach the health check. Bounded inspection confirmed that the new execution-fill index had
committed, schema 16 remained compatible, and cash, season, permissions and all three saved
positions were preserved. The exact contribution of index creation versus other cold-start/host
costs was not measured; the delay is not attributed entirely to the index.

One guarded retry of the identical verified image then completed successfully. Application
startup finished at **19:05:17 BST**, approximately 29.46 seconds after container start, without
widening the guard or changing the candidate. The running build is
`e14d014b9a94610467cd5a31f4ef7990f267fe4e3bd62343704d8ca65faa289c`.
Both intentional upgrade interruptions are observation gaps, not healthy market traffic.

At **19:06:59 BST**, all seven workers were running with no restart/OOM, queue 39, overall lag
0.232 seconds, zero measured critical lag and a 1.28-second-old dashboard snapshot. No pipeline
expiry/shedding or diagnostic loss had been reported since this boot. The Settings operation
was completed; cash, three position identities, season 61, active Manipulation skill, coverage
55% revision 2, Coach 70%, training window 1,000 and execution permissions matched preparation.
The paper execution audit was verified. Served asset hashes matched the tested package, protected
snapshot access required authentication, and saved model/observed artifact payloads verified by
bounded primary-key reads. Those artifacts predate this restart; they do not establish a new fit.

The unchanged six-hour runtime acceptance window starts at completed application startup. Early
startup observations do not settle burst performance, retention catch-up, repeated publication
or long-term readiness. Workspace/system headroom was approximately 5.18/2.08 GiB; remaining
above the emergency startup floor does not establish the required 24-hour projected headroom.
No community push was performed.

At **19:10:38 BST**, the dashboard refreshed to 2.75 seconds old, all seven workers remained
running, and the new boot still reported no pipeline shedding/expiry or diagnostic loss. The
first scheduled cleanup had removed 813 raw events and 92 equity points. Its deadline/reader
guards deferred further work when busy; the new setup/restoration and worker-CPU fields were
present. The first fresh history sample showed retention about seven hours late, which is an
inherited backlog baseline, not evidence of catch-up or regression from this short run.

The bounded saved-history read through **19:10:56 BST** retrieved all available pages within
its limits: three complete intervals, sequences 1–3, covering 198.94 seconds and 28,031 enqueued
events, with no holes or recording-gap flags. Peak saved queue/overall lag were 734/5.46 seconds;
no critical lag was recorded. The initial interval crossing startup was excluded and the final
83.20 seconds were not yet saved. A retention sample was durable, but no post-startup natural
training/proof group had yet been observed. Enrollment/outcome warm-up, repeated publication,
essential collection under sustained pressure and the six-hour comparison remain open checks.

## Delayed-response and deadline follow-up — 23 September 2026

The next bounded review still found burst pressure and long diagnostic acknowledgement delays.
A fresh dashboard could recover after an explicit request, but worker health and recovery alone
did not establish sustained acceptance. Worker completion followed by delayed event-loop resumption
also prevents attributing all slow intervals to SQL execution or disk I/O.

Isolated reproductions confirmed three correctness hazards: maintenance reader setup could consume
the original deadline before a short SQL statement; metadata application could block the event loop
on a feature lock; and a delayed held-route response could apply to a replaced engine/token or a
changed pool. A negative response could also modify replacement retry state. These are specific
defects, not proof that they explain every live burst.

Maintenance now rechecks its original deadline/cancellation after connection setup and attempts
busy-timeout restoration even if progress-handler cleanup fails. Enrichment preparation and result
application use a joined worker while owning the market boundary. Provider I/O stays outside it.
Result application verifies the original engine, token identity, source mode and, for route replies,
provider generation, venue and pool. An already accepted newer verification is preserved. Ordinary
trades advancing the same token remain valid; current failures retain the existing retry policy.
Cancellation keeps ownership until an executing worker has finished, including repeated cancellation.

Optional coherent enrichment and candidate-preparation timings distinguish worker CPU, elapsed work,
executor dispatch and event-loop resume delays. Training records reconstruction/fit CPU alongside
elapsed time. These measurements overlap and are not additive CPU estimates. Fixed optional fields
use existing bounded payload/admission rules; interval counter dimensions and pressure guards are
unchanged. No speculative cleanup budget, trading rule, proof window or Champion permission changed.

The initial regression run reproduced 13 failures on the preceding implementation, with seven
control cases passing. Maintenance validation then passed 95 cases; ownership checks passed 138,
then 150 after additional source/venue/removal/maintenance/cancellation cases. The final combined
timing, ownership, provider, publication, payload and training checks passed 276 cases. Intermediate
timing checks caught optional fields omitted from saved samples; the corrected path is included in
that final passing run. Full-suite, package and rollout evidence follow after completion.

The predeclared six-hour acceptance criteria remain unchanged. The new instrumentation and isolated
fixes do not certify retention catch-up, sustained burst performance or improved trading outcomes.

Strict typing passed for 58 source files; lint and formatting passed for 209 Python files. The
standard installed wheel matched all 58 backend/resource files and nine unchanged frontend assets,
with the exact previously audited runtime dependencies. Isolated first startup and Settings
prepare/restart and prepare/cancel/restart rehearsals passed using disposable data and schema 16.
This is a package check, not a full live-database restore. The release-file privacy review found
no local-credential matches, private publish paths or new finding groups. Existing documented
public references and security-test fixtures remain exceptions. The frontend source/assets are
unchanged from the preceding 537-test release validation.

The complete backend suite passed **3,045 tests across all 152 collected test modules** on the
same immutable source archive, in ten serial groups. An initial single-container attempt exhausted
its 768 MiB temporary filesystem; diagnostic writes first yielded at the existing 512 MiB free-space
floor, followed by SQLite fixture failures. One grouped attempt also crossed that floor. The
affected group passed unchanged with a larger, capped RAM-backed temporary filesystem, and all
remaining groups completed. No production safety floor or assertion was weakened. Passing groups
were retained; every module is accounted for once in the final successful coverage record. These
test-harness capacity failures do not establish a live application regression.

The guarded Settings upgrade completed on **23 September**, with application startup at
**20:25:49 BST** (approximately 75 seconds after container start). Docker health passed within
the unchanged 180-second guard, with zero restarts/OOM and no rollback. The running build is
`1be035ea213b5aff8075c0abdb6f122d4e746f5b61172fdab276bd9ff22fed20`.
The intentional interruption remains an observation gap.

At **20:26:39 BST**, all seven workers were running; the snapshot was 0.93 seconds old, queue
depth was 80 and overall/critical lag was 0.76 seconds. No pipeline expiry/shedding or diagnostic
loss had been reported on the new boot, and publication backlog was empty. Cash, three position
identities, season 61, profile, permissions, active Manipulation v1, coverage 55% revision 2,
separate Coach 70% and training window 1,000 matched Settings preparation. The paper audit was
verified. Authentication and served asset hashes passed; bounded primary-key reads verified
schema 16, the latest saved model and five observed unique skill artifacts. Those artifacts
predate this restart and do not demonstrate a new publication.

New candidate and enrichment timings were present in the live diagnostic view, explicitly marked
pending optional handoff rather than durable history. Startup/warm-up observations cannot establish
sustained capacity or improved decisions. The unchanged six-hour window ends at **02:25:49 BST on
24 September**. Host free space remained approximately 5.16/2.02 GiB on workspace/system storage;
24-hour projected headroom, sustained burst/retention acceptance and complete restore/integrity
checks remain unverified. No community push was performed.

The closing read at **20:28:54 BST** recovered an idle cached dashboard from 129.28 seconds old
to 6.38 seconds old after a bounded serial retry. Current overall/critical lag was 0.040 seconds,
queue depth 75, diagnostic acknowledgement age 13.49 seconds, all workers running and no reported
pipeline or diagnostic loss. Saved history through the fixed read end contained two complete
intervals (sequences 1–2), covering 145.80 seconds and 15,637 enqueued events. Both page streams
completed within their limits, with no sequence holes or recording-gap flags; the longest interval
was 85.12 seconds and the unsaved tail 17.27 seconds. Peak queue/overall/critical lag was
1,582/17.63/5.86 seconds. This short warm-up sample still shows latency and is not a matched-load
performance comparison or evidence that burst pressure is resolved.

One natural post-startup publication retained its training event and all five expected proof
events, with indices 0–5 and maximum collection delay 3.31 seconds. Bounded reads verified the new
model and observed artifact payloads; the latest XGBoost artifact remained from before this boot.
New enrichment and candidate timing samples were durable. The training event also preserved the
new CPU timings: reconstruction took 5.04 seconds elapsed/4.63 seconds on its worker thread, and
fitting 0.63/0.62 seconds. This is one attributed operation, not proof of the cause of every lag
spike. Cash, position identities, coverage and profile still matched preparation. Repeated
publication, retention catch-up and the six-hour acceptance gates remain open.

## Processing contention follow-up — 23 September 2026

A read-only review of the preceding deployed build found continued event expiry, long shared
market-boundary waits and delayed retention. Complete publication groups and running workers
did not establish sustained capacity. Subsequent isolated profiling identified repeated ledger
reads and Policy feature-vector validation as actionable costs; SQL time and executor/loop
resumption remained distinct. No single cause was established for every critical-lag spike.

The bounded changes are:

- Add an idempotent covering ledger index on account, ledger ID, debit and credit. Balance reads
  remain fresh and preserve ledger-ID summation order. One synchronous entry assessment reuses
  its existing cash valuation; submission and filling still start fresh checks. Schema 16,
  accounting, season reset, peak-watermark writes and permissions are unchanged.
- Traverse current feature values using bound built-ins, in the original feature order, with
  missing/nonfinite values and malformed-value short-circuit behavior preserved. No validation,
  outcome or Champion-health result is retained across calls. Checkpoint and governance order,
  dependency requalification, Policy identity reservations and training/proof separation remain.
- Construct only compact dashboard values while retaining identical rolling calculations and
  cache warming. Full decision and held-position snapshots keep their existing default paths;
  snapshot ownership, cancellation and original capture timestamps are unchanged.
- Read related page-size/count/freelist counters in one SQLite statement under the same reader
  ownership and maintenance admission. No cleanup deadline, deletion cohort, per-category limit,
  urgency threshold, RPC pressure guard, database durability setting or retention policy changed.
- Add bounded candidate/governance timing detail without additional reads, unbounded traces or
  proof-event displacement. Empty handoffs are omitted; worker results survive reporting failure.

Staged checks passed: accounting/database/decision **172**, feature/proof/participation **346**,
dashboard/features/refresh **126**, and capacity/maintenance/upgrade **206** cases. The final
instrumentation-specific correction passed **22** cases; earlier broad instrumentation checks
are included in the complete-suite verification. Intermediate tests caught an empty measurement
handoff, a legacy-path fixture and omission of the ledger table from index discovery; all were
corrected before proceeding. No failing assertion or safety limit was weakened.

Small isolated comparisons used identical inputs and alternating execution order. For 3,000
ledger rows, 100 indexed reads used median 0.0363 CPU seconds versus 0.1136 for table scans; at
30,000 rows, 0.4682 versus 2.2185. Index sizes were 80 KiB and approximately 736 KiB. Inserting
3,000 synthetic rows took 0.0362 versus 0.0263 CPU seconds, an explicit additional write cost.
The account index avoids a persistent cash cache and is retained for the read-heavy workload.
For 10,000 mixed feature vectors, traversal used 0.0433 versus 0.0549 CPU seconds with identical
results and no profiler hooks. Compact dashboard construction used 0.0681 versus 0.1802 CPU
seconds for 300 calls; related capacity reads used 0.0213 versus 0.0393 for 1,000 calls.
These are fixture results, not live latency guarantees or evidence of improved trading returns.

Broad lock removal, delayed/batched Champion governance, persistent portfolio caches and training
population changes were excluded. Training reconstruction was left unchanged: its remaining
cost is observable, but this review did not justify changing frozen model inputs or the 1,000-row
window. Full regression, packaging and deployment evidence follow only when completed. Sustained
burst/retention acceptance still requires the unchanged six-hour observation criteria.

The complete immutable backend archive passed **3,254 cases in 157 modules**, split into eleven
serial, resource-capped groups with no network or live mounts. The tested backend and tests matched
the reviewed files byte for byte. Strict typing passed for **56 source files**; lint and formatting
passed for **214 files**. The existing Starlette/AnyIO deprecation warning remains unrelated to
these changes. Frontend source and its nine built assets were unchanged from the preceding
537-case validation.

The installed candidate image verified all **58 backend/resource files**, the built assets,
version 1.10.11 and the audited runtime dependency inventory. Disposable packaged first-start,
Settings preparation/restart and preparation/cancellation/restart rehearsals passed with schema
16 and unchanged synthetic journals. These checks did not mount live data or rehearse a full
production-database restore. The release/privacy review covered **479 publishable files**, with
no private evidence paths, unscanned files or local credential matches; remaining pattern groups
matched previously audited public references and security-test fixtures.

The rollout review also found that Settings Ready does not imply pending diagnostic reports have
been saved: maintenance pauses their normal collection/writing. The private deployment guard now
requires no active fit, pending publication group or queued diagnostic write both before preparing
and after Ready. A race at preparation aborts replacement and resumes the preceding app. Eight
isolated gate cases and the complete rollout script's syntax passed. This safeguards this rollout;
it does not add durable shutdown storage to the application or certify abrupt-crash recovery.

At **22:37:34 BST on 23 September**, the guarded rollout stopped **before requesting Settings
preparation**: a training job was running, one publication group containing six events remained
pending, and five diagnostic writes were queued. The last diagnostic acknowledgement was
1,266.75 seconds old. No stop, replacement, configuration change or rollback occurred; the
preceding ownership build remained live. The locally verified candidate is therefore **not yet
deployed**, and no new six-hour acceptance window has started.

The preceding live read at **22:35 BST** had all seven workers running and a verified paper
audit; the requested dashboard refreshed to 5.36 seconds old. It also reported substantial
pressure: 48,346 candidate expiries among 89,862 received events in its five-minute view, zero
capacity shedding, and eight optional diagnostic event losses (seven storage, one heartbeat).
There was no reported training/proof diagnostic loss, but delayed or pending reports are not
durable evidence. Local tests shared the host during this sample; it is not an untouched natural
traffic comparison or evidence about the undeployed candidate. Bounded primary-key reads verified
the latest observed saved model and five unique native skill artifacts, including their payloads.

Free workspace/system storage was approximately **5.11/2.69 GiB**, just above the existing workspace
rollout floor. Projected 24-hour headroom and sustained burst/retention acceptance remain open.
The existing scheduled read-only review retains the actual running build and original window;
it must distinguish this verified local candidate from a deployed improvement. No community push
was performed.

### Processing contention edge recheck

The subsequent edge review confirmed that the application and tests still matched the immutable
3,254-case archive. Fresh balance visibility, integer aggregation, feature-validation short
circuiting, compact snapshot cache effects and joined-worker cancellation/reporting paths showed
no additional application defect. The private rollout helper was tightened to reject unknown
training states, contradictory active-fit fields, malformed or missing counters, paused/error
writers and inconsistent publication status. All **26 isolated rollout-gate cases** passed;
no application or image change was needed for this helper correction.

At **22:40 BST on 23 September**, the preceding image remained healthy with seven running workers,
zero restarts/OOM and a verified paper audit. Dashboard refresh recovered to 5.35 seconds old.
Diagnostic writing had resumed (acknowledgement age 58.18 seconds), but one six-event publication
group and three queued diagnostic writes remained pending. Nine optional event losses and one
interval-queue loss were reported cumulatively; zero reported training/proof loss does not remove
those gaps. The recent five-minute pipeline still showed 6,089 expiries among 87,766 received
events, with no capacity shedding. This is a short snapshot of the preceding build, not validation
of the undeployed candidate. No live settings, services, trading permissions or rollout were changed.

## Optional cleanup and writer-wait follow-up — 24 September 2026

The subsequent read-only review found a coherent storage operation with roughly six seconds in
optional housekeeping overlapping a market-persistence writer-lock wait. The combined older
timing could not identify which optional category held the writer. Both optional deletion methods
used ordinary writer admission and SQLite busy waits rather than the bounded maintenance path.
Separately, the diagnostic writer could correctly remain blocked by a retained market-yield flag
while collector admission reported no current blocker. That discrepancy justified better visibility,
not clearing the flag or relaxing writer pressure guards.

The follow-up routes optional incident and AI-audit deletion through the existing bounded
transaction helper, preserving the exact selection and retention requirements. It limits each
attempt to 50 rows and an original 50 ms cooperative deadline including executor dispatch and
writer admission. Deferral is distinct from a completed zero-row query; committed counts remain
accounted for when cancellation follows a commit. Due categories rotate, attempts are paced, and
quiet-stream retries run without repeating primary maintenance. Cancellation retains ownership
until the real worker exits. No hard wall-clock guarantee is claimed for descheduling or I/O.

A larger disposable incident fixture exposed repeated deadline exhaustion from sorting the
resolved backlog. A partial `last_seen_at DESC` index avoids that sort, retaining existing rowid
tie behavior; unresolved rows stay outside the index. Index initialization is additive and schema
16 remains compatible. The new fixed-size writer-wait observations are separate from collector
admission and cannot authorize writes. Optional reporting retains the existing cadence, byte
limits, pressure guards and complete-publication priority.

The frozen Manipulation study, trading/Champion permissions, coverage policy, separate Coach
requirement, chronological validation, negative outcomes and training/proof separation are unchanged.
The earlier locally validated processing-contention changes remain part of this combined candidate.
Local regression, packaging and rollout results are recorded below only once completed. The
preceding live build failed sustained acceptance; no community-ready or profitable-trading claim
follows from these source changes. A deployed candidate requires a fresh six-hour review under
the predeclared criteria, with host validation activity excluded from causal performance claims.

The combined candidate passed **3,309 backend cases in 160 modules**, in eleven serial,
resource-capped groups without network or live-data mounts. The application source was identical
throughout this run. An existing publication test double needed the new observational method;
the complete affected group was rerun successfully, with unchanged assertions and retained failed
attempt evidence. The final backend and test files match the corrected source archive. Focused
checks covered large-history progress, timestamp ties against the unindexed selection, unresolved
record retention, SQLite contention/restoration, dispatch deadlines, paced quiet-stream retries,
repeated cancellation and committed counts, writer reasons, reporting failure, byte limits and
protected publication priority. Strict typing passed for **58 source files**, and lint/formatting
passed for **217 files**. The existing Starlette/AnyIO deprecation warning remains unrelated.

The local image installed and verified all **58 backend/resource files**, **nine frontend assets**,
version 1.10.11 and the unchanged audited runtime dependencies. Disposable first-start, Settings
upgrade/restart and cancellation/restart rehearsals passed, preserving schema 16 and synthetic
journals. The 77 frontend source/manifest files match the preceding 537-case validation. The
privacy check covered 482 publishable files plus the Git index, with no private evidence paths,
unscanned files, local credential matches or new finding groups. The guarded rollout's 26 isolated
publication-gate cases passed. No live backup, main-database integrity scan or full restore was run.

At **05:38 BST on 24 September**, the preceding ownership build remained live. All seven workers
and the paper ledger audit passed; the requested dashboard refreshed to 6.20 seconds old. One
seven-event publication group and three diagnostic writes were still pending, so the read-only
preflight did not permit an upgrade. Diagnostic acknowledgement age was 95.53 seconds. Its recent
five-minute view reported 18,515 expiries among 90,580 received events and zero capacity shedding;
the current overall/critical lag was 16.99/0.096 seconds. These are preceding-build observations
during shared-host validation, not evidence about the new candidate. Existing settings and the
unsuccessful frozen study were unchanged. Workspace free space remained only about 5.01 GiB,
barely above the existing rollout floor; projected 24-hour headroom remained unverified.

The bounded recheck at **05:39 BST** still found the same seven-event group and three queued
diagnostic writes; acknowledgement age had reached 159.15 seconds. The current queue/lag had
recovered to 67 events and 0.215 seconds, but that recovery did not make pending evidence durable.
The seven workers and paper audit still passed, and the dashboard refreshed to 6.02 seconds old.
The new candidate remains **locally validated, not deployed**. No Settings preparation, service
stop, configuration change, forced collection or community push occurred. Upgrade and fresh
six-hour acceptance remain pending the unchanged publication and headroom checks.

### Optional cleanup edge review

A subsequent focused review reproduced a gap in the new quiet-stream retry path: it could
mark storage active while an already admitted learning reserve request was awaiting its provider.
The primary cleanup path already protects those requests. Optional retries now yield before
taking storage ownership whenever a learning request is in flight; urgent primary retention keeps
its existing bounded admission rules. This avoids unnecessary storage handoff or expiry risk;
it does not imply that the earlier live build experienced this undeployed-path defect.

The regression first failed on the overlapping cleanup attempt, then passed with the guard.
The test verifies that both Discovery and Policy primary checkpoints receive their fetched outcome,
no batch is discarded, and optional cleanup resumes after the request finishes. A separate test
verifies repeated cancellation of the quiet-stream wrapper: ownership remains held until the
worker exits, and committed deletion counts remain accurate. All **215 focused cases** passed
across cleanup, RPC handoff, SQLite interruption/restoration, diagnostics and publication retention.
The earlier 3,309-case run belongs to the preceding candidate; it is not a new full-suite run of
this correction. The only application-source change in this review is this optional admission
guard. Strict typing passed for 58 source files, and lint/formatting passed for 217 files.
Packaging and runtime acceptance must match the corrected source before rollout is claimed.

A bounded read-only check at **05:47 BST** confirmed the unchanged ownership build and boot,
seven running workers and a verified paper ledger. The old dashboard refreshed to 5.21 seconds
old. The publication backlog was empty, but one diagnostic write remained queued and acknowledgement
age was 90.44 seconds. Current queue/overall/critical lag was 368 events / 0.299 / 0.079 seconds.
These short observations do not establish sustained acceptance or improvement from the undeployed
correction. Workspace free space was still about 5.01 GiB. No image rebuild or live rollout was
performed in this edge review; the earlier packaged candidate does not contain the new RPC guard.

### Corrected optional-cleanup deployment — 24 September 2026

The corrected source was rebuilt as `v1.10.11-optional-cleanup-edge-20260924`. Installed and
source hashes matched all 58 backend/resource files, nine frontend assets and the packaged README;
runtime dependencies matched the audited inventory. Disposable first-start, Settings preparation/
restart and cancellation/restart rehearsals passed. The prior 3,309-case baseline and the 215-case
corrected-source regression run remain distinct evidence. The unchanged publication admission
checks also passed 26 isolated cases.

Live preflight at **05:52 BST** found no pending publication or queued diagnostic write. Settings
preparation reached Ready, and the repeated checks still passed before a clean stop. The replacement
completed application startup at **05:54:20 BST**, about 80 seconds after container start; Docker
health passed at the 113-second observation, within the existing 180-second rollout limit.
There were no restarts or OOM failures. The intentional shutdown/startup period is an observation
gap, not healthy traffic. No backup, restore, forced training, policy change or push was performed.

The fresh post-start snapshot preserved cash, all three position identities/quantities, season 61,
profile, permissions, skill versions, 55% coverage revision 2, separate Coach 70% and the 1,000-row
training window. Manipulation v1 remained active, Entry collecting proof, Sizing candidate-testing
and Exit suspended. Seven workers ran, the ledger audit verified, authentication was enforced and
served UI assets matched the verified package. Startup logs contained no warnings/errors in the
bounded read. Both the restored and subsequent naturally published models, with five observed
unique native skill artifacts each, passed bounded primary-key payload verification.

By **05:56 BST**, one natural fit/publication had completed without a trainer error. Its training
event and all six proof events were durable, with indices 0–6 and a maximum collection delay of
4.52 seconds. The backlog and diagnostic queue were empty at the closing snapshot; acknowledgement
age was 53.65 seconds. Dashboard refresh recovered to 6.76 seconds old. Optional incident cleanup
completed and AI-audit cleanup made committed progress; subsequent budget deferrals remained
explicit, rather than being reported as successful empty cleanup.

The startup-filtered diagnostic read returned two consecutive intervals (sequences 1–2), covering
138.26 seconds and 13,629 enqueued events, with no reported pipeline expiry, shedding, recording
gaps or record loss in that sample. Peak queue/overall/critical lag was 926 / 7.87 / 5.16 seconds.
The initial partial startup interval was outside that query, and the fixed-end unsaved tail was
6.82 seconds. This is a short, unmatched startup/warm-up sample, not sustained-burst acceptance.

The unchanged six-hour acceptance window ends at **11:54:20 BST on 24 September**. Workspace
headroom remained only about 5.01 GiB, just above the existing emergency floor; projected 24-hour
headroom, sustained retention recovery and burst comparisons remain unverified. Full main-database
integrity and a full restore rehearsal also remain unverified. The corrected release is deployed
and initial checks passed; these observations do not establish community or long-term acceptance.

### Assessment handoff and retention-cost candidate — 24 September 2026

Further investigation identified two reproducible mechanisms. A synchronous optional Shadow
assessment save could block the event loop while waiting for the SQLite writer. Separately, the
history controller treated transaction exit as row-dependent execution, so a fixed slow commit
could repeatedly halve deletion chunks without shortening that fixed cost. These are specific
findings, not proof that they explain every live burst. In one coherent live incident, a 4.05-second
persistence span contained about 0.074 seconds of worker execution and 3.96 seconds of resume
delay. The exact synchronous work responsible for that incident remains unproven. Earlier live
retention debt was still increasing; passing tests cannot overturn that observation.

The candidate moves assessment persistence onto the existing joined-worker mechanism and owns
both commit and pending-outcome registration through cancellation. Same-token market handling
settles that handoff before outcome dispatch, keeping the original observation timestamp. Failed
saves register no outcome. Short memory locks protect pending-map snapshots and updates; no such
lock spans SQL or an await. Settings preparation waits for post-inference assessment work and
fails closed if it does not settle. Optional qualification/incident workers are joined at shutdown.
The serial market worker can still wait for a same-token save; this change removes the global
event-loop block, not all database contention.

Cleanup now measures statement execution/CPU separately from transaction exit and reports only
committed row counts. Shrinking responds to execution cost; growth still requires the complete
transaction to be fast. Existing per-category limits, rotation, deadlines, pressure checks and
SQLite durability remain unchanged. A one-row chunk does not grow while commits remain slow;
it can recover under the existing growth rule when the whole transaction becomes fast again.
Bounded feature/assessment and capacity dispatch/worker/resume timings add attribution without
new provider requests or larger diagnostic records. An initial payload-size regression was found
and corrected with compact optional fields; the final interval/event byte-limit tests pass.

Cancellation, repeated cancellation, failed saves, same-token due ticks, mode changes, shutdown,
restart, Settings readiness/timeout, rollback, equal timestamps, category fairness, depleted
budgets and chunk recovery were checked after the relevant stage. The complete backend run
passed **3,335 cases in 164 modules**. An existing simulated-clock fixture needed the newly used
thread CPU clock; its deadline assertions were unchanged, and the full affected group was rerun.
Application source remained identical across all groups. Strict typing passed for **56 source
files**, with lint/formatting passing for **221 files**. All **537 frontend cases in 27 modules**,
frontend lint/type checks and the production build passed. Its nine assets exactly match the
preceding deployed assets. Existing dependency deprecation, Fast Refresh and bundle-size warnings
remain; no unrelated UI changes were made.

The identical small before/after fixtures produced the same saved assessment digest. Under an
injected 350 ms writer hold, median unrelated-worker resume delay fell from 330.38 ms to 0.26 ms.
Under an injected 65 ms transaction-exit delay, six retention passes deleted 300 rows instead of
97; median throughput was about 718 versus 246 rows/second. These are three-repeat mechanism
experiments on disposable tmpfs, with one CPU, blocked networking and no production data mount.
They do not measure real fsync latency or establish production retention velocity.

No persistence batch split, retention cursor, learning/trading policy change, schema migration,
new provider demand, season reset or frozen-study activation is included. Thirty learning,
provider and paper-broker source files match the preceding deployed build. Larger architectural
changes remain conditional on measured need. The candidate remains local until separately
authorized rollout; a new six-hour burst/recovery review and sustainable retention/headroom
evidence are required before recommending unattended community use.

The mixed-path rehearsal then exposed a priority-transition edge in the undeployed candidate:
newer ticks could be admitted as critical after an assessment registered, while older ticks for
that token retained candidate priority in the queue or prefetched batch. The unchanged chronology
guard correctly rejected those older ticks; the avoidable loss was still a regression to fix.
The two initial candidate trials included two reordered ticks, and four traced follow-ups included
one trial with 33. These failed-edge observations are retained, not excluded from the comparison.

The correction refreshes that token's queued priority once after successful registration and
rechecks the bounded prefetched batch before selecting newer arrivals. It preserves original
sequence numbers, season admission flags, queue receipts and persistence-before-processing;
genuinely older evidence is still rejected. Only an empty-to-pending transition triggers the
refresh. Failed or duplicate registration grants no new authority or repeated promotion.
The deterministic pre-correction regression reproduced the ordering loss, and all **117 focused
cases** passed after correction, including season boundaries and cancellation. The fresh full
backend run subsequently passed **3,340 cases across 165 modules** for this additional source
change; the 3,335-case result above belongs to its predecessor.

Four corrected replay trials each processed all 3,200 events, with zero shedding, expiry,
chronology rejection or duplicate receipt; all kept one saved invalid assessment and its pending
outcome. The replay included ordinary traffic, a burst and continuing ordinary recovery traffic,
snapshots, actual feature/candidate processing, cleanup and a contended optional save. It had
no held-position workload or completed paper fills. Protected AI-tick p95 ranged from
118–237 ms versus 194–268 ms in the four traced baseline trials;
event-loop maxima were 30–220 ms versus 245–261 ms. Shared-host variability remains substantial.
The same 30,000-row disposable fixture and scheduled trace were used, with networking blocked
and no attempted RPC in these exercised paths. It did not contain mature training/publication,
real provider replies, production-size history or realistic physical disk latency.

Retention advancement remained similar: about 1.10–1.30 seconds of the fixture's old timestamp
range over eight seconds, with debt still increasing in both builds. This is **not a sustainability
pass**. DB/WAL physical sizes were identical across those trials, and freed pages were reusable.
Corrected-process peak RSS reached about 91 MiB versus 86 MiB for the baseline; these short
repeated-start high-water measurements cannot establish memory stability or a leak. A separate
transition-cost probe measured about 14 ms median CPU for a 10,000-event queue and 124 ms at the
configured maximum of 100,000. This work occurs once per new pending token, not per event. The
empty-span timing probe added about 19 microseconds per enabled feature/assessment pair; these
small probes are attribution evidence, not a whole-app throughput guarantee.

Final validation also passed strict typing across 56 source files and lint/format checks across
222 Python files. All 236 frozen backend/test input hashes still matched after the final suite.
The locally built v1.10.11 candidate passed installed-package verification of 58 backend/resource
files, nine frontend assets and the README. Disposable first-start, Settings-ready restart and
Settings-cancellation restart rehearsals preserved schema 16 and their synthetic journals.
The 537-case frontend validation and unchanged asset hashes remain applicable. Existing
dependency, Fast Refresh and bundle-size warnings remain documented above.

This completes local candidate implementation and regression validation. The live service was
not updated or restarted during this work, and nothing was pushed or released. Production-scale
combined replay, sustained retention recovery, long-term memory/storage headroom and the next
six-hour runtime acceptance remain unverified. Main-database integrity and a full backup restore
were not exercised. These limits prevent an unconditional long-term/community readiness claim.

### Assessment handoff live rollout — 24 September 2026

The user subsequently authorized deployment of the locally validated candidate. The first
attempt stopped before Settings preparation because diagnostic writes had not settled. On retry,
a new training/proof group was also allowed to save naturally. The unchanged guard then verified
idle training, an empty publication backlog and zero queued diagnostic writes, both before
preparation and after Settings reached Ready. No pressure guard was bypassed.

The same data volume was retained, shutdown completed cleanly, and the validated performance
candidate started on schema 16. Container startup was at 08:56:19 UTC; application startup
completed at 08:57:36 UTC. Docker health was confirmed about 114 seconds after replacement.
The slow startup included transient failed health probes, but there were no restarts or OOM
events and startup completed within the existing 180-second rollout limit.

All seven workers, Settings completion, authentication and served asset hashes passed. Season
61, cash and all three position identities matched the prepared snapshot. Skill activation,
permissions, 55% coverage revision 2, separate Coach 70%, and the 1,000-observation training
window were preserved. The paper ledger audit passed. Manipulation v1 remained active; Entry
was collecting proof, Sizing was candidate-testing and Exit remained suspended.

One natural training/publication cycle completed. Bounded primary-key reads verified the saved
learning model and five observed unique skill artifacts, including inline and external payload
digests. The saved diagnostic group contained the training event and all six proof events with
original indices 0–6; maximum collection delay was 4.41 seconds. The initial bounded history
read contained one complete 60.02-second interval, with no sequence holes or recording flags,
and a 20.83-second unsaved tail at its fixed end. Its peaks were queue 274, overall lag 2.24
seconds and critical lag 1.92 seconds, with no expiry or shedding. This is startup evidence,
not a sustained burst comparison.

At the closing 08:59:58 UTC read, all workers remained running, the refreshed dashboard was
6.17 seconds old and diagnostics acknowledgement was 61.08 seconds old. The publication backlog
and diagnostic write queue were empty, with zero reported diagnostic record loss. The short
pipeline window reported zero expiry/shedding, queue 88 and critical lag 0.57 seconds.
Earlier immutable history and its failures were not reset or reclassified.

The fresh six-hour acceptance window ends at 14:57:36 UTC (15:57:36 BST), with enrollment warm-up
and the intentional upgrade gap identified separately. Initial storage measurements still
reported cleanup needed; no new retention-boundary measurement was yet available. Sustained
retention catch-up, production-scale performance and long-term storage/memory stability remain
unverified. No release was pushed and no new follow-up schedule was created. The README's rollout
status was updated after deployment; application source and the tested image were unchanged.

### SQLite work reduction candidate — 24 September 2026

The subsequent review did not establish sustained runtime acceptance. In the earlier
unconfounded retention sample, about 84 minutes of wall time advanced the retained boundary
by about 68 minutes. Debt increased rather than recovering. A later large-copy experiment
shared the host's storage and overlapped severe pressure; that period cannot establish a
causal before/after comparison. Significant pressure also preceded the experiment. Tests and
fresh snapshots do not erase recording gaps or missing intervals.

The next local candidate makes three limited changes:

- Maintenance capacity reads distinguish lock admission, connection setup, SQL/read work,
  restoration and deferral markers in a bounded optional capacity sample. Dispatch,
  worker CPU/wall time and coroutine resumption remain separate. The original absolute
  deadline, progress handler, retry pacing and pressure guards are preserved.
- Budget deletion avoids the second newest-cohort count for chunks strictly older than the
  protected timestamp. A chunk reaching that timestamp still uses the exact identifier
  tie-break. The boundary is selected inside each transaction; no cross-transaction cursor
  or schema change is introduced. Ordinary age-based pruning retains its existing rules.
- Event batches of at least 32 rows use statements of at most 64 rows, with inserted IDs
  returned by SQLite. All statements remain inside the original single atomic transaction.
  Smaller batches use single-row statements. A statement boundary is not a commit, priority
  handoff or permission to process undurable events. Durability pragmas are unchanged.

The first disposable retention comparison used the same 30,000 rows and indexes for each
variant. Ordinary 50-row deletions fell from approximately 122,000 to 62,000 SQLite VM steps.
The exact deletion set was unchanged for unique timestamps, groups of ties, all-equal
timestamps, insufficient retained population and near-boundary chunks. Large all-tied
populations remain expensive; this change does not claim to solve that worst case.

Targeted checks passed for maintenance cancellation/admission and exceptional restoration,
retention ties/late inserts/restarts/protected records, event deduplication, later-statement
rollback, priority handoff and season boundaries. Isolated CPU/SQLite results do not prove
real-disk latency or long-run sustainability.

The first full regression run caught a worst-case compressed diagnostic byte-cap overflow.
The candidate was corrected to retain capacity detail as its own finite optional slow-work
lane, including whether it was the initial or final read, rather than enlarging the storage
sample. The recorder's byte limits, queues, cadence and training/proof priority were not
increased. That failed test belongs to the intermediate candidate and is retained in the
private evidence; final validation must cover the corrected source.

Only database operations and observational diagnostics changed in application source.
Learning, qualification, Champion governance, broker rules, provider code, schema and learner
generation are unchanged. No additional RPC demand is introduced. Production-scale combined
replay and restore/integrity work require isolated storage or an agreed maintenance window;
limiting container CPU/RAM does not isolate disk traffic. A clean live acceptance window and
retention recovery remain required. This candidate has not been deployed or released.

The final isolated comparison copied the same immutable 30,000-row database before each
trial, alternated baseline/candidate order and exercised both idle and competing Python work.
For 250-event batches, median idle persistence CPU fell from 22.22 to 16.18 milliseconds;
64-event batches fell from 5.47 to 3.69 milliseconds. Small batches retain the original path.
Some elapsed-time maxima worsened amid host variability; this is evidence of reduced work,
not a universal latency bound. A separate process-kill rehearsal verified that termination
mid-batch left no partial committed batch, while termination after commit preserved all rows.
These used disposable databases with WAL and full synchronous durability, not the live database.

The combined comparison used two trials per variant, each with the same 9,500-event trace:
15 seconds at 100 events/second, five seconds at 800/second, then 40 seconds at 100/second.
All four trials processed every event without shedding, expiry, reordering or duplicate queue
receipts; handled identities matched exactly and no provider request was attempted. Both
builds reduced retention debt in this fixture. Baseline debt reductions were 33.98/35.49
seconds; candidate reductions were 31.49/35.48 seconds. Candidate critical-lag p95 ranged
28–83 milliseconds versus 34–54 milliseconds for baseline, with overlapping maxima. Candidate
CPU and peak RSS were slightly higher in these short trials. These mixed results do not prove
a whole-application speed or memory improvement. The memory-backed fixture lacks production
database size, physical disk latency, held positions, mature training/publication and real
provider behavior; its age-pruning recovery also does not prove the budget-selection gain
resolves the production backlog.

Final validation passed all 3,383 backend cases in 168 modules against frozen source, all
537 frontend cases in 27 modules, strict backend typing across 56 files, lint/format checks
across 225 Python files, and frontend lint/type/build checks. Existing dependency deprecation,
Fast Refresh and bundle-size warnings remain; they were not suppressed. The installed local
v1.10.11 image verified 58 backend/resource files, nine frontend assets, the README and the
unchanged runtime dependency inventory. Disposable first-start, Settings-ready restart and
Settings-cancellation restart rehearsals preserved schema 16 and synthetic journals. No live
volume was mounted. This is not a full production database migration, integrity scan or restore.

At the closing read on 24 September at 12:43 UTC, the preceding performance build and boot
were still running, with all seven workers, Docker healthy, zero restarts/OOM and an empty
publication backlog. Current critical lag was 0.015 seconds and queue depth was 174. The latest
five-minute counters showed zero expiry/shedding, but diagnostics acknowledgement was 193
seconds old. Since boot, nine optional detail events and one queued interval had been lost;
no training/proof loss was reported. A prior check during this work had shown severe candidate
loss. These snapshots are not equivalent traffic cohorts, local checks shared the host, and
no full-window publication/continuity audit was performed here. The later quiet sample does
not erase the earlier pressure or delayed diagnostics, and cannot demonstrate an improvement
from this undeployed candidate.

Local implementation and regression/package validation are complete. The candidate was not
deployed and nothing was pushed. Representative production-scale burst/recovery evidence,
long-run memory/storage behavior and clean runtime acceptance remain open. The current
shared-storage constraint prevents another heavy production-copy test while live traffic runs;
independent test storage or an agreed maintenance window is needed for that route. The frozen
studies, live settings, learning/trading rules, proof gates and permissions remain unchanged.

### SQLite work reduction rollout — 24 September 2026

Following explicit deployment authorization, the candidate passed the unchanged rollout
guards. Pending training/proof groups were allowed to save naturally. A new training job
started between the first readiness check and preparation, so the first upgrade attempt
stopped before any mutation. The retry waited for that work to settle; no guard was bypassed.
The isolated rollout-guard checks also passed all 26 cases, including missing, contradictory
and incorrectly typed publication counters.

Settings reached Ready with three positions in season 61, and shutdown completed cleanly.
The same data volume was retained. The verified image started at 12:52:01 UTC; application
startup completed at 12:53:26 UTC. Docker health passed at about 113 seconds after replacement,
inside the existing 180-second guard, with no restart or OOM. Transient failed health probes
during startup were preserved in the evidence. No startup traceback or error was observed.

Post-start checks verified the new diagnostic build/boot, all seven workers, Settings
completion, authentication, served asset hashes and the paper execution audit. Cash, the three
position identities and units, season, profile, permissions, active Manipulation v1 and other
skill states matched the prepared snapshot. Coverage 55% revision 2, separate Coach 70%, the
1,000-observation training window and schema 16 were preserved. Source and test hashes remained
identical to the validated candidate; only rollout status documentation was subsequently updated.

One natural training/publication cycle completed by 12:54:47 UTC. Bounded primary-key reads
verified the saved learning model and all five observed unique skill artifact payloads,
including the external XGBoost payload. Its saved group contained the training event and six
proof events, with original indices 0–6 and a maximum collection delay of 4.51 seconds.
This verifies one normal post-start publication, not repeated burst/overflow recovery.

A fixed-end diagnostic read at 12:57:11 UTC returned three consecutive complete intervals
(sequence 1–3), covering 202.78 seconds and 32,936 enqueued events. There was no reported
shedding, expiry, sequence hole or recording-gap flag in those intervals. Peaks were queue
1,042, overall lag 8.27 seconds and critical lag 4.04 seconds; the longest interval was 75.52
seconds. A separate bounded overlap read recovered sequence 0, correctly marked as a partial
startup interval; it is not steady traffic. The fixed-end read still had a 12.34-second unsaved
tail. Both page streams exhausted their bounded ranges; this is only a short startup sample.

The dashboard recovered from its idle cache to 6.11 seconds old after an explicit request.
At that 12:56 UTC check, diagnostics acknowledgement was 77 seconds old and one diagnostic
write was queued; the publication backlog was empty and no diagnostic record loss was
reported. Those delayed/unsaved observations must not be described as continuously healthy
recording. Initial retention evidence lacked an oldest-history timestamp, so retention
velocity and catch-up cannot yet be assessed.

At the final 12:58:40 UTC check, the diagnostic write queue and publication backlog were empty,
acknowledgement age had recovered to 17.24 seconds, and no diagnostic loss was reported.
The refreshed dashboard was 6.26 seconds old. All workers and the paper ledger check passed;
the recent pipeline counters still reported zero expiry/shedding. Current queue depth was
934, overall lag 4.31 seconds and critical lag 1.10 seconds. This recovery is encouraging
initial evidence, not a matched-load comparison or a sustained retention result.

The fresh six-hour window ends at 18:53:26 UTC (19:53:26 BST) on 24 September. Its criteria
remain unchanged, with the upgrade gap and enrollment warm-up identified separately. The
app is updated and initial rollout verification passed; sustained priority responsiveness,
retention recovery and long-run memory/storage readiness remain unverified. No release was
pushed, no new schedule was created, and no full database scan or restore was performed.

### Storage status and save safety — 24 September 2026

This subsequent local polish does not change the deployed SQLite-work candidate or its runtime
acceptance window. The live storage budget and retention setting were not changed. No cleanup,
learning, trading, proof, provider or schema rule was altered, and nothing was deployed or pushed.

The storage card now shows capacity and raw-history measurement ages separately. An overdue
history sample says it was behind target at its recorded check; it does not imply positive
catch-up velocity. Missing, invalid, future and inconsistent timestamps remain unavailable or
explicitly uncertain. Empty raw history is reported only with a valid completed history check.
A failed capacity refresh remains unknown even while a retry is active or a policy save succeeds.
The live-data budget is described as a soft cleanup target, separate from physical allocation,
reusable pages, the WAL and protected records. Raising it is not presented as a throughput fix.

Cached dashboard responses now pair the latest in-memory capacity fields with that sample's
measurement timestamp. This requires no new SQL, scan, polling or provider request and does not
mutate the cached response. A policy edit preserves both original measurement timestamps.

Browser saves carry a storage-policy revision, checked inside the existing serialized Settings
mutation boundary. Both policy values and their revision commit atomically in the existing
settings table; a no-op does not advance it. Repeated request cancellation retains ownership
until the committed policy and in-memory values agree. Stale edits receive a conflict without
silently overwriting another browser's save. Drafts survive conflicts and uncertain requests;
an acknowledged response survives an older dashboard snapshot. Failed refreshes are separate
from failed saves. Fractional existing budgets are preserved in retention-only edits.

Compatibility is deliberately limited: older API clients may still omit the revision and use
their existing unconditional-save behavior. Such actual changes advance the revision for new
clients. New UI code does not silently fall back to an unguarded save when a server omits or
returns an invalid revision. Database restore/rollback and external edits are not a distributed
concurrency protocol; this guard covers normal saves through the current application.

Stage checks passed 23 backend presentation/maintenance cases, 110 storage/API/security/upgrade
cases, then 251 affected storage, retention, snapshot, upgrade and learning-handoff cases.
These runs overlap and must not be added as a unique-test total. Strict backend typing passed
across 58 source files; lint and format checks passed across 227 Python files. The full backend
suite was not rerun for this narrow follow-up; the preceding complete release run remains
separate evidence for the earlier source.

The complete frontend run covered 563 cases. It found stale test expectations in the new form
selectors and one old cleanup message; correcting those expectations required no behavior
change. All 171 cases in the two affected modules then passed. Three further tests cover just
before, exactly at and just after the retention-age boundary; the final time/presentation run
passed all 25 cases. Together the complete run and affected-module reruns covered all 566
frontend cases present at that stage. Final frontend lint, strict type checks and production build passed. Existing
dependency deprecation, Fast Refresh and bundle-size warnings remain visible.

A synthetic, static render of the actual storage card/form and current stylesheet was visually
checked at 320- and 390-pixel phone widths and a 1,200-pixel desktop width. It used no live data
or live settings endpoint. The tests cover duplicate submission, concurrent edits, failed commit,
restart, repeated cancellation, uncertain response, malformed acknowledgement, old snapshots,
unknown/future clocks, and preservation of an existing fractional budget. Private evidence and
temporary browser artifacts remain excluded from Git and Docker build context.

Offline test containers had bounded resources, disabled networking and no live volume mounts.
They shared host CPU, so this period must not be treated as a controlled runtime-performance
comparison. A final read-only Docker inspection confirmed the preceding deployed image was
still running and healthy with zero restarts. This polish does not demonstrate improved burst
throughput or sustainable retention. The existing runtime observation and release gates remain
open; no budget increase or heavier storage experiment was performed.

#### Follow-up edge review

A further isolated check passed 19 backend and 49 frontend cases. New regression coverage
verifies that changing a policy and then restoring its old values does not make an obsolete
revision valid; cancellation combined with a failed commit rolls back and releases ownership;
a delayed save acknowledgement cannot replace a newer browser policy; a lost response can be
reconciled without another write; and blank, fractional or out-of-range inputs cannot bypass
the relevant bounds through direct submission. Existing clock, conflict, restart and upgrade
cases also passed. Only tests and this validation record changed: application source and the
previous successful build remained unchanged. No live request, settings mutation, deployment
or release was performed. Runtime retention acceptance remains separate and pending.

### Storage polish deployment — 24 September 2026

The subsequent authorized rollout deployed the storage presentation and save-safety changes
through Settings preparation. The final frozen source passed all 3,396 backend cases across
170 modules and all 574 frontend cases across 29 modules. Backend lint/format, frontend
lint/type/build, and the strict backend typing result for the identical source passed. The
existing dependency deprecation, Fast Refresh and bundle-size warnings remain. Installed and
source package hashes, all nine built frontend files and the audited runtime dependency
inventory matched. Disposable offline package rehearsals passed initial startup, prepared
upgrade/restart and cancellation/restart, including saved storage policy/revision persistence
and rejection of a stale save. The rollout guard passed 26 isolated edge cases.

An initial upgrade attempt stopped before preparation because diagnostic writes were pending.
They drained naturally; fresh checks before preparation and after Ready then passed. The app
shut down cleanly and reused its existing data volume without a backup restore or schema change.
Initialization took about 82 seconds; Docker temporarily reported unhealthy before recovering
within the unchanged 180-second startup guard (healthy at the 113-second poll). There was no
container restart or OOM. Settings recorded completion of the same prepared operation.

Deployed image: `signal-arcade:v1.10.11-storage-polish-20260924`.
Image ID: `sha256:82d356f3129f153fcbe458ac2a8dd3c87d5ccb639f1dfb77545be6c8f21e2936`.
Diagnostic build: `d004c684f9e25bb8927b7d72a90421eb824c51c3edb03e7d1b75b09228923171`.
Application startup completed at 14:30:20 UTC; schema remains 16 and version remains 1.10.11.
Authenticated live asset hashes matched the verified image; unauthenticated snapshot access
was rejected and the bounded history/results/maintenance reads succeeded.

The 14:31:02 UTC read verified seven running workers, an execution audit with no issues and
unchanged cash, all three position identities, season 61, permissions and active Manipulation
Champion. Coverage stayed 55% revision 2, Coach 70%, and the training window 1,000. Storage
remained 16 GiB / 24 hours with initial policy revision 0. The snapshot was 1.07 seconds old,
queue 26, overall/critical lag 0.026/0.031 seconds, diagnostics acknowledgement 22.30 seconds
old, and both diagnostic and publication queues empty. No post-start pipeline expiry/shedding
or diagnostic record loss was reported in this short initial sample.

One natural training publication was durably recorded with its training event and all six
proof events, original group indices 0–6 and maximum collection delay 1.84 seconds. Bounded
primary-key reads verified its saved learning model and the five observed unique skill
artifact payloads, including external XGBoost bytes. The first diagnostic interval overlaps
startup and is explicitly partial; the first bounded history read contained no complete
post-start intervals. It cannot establish continuous or sustained healthy traffic.

This rollout improves storage reporting and save correctness, not retention throughput.
Pre-upgrade pressure and retention debt remain relevant; shared-host release tests also
confound short performance comparisons. Initial history-boundary evidence was unavailable,
so cleanup velocity was not inferred. The new uninterrupted six-hour window ends at 20:30:20
UTC (21:30:20 BST), with unchanged acceptance gates. The existing early review remains an
interim check. Long-run burst/retention acceptance, full main-database integrity and restore
rehearsal remain unverified. No GitHub push or release was performed.

The closing read at 14:33:53 UTC limits that initial result: the snapshot had recovered to
7.39 seconds old, all workers and the paper ledger still passed, but queue depth was 3,888,
overall/critical lag 20.03/0.67 seconds, and the recent pipeline view reported 10,484 candidate
expiries out of 33,870 received (30.95%), with zero capacity shedding. Diagnostics
acknowledgement was 192.78 seconds old and one write remained queued. No record loss was
reported, but this delay is not healthy continuous recording. The preceding bounded saved
read at 14:33:01 still contained no complete post-start intervals, only the previously verified
publication and other saved events. Empty interval totals must not be interpreted as zero
pipeline loss. These unmatched startup samples neither certify performance improvement nor
establish a regression caused by the storage polish. The deployment and state-preservation
checks passed; runtime pressure, diagnostic continuity and long-run retention gates remain open.

## Catch-up candidate: bounded retention and scheduling (24 September)

This candidate is local and has not replaced the storage-polish deployment. Learning recipes,
proof populations, coverage policy, Champion permissions, Coach semantics, fees and provider
demand remain unchanged. Runtime acceptance must not be inferred from the local checks below.

Capacity-reader admission failure no longer prevents independently eligible history cleanup
from receiving its ordinary bounded turn. Unknown capacity cannot authorize urgent or budget
deletion, old capacity values keep their original timestamp, and history measurements can
refresh independently. A changed storage-policy revision stops further chunks; committed
removals remain counted. Original dispatch deadlines, cancellation joins and pressure guards
remain in force.

Decision-budget cleanup now selects the timestamp boundary before resolving its exact ID ties,
using an additive non-entry descending-time index. Migration and season rotation both establish
the index; schema version remains 16. Age pruning explicitly preserves the previous descending
row-ID order within equal timestamps. Protected ENTER records remain excluded. The disposable
30,000-row comparison preserved every selected age/budget ID, with approximately 97,000 versus
16,000 SQLite VM steps for a 50-row default-budget selection. This does not measure a full
production-size index build, physical fsync or sustained retention recovery.

Training-workspace references are released by a joined worker after publication and diagnostic
capture; published objects are not cleared or mutated. A temporary, bounded major-GC observer
records count, elapsed sum, maximum and the maximum's original timestamp during reconstruction.
These are overlapping process-wide observations, not additive CPU time or proof that all live
stalls are caused by GC. Collection thresholds and GC enablement are unchanged.

Dashboard Policy-twin checks are reused only within the existing coherent synchronous response.
They are discarded on normal, exceptional and nested exits; authority and outcomes are still
evaluated normally. Alternating uncached/cached runs on 1,200 disposable observations produced
12 identical complete status payloads and reduced population checks from 3,600 to 1,200 per
response. Synthetic CPU measurements do not establish a live throughput gain.

Targeted checks cover unknown capacity, priority/deferral, settings revisions, exact retained
cohorts, late arrivals, ties, migration, season rotation, rollback, real training/publication,
workspace ownership and snapshot scope restoration. The admission-policy fixtures use a fixed
test clock; separate real worker/deadline/rollback tests retain the original budgets. Adaptive
row limits are unchanged. Final release-suite/package checks and runtime acceptance are
reported separately; production-size isolated replay and a clean complete live window remain
required before an unattended-use claim. Heavy shared-host tests are a workload confounder.

Full regression validation exposed three older test assumptions: an immediately fresh
dashboard after a coverage save, no history-category progress after an unknown capacity read,
and a worker acknowledging cancellation within 40 milliseconds. Both the unchanged baseline
and candidate reproduced the documented timestamped-cache behavior: the save was authoritative,
the blocked refresh returned the older view, and the completed refresh showed the saved policy
without changing permissions. The API test now awaits a bounded refresh and verifies its revision.
The maintenance test expects the intended independent history turn while retaining its unknown
capacity and original-timestamp assertions. Cancellation tests verify the stop flag directly and
await a bounded worker acknowledgement, then still require joined ownership and exact committed
counts. Application deadlines and priority guards were not loosened. Original failing runs and
the subsequent checks remain in private validation evidence.

The complete backend regression now passes **3,437 cases in 174 modules**, using the same
application hashes throughout the serial batches. The three test-only corrections above and
each batch's input manifest are retained. Strict backend typing passes in 58 source files;
Ruff lint and formatting pass in all 231 Python files. Version declarations remain 1.10.11.

A larger disposable upgrade rehearsal populated 120,000 decisions with 2,063-byte payloads,
including 24,000 protected ENTER records and equal-timestamp groups. All rows survived the
actual additive-index migration, schema stayed 16, and reopening reused the same index.
Migration measured 2.30 seconds wall / 0.577 seconds thread CPU at a quarter-CPU quota;
the index added 3,268,608 bytes. This is row-scale and migration-correctness evidence on tmpfs,
not cold physical-I/O or full live-database startup evidence. An initial fixture build exceeded
its five-minute bound; a phase-instrumented retry located the delay in the single enormous
fixture transaction's commit, before migration. Both attempts are retained. Building the same
history in 2,000-row committed setup chunks completed, without changing the measured migration,
assertions, application transactions, durability settings or test resource limits.

The paired mature-history rehearsal used identical 9,500-event, 60-second traces, 5,000
retained observations and 6,000 episodes, serially at a quarter-CPU quota on the shared host.
Both variants handled all events with identical handled-ID digests, monotonic accepted slots,
zero shedding/expiry, 1,187 persisted events, one saved unavailable Shadow assessment and one
pending outcome. Neither attempted a provider request. The 401 historical checkpoint expiries
were settled before each trace and stayed unavailable; no outcome was invented.

| Measured span | Before | Candidate |
| --- | ---: | ---: |
| Protected queue age p95 / maximum | 5.09 / 5.55 s | 4.76 / 5.17 s |
| Overall queue age p95 / maximum | 6.48 / 7.30 s | 7.63 / 8.94 s |
| Maximum event-loop delay | 4.00 s | 4.30 s |
| Maximum snapshot call | 2.80 s | 3.19 s |
| Retention boundary advance | 55.50 s | 52.75 s |
| Backlogged retention velocity | 0.925 | 0.879 |
| Retention debt change | +4.50 s | +7.25 s |
| Process CPU during trace | 11.19 s | 11.36 s |
| Peak RSS, including fixture setup | 1,400,270,848 bytes | 1,403,617,280 bytes |
| Final WAL size | 14,209,912 bytes | 14,209,912 bytes |

These mixed results do **not** establish an overall performance improvement or sustainable
retention. A single shared-host pair cannot prove causality or a regression, but its adverse
queue/retention results must not be hidden behind the isolated query speedup. The candidate
remains undeployed; production burst/recovery acceptance is open. This small raw-history
fixture does not exercise production-sized storage, physical fsync, natural publication or
active Champion authority. Initial baseline setup exceeded the original 360-second harness
containment limit. The retained retry added phase/stack timestamps and a 600-second outer
allowance for each variant; resource limits, the timed trace, application deadlines and all
correctness assertions stayed unchanged. Setup timestamps distinguish fixture loading and
learner restoration from measured traffic; their differing times are not a migration speedup.

Frontend regression covers **574 passing cases in 29 modules**. The initial quarter-CPU run
hit its outer 900-second harness limit and reported two failed UI tests. Review found a
recursive storage mock in the corrupt-preferences test: unrelated-key writes called the
mock again. That fixture now calls the original method and explicitly verifies unrelated
storage still works. No UI implementation changed. Fourteen complete unchanged modules
(314 cases) retain their original passing results; all 15 failed or unfinished modules
(260 cases) passed in full at a bounded half-core quota. The original focus-test assertions
and every application timeout remain unchanged. Original failures, source manifests and the
rerun's per-test JSON report are retained; this is functional validation, not a UI speed claim.

Frontend lint (zero errors), strict type checking and production build pass; the existing
Fast Refresh and bundle-size warnings remain unchanged. All nine built asset hashes exactly
match the preceding validated UI. The offline candidate package verifies its installed/source
backend files, asset bytes and unchanged audited runtime dependencies. Disposable Settings
preparation, prepared restart, cancellation and second restart pass with schema 16, the
synthetic journal and revisioned settings preserved, including rejection of a stale storage
save. No live data was mounted and no main-database restore was rehearsed.

The local image is `signal-arcade:v1.10.11-catchup-candidate-20260924`; it has **not** been
deployed or pushed. A single read-only health check at 19:37:45 UTC confirmed the preceding
storage-polish image/start, all seven workers, zero restarts/OOM, coverage 55% revision 2 and
separate Coach 70%. The old live build still reported queue 6,178 and 1,820 expiries from
78,481 received events over five minutes, with no capacity shedding in that window. Its
short current overall/critical lags (0.101/0.082 seconds) do not erase those losses or the
backlog. This shared-host validation period is confounded and is not a candidate comparison.
The implementation and local correctness checks are complete; sustained burst/retention
acceptance remains open, so this record does not recommend an unattended-release all-clear.


### Final disk-backed migration and rollout guards

A separate offline Docker volume exercised the same 120,000-decision fixture on disk-backed
storage. Actual migration took 4.50 seconds wall / 0.821 seconds thread CPU at a quarter-CPU
quota. All rows and 24,000 protected ENTER decisions remained present; schema stayed 16,
`quick_check` returned `ok`, and reopening reused the index in 0.028 seconds. The index added
3,268,608 bytes. WAL mode and FULL synchronous durability remained unchanged. No live volume
was mounted. OS caches were not evicted and the full production database was not cloned;
this is an isolated migration rehearsal, not proof of worst-case full application startup.
The existing 180-second rollout guard remains unchanged.

The first disk-fixture attempt stopped before database creation because its new empty test
volume was root-owned. Only that labelled disposable volume's ownership was corrected; the
application image and live permissions did not change. Both attempts are retained privately.
The candidate rollout's original publication safeguards pass 26 isolated cases, and 14
additional checks reject incomplete/malformed measurements and failed comparison gates.
Neither check prepares, stops or deploys the live app.

### Repeated comparison: rollout remains on hold

The predeclared four serial trials used before/candidate/candidate/before order, the same
9,500-event trace and mature-history fixture, and the same quarter-CPU limit. All four
handled every event with identical unique ID digests and monotonic accepted slots, no
shedding/expiry/reordering and no provider attempts. The unavailable Shadow assessment and
pending outcome remained intact. Persistence/critical counts ranged from 1,155 to 1,187:
this fixture makes a token protected after an asynchronously saved assessment, so the
population changes with registration timing. The priority, durability and event-worker
implementations are identical between variants; these are event counts, not proof counts. This
remaining cohort difference and shared-host contention limit causal performance claims.

| Median across two trials per variant | Before | Candidate |
| --- | ---: | ---: |
| Protected queue age p95 | 2.53 s | 2.77 s |
| Overall queue age p95 | 3.17 s | 4.43 s |
| Backlogged retention velocity | 0.917 | 0.982 |
| Retention debt change | +5.11 s | +1.06 s |
| Process CPU during trace | 11.34 s | 10.63 s |
| Peak RSS, including fixture setup | 1,403,977,728 bytes | 1,403,828,224 bytes |
| Final WAL size in every trial | 14,209,912 bytes | 14,209,912 bytes |

Both latency non-regression gates **failed**; the relative retention-velocity gate passed.
Candidate retention velocity ranged from 0.919 to 1.045, so catch-up was not consistent.
Lower CPU and improved median retention do not override the failed latency gates. Neither
these short trials nor the earlier mixed pair certify sustained recovery. The candidate
remains undeployed; no gate changed.

An initial unchanged-baseline setup exited with code 139 while periodic Python stack
dumping was active, before its timed trace. The failure and incomplete dump were retained;
its cause is unproven. One instrumentation-only retry removed periodic stack dumping while
preserving phase markers, workload, resources and assertions. All four completed trials
above belong to that retry. Failed attempts and adverse results are not discarded.

Two further bounded attribution pairs retained the same workload and resources, with
additional in-memory observations only. They are diagnostic experiments, not replacement
acceptance trials. The first observer captured persistence and GC but missed phases reported
without a context manager; the second also captured those existing phase callbacks. Its
coherent timestamps show dashboard construction owning the market boundary while market
events wait: the preceding build's longest snapshot held it for 5.07 seconds with an
overlapping 4.90-second market wait; the candidate held it for 5.42 seconds with a 5.40-second
market wait and 5.04-second heartbeat wait. Learning-display assembly accounted for 5.01
seconds of that candidate snapshot. These are overlapping wall spans, not additive CPU:
the same snapshot used 0.809 seconds of worker CPU under the quarter-core quota.

In that attribution pair, individual measured event-persistence spans peaked at about
0.094/0.104 seconds before/candidate. No generation-2 GC occurred during either timed trace;
this does not rule out reconstruction GC during real training, which this trace excludes.
The result identifies a snapshot/market-lock bottleneck in this constrained replay, without
proving the cause of every live burst or a causal regression from a particular new change.
Instrumentation, CPU throttling, shared-host load and the small fixture remain limitations.
All attribution trials preserved the event receipts, order and unavailable evidence and
attempted no provider request. None demonstrates sustained production retention recovery.

The final local correctness checks remain valid against unchanged application/test hashes.
No further application change or live update was made from these measurements. The next
required performance work is to reduce the measured learning-display work while preserving
snapshot coherence and exact evidence/authority boundaries, then repeat the unchanged
comparison and runtime acceptance gates. Moving mutable learning reads outside the lock or
caching authority conclusions would not be a safe shortcut. Community/unattended readiness
is still unproven; full database integrity and restore rehearsal remain unverified.


### Final cooperative scheduling validation — 24 September 2026

A further bounded attribution replay located synchronous market-worker callbacks lasting
1.984 and 1.698 seconds, with 0.485 and 0.424 seconds of thread CPU under the quarter-core
quota. Their timestamps match the event-loop stalls; no overlapping GC pause explains them.
An ordinary event's async fast path can complete without suspending, so processing a whole
prefetched batch can delay other ready tasks even after database work has completed. This
identifies a replay mechanism, not the cause of every live delay.

The final follow-up yields after a nominal 25-millisecond processing slice, only between
complete events, outside the market lock and after persistence. In-flight batch receipts
remain owned, and existing priority/dependency checks run after resumption. Newly urgent
work still obeys chronological ordering and finite season boundaries. Transactions, fees,
learning/trading/proof rules, unavailable outcomes, provider demand and durability are unchanged.
The slice is cooperative: a single expensive event, OS scheduling or other work can exceed it.

A broader display-reuse prototype produced mixed isolated measurements and failed its overall
queue-latency gate. Combining it with the yield also failed the three relative median gates.
Those attempts remain recorded privately. The display prototype was removed; learning.py is
byte-identical to the previously validated catch-up candidate. Only the market-worker yield
and its two regression cases are new relative to that candidate. No failed result was replaced
by a favorable-only retry and no comparison threshold was loosened.

The final four trials used before/candidate/candidate/before order, the same original preceding
source, mature fixture, 9,500-event trace and quarter-CPU limit. Every trial processed all events
with identical handled-ID digests, monotonic accepted slots, zero shedding/expiry/reordering
and zero provider attempts. All 401 historical unavailable checkpoints remained unavailable;
one saved unavailable Shadow assessment and one pending outcome remained intact. Critical and
persisted counts ranged from 1,156 to 1,187 because protection registration is asynchronous;
these are not proof counts. This cohort difference and shared-host timing limit causal claims.

| Median across two trials per variant | Before | Final candidate |
| --- | ---: | ---: |
| Protected queue age p95 | 3.246 s | 1.975 s |
| Overall queue age p95 | 4.562 s | 3.124 s |
| Backlogged retention velocity | 1.048 | 1.089 |
| Retention debt change | -2.857 s | -5.322 s |
| Maximum event-loop delay | 1.894 s | 0.329 s |
| Process CPU during trace | 10.427 s | 10.274 s |
| Peak RSS, including fixture setup | 1,401,026,560 bytes | 1,401,366,528 bytes |
| Final WAL size in every trial | 14,209,912 bytes | 14,209,912 bytes |

All three predeclared relative gates passed. Candidate loop-delay maxima were 0.374 and
0.283 seconds versus 1.789 and 1.999 seconds before. Retention velocity varied from 0.978
to 1.200: one candidate trial added 1.349 seconds of debt, while the other removed 11.993.
Consequently this is not proof of consistent catch-up or production sustainability. The trace
uses 30,000 raw rows on tmpfs, historical learning and demo route evidence; it does not exercise
full production storage, physical fsync or a natural training/publication cycle. It cannot
certify profitable trading, Champion efficacy or unattended operation.

All **3,439 backend cases in 175 modules** passed against one frozen source archive, in serial,
resource-bounded offline containers without live data. The targeted edge checks include urgent
arrivals during an ordinary batch, committed persistence before handling, exact-once receipts,
ordering and finite season boundaries. A no-yield control failed both new fairness cases,
confirming that the tests expose the original starvation mechanism. The private control's first
log matcher expected a later assertion; the retained log instead proves failure at the earlier
in-flight-batch assertion. Neither application behavior nor test assertions were weakened.

All 84 frontend input hashes and nine asset hashes match the frontend that passed 574 cases
in 29 modules plus lint, typing and build checks; no UI implementation changed in this follow-up.
The additive-index physical migration and compatibility evidence above remains applicable to
unchanged database source. Forty isolated rollout-guard cases passed, rejecting pending reports,
malformed counters, incomplete comparison evidence and failed measurements without live actions.

At this section's local-validation point, the live application remains the preceding
storage-polish build. Its read-only 22:11 UTC check showed seven workers, a verified paper
ledger and continuing training, but diagnostics were 111 seconds behind with one queued write.
An idle snapshot refreshed to 9.88 seconds old. Zero losses in that five-minute sample do not
erase earlier pressure; validation shared the host. Packaging, rollout and their actual results
are recorded separately below. A new uninterrupted six-hour window with the unchanged runtime
gates is required after any deployment. Full live-database integrity and restore rehearsal
remain unverified; no community push or schedule is authorized by these checks.


Final package verification for the cooperative-scheduling candidate also passed. Strict
backend typing checked 56 source files; lint and formatting checked 232 Python files.
The offline image verified all 58 installed/source backend files, all nine UI assets and
unchanged audited runtime dependencies. Disposable first start, Settings preparation,
prepared restart, cancellation and a second restart preserved schema 16, the synthetic
journal and revisioned settings, including stale-save rejection. No live data was mounted.
The comparison runner's complete source, including its two shared IDL resources, matches
the actual preceding storage-polish build fingerprint. README/changelog changes are recorded
separately from the immutable tested source archive. These are completed local checks;
initial deployment and sustained runtime acceptance remain separate gates.


### Cooperative scheduling live rollout — 24 September 2026

The guarded Settings update deployed the final candidate on the same data volume. The first
attempt reached Ready and stopped cleanly, but Windows PowerShell treated normal Docker log
stderr as a terminating error before the image pin changed. Its recovery restarted the
preceding image successfully. The private rollout helper now captures native output as data
and checks the actual exit status; five capture tests, seven exit-guard tests and all forty
original guard cases passed. The application source/image did not change for that correction.
Both attempts and the extra intentional restart gap are retained in private evidence.

The retry passed fresh publication guards before preparation and after Ready, clean shutdown,
Docker/HTTP health and Settings completion. Image: `signal-arcade:v1.10.11-fairness-only-candidate-20260924`;
diagnostic build: `3053630de2f69e30f486b50f70986b6a7463e13ab37e057b8b7314d0e0852583`.
The container started at 22:37:56.817 UTC and application startup completed at 22:38:51.859 UTC.
Health was observed at the 73-second poll within the unchanged 180-second guard, with zero
restarts/OOM. The extra preceding-build recovery and successful upgrade are observation gaps,
not healthy traffic. No backup restore or community push occurred.

Cash, all three position identities, season 61, risk/execution permissions and active
Manipulation v1 were preserved; the paper ledger audit verified. Coverage remains 55% revision 2,
Coach remains separately at 70%, the training window remains 1,000, and storage remains
16 GiB/24 hours at revision 0. Entry is collecting proof, Sizing v8 is candidate-testing/inactive,
Exit v1 is suspended and Coach is inconclusive. No qualification, authority, study or training
rule was relaxed. The initial current snapshot was 0.77 seconds old. Authentication and four
bounded read routes passed; the served entry-point JavaScript/CSS hashes match the package.
The asset helper initially used an unsupported Windows PowerShell parameter before issuing a
request; running the unchanged helper under its required PowerShell 7 runtime passed.

A natural training cycle completed from retained eligible history. Its training event and five
expected proof events were durably saved with original indices 0–5, expected count 6 and maximum
collection delay 48.61 seconds. The authoritative learning model and five observed unique skill
artifacts passed bounded primary-key payload-digest checks: four new native artifacts and the
retained older XGBoost payload. A retained XGBoost artifact is not a new nonlinear refit. This
single cycle does not establish repeated-publication or overflow behavior on the new boot.

At 22:42:09 UTC all seven workers ran, the ledger still verified, the queue was zero and current
overall/critical lag was 0.021/0.015 seconds. An idle snapshot refreshed to 6.16 seconds old;
diagnostic acknowledgement age was 15.52 seconds. Publication and diagnostic-write backlogs
were empty, with no reported record loss. The saved fixed-end read contained two consecutive
complete intervals (sequences 1–2), covering 121.99 seconds and 15,789 enqueued events, with no
shedding/expiry, sequence holes or recording-gap flags. Peaks were queue 437, overall lag
3.594 seconds and critical lag 0.645 seconds; longest interval was 61.88 seconds. Pagination
completed within its limits, but the final 19.03 seconds were unsaved. The startup-overlapping
partial interval is excluded. These short warm-up observations do not validate sustained bursts
or support a causal comparison with the preceding busier traffic.

Initial saved capacity was approximately 20.44 GiB live, 22.87 GiB allocated and 2.43 GiB reusable,
with about 5.06 MiB of WAL. The first history-boundary measurement was still unavailable at this
closing sample; retention velocity and debt recovery cannot be inferred. The inherited cleanup
backlog and full six-hour runtime gates remain open. The uninterrupted six-hour end is
**25 September at 04:38:51 UTC / 05:38:51 BST**. No new schedule was created. Full live-database
integrity and restore rehearsal remain unverified. Local implementation, regression and initial
rollout checks are complete; this is not an unattended-release all-clear.

### Six-hour runtime and source publication review — 25 September 2026

This read-only review used the unchanged deployed build and boot from the preceding section.
The fixed window was 24 September 22:38:51.859 UTC through 25 September 04:38:51.859 UTC.
Serial bounded pagination retained 281 complete intervals, sequences 1-281, and 2,046 events.
The interval helper initially reached its six-page cap; a separate continuation query returned
no additional eligible records. Events completed in 22 of the permitted 40 pages. There were
no sequence holes. Complete intervals cover 21,505.68 seconds; the startup-overlapping partial
interval and final 35.76 seconds before the fixed end are outside that coverage. The latter is
an interval-boundary exclusion, not evidence that reports are still unsaved at review time.
The initial ten-minute warm-up is excluded from rate-band comparisons.

**Learning, accounting and current health:** all 119 publication groups in the fixed window
contained their expected training/proof events and original indices; maximum collection delay
was 100.62 seconds. At 06:55 UTC the same image remained healthy with all seven workers,
zero restarts/OOM, no trainer error, no stale-job discards, an empty publication/write backlog
and a verified paper ledger. The current snapshot was 8.51 seconds old and diagnostics
acknowledgement was 51.47 seconds old. The current learning model and five observed unique
skill artifacts, including external XGBoost payload bytes, passed bounded primary-key digest
checks. The trainer reported 156 publications since boot; this is distinct from the 119 groups
verified within the fixed six-hour window. No training/proof diagnostic loss was reported.
Nine optional diagnostic events had been lost by the later current-health check; they must
not be presented as zero loss. Manipulation v1 remained active, Entry collecting proof,
Sizing v8 candidate-testing/inactive and Exit v1 suspended. Coverage 55% revision 2 and
separate Coach 70% were unchanged. Worker health and saved proof do not establish trading
efficacy, better returns or guaranteed future Champions.

**Retention:** 33 samples had usable original history timestamps. Between the first and last
fresh measurements, 342.81 minutes elapsed while the retained boundary advanced approximately
453.67 minutes: velocity 1.323 while backlogged. Debt fell from 21.78 to 19.93 hours overall.
Live pages fell from approximately 20.35 to 17.99 GiB and reusable pages increased from 2.52
to 4.88 GiB; the allocated database remained approximately 22.87 GiB. WAL samples reached
approximately 429.90 MiB and then plateaued. Physical file size need not shrink after deletion.
However, within the final two-hour block's available endpoints, debt rose from 19.909 to
19.933 hours and live pages rose slightly. The strict requirement for recovery in every block
therefore did not pass. Overall catch-up is supported; sustained catch-up is not yet established.
By the separate 06:54:57 UTC history measurement, debt was approximately 18.23 hours.

**Burst and diagnostic gates:** the fixed-window intervals recorded 4,361,271 enqueued events,
16,950 candidate expiries (0.389%) and zero capacity shedding. Peak overall/critical lag was
23.56/19.37 seconds. There were 51 recording gaps out of 281 intervals (18.15%), above the
predeclared comparison ceiling of 20/132 (15.15%). The longest interval was 157.33 seconds,
within the separate 170.63-second ceiling. Summed critical-lag histogram p95 remained in the
two-second bucket for both sufficiently sampled 100-200 and 200-300 events/second bands.
Candidate expiry rates were 0.254% and 0.510%, respectively, compared with 0% and 0.0669%
in the preceding-build sample. Those relative expiry gates did not pass. Critical-event mixes
differed (approximately 3.64%/4.55% now versus 5.74%/4.95% before), and traffic, provider and
host conditions were not controlled; this is not causal proof of a software regression.
The >=300 events/second band had only one current interval and is inconclusive. Histogram
p95 values are bucket bounds. The critical-lag spike still requires coherent attribution
before claiming that the burst issue is resolved.

**Headroom and limits:** free space at review was approximately 112.11 GiB on the workspace
drive and 2.52 GiB on the system drive. Both exceed the existing emergency rollout floors,
but a reliable 24-hour capacity projection remains unverified. Full main-database integrity,
full restore rehearsal and weeks/months of unattended operation remain unverified. No heavy
tests, forced training, provider requests, restart, deployment or policy changes were made.

**Source publication:** all 246 packaging-input hashes, 84 frontend-input hashes and 364
post-rollout manifest entries matched before documentation-only corrections in this review.
The unchanged application remains backed by 3,439 backend cases and the unchanged 574-case
frontend validation, plus the recorded typing, lint, packaging and restart checks. Three
legacy-encoded punctuation bytes in this document were corrected to UTF-8. README and
changelog now disclose the runtime results; these documentation edits need no live rollout.
Version declarations remain 1.10.11. The publishable-file scan found no configured credential
values or common secret formats; local credentials, databases, backups and private test evidence
remain excluded. This is a scoped scan, not a guarantee that arbitrary future files are safe.
The user must include new source/tests/docs when committing the working tree; pushing alone
does not preserve uncommitted files. Nothing was committed, pushed, tagged or released here.

The repository can be published as a tested paper-trading update with these explicit limits.
The six-hour unattended-release acceptance **did not pass in full**. Keep observation active
and investigate sustained expiry, delayed diagnostics or renewed debt growth; an unmonitored
week is not a substitute for resolving a failed gate. No future improvement or release is
implied by the passage of time alone.
