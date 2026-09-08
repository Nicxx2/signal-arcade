# v1.10.7 verification — 7 September 2026

This patch releases the checkpoint-collection and diagnostic-continuity fixes developed on
v1.10.6. The [collection review](V1_10_6_LEARNING_COLLECTION_REVIEW.md) records the investigation,
historical comparison, reproduced bugs and staged live observations. The
[changelog](../CHANGELOG.md#1107---2026-09-07) also includes the subsequent independent-review fixes.

The later [burst-performance follow-up](V1_10_7_BURST_VALIDATION.md) records a real queue overrun,
the additional reproduced costs, isolated comparisons and deployment status. Earlier healthy
snapshots below do not establish that the later burst problem was absent or permanently resolved.

## Final corrections and regression checks

The final follow-up reproduced same-season reuse of a pruned Policy episode ID and invalid clock
handling. Policy proof now requires the original reserved episode and exact entry instant. Durable
ordering compares UTC datetimes with microsecond precision rather than lexicographic timestamp
strings. Recreated journal payloads remain non-authoritative. Tests cover cache misses, restart,
equivalent timezone offsets, changed/naive clocks, first eligible reservations and corrupt records.

Entry family selection now records the exact Policy population in existing artifact parameters,
including resolved unavailable labels. Linear/XGBoost scores are compared only when both Discovery
and Policy provenance match. Legacy artifacts keep chronological waiting order. A real fitting and
publication test verifies identical frozen Policy provenance for both families despite later changes
to live evidence. This adds no database schema or strict artifact-model field.

Results and Seasons now validate copied positions against the same SQL fill snapshot and accounting
generation. Reads retry at most twice across fills, rollover or same-season currency changes, then
return a retryable response. Cancelled readers release the SQLite snapshot before another Results
scan starts, including repeated cancellation. Tests cover BUY/SELL interleavings, fees, all three
sorts, rollover, unstarted bankroll changes, cancellation, retry exhaustion and public API responses.

An isolated one-CPU fixture with **100,001 fills**, 50,000 closed trades and one open position returned
exact totals without an accounting cap. Full scans took **7.0–8.3 seconds**; subsequent same-revision
refreshes using the bounded closed-results cache took **4–35 milliseconds**. Process peak RSS was
about **71 MiB**, and the revision query used 45 SQLite VM instructions. Open values and fees are
refreshed through indexed buys. A new fill or accounting boundary requires a full rebuild. These are
synthetic timings, not a live end-to-end benchmark or proof that arbitrarily long seasons are free.

The Coach regression matrix now earns real common-forward battle wins before testing fresh crown
activation. All four skills cover both first support and replacement of an active native Champion,
then healthy, harmful, unavailable or pending health evidence and restart. The 32 lifecycle cases
passed alongside existing permission and composition tests; this stage required no further Coach
runtime change.

The final complete backend suite passed **1,045 tests**, with zero failures, errors or skips in
163.504 seconds. Ruff lint and formatting validation passed; strict mypy passed for all 38 backend
source files. The existing upstream Starlette/AnyIO deprecation remains the only suite warning.
Tests used isolated temporary data, one CPU, bounded memory, no network and no production volume.
The 70% coverage threshold, valid unknown denominators, chronology, model recipes, Baseline
boundaries and separate Champion/Coach permissions remain unchanged.

The subsequent edge-case recheck verified 168 distinct targeted cases, including nine newly added
Results cases covering repeated cache reuse with invalid historical receipts, legacy receipts,
zero/single-row limits, all sorts and changing open-position route availability. The remaining
checks covered accounting boundaries, retained Policy identity, candidate provenance, Coach
activation/health/restart, backpressure and permissions. The new test file passed Ruff lint and
format checks. No runtime source changed after the complete suite above; the nine new cases were
validated separately rather than rerunning the full suite.

The final image is
`sha256:dd4ce8be17363af6cceaf5cdcf5f2feaa2b43955b547ce439833a3a75d881b2b`.
All tested backend source hashes match. Relative to the earlier reviewed image, only `api.py`,
`database.py`, `intelligence/learning.py` and `orchestrator.py` changed. Installed dependencies and
compiled frontend files are identical. An additional isolated frontend run passed **355/355 tests**
across 28 suites, with no skipped tests. Offline empty-data startup passed. The previous schema-16
image successfully read the final image's synthetic artifact metadata and compact Policy identities.
This follow-up requires no additional schema migration. The original pre-schema-16 backup remains
necessary when rolling back to a pre-schema-16 image.

Release metadata, the frozen lockfile, 53 local README links and all gallery hashes passed checks;
97 earlier screenshot files remained unchanged. The interface bundle did not change in this final
correction, so the existing v1.10.7 gallery remains representative.

### Final local update and bounded observation

After two recovered queue readings, the local app used its maintenance flow and switched to the
final image between **17:24:57 and 17:25:22 UTC**. The data mount, season 36, Balanced profile and
separate Champion/Coach permissions were preserved. No additional schema migration or database
restore was performed; the compatible previous schema-16 image remains available for code rollback.

At **17:26:48 UTC**, all three live Results sorts and Seasons returned HTTP 200 in approximately
33–194 ms, with no internal cache metadata exposed. The Results summaries agreed on 73 closed
trades, two open positions and fee totals, with no invalid or unverified receipts.

At **17:30:54 UTC**, all seven workers were healthy, paper accounting was verified and Sizing
**Lucid Allocator v2** and Exit **Steady Trailkeeper v1** remained active with healthy monitoring.
The new boot had processed **60,312 events without drops, shedding or expiry**, published two
models without error, and recorded **107 reserve-checkpoint updates** without worker errors.
Coach remained enabled without worker errors. Its latest attempt was at **17:29:52 UTC**;
at the final snapshot it was yielding to protect market throughput.

The first post-update Linear artifact at **17:27:46 UTC** carried the new Policy-population
fingerprint. Its fitted coverage was **37.4%**; it also failed error, top-return and conservative
Policy-advantage gates. Its 228 training rows were below the unchanged 250-row XGBoost fitting
minimum. Current operational Entry coverage reached **44.8%** at the later snapshot. These are
different populations; neither implies 70% qualification or better paper returns.

Bursts still occurred: the last snapshot had queue depth 778, overall lag 3.87 seconds and critical
lag 0.143 seconds. Earlier pre-update intervals during development workloads included real shedding,
expiry and a critical-lag peak of 12.90 seconds. This is not a controlled performance comparison.
Post-update diagnostics retained the observed boundaries and recorded two omitted detail events:
two close training publications produced ten events for an eight-event buffer. The latest eight
were retained and the interval was marked `recording_gap`; both model publications remained saved.
Diagnostics resumed recording with no writer error. Exact proof remains in the main database.

The edge-case recheck sampled **17:34:51 and 17:39:24 UTC** and read ten retained intervals.
All seven workers remained healthy, paper accounting remained verified and Sizing/Exit remained
active. At the later sample, the boot had processed **155,546 events without drops, shedding or
expiry**, published four models without training errors and made **217 reserve-checkpoint updates**
without worker errors. Entry coverage was **44.8%**. Coach's worker was running without an error and
yielding to protect open positions. The intervals included overall lag up to **12.00 seconds** and
critical lag up to **4.78 seconds**; the later snapshot itself had queue depth **2,454** and critical
lag **2.65 seconds**. Diagnostics still reported two omitted detail events and no writer error;
its acknowledgement age was 96 seconds at the later sample. These observations show continued
processing and learning during bursts, not absence of latency or proof of long-term reliability.

No additional release blocker was demonstrated. Cold history scans, burst recovery, diagnostic
detail omissions and learning quality still require longer observation. These short checks do not
establish month-long reliability or guarantee an Entry Champion. Nothing was committed or pushed.

## Earlier reviewed build

The subsequent review reproduced a Coach lifecycle failure: a crowned Coach could activate without
receiving the expected ongoing health evidence. Eight regression cases failed before the fix.
The corrected path separates research/battle dependencies, fresh crown composition proof and active
health context. Tests cover all four skills, replacement of active native Champions, missing mature
receipts, pending outcomes, changed upstream context and restart. Native activation receipts remain
valid and immutable artifacts are unchanged.

Current Entry coverage now requires the correct source, Baseline and feature schema. Schema 16 adds
compact Policy identities that survive payload pruning, keep Discovery/Policy separation and stop a
later season from recycling an already-used mint into proof. Retained history is backfilled; deleted
pre-upgrade history cannot be reconstructed. Tests cover migration, pruning, repeated seasons,
restart and frozen training inputs. A full-suite check caught a legacy season-only import without a
fills table; the additive index migration now handles that case.

Candidate validation scores are compared only for matching cohorts, cutoffs, feature lists and
sample counts. Otherwise waiting cohorts are served chronologically. Native generations cannot
remove a waiting Coach proposal; the queue remains bounded and ongoing battles are preserved.

An offline 40,000-row fixture confirmed that an indexed equity boundary selects exactly the same
rows as the previous exclusion query. Representative medians were approximately 0.3–1 ms versus
11–53 ms. These are fixture timings, not a claim about live end-to-end speed. Retention limits,
maintenance deadlines, checkpoint gates and provider budgets are unchanged.

Restart re-entry guards, season totals and Results now read exact fill history. Bounded decoded
batches and indexed entry joins replace the 100,000-fill authority limit. Leaderboard selection
retains bounded top results while accumulating exact totals. Tests verify cross-page entries,
fees, win/loss counts, restart, and a read snapshot during concurrent rollover.

The complete reviewed backend suite passed **960 tests**, with zero failures, errors or skips in
145.375 seconds. Ruff lint/format passed for 90 Python files; strict mypy passed for 38 source files.
Tests ran with one CPU, bounded memory, read-only source, no network and no production data mounts.
The only suite warning was the existing upstream Starlette/AnyIO deprecation.

The repository Dockerfile built reviewed image
`sha256:d99b2c3df9430fe4a27b44dc04efd6319bec9cd3c8fe0f9db6df6be24cbd45a5`.
Source hashes matched the tested checkout. Relative to the initial image recorded below, only
`database.py`, `intelligence/learning.py`, `orchestrator.py` and `paper/broker.py` changed;
installed dependencies and compiled frontend files were byte-identical. An offline empty-data
startup passed. Backup, restore and rejection of a damaged backup were rehearsed with temporary
fixtures before the live schema upgrade.

Pre-update diagnostics captured real bursts, including a full candidate queue, expiries, delayed
snapshots and a brief critical-lag spike. Later intervals showed recovery. This period overlapped
development validation/build activity and is not a controlled before/after performance comparison.
Do not interpret passing tests or an isolated healthy reading as proof of month-long reliability.

## Reviewed local upgrade and observation

The schema-16 upgrade used the existing maintenance flow and a verified backup of the stopped
app's active database, provider settings and diagnostic history. File hashes and SQLite integrity
checks passed before the new image started. The backup remains available locally for rollback
with the matching previous image. The roughly 15 GB database made the full backup verification
slow: maintenance ran from **15:20:15 to 15:41:55 UTC**, followed by service startup. This is a real
collection gap; expired checkpoints are not reconstructed or counted as usable evidence.

The reviewed image preserved season 36, Balanced settings, the data mounts and the separate
Champion/Coach permissions. Sizing **Lucid Allocator v2** and Exit **Steady Trailkeeper v1** remained
active. Schema 16 and 2,678 compact Policy identities were verified after migration. Paper accounting
remained verified, and all seven core workers were healthy with no startup exception.

Fresh snapshots between **15:44 and 15:48 UTC** showed continued market processing and diagnostic
recording. Enrollment waited for the existing five-minute stream-continuity requirement. At
**15:48:44 UTC**, reserve collection had resumed with five checkpoint updates from one request and
no worker error. Storage cleanup had also resumed in bounded transactions. A short candidate queue
of 238 and processing lag of 2.29 seconds were observed; critical lag was 0.135 seconds. No dropped,
shed or expired events had been recorded among the 39,462 processed events in this boot.

Retained intervals also captured brief burst delays: the 15:48:30–15:49:40 interval reached a queue
peak of 865 and critical-lag maximum of 4.05 seconds, with no event losses. At **15:50:36 UTC**, the
queue was empty again, 55,995 events had been processed without drops, shedding or expiry, and the
reserve worker had saved 17 checkpoints from seven requests. All workers and paper accounting
remained healthy. Diagnostics had no dropped records or writer error. Cleanup and optional refresh
continued to yield to market work. This confirms recovery in the observed period, not freedom from
future bursts or sustained performance superiority.

Current Entry coverage was **431 / 1,000 (43.1%)**, below the unchanged 70% requirement. The latest
fitted artifacts still used the pre-upgrade cohort, with 40.9% model coverage; Linear also failed its
validation-error requirement and XGBoost had not earned its extra complexity. These readings do not
establish a new model-performance improvement. They confirm that qualification remains guarded.
Coach was healthy and waiting for additional outcomes; this production run had no qualified Coach
contribution with which to exercise the complete lifecycle. That path was verified in regressions.
No post-upgrade training publication had occurred by this final check; fresh enrolled observations
were still awaiting their required horizons. Model fitting and publication were exercised by the
isolated test suite. A longer run is needed to compare equivalent new cohorts.

## Additional edge review

A follow-up reviewed restart authority, missing versus pending evidence, retained identities,
candidate population matching, fill pagination and cleanup boundaries. Sixteen additional cases
cover Coach receipt-version mismatches with automatic support enabled or disabled, missing/invalid
join clocks, invalid fill-page limits and releasing a WAL read snapshot after early close or
malformed data. All **163 focused tests** passed, including those new cases and the existing related
regressions. Lint, formatting and diff checks passed. No additional runtime fix or restart was needed.

At **15:54:32 UTC**, the app had completed **two post-upgrade training publications** without error.
Reserve collection had saved 36 checkpoint updates, all seven workers were healthy, paper accounting
was verified and this boot had processed 86,520 events without dropping, shedding or expiry. Sizing
and Exit both reported healthy active support, with respective health coverage of 57/60 and 50/60.
Coach had no worker error and was deferring research to protect open positions.

Current Entry coverage was 43.5%; the newly fitted Linear cohort had 40.9% model coverage and still
failed its validation-error requirement. The change from 43.1% to 43.5% is a small moving-window
change, not evidence of improved prediction quality or a guarantee of future qualification.

## Scope and preserved contracts

- Checkpoints in the final 15 seconds of their original 90-second grace window gain priority
  within their evidence lane. Shared Policy/Discovery mints keep their earliest eligible deadline
  in one fetch slot. Expired clocks cannot grant priority or reopen an outcome.
- A bounded 128-entry cache skips locally invalid RPC route identities. Changed identities retry;
  transient provider/account failures and fresh cached checkpoints remain eligible.
- Brief diagnostics lock contention retries on the next five-second poll without a false dropped
  record. Cancellation releases the lock; actual failures and long gaps remain explicit. Bounded
  refresh counters use the existing separate diagnostics store and 512 MiB allowance.
- The 3:1 Policy/Discovery share, request budgets, original deadlines, valid unknown-outcome
  denominator, model recipes, 70% coverage gate and independent Champion proof are unchanged.
  The review corrections enforce the intended evidence contracts and durable identity separation.
  Baseline entry approval, executable routes, sizing limits and hard exits retain authority.
- The reviewed release uses schema 16, Baseline v1.5 and the existing feature contract. The compact
  identity migration requires a pre-upgrade backup for rollback, but no new season. Automatic
  Champion and Coach permissions remain separate.

## Initial checkpoint-only build checks (historical)

The complete backend suite passed again with v1.10.7 metadata: **905 tests**, zero failures,
errors or skips, in 95.13 seconds. It ran in an isolated container with read-only source, no
network and no production data volume.

Coverage includes deadline/expiry boundaries, lane fairness, repeated urgent failures, shared-mint
deduplication, changed context during a request, all refresh guards, invalid-identity repair and
cache bounds, transient provider failures, diagnostic readback, cancellation and real collector
exceptions. The shared-clock defect was reproduced in four cases before its earlier fix.

Ruff lint and formatting checks passed for 86 Python files. Strict mypy passed for 38 source files.
Formatting validation used a temporary LF-normalized copy to match Linux CI without rewriting
unrelated Windows working files. The test environment reported one upstream Starlette/AnyIO
deprecation warning; it did not cause a test failure.

## Initial image and local update (historical)

The repository Dockerfile built `signal-arcade:v1.10.7` successfully:
`sha256:c16e661edbee6c64a5865b5d21f030cf52b871322c9962f72ab8502e02139f34`.
Backend, installed package and OCI label all report 1.10.7. The README's version-pinned Compose
example passed `docker compose config --quiet`. The frontend rebuilt with the frozen lockfile.

Compared with the preceding tested local checkpoint-fix image, dependencies and compiled frontend
files are identical; only the backend version identifier differs. This comparison is against the
local build that already contained these fixes, not the previously published v1.10.6 release.
An isolated startup check used empty temporary storage, no network and no production volume,
and reported a healthy v1.10.7 service and database.

The local update used the app's maintenance flow and verified the same environment, data mount,
season, risk profile, Champion permission and both Coach permissions. At 13:52:58 UTC, all seven
core workers were healthy, the app reported no current degradation, paper accounting was verified,
and Sizing **Lucid Allocator v2** and Exit **Steady Trailkeeper v1** remained active. Diagnostics
was recording within its separate allowance, with no dropped records or write error. Its four
brief collection deferrals were recorded separately from data loss.

At that same snapshot, this boot had processed 48,637 market events with no dropped, shed or expired
events and an empty queue. Training had published a new model without error, and the optional
reserve worker had recorded 80 checkpoint updates from 17 requests with no worker error. Coach
had resumed review activity without an error. Entry's current executable coverage was 52.0%,
below the required 70%; it correctly remained unqualified.

## README captures

[The v1.10.7 gallery](screenshots/v1.10.7-live-2026-09-07/README.md) contains 18 new unedited
screenshots from the actual locally running app. All images were visually inspected. The capture
received 240 WebSocket frames with no page exception, failed non-authentication response or attempted
HTTP mutation. All 97 files in the older screenshot folders retained their original hashes.

The documentation helper now avoids unsupported permission overrides on plain-HTTP LAN origins
and bounds browser shutdown after the image manifest is written. These are capture-tool changes,
excluded from the runtime image; they do not change app behavior or captured figures.
A second read-only capture completed all 18 views and exited successfully through the ten-second
shutdown bound. It was kept outside the repository; the visually checked gallery was not replaced.
Release metadata, the frozen lockfile, 53 local documentation links and screenshot hashes were
checked. Local environment files remain ignored; the new screenshot folder is included by Git.

## Interpretation and follow-up

The fixes improve collection scheduling and observability. They do not establish better trading
returns, guarantee 70% usable coverage or promise an Entry Champion. Poor liquidity, fees,
unavailable routes and failed independent model proof must still block qualification.

Short live observations are not a month-long endurance test. Market bursts can still defer optional
work or expire low-priority candidates, and storage cleanup can need time to catch up. Review
diagnostic interval boundaries, coverage denominators, provider availability, active-skill health,
training publications and realized paper outcomes over a longer run. Recorded gaps remain gaps.
