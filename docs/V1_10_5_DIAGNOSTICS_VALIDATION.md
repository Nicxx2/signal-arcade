# v1.10.5 diagnostics validation — 5 September 2026

Diagnostics is a separate observer. It does not feed training, change proof thresholds, request
market prices or make paper-trading decisions. The final controlled performance comparison passed;
live deployment and observation are separate checks below.

## Storage decision

The original 256 MiB proposal used smaller sample payloads. A fuller fixture with six independent
model identities, all 31 allowed proof metrics, equity, phase and operational measurements needed
2,573 compressed bytes. The old 1,792-byte record limit was insufficient; an event could also exceed
the original 1,024-byte handoff allowance. Those limits were corrected before deployment.

The implementation uses a separate **512 MiB** allowance, a 384 MiB main-file limit, a 448 MiB
pause threshold and 416 MiB resumption threshold. Input messages are bounded at 32 KiB, compressed
intervals at 3,584 bytes, compact events at 768 compressed bytes, individual queued events at
2 KiB, and queues at fixed sizes. Disk free
space below 512 MiB pauses recording. Main database budgets and schema remain unchanged.

The production schema was populated with 43,200 detailed intervals, 8,760 hourly rows, 100,000
events and 10,000 boot watermarks, using maximum-size compressed payloads. Peak owned files were
339,440,344 bytes (about 324 MiB); settled allocation was 338,358,272 bytes. Integrity was `ok`.
After 9,000 additional transactions spanning 90 simulated days, allocation remained bounded and
hourly evidence was preserved. This is accelerated storage testing with time gaps, not 90 days
of continuous real operation. Capacity runs used isolated tmpfs and no live database mount.

## Correctness and failure checks

Focused diagnostics tests cover full operational/proof payloads, round trips, duplicate
records across restarts and detail expiry, atomic rollups, histogram counts, extrema, missing
intervals, changed context, clock jumps, corrupted compressed values and invalid metric slots.
They also cover immutable bounded queues, pressure rechecks, duplicate writer ownership, shutdown
while deferred, low disk space, actual `SQLITE_FULL` rollback, read-only storage and a reader
pinning the WAL. Storage resumes after that reader closes; committed history remains intact.
Reclamation also distinguishes live pages from reusable allocated pages and makes room before
insertion reaches the main-file cap. A failed transaction rolls that reclamation back atomically.

The main database storage accounting and paper reset are tested separately from diagnostics.
Both export routes require the existing authentication. Concurrency limits, cancellation and
idempotent cleanup were checked, including a disconnect before response headers. The response's
ASGI exit path releases the slot even when a send error skips generator and background cleanup.
Enabling
diagnostics preserves the learning configuration identity. Export pagination closes each read
connection before sending the page, with explicit completion/incomplete trailers. An observer
reporting fault cannot turn an already-published model into a training failure.

The 536-case backend run had one obsolete assertion expecting the previous 3,601-bucket limit.
The buffer now allows 4,096 bounded buckets to retain a full hour despite minute boundaries.
The concurrency test was extended to 5,000 writes to verify actual rollover, then passed together
with all 35 diagnostics tests then present; the additional early-header-disconnect test and all
three export checks subsequently passed. The other 535 cases passed in the full run.
The final focused run passed 65 diagnostics, API/security, release-readiness and pipeline
concurrency checks on the deployed source. This does not replace the distinction between the
earlier full run and the later focused checks.

The frontend regression run passed all 310 cases present at that point; the final four
diagnostics cases also passed, including an additional test for a wrong device clock. TypeScript,
ESLint and backend Ruff checks passed. Mypy passed all 39 backend modules. Production UI builds
succeeded with the existing warning about the lazy 3D scene bundle size.

Twelve browser fixture views covered recording, storage pause, disabled and unavailable states at
1,440, 390 and 320 pixel widths. There were no page errors, horizontal overflow or mutations.
Screenshots were inspected, including the final 44-pixel refresh control at 320 pixels.

## Performance evidence and limitations

Tests use isolated containers with one CPU, no network and synthetic data. They exercise real
event workers, feature processing, quote arithmetic and Linear/XGBoost fitting. A labelled mint
uses the critical queue lane; this is a scheduling test, not a held-position execution test.
Main fixture databases use tmpfs; small diagnostic stores use a separate physical bind mount.

Predeclared limits are 3% paired median CPU/core-time overhead, 5% fit-time overhead,
95th-percentile latency growth no greater than the larger of 5% or 0.25 ms, at most 16 MiB added
peak RSS, identical deterministic outputs and no event loss.

The initial subprocess implementation failed memory and timing checks and was replaced with a
dedicated I/O thread. The first normal-cadence thread run preserved all outputs and had 384 KiB
additional median peak RSS; latency and fit-time checks passed, but CPU overhead measured 6.88%
and failed the 3% gate. Individual runs varied substantially, so this is not evidence of a
reliable 6.88% causal overhead, nor is it a performance pass.

Interleaved follow-ups retain their failed results. An initial harness incorrectly included its
own acknowledgement wait in core elapsed time. The corrected harness reports that wait separately;
the app's handoff never waits for disk completion. A later revision signals acknowledgement once,
instead of charging a benchmark-only polling loop to the recorder. Filesystem metadata checks
were also reduced without weakening the storage guards. A 120-pair follow-up passed individually,
but combining all 144 pairs of that revision gave 3.21% CPU overhead and failed the unchanged 3%
limit. The next revision removes a redundant per-write passive checkpoint: the existing 128-page
automatic checkpoint and periodic truncation remain, as does FULL commit durability. Its fixed
144-pair qualification run is evaluated independently because the implementation changed.
An attempted run aborted around pair 91 because its test-only acknowledgement fired before the
writer published cached status. The harness now acknowledges the published status, preserves
progress records, and reruns the full fixed comparison; that aborted run is not a pass.

The completed final comparison passed all gates across **144 AB/BA pairs**:

| Measurement | Paired median change | Limit |
| --- | ---: | ---: |
| CPU | -0.93% | <=3% |
| Core elapsed time | -1.60% | <=3% |
| Linear fit time | +1.82% | <=5% |
| XGBoost fit time | +4.84% | <=5% |

Both ordinary and critical-lane p95 checks passed. Quote checksums and model fingerprints matched;
there was no event loss. Negative timing changes are measurement variation, not a claimed speedup.
The separate normal-cadence memory measurement was 384 KiB of additional median peak RSS, below
the 16 MiB limit. The final test deliberately records once per 512 events, substantially more
often than production's one-minute collection cadence. The final implementation also includes
the live-page reclamation safeguards and cancellation cleanup described above.

Raw test artifacts and harnesses are retained in the workspace's sibling `audit/diagnostics-verification`
directory. No earlier failed run is relabelled as passing. Short controlled tests cannot establish
month-long reliability or profitable improvement; live observation remains necessary.

## Deployment status

The qualified image was deployed through the app's maintenance preparation on 5 September 2026.
Operation `bb23446c128346f09acd9a99009f283b` completed at 15:35:50 UTC and the paper engine resumed
through its existing freshness gates. The existing `/data` mount was preserved; the prior image is
retained as `signal-arcade:v1.10.5-before-diagnostics`. No community release was published.

The running image is `sha256:0a1a4dfd1151574f0d6150d1bb6b756094a1773ef8231b46fa62a374c506b393`.
The installed backend/UI fingerprint matches
`609a7b39ecafdad3592a88d6d7a878227654df4c9c49c1d795b0388f854b9eea`.
The staged image also passed an unprivileged smoke test with a read-only root filesystem.

Post-upgrade checks confirmed season 31, 400 USDC starting balance, Balanced mode, the custom
25% drawdown limit, Shadow learning and automatic season handling were preserved. Main database
schema remains 14; there were zero ledger imbalances and zero orphan fills. Artifact gate
identities and exclusions for manually reset seasons remained valid.

Actual history advanced from one interval/five events to two intervals/ten events. Diagnostics
schema is 1, SQLite integrity is `ok`, exported histograms reconcile to their counts, and all
five current skill/family summaries carry the expected build/context. The first interval records
a partial startup interval and a recording gap after one skipped diagnostic sample. That skip
count remained at one in the follow-up; the next interval has no gap flag. Initial verification
correctly rejected an empty history and then the nonzero skip count; the follow-up explicitly
accounts for this observed skip rather than presenting it as a zero-loss recording.

The authenticated live Settings card passed read-only browser checks at 1,440, 390 and 320 pixel
widths, without JavaScript errors, overflow or application mutations. The mobile screenshot was
inspected. These live checks supplement the twelve fixture views above.

### Observation still required

Before this deployment, the old build experienced substantial candidate-event shedding. A
pre-upgrade recovery check observed no further drops and a queue of 32 with about 42 ms lag at its
last sample. The new recorder was not deployed during that earlier shedding; the evidence does
not establish its cause, and these changes do not claim to fix it.

After restart, all core workers were healthy, training completed a fit and no market events had
been dropped in the initial observation. Recorded intervals nevertheless include latency spikes
(about 13.4 seconds maximum ordinary lag in the startup interval and 9.7 seconds in the next).
Diagnostics makes those spikes visible even when the current health state has recovered.
Leave the app running for a fresh multi-hour review before deciding on community readiness.
These short checks establish recording and preservation, not month-long reliability or the
absence of every performance issue.

### Follow-up edge check

A later live review found the recorder still advancing: 40 detailed intervals and two hourly
rollups were retained after about 55 minutes, using 806,016 bytes. There were eight diagnostic
skips, no queued diagnostic records and no recorder error. The latest writer duration was about
15 ms; cumulative I/O-thread CPU time was about 0.29 seconds. This CPU figure covers the writer
thread only and is not a measurement of all observer overhead.

An export at 36 intervals/90 compact events passed integrity, build/context and histogram checks.
Both hourly rollups reconciled exactly with their constituent intervals, and saved interval
sequences were contiguous. Seven skips at that earlier sample coincided with marked, longer
intervals; intermediate sampling must not be inferred from those longer summaries.

The existing 37 focused diagnostics/pipeline checks passed again. Two additional regression
cases also passed: event-boundary lock timeout preserves unconsumed pipeline counts for the next
interval, and paginated minute/event exports preserve 205 rows with equal timestamps across
multiple boots and sequences. Documentation now explicitly distinguishes diagnostic skips from
market-event losses, and describes queue maxima as sampled during event processing.
These follow-up changes are tests and documentation only; the deployed runtime was not changed
or restarted for this check.

The wider app remains an observation item: the final status had processed 624,293 events with
15,579 candidate drops since restart, a queue of 1,830 and current lag of about 1.16 seconds.
An earlier sample in this same review had about 15.9 seconds of lag. All six core workers were
alive, 16 training runs had completed, and no training error was reported. Liveness and successful
training do not clear the recurring market-pressure issue or establish that diagnostics caused
it. Review the retained latency, expiry/shedding and workload evidence before community release.
