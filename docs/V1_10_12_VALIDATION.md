# v1.10.12 validation

## Current status — 27 September 2026

v1.10.12 contains the validated checkpoint-selection, diagnostic handoff, stream recovery and
dashboard reconnection changes. The latest reference build was deployed through the guarded
Settings path on 27 September, including the notification-authentication fix. Local regression,
package, restart, live notification and preserved-state checks passed, as recorded below.

The final source passed 3,540 backend cases, strict typing and lint/format checks. The 577-case
frontend result was reused after verifying unchanged inputs and assets, with additional real-browser
integration checks. The later training-copy experiment failed its predeclared performance gate;
the preceding validated source was restored exactly. Neither that experiment nor the earlier
rejected scheduling experiment is included in the release.

The latest bounded runtime review retained 16 complete training/proof groups and verified the
paper ledger and observed artifact payloads, but also found candidate expiry, five recording
gaps and one optional diagnostic-detail loss. Sustained burst handling, retention sustainability
and diagnostic continuity remain open acceptance requirements. This supports publishing the
tested fixes with disclosed limits, not a weeks/months unattended-reliability claim.

The dated sections below preserve what was known at each checkpoint. Earlier local-only states
and rollout windows are historical; use the latest deployment and review for the current baseline.

## Initial candidate status — 26 September 2026

At this earlier checkpoint, the candidate was not deployed, tagged or released and the public
and local live release remained v1.10.11. Local regression and package validation had passed.
It was ready for a separately authorized guarded rollout; live runtime acceptance had not started.
No schema, learner-generation, trading-rule, proof-gate or provider-budget change is included.

## Measured mechanism and selected change

A bounded historical fixture contained 5,164 Discovery observations, 6,000 evidence episodes,
256 learning models, 512 skill artifacts and 20 skill states. An initial fixture left governance
inactive; its governance timings were rejected as unrepresentative and the fixture was corrected.
With the retained context enabled, a profiled 20-mint checkpoint pass performed 20 identical Policy
population selections. Selection used about 2.75 seconds of the 3.47-second profiled operation.
Profiling overhead means those durations are not live latency estimates.

The candidate reuses only population selection during that one synchronous pass, invalidating it
on population changes and pruning. It still applies all updates and immediate governance in order.
No new await, lock release, deadline, transaction split or cached authority decision is introduced.
Additional heartbeat and publication-wait measurements retain the existing diagnostic byte caps.

## Predeclared paired comparison

Four serial runs used baseline/candidate/candidate/baseline order, identical retained evidence,
fixed observation timestamps, 20 mints including an unavailable quote, one CPU and 3 GiB memory.
The disposable container had no network or live-data mount. Source manifests were verified before
and after the runs. All trials are retained privately; no fixture or private evidence is published.

| Metric | Baseline median | Candidate median |
| --- | ---: | ---: |
| Checkpoint worker elapsed | 1.878 s | 0.912 s |
| Checkpoint worker CPU | 1.812 s | 0.834 s |
| Protected work waiting behind the pass | 1.879 s | 0.913 s |
| Repeated population selections | 20 | 1 |
| Immediate governance calls | 20 | 20 |
| Recorded checkpoint updates | 70 | 70 |
| Peak process RSS | 1.409 GB | 1.409 GB |
| Provider requests | 0 | 0 |

All four evidence digests and per-outcome governance digests matched. The predeclared correctness,
CPU, protected-wait and memory gates passed. The auditing callback ran identically in both variants.
Governance digests omit the record-maintenance `updated_at` timestamp; active authority, proof,
health and participation values remain in the comparison, and outcome timestamps are retained.
Shared-host scheduling remains a confounder; this is a repeatable mechanism improvement, not a
production-scale disk test or a guarantee of end-to-end burst performance.
These are the final ownership-corrected candidate's repeated results. They supersede the earlier
prototype's larger speed-up. Maximum sampled event-loop delay in these isolated runs was higher
for the candidate (0.038 versus 0.020 seconds); protected waiting and CPU still improved, and all
original comparison gates passed.

## Mixed-workload comparison

One baseline/candidate pair replayed the same 60-second trace: ordinary traffic, a five-second
burst and continuing ordinary traffic. Both used retained learning evidence, 30,000 expired raw
events, six real 20-mint checkpoint/governance passes, event processing, paper-broker paths,
snapshots, cleanup and an explicitly unavailable optional AI assessment. Networking was disabled.

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| Events processed | 9,500 | 9,500 |
| Expired / shed events | 0 / 0 | 0 / 0 |
| Protected queue-age p95 | 1.610 s | 0.365 s |
| Maximum protected queue age | 4.421 s | 1.196 s |
| Maximum queue count | 1,504 | 126 |
| Process CPU during trace | 25.768 s | 18.572 s |
| Retention boundary advance / elapsed | 1.392 | 1.512 |
| Retention debt change | -23.502 s | -30.742 s |
| Peak process RSS | 1.409 GB | 1.409 GB |
| Provider requests | 0 | 0 |

Event-receipt digests matched, accepted slots remained monotonic, and all six passes completed
70 checkpoint updates each. The unavailable AI assessment remained unavailable and its pending
outcome was saved. Maximum sampled event-loop delay fell from 0.125 to 0.045 seconds; maximum
snapshot duration was nearly unchanged (0.757 versus 0.758 seconds). Timing-dependent persistence
counts were 1,163 and 1,162; these are not identical-time trading cohorts.

These are the repeated final-candidate results. The earlier prototype pair had protected p95
1.717/0.420 seconds, peak queue 372/424, and slightly higher candidate event-loop delay. Both runs
are retained. The variation between trials limits causal claims about queue peaks on a shared host;
it is not evidence that every production burst will reproduce the final pair's improvement.

This single pair supports interaction safety and shorter protected waiting in the fixture.
Its disposable tmpfs storage is not production disk latency or full live database scale. It did
not include a new coefficient fit/publication; those paths require separate regression checks
and natural live observation. It does not establish sustained retention capacity or trading efficacy.

## Edge checks completed before full validation

Targeted checks cover unchanged publication admission and validity, delayed task resumption,
repeated cancellation ownership, diagnostic payload capacity, immediate outcome governance,
unavailable/negative outcomes, both sides of checkpoint deadlines, repeated/backward timestamps,
more mints than one pass can admit, multiple episodes for one mint, tied timestamps, restart,
membership replacement/enrollment and pruning failure. A duplicate-key test-fixture error was
corrected by assigning distinct episode idempotency keys; the production guard was retained.
The first full run also caught reuse of an unrelated enclosing selection scope. Reuse was narrowed
to the explicit checkpoint-pass owner, keeping the existing isolation test unchanged. The focused
83-case rerun passed, including nested-scope failure and owner restoration. Final comparisons and
full validation were repeated against that correction; the earlier failed run is retained privately.
At this initial checkpoint, release consistency checks distinguished development source from the
installation image. Package versions and the Docker label were aligned to v1.10.12, while the
public installation example still used v1.10.11. Release documentation now pins v1.10.12.

## Initial learning-continuity validation — 26 September 2026

The backend suite passed **3,464 cases in 177 modules**, executed in serial bounded offline
containers. Production source hashes remained fixed through the final run. Its last group exposed
an outdated test adapter that did not forward the helper's new keyword; the adapter was corrected
without changing its behavioral assertions or production code. That full group then passed, with
the earlier passing groups retained against identical production and test-module hashes.

Ruff checks and formatting passed for all 234 Python files, and strict typing passed for 56
backend source files. The frontend passed **574 tests in 29 modules**, lint with no errors,
TypeScript checks and its production build. The pre-existing Fast Refresh export warning remains.
All nine built frontend assets matched the preceding validated build; no JavaScript UI behavior
change is part of this candidate.

The local offline candidate image passed installed-package verification: 58 backend source/resource
files matched both their installed and image-source copies, all nine UI assets matched, and the
README, package metadata and diagnostic build fingerprint matched the build inputs. Runtime
dependency versions were unchanged except for Signal Arcade's own version; `pip check` passed.

Disposable Settings preparation, Ready restart and cancelled-operation restart all passed using
the installed package, with no source overlay, network access, published port or live-data mount.
Authentication remained enforced; schema 16, the synthetic paper journal, protected history and
saved coverage/storage revisions survived. Stale storage saves were rejected. This is not a full
main-database migration, integrity scan or backup-restore rehearsal.

Read-only Docker inspection confirmed that the original live v1.10.11 container remained healthy,
on its original image/start time, with zero restarts and no OOM. That verifies it was not deployed
or restarted by this work; it does not establish current learning efficacy or burst performance.

## Remaining gates

Each authorized Settings rollout starts a new six-hour observation window; the latest rollout
below supersedes earlier windows. Then seek a full day including bursts and ordinary recovery.
Preserve existing acceptance requirements for
protected lag, truthful durable proof, diagnostics continuity, retention catch-up and disk headroom.
No local test certifies weeks/months of unattended use, profitability or Champion qualification.

## Authorized reference deployment — 26 September 2026

The verified v1.10.12 package was deployed through Settings preparation and Ready, a clean
shutdown, and restart on the same volume. Both publication guards passed with no active fit,
buffered publication group or queued diagnostic write. Schema 16 remained unchanged. Application
startup completed at 20:47:19 UTC, about 80 seconds after container start; Docker became healthy
within the unchanged 180-second guard, with zero restarts or OOM. No backup was restored.

Initial checks verified the exact image/build, authenticated assets and read-only UI routes.
Season, cash, position identities, Champion versions, participation/execution permissions,
55% coverage revision 2, separate Coach 70%, 1,000-row training window and storage policy were
preserved. Manipulation v1 remained active and healthy, Sizing v9 remained in candidate testing,
Entry was collecting proof, Exit v1 remained suspended, and Coach remained inconclusive in shadow
mode. Six observed Coach hypotheses retained their forward evidence and contribution state.
A newly visible Coach review had completed before shutdown; bounded primary-key reads verified
all four observed old/new review records rather than mistaking the shifted recent list for loss.

One natural training/publication cycle completed using retained eligible evidence. Its training
report and five expected proof reports were durably saved as one complete group (indices 0–5),
with maximum collection delay 5.66 seconds. The saved model and five observed unique skill
artifacts passed payload-digest verification, including the retained external XGBoost payload.
That retained XGBoost artifact was not a new refit. New publication attribution recorded about
4.13 seconds waiting behind dequeued work; it did not grant additional publication authority.

The closing bounded read contained three complete saved intervals covering 207.74 seconds,
with no recording flags or sequence holes, 24,637 enqueued events, zero expiry and zero shedding.
Peaks were queue 788, overall lag 7.84 seconds and critical lag 5.11 seconds. The longest interval
was 87.40 seconds and the unsaved tail was 24.13 seconds; this is not full-window continuity.
The closing snapshot refreshed to 6.30 seconds old, seven workers were running and the paper
ledger verified. No diagnostic loss was reported; acknowledgement age was 23.54 seconds.
The new coherent heartbeat detail captured a 4.64-second operation dominated by checkpoint
expiry, with only 0.31 seconds of worker CPU. Its nested elapsed timings overlap; this sample
does not prove the cost was CPU or identify every scheduling delay. The first raw-history
boundary measurement was still unavailable, so retention velocity was not evaluated.
These short startup/warm-up samples are not a matched-load comparison or evidence that every
burst problem is resolved. Closing bounded logs contained no ERROR/CRITICAL lines or tracebacks.

The upgrade helper's isolated checks caught a host PowerShell integer-parsing difference before
any service action. Its private exit-status guard now accepts both integer widths while rejecting
Boolean, string, fractional, missing and nonzero statuses; all 36 helper guard cases passed.
Application/test source and the packaged runtime remained identical to the validated candidate.

The new six-hour acceptance window ends at 02:47:19 UTC on 27 September (03:47:19 BST).
Sustained burst recovery, retention catch-up and diagnostic continuity remain open gates.
No schedule, public push or release was created by this deployment.

## Recovery follow-up — 27 September 2026

This follow-up is local candidate work, not a deployment. The preceding live review still
showed burst expiry, diagnostic gaps and retention debt. Missing diagnostic reports were not
treated as proof that authoritative model records were missing. No trading rule, feature,
proof threshold, Champion permission, database schema or learning generation is changed.

The retained fixes address three bounded failure paths:

- Diagnostic handoff preferentially retains intervals carrying training/proof reports without
  reordering the surviving sequence. If all four pending intervals are protected, finite overflow
  remains possible and its embedded event losses are counted explicitly. Failed serialization
  leaves reports pending with their original identities. Writer failures distinguish a committed
  row from a rejection or an unresolved result; uncommitted visibility is not durability.
- Stream setup has a 30-second receive-progress allowance; a subscribed connection with no valid
  notification from either broad program feed for three minutes reconnects through existing
  backoff. Failed transactions count as stream activity, without becoming trading evidence.
  Local handler time does not consume the receive allowance, including work between the first
  and second acknowledgements. Stalled subscription and manual ping sends are bounded too.
- Existing dashboard polling notices a CLOSED/CLOSING notification socket whose close callback
  was missed. It keeps one retry path, preserves hidden-tab pacing and leaves quiet OPEN sockets
  alone. Connection status still does not certify snapshot freshness.

An additional scheduling experiment tried coalesced wakeups when market work drained. Its
isolated quiet-window mechanism worked, but the repeated combined comparison did not retain
equal fit counts, as required before a matched performance claim. Median per-run protected p95
also exceeded the declared limit (0.682 seconds versus 0.370 seconds for the reference).
The scheduling candidate and
its experimental tests were therefore removed from the release source; the exact preceding
orchestrator was restored. No wakeup, cadence or pressure-guard change is included here.

The combined comparison used serial reference/candidate/candidate/reference runs, each with
8,700 generated events, a burst followed by ordinary traffic, mature retained learning evidence,
real fitting/publication and 300,000 old raw rows. An earlier 30,000-row fixture exhausted eligible
history and was excluded from retention assessment; its unfinished comparison was intentionally
stopped. All trial evidence was retained. Disposable tmpfs, shared-host scheduling and four-minute
traffic windows do not establish production disk throughput or six-hour sustainability.

All four corrected trials handled 8,700 events with zero pipeline expiry/shedding, preserved
each generated publication group and verified the paper ledger without provider requests.
The reference completed three fits in each run; the candidate completed two and three. Median
retention debt decreased by 130.47 seconds for the reference and 140.34 seconds for the candidate,
with eligible backlog remaining. That small unmatched improvement does not override the failed
acceptance requirements. One candidate run reported one optional work-detail loss, with no lost
training/proof reports. The reference source with the retained recovery fixes also completed
the combined workload; these tests do not certify live sustained burst handling.

The final retained source passed **3,494 backend cases in 179 modules**, with unchanged source
hashes throughout the complete serial offline run. Ruff and formatting passed for 237 Python
files; strict typing passed for 57 backend files. All **577 frontend tests in 29 modules**,
frontend lint/type checks and the production build passed. The existing Fast Refresh export
and bundle-size warnings remain. The earlier targeted 68-case recovery rerun also passed.
Two newly added stalled-send tests initially expected a timeout label, then were corrected to
assert the existing redacted transport category; their bounded recovery assertions were retained.

The built local image verified 59 installed backend source/resource files, their image-source
copies, all nine UI assets, README/package metadata and the diagnostic build fingerprint.
Runtime dependencies matched the audited inventory and `pip check` passed. The source was not
overlaid on the installed package. Disposable first start, Settings preparation/Ready restart
and cancelled-operation restart passed, preserving schema 16, the synthetic paper journal,
coverage/storage revisions and authentication; stale storage saves remained rejected.
There was no network access, published port or live-data mount in these rehearsals. This is
not a full main-database integrity scan, migration or backup-restore rehearsal.

Read-only inspection confirmed that the preceding live image retained its original start time,
with Docker healthy, zero restarts and no OOM. This follow-up did not deploy, change live settings,
push, tag or release anything. It did not repeat a live diagnostics acceptance review while
sharing the host with release tests.

After an authorized guarded Settings rollout, start a fresh six-hour observation window and
retain the existing protected-lag, loss, complete-publication, diagnostic-continuity, retention
catch-up and storage-headroom gates. Longer observation remains necessary for an unattended-use
claim. The retained fixes improve recovery and diagnostic truthfulness; they do not establish
that burst expiry or retention sustainability is solved, or that trading results improve.

## Subsequent protocol edge review — 27 September 2026

An additional offline check reproduced an unnecessary watchdog reconnect when otherwise valid
log notifications contained string-shaped transaction errors. Solana's SDK accepts both object
and string errors in `LogsResult` (see its
[notification schema](https://github.com/solana-foundation/solana-web3.js/blob/maintenance/v1.x/src/connection.ts)).
The provider's progress predicate now accepts both forms. Failed transactions still take the
existing early return before market-event decoding; they cannot become synthetic successful
trades or learning outcomes. Boolean, numeric and array error values do not extend the timer.

All 84 focused rechecks passed, including blocked-send/receive cancellation with no remaining
tasks and five seeded interval-overflow runs. The overflow probe paginated the persisted event
envelopes and reconciled generated, saved and explicitly lost proof counts. An initial probe
mistakenly treated the reader envelope as the event itself; correcting the probe required no
diagnostic source change. The only production change since the preceding validated image is
the transaction-error shape predicate. The corrected image was rebuilt and checked as follows.

The complete serial offline backend run passed **3,500 cases in 179 modules**. The subsequent
format check found one LF line ending inside the provider's otherwise CRLF file. Normalizing
that line preserved identical normalized source bytes and Python syntax trees, including
locations. The original tested snapshot and formatting failure were retained; the formatted
package inputs were recorded separately. Ruff and formatting then passed for 237 Python files,
and strict typing passed for 57 backend files. No behavioral change followed the full test run.

All 84 frontend input files and nine built assets matched the preceding validation by hash.
Its **577 frontend tests in 29 modules**, lint, type checks and production-build result were
therefore reused explicitly; no new frontend test run is claimed. Existing frontend warnings
remain unchanged.

The corrected local image, `signal-arcade:v1.10.12-recovery-edge-20260927`, verified all 59
installed backend source/resource files, their image-source copies, nine UI assets, package
metadata and diagnostic build identity. Runtime dependencies matched the audited inventory,
and `pip check` passed. Disposable first start, Settings Ready/restart and cancellation/restart
passed with schema 16, the synthetic paper journal, authentication, coverage/storage revisions
and stale-save rejection preserved. These checks had no network or live-data mount.

No additional production defect was established in this edge review. The rejected scheduling
experiment remains excluded. The live app, settings and data were unchanged; no deployment,
push, tag or release occurred. This local validation does not close the existing live burst,
diagnostic-continuity or retention-sustainability acceptance requirements, and is not a full
main-database integrity or backup-restore rehearsal.

## Recovery Settings rollout — 27 September 2026

The user authorized the live update after the edge review. The first attempt refused before
Settings preparation because diagnostic writes were pending. They drained naturally; a new
training cycle also completed and its final seven-event publication was verified saved.
Both the pre-preparation and post-Ready checks passed before a clean shutdown. The existing
data volume was retained, with no backup restore or schema reset. The rollout helpers passed
26 isolated publication-guard and ten native-exit edge cases before live use.

The verified image is `signal-arcade:v1.10.12-recovery-edge-20260927`. Application startup
completed at **04:27:40 UTC**, and Docker health passed at the 73-second startup poll, within
the unchanged 180-second guard. The exact image/build, all seven workers, zero restarts/OOM,
served frontend hashes, authentication and Settings completion were confirmed. Bounded closing
logs contained no error or traceback lines.

Prepared cash and position state, season 62, execution permissions, active Manipulation v1,
coverage 55% revision 2, separate Coach 70%, storage policy and the 1,000-observation window
were preserved. The paper ledger verified. Entry remained collecting proof, Sizing v9 remained
candidate-testing and inactive, and Exit v1 remained suspended. No Champion was forced to join.

Three natural training/publication cycles completed after startup. Each saved its training
event and six proof events with original indices 0–6/expected 7. Bounded primary-key reads
verified the latest model and five observed unique skill artifacts, including XGBoost payload
bytes. The initial empty AI qualification view recovered after model-inventory refresh; seven
old/new AI assessment identities and four Coach review identities remained saved. Coach's
hypotheses, permissions and gates were preserved, and a new review advanced naturally while
Coach remained inconclusive. A private probe initially compared the mutable recent-review list;
it was corrected to verify durable identities, with no application change.

At the closing snapshot, the dashboard refreshed from an idle cached response to **6.26 seconds**
old, diagnostic acknowledgement age was **37.02 seconds**, and publication/diagnostic queues
were empty. The saved read contained three consecutive complete intervals covering **213.02
seconds**, with 26,983 enqueued events, zero expiry/shedding, no reported diagnostic loss,
no sequence holes and no recording-gap flags. Peak queue was 1,976; maximum overall/critical
lag was 11.31/2.40 seconds. The initial interval overlapped startup and was excluded, and the
fixed-end read still had a **47.55-second unsaved tail**. Page streams completed within their
six-interval-page/twelve-event-page caps; that does not turn the unsaved tail into an observation.

This is an early warm-up sample using retained eligible evidence, not a matched performance
comparison or sustained-burst result. The preceding boot still showed severe candidate expiry
and diagnostic delays. The new retention boundary was unavailable at the closing snapshot, so
no catch-up velocity is established. Disk space remained above the existing rollout floors,
but projected 24-hour headroom, full main-database integrity and restore rehearsal remain
unverified. The rejected scheduling experiment remains excluded.

The fresh uninterrupted six-hour window ends at **10:27:40 UTC / 11:27:40 BST on 27 September**.
The existing acceptance gates remain unchanged. No automatic follow-up schedule was created.
The app is left running for observation; these initial checks do not certify weeks or months
of unattended use or improved trading returns.

## Dashboard notification authentication follow-up — local validation checkpoint

The preceding live check found repeated `/ws` 403 responses. A bounded direct handshake
succeeded with Basic authentication and failed without it. The exact headers of the affected
user's browser were not available, so omission of credentials is a supported failure mechanism,
not a proven explanation for every observed rejection. Clean Chromium and Firefox sessions
successfully reused their login; the installed WebKit test engine could not complete its
compatibility check and is not counted as passing.

The follow-up uses existing authenticated `GET /` and `GET /api/v1/snapshot` responses to
renew a five-minute HMAC-signed notification cookie. It is HttpOnly, SameSite=Strict, host-only,
restricted to `/ws`, and Secure on HTTPS. Both the signature and cookie name distinguish the
scheme/host/port. A per-app random key invalidates outstanding credentials on restart. No
session registry, database write, new endpoint, provider request or additional polling is added.
Expiry controls new handshakes; already accepted connections retain their existing lifetime.

Cookie authentication applies only to notifications, requires an explicit matching Origin,
and is not used if an explicit Authorization header is invalid. API requests retain Basic
authentication. Rejection diagnostics emit at most one credential/origin/session-origin/session
message per application lifetime and contain no cookie, password, URL or arbitrary header value.
Existing origin checks and proxy-header trust are unchanged; proxies must preserve a coherent
public origin. Cookies blocked by the browser continue to leave HTTP fallback available.

A disposable server used the actual built UI and actual API middleware/routes with synthetic
snapshots, no market workers and no database. Its test boundary deliberately removed only the
WebSocket Authorization header. Before the fix, Chromium stayed on Auto refresh with four
rejected handshakes and two successful snapshot reads. With the fix, Chromium and Firefox
reached Live updates and received notifications without that header. Both recovered after a
forced disconnect and cookie clearing while a second tab remained connected. Neither produced
JavaScript errors; external font requests were blocked, and no provider requests occurred.
A separate Chromium HTTPS/WSS run with an ephemeral local certificate also passed the same
reconnect, cookie-clearing and two-tab checks with Secure cookies.
These are controlled recovery checks, not a claim to have inspected the user's browser headers.

Focused tests cover expiry boundaries, renewal through existing polling, key/password restart,
multiple tabs/ports, HTTP/HTTPS, malformed/tampered credentials, origin rejection, API authority
separation, failed reads, direct Basic clients and unchanged passwordless localhost mode.
Final validation passed **3,540 backend cases across 180 modules**, including 40 new
notification-authentication cases, in serial offline containers with no live data mounts.
Strict typing passed for 58 source files; Ruff lint and formatting passed for 239 Python files.
All 253 frozen validation inputs still match their hashes. The previous 577 frontend cases
across 29 modules are reused, not rerun: all 84 frontend inputs and all nine built assets are
identical. New real-browser integration checks exercised those assets against the changed API.
The final diff contains two production changes for this follow-up: the API integration and
its notification-session helper. Trading, learning, provider, storage and scheduling source
remain unchanged from the preceding validated build; the rejected scheduling code is absent.

This follow-up does not change learning, proof, Champion governance, trading, retention or
burst scheduling. At this checkpoint it remained local pending the separately authorized update
recorded below; the affected user browser itself had not been inspected.

## Dashboard authentication Settings rollout — 27 September 2026

The user authorized the update. The exact validated backend and unchanged frontend were
packaged offline on the preceding audited runtime. Installed source, 60 backend/resource
files, nine frontend files, dependencies and package metadata verified. Disposable first
start, Settings Ready/restart and cancellation/restart passed without live data mounts.
The rollout helper also passed 26 isolated publication-guard and ten native-exit cases.

Pending reports drained naturally before preparation. Pre-Ready and post-Ready checks
passed, followed by a clean stop and replacement using the same data volume. No backup
restore, schema reset or settings-policy change occurred. The verified image is
`signal-arcade:v1.10.12-dashboard-auth-20260927`; application startup completed at
**08:18:08 UTC** and Docker health passed at the 73-second poll, within the unchanged
180-second guard. Seven workers ran with zero restarts/OOM and no error/traceback lines
in the bounded closing logs. Served asset hashes and Settings completion verified.

Live read-only handshakes verified the new notification cookie, receipt of actual
notifications without a WebSocket Authorization header, and reconnect using that cookie.
API reads still required Basic authentication. Three deliberate negative handshakes
confirmed rejection without credentials, without Origin, and with a different Origin;
their expected 403 responses are validation traffic. These checks do not inspect the
affected user's exact browser session.

Prepared cash, position state, season 62, permissions, active Manipulation v1, coverage
55% revision 2, separate Coach 70%, training window 1,000 and storage policy were preserved.
The paper ledger verified. Entry remained collecting proof, Sizing v9 candidate-testing
and inactive, Exit v1 suspended, and Coach inconclusive. Eight observed AI assessment
identities and four Coach review identities were verified saved with bounded primary-key
reads; the Coach permissions, hypotheses and gates were preserved.

Two complete natural training/proof groups were saved with original indices 0–6 and
expected count seven, with maximum collection delays 28.56 and 60.24 seconds. Observed
model and five unique skill artifact payloads verified, including XGBoost bytes. At
09:20:28 BST the publication and diagnostic queues were empty and no diagnostic record
loss was reported; a further training job was in progress. These are point-in-time checks,
not a guarantee that future pending reports are durable.

The fixed-end saved read covered only one complete 60.49-second interval, with 6,270
enqueued events, no expiry/shedding and no recording-gap flag. Peak queue was 440 and
overall/critical lag 6.90/2.69 seconds. Both page streams completed within their caps,
but 39.74 seconds at the end remained unsaved and the initial startup-overlapping
interval was excluded. This is a warm-up sample, not sustained-burst validation.

The later health sample still showed queue 523 and overall/critical lag 7.72 seconds.
The dashboard refresh read an old 65.13/71.49-second response, then a newer response
at 11.72 seconds old, finally 17.30 seconds old. Diagnostic acknowledgement age was
36.34 seconds. These delays remain visible; the authentication update is not claimed
to improve market scheduling, retention or snapshot computation. The preceding build
also had burst losses. No matched-traffic causal comparison was performed.

The new uninterrupted six-hour window ends at **14:18:08 UTC / 15:18:08 BST**. Existing
acceptance gates remain unchanged. No follow-up schedule, public push, tag or release
was created. Full main-database integrity and restore rehearsal remain unverified.
The app is left running; upgrade and notification checks passed, while longer runtime
acceptance and affected-browser confirmation remain separate.

## Final experiment review and runtime check — 27 September 2026

A further isolated experiment omitted Execution-lane copies from the temporary native fitting
workspace. Two serial ABBA blocks used identical retained fixtures and no provider requests or
live-data mounts. All eight runs published one model and produced matching logical results and
payload digests across six artifact paths. The 53 targeted edge cases passed, including lane
selection, unavailable/negative outcomes, chronology, identity retention and workspace isolation.

Serialized input fell from 69,452,775 to 61,315,807 bytes, but median preparation/reconstruction
thread CPU changed from 5.7626 to 5.7881 seconds. The first block was 4.11% worse and the second
8.22% better; neither met the predeclared 15% repeatable improvement gate. The experiment was
rejected and all 509 public files matched the preceding validated source afterward. No new
combined replay, full release-suite run, package or deployment was claimed for the rejected work.

The subsequent read-only review verified the existing dashboard-authentication build, all 60
installed backend/resource files and nine frontend files, with no restart or deployment.
At 09:00 UTC, all seven workers were running, the paper ledger verified, and the dashboard
refreshed from a long-idle cache to 5.91 seconds old. Diagnostic acknowledgement age was
57.19 seconds. The fixed-end saved history through 09:00:19 UTC covered 34 consecutive complete
intervals, about 41.5 minutes. Both page streams completed within the bounded query limits;
the initial startup-overlapping interval was excluded and the unsaved tail was 0.94 seconds.

That history contained 391,628 enqueued events, 7,079 expiries and zero capacity shedding,
with five recording gaps and one lost optional work-detail event. Peak queue was 5,838;
overall/critical lag peaked at 33.08/19.94 seconds. Sixteen complete publication groups retained
their training event and six proof events, original indices and expected count seven. Maximum
collection delay was 112.16 seconds. Bounded primary-key reads verified the latest saved model
and five observed unique skill artifact payloads, including external XGBoost bytes.

Four fresh retention samples showed the boundary advancing 44.04 minutes over 33.30 minutes
of wall time, reducing debt by 10.74 minutes; the final debt still exceeded the 24-hour target
by about 8 hours 22 minutes. This is short-term catch-up, not proof of sustainable retention.
The window includes warm-up and shared-host offline tests, so it is not a matched-load causal
comparison or six-hour acceptance result. Full main-database integrity and restore rehearsal
remain unverified. Trading, learning and qualification rules were not changed by this review.

## Release documentation — 27 September 2026

The README, version badge, Compose image example and changelog now identify v1.10.12. Long
release history is collapsible; screenshots, installation instructions and operational limits
remain available. Learning and diagnostics reference pages use the current release terminology.
This documentation update does not alter application/test source, settings, data or services.
Publication of a Docker tag remains a separate release action; a local validated image alone
does not make that tag available to users.

## Multi-platform frontend build — 27 September 2026

A local multi-platform Docker build failed during the ARM64 web stage's frozen pnpm install.
The log recorded slow registry requests, numeric error 23 and a final `fetch failed`, after
lockfile policy validation. The inspected pnpm 11.19.0 implementation uses timed fetches;
Node's timeout exception has code 23. The final exception's underlying cause was unavailable,
so this is not proof of a registry outage, disk exhaustion or a dependency incompatibility.

The web stage now uses Docker's automatic `BUILDPLATFORM`. Its only runtime output is static
browser assets, so both AMD64 and ARM64 targets can reuse a native frontend build. The Python
stage still uses each requested target platform. Dependencies, frozen-lockfile enforcement,
security checks, runtime code and learning/trading behavior are unchanged. This follows
[Docker's native build-stage guidance](https://docs.docker.com/build/building/multi-platform/#cross-compilation).

A two-platform asset export passed using the builder's existing native cache. All nine files
matched between architectures and matched the preceding validated package by SHA-256. Source
maps also matched the validated package and all 37 application source files checked against
the checkout. This verifies artifact equivalence and removes the redundant emulated web build;
it is not a fresh registry-download test or a guarantee against future network failures.

An additional cache-only full-image build cleared the shared web stage and cached AMD64 runtime,
then spent about 11 minutes in the unchanged ARM64 Python installation under emulation. The
builder was limited to one CPU; its pip process remained CPU-active and downloaded the pinned
installer, without a new reported error. This optional check was cancelled and its worker exit
verified. A complete fresh ARM64 runtime build remains unverified by this check; no image was
published or loaded into the live service. Release-version alignment and `git diff --check`
passed, and source hashes confirmed that this fix changed only Dockerfile and release notes.

An initial comparison used stale ignored local `frontend/dist` output and failed. Rechecking
against the authoritative packaged assets resolved that discrepancy; read-only inspection also
confirmed the expected refresh and storage UI changes in the live container. Local generated
output is excluded from the Docker context and is not the input to the public Dockerfile.
No live update, push or release was performed during these checks.
