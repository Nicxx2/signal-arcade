# v1.10.9 validation

This release corrects the suspended-comparison display and adds one bounded contextual Exit
family. Existing fixed Exit policies, Entry Linear/XGBoost recipes, Baseline safeguards,
permissions, 70% coverage requirements and the v1.10.8 recovery rules remain in place.

## Burst follow-up on 9 September

Isolated reproductions demonstrated four advisory read paths blocking the event loop while
waiting for the history reader, duplicate heartbeat valuation, and a completed training job
publishing despite critical traffic arriving during its fit. Further reproductions showed
repeated price-window scans, repeated Exit authority checks within one position review, repeated
Policy selection within one outcome update, and stale ordering of a newly protected mint within
an already prefetched batch.

- Advisory detail reads use one joined worker at a time. Reader-lock acquisition has a 50 ms
  limit and SQLite work has a cooperative 100 ms query deadline; the existing SQLite busy
  timeout still applies. Busy requests return a retryable response. Cancellation joins the
  worker, releases its slot and clears the reader's progress handler. Cohort changes reject
  stale Champion pages, and Results retain their accounting revision checks. These are bounded
  waits, not a hard guarantee against an operating-system or storage stall.
- Heartbeat/watchdog work values the same frozen state once and keeps both the durable mark and
  exit assessment. Standalone order processing still revalues fresh input. Future reserves,
  write failures, unavailable conversion, both venues and restart persistence remain guarded.
- Completed training rechecks pressure before and after acquiring the market boundary. One
  private job can wait within its existing 120-second validity limit. A small candidate backlog
  is allowed; urgent work, maintenance, season boundaries and in-flight batches block normal
  publication. Stale jobs are discarded and cancellation preserves the queued request. This
  cannot guarantee training progress while the critical path is persistently overloaded.
- Derived trade metrics share the existing one-second window, without extending that window or
  caching live reserve/freshness checks. Exit timing and attribution use one synchronous
  authority check and revalidate on the next review. Policy reuse covers population selection
  only within one update: health, receipts, authority, harm and suspension are recalculated.
- Prefetched events are sorted by their newly checked priority, with admission sequence retained
  within each priority. The whole queue is not rescanned. Existing urgent admission limits and
  candidate expiry/loss reporting remain unchanged.

Five alternating measured pairs followed a warm-up pair in a one-CPU offline container. Each
side produced 100 snapshots from the same 5,000 synthetic trades within an already cached window.
All serialized snapshots matched exactly. Median wall time fell from **297.7 ms to 147.5 ms**;
median thread CPU fell from **297.6 ms to 147.5 ms**. This measures cached feature snapshots,
excluding the cold-window calculation, database work and the rest of market processing.

Regression counts also demonstrate two valuations becoming one per clock update, three Exit
authority checks becoming one per combined review, and two Policy selections becoming one per
outcome update in the exercised scenarios. The focused stage suites passed 121, 185, 111, 124,
124, 251 and 126 checks respectively; these overlap and are not a unique-test total.

Retained live burst intervals did not establish one exclusive cause. Queue pressure can still
outlast a finite urgent allowance, and a newly protected event deeper in the heap is reclassified
when selected for a batch. Whole-heap reprioritisation and unlimited urgent draining were not
introduced: they need separate performance/fairness evidence before changing the queue contract.
No learning threshold, population, fee rule, model recipe or proof separation was relaxed.

The follow-up full backend run passed **1,404 tests**. A subsequent missing-configuration
correction preserves an absent cohort without consulting mutable configuration in the reader
thread; all **69 final advisory/API/accounting checks** passed after that correction. The full
frontend suite passed **368 tests across 21 files**, and TypeScript/Vite builds passed. Linux
Ruff lint and format checks passed for **117 files**, and strict mypy passed for **40 source
files**. Existing non-failing frontend and test-client notices remain. These later results
supersede the earlier release counts below for the burst follow-up.

The actual Dockerfile then built the follow-up image. Packaged backend hashes matched the
validated source; schema 16, installed dependencies and frontend assets matched the preceding
review image. An isolated disposable demo container passed health, snapshot, diagnostics,
Champion journey, Results and frontend checks before the authorised live update. A stopped-volume
backup was fully verified, and the existing data volume, settings, season, permissions and active
Sizing/Exit Champions were retained. The prior image remains available for rollback. Restoring
the backup would discard evidence collected afterwards and is not a routine rollback step.

The updated instance was observed from 09:56:45 to 10:13:43 UTC on 9 September. It processed
97,037 events with no recorded market-event shedding or expiry, completed three natural training
publications and recorded 246 reserve checkpoint updates. All seven workers were running;
database health and the paper execution audit passed, with no restart or OOM event. Sizing and
Exit remained active with healthy monitoring. Entry remained unqualified at 49.4% on its displayed
1,000-observation availability population; this is separate from fitted and independent proof.
Coach remained waiting to protect market throughput, so this observation does not establish a
new Coach research opportunity.

Twelve retained intervals covering the first 12 minutes reported a maximum queue depth of 544,
overall lag of 4.954 seconds and critical lag of 2.568 seconds. At the final observation the queue
was 5 and critical lag was 0.010 seconds. These conditions were lighter than the earlier severe
burst, with different process lifetime and collection windows. They verify live operation and
continued learning, not equivalent-load burst capacity or improved trading returns.

One diagnostic-detail drop was reported during overlapping training and cleanup. The twelve
minute records had continuous sequence numbers and interval boundaries. The affected interval
retained eight details: one training event, six proof events and one storage event, all below the
per-event size limit. This is consistent with the existing eight-event detail buffer overflowing;
that recorder code was unchanged by this follow-up. The drop count remained one at the final
observation, with recording healthy. It is an observability limitation, not evidence of a lost
market event or missing learning outcome; the precise discarded detail cannot be reconstructed.
The reported gap must remain visible. More detailed overflow classification or event prioritisation
would need a separately bounded change and record-size regression checks.

No new release blocker was identified in the exercised checks. Severe natural bursts, optional
work fairness and longer operation still require observation. README and changelog include the
follow-up; no commit, push or community image publication was performed.

## Reproduced issue and implementation

A further cancellation recheck reproduced an interrupted preparation returning a job after the
async caller had been cancelled. Joining the worker preserved the database boundary, but normal
result assignment never ran, so the learner's active-job flag could remain set. The trainer now
retains that joined result for its existing cleanup, releasing ownership and preserving a pending
retry without fitting or publishing the cancelled job. Normal service shutdown already waits for
the trainer; this correction covers forced task cancellation and reuse of the learner. Regressions
exercise repeated cancellation, a coalesced newer request, readiness returning no job, preparation
failure and cancellation during fitting. The correction changes no learning population or proof.
The full backend rerun passed **1,410 tests**, including the earlier absent-cohort correction and
all five new cancellation cases. Ruff lint/format passed for 117 files and strict mypy passed for
40 source files. Frontend source was unchanged from the completed 368-test validation.

The cancellation correction was packaged and deployed after another verified stopped-volume
backup. The image matched the tested source, with unchanged dependencies, frontend and schema.
By 10:43 UTC on 9 September, the updated process had handled 31,709 events without recorded
market shedding or expiry. All seven workers were running, Sizing and Exit were healthy and
active, the paper execution audit passed, and the season and permissions were retained. At that
observation the queue was empty, critical lag was 0.113 seconds and the rolling processing-lag
P95 bucket was 2 seconds. Diagnostics had saved six new minute records, with no new detail drop
and one deferred collection. New observations were pending; readiness checks completed, but a
new training publication was not yet due in this short run. No cancellation was injected into
the live app. These observations do not establish sustained burst capacity or long-term returns.

By 10:48:05 UTC, that same process had handled **70,593 events**, with no recorded market
shedding or expiry. Its first natural training publication completed at 10:46:55 UTC without
an error or stale-job discard, and training returned to idle. Between observations at 10:46:47
and 10:48:05, usable outcomes increased by eight and reserve checkpoint updates by thirteen.
All seven workers remained running, Sizing and Exit remained active with healthy monitoring,
and the paper execution audit passed. Entry remained unqualified at 49.1% on the displayed
1,000-observation availability population; fitted coverage and independent proof remain separate.
Coach was still waiting to protect market throughput, so research progress was not established.

Ten retained intervals from 10:36:35 to 10:47:06 UTC had continuous sequence numbers and interval
boundaries, with only the initial partial-interval flag and no new diagnostic-detail drops.
They recorded 61,045 processed events, zero shedding or expiry, a maximum queue depth of 732,
and peaks of **10.372 seconds overall lag and 6.640 seconds critical lag**. The worst interval
was 10:41:44–10:42:54 UTC; at the final observation critical lag had recovered to 0.246 seconds.
Snapshot, market-lock and learning-wait work overlapped that interval, as did host compression
of the already verified backup. This maintenance load is a confounder, not an established cause;
the first new training fit occurred later. No new release blocker was identified, but these
observations do not show that burst latency is resolved. Longer observation without audit or
backup work is still needed before attributing sustained performance changes to this build.

Champion Arena treated suspended trade support as a pause in shadow comparison. A regression
reproduced that false pause for all four skills before the fix. Suspension now changes the
influence label without stopping a valid battle readout. Learning Off, a different source,
missing artifacts, stale evidence and interrupted pairs retain their separate behaviour.

Newly completed recovery trials retain failed check names. The expandable UI shows those saved
results without inventing reasons for older trials. A failed 60-entry trial remains failed;
replacement candidates and shadow learning continue under the existing rules.

The new Exit family learns from original entry features. It must outperform both Baseline and
the existing fixed selector on the same chronological validation cohort, then earn fresh battle
and activation proof. It is allowed to remain unqualified. Its prediction is frozen before
entry-order latency and carried through the existing order/fill persistence path. Held-position
updates reuse the saved choice while rechecking current authority and context.

A follow-up edge-case regression found that a contextual contender replacing a **suspended**
Champion could reuse its battle rows for activation because no Exit skill was active on those
rows. Contextual predictions now freeze the reigning Champion identity. Activation accepts only
rows frozen while that artifact was already Champion; battle evidence remains available for the
battle, and unavailable post-crown outcomes remain in activation coverage. The versioned
activation marker rejects earlier review-build receipts without this separation. No extra query,
provider request, threshold change or per-observation state write was added.

## Edge cases covered

- All three risk-profile horizon bounds; missing, non-finite, unfamiliar and malformed context;
  corrupt payloads/digests, invalid scales and unsupported model contracts; conservative ties.
- Chronological embargo, unchanged trained parameters when only validation outcomes change,
  and unavailable validation markets staying in the denominator: 70% and 68% boundary cases.
- Constant timing cannot qualify by adding complexity. The simple fixed selector stays intact.
- Forward battle win followed by separate activation; all eight upstream skill combinations;
  Entry veto, Sizing with missing exact quotes and a Coach contender facing a contextual crown.
- Replacement of a suspended Exit Champion cannot reuse battle rows for activation, including
  after restart. Fresh post-crown proof retains unknown outcomes: 42/60 meets the 70% coverage
  gate and 41/60 does not. Earlier contextual activation markers cannot restore authority.
- Queued candidates cannot collect hidden proof before their battle. Missing mature health
  receipts count as unavailable. Suspension, revoked permission, changed policy/configuration
  and upstream activation epochs remove contextual influence.
- One-shot recovery cannot pass at 59 entries, and recovery cannot revive an older position's
  obsolete plan. Champion identity and generation are retained.
- Delayed order, restart, fill and subsequent restart retain the original plan. Legacy positions
  and damaged optional plan fields remain loadable and use Baseline timing. A held-position
  regression makes inference fail if called again and exercises 100 successful saved-plan reviews.
- Diagnostics retain all current native/Coach combinations, recovery details and optional
  fixed-reference metrics within unchanged record limits. Earlier schema-1 readers can retain
  the named optional fields; the metrics-slot schema was not changed.

## Bounded cost comparison

Five alternating measured pairs followed a warm-up pair, using the same 1,000 synthetic Policy
episodes in an offline container limited to one CPU and 2 GiB. Timing covers Exit publication
in a private training workspace, excluding storage publication and the rest of the training job.

| Exit publication work | Median wall time | Median thread CPU |
| --- | ---: | ---: |
| Existing fixed selector alone | 10.3 ms | 10.3 ms |
| Fixed selector plus contextual family | 89.6 ms | 89.6 ms |

The fixed selector's parameters, qualification and metrics were identical in each pair. Training
freeze/thaw preserved all 1,000 entry-feature records and the complete contextual artifact.
The added family costs roughly 79 ms in this synthetic comparison. It stays in the existing
private worker, uses at most five small regressions and makes no additional provider requests.
The parsed-policy cache is limited to eight entries, with a 24,000-character payload limit.
These timings do not establish live burst throughput or performance on every host.

## Upgrade, rollback and packaged smoke test

Schema 16 is unchanged. A synthetic v1.10.9 database earned a real forward activation and saved
a held position with a contextual plan. The actual v1.10.8 reference source then opened that
database, retained the position and Champion, rejected the new activation receipt and used
Baseline review timing, including a governance pass. Reopening it with v1.10.9 retained the
position and safely kept Baseline timing after the older build invalidated authority. SQLite
integrity checks passed. This checks the saved-data contract, not every possible live state.

Older builds do not implement contextual timing and may omit its optional fields when rewriting
positions. Returning to v1.10.9 must not reconstruct those choices. Keep a consistent backup and
verify current support after any rollback; restoring an older backup would discard newer evidence.

The actual Dockerfile built `signal-arcade:v1.10.9-review` successfully. An isolated demo container
used disposable data, no external network and no published ports. It served the frontend,
snapshot and diagnostics; health reported v1.10.9, a healthy database, all seven workers running
and no degraded pipeline. No production data was mounted and neither live instance was changed.

After the follow-up activation correction, the image was rebuilt and its new activation
contract, health and snapshot were checked again in an offline disposable container. All seven
workers were running, the database was healthy and restart count remained zero. The test
container was then removed. The earlier frontend, diagnostics and rollback checks above were
performed before this correction; the correction changes contextual activation proof only.

## Final checks and limits

- Full backend suite: **1,361 passed** after the activation-separation correction. The final run
  used offline temporary data with two CPUs
  and a 3 GiB memory limit. The surrounding suite covers trading, fees, Entry/Coach proof,
  cleanup, long-season accounting, cancellation, scheduling and market-burst boundaries.
- Full frontend suite: **368 passed** across 21 files. Frontend source was unchanged by the
  follow-up activation correction, so the completed frontend run remains applicable.
- Ruff lint and format check passed for all 113 Python files; strict mypy passed for 40 source
  files. Frontend lint had no errors, and TypeScript and Vite production builds passed.
- Dockerfile build, isolated health/snapshot/diagnostics/frontend smoke checks and synthetic
  downgrade/re-upgrade checks passed. The smoke container remained healthy with zero restarts
  and was removed after testing. The local review image remains available.
- Final release checks: the README Compose example parsed successfully, local documentation
  links resolved, and the validated source/test hashes remained unchanged. Both CI dependency
  audits (`pip-audit .` and `pnpm audit --prod --audit-level high`) reported no known
  vulnerabilities on 8 September 2026. Dependency versions were unchanged.
- Existing non-failing notices remain: Starlette's test-client deprecation, the EquityChart
  Fast Refresh lint warning and the optional 3D scene's bundle-size advisory.

No release blocker was found in these checks. Tests establish the exercised contracts, not
issue-free long-term operation or guaranteed improvements in trading results.

Exit evidence compares fee-inclusive checkpoint values, not a complete replay of adaptive exits.
Actual exits still depend on current signals, executable routes and Baseline safety rules. Better
checkpoint validation cannot guarantee improved realised results or a new Champion. Natural
bursts, provider outages, correlated markets and month-long operation still need observation.
No thresholds were relaxed, failed markets excluded or live performance gains inferred from tests.

README release information, Compose image tag, package versions and Docker label are v1.10.9.
The existing screenshot gallery remains explicitly labelled as its original v1.10.7 capture.
No release was published or pushed as part of this validation.

## Subsequent authorised live update

On 8 September 2026, the validated image was deployed to an existing local instance after normal
upgrade preparation and a fully verified stopped-volume backup. Environment settings, mounts,
the current season, saved learning permissions and the active Sizing/Exit Champions were retained.
Changes between the cached preflight portfolio and the fresh startup view reconciled exactly to
recorded fills before maintenance; they were not lost positions or an accounting reset.

Across roughly twelve minutes after startup, all seven workers remained running with no restart,
OOM event or application error in the bounded logs. Over 100,000 events were processed with no
recorded candidate shedding or expiry. Existing diagnostics history remained readable and new
minute records were saved. Six main UI tabs, Challenger/Coach views and a 390-pixel mobile layout
were checked without JavaScript errors, failed application requests or horizontal overflow.

The first natural training publication completed in about 4.6 seconds and created an
`exit-context-v1` Linear candidate. Its measured advantage gates did not pass, so it correctly
remained unqualified while the existing Exit Champion kept its separately verified authority.
Entry remained unqualified; the update did not bypass its coverage or performance requirements.

This short run does not establish better returns or sustained burst capacity: traffic conditions
and process counters changed across restart, and the previous run had recent candidate losses.
Host loopback requests later timed out while container-local and LAN requests succeeded; a
separate WSL loopback listener was present. No application change or infrastructure restart was
made to mask that host-specific observation.
