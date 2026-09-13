# v1.10.10 validation — 2026-09-09

**Current status:** the [holder-rewards contract review](#holder-rewards-and-dashboard-recheck--12-september)
resolved the newer Pump Global layout. The [authorised 12 September rollout](#holder-rewards-rollout--12-september)
installed the validated changes and confirmed initial learning and watchdog collection recovery.
The subsequent [collection-recovery rollout](#collection-recovery-rollout--12-september) installed
the guard-retry and diagnostic-detail changes; its verification is recorded at the end of this document.
Longer observation is still needed for mature Entry coverage and sustained burst performance;
earlier pending-deployment and unresolved-layout entries below describe their historical stage.

The later [Coach extended-hold scheduling fix](#coach-extended-hold-scheduling--12-september),
[passive Champion impact panel](#champion-impact--13-september) and
[dashboard reconnection fix](#dashboard-reconnection--13-september) were installed by the
[authorised 13 September rollout](#coach-impact-and-reconnection-rollout--13-september).
The local live app now includes all three follow-ups. Earlier pending-deployment statements
record their status before that rollout. No public release or image was pushed by this check.

The subsequent [stale reserve-warning follow-up](#stale-reserve-warning-follow-up--13-september)
is validated and installed by the [final UI rollout](#final-ui-rollout--13-september).
The live app includes this correction as well as the earlier changes; statements below that
it was not yet deployed describe the checks before that rollout.

This release follows v1.10.9 with Entry scoring and collection diagnostics fixes. Release metadata
is 1.10.10. No live settings, data, service, deployment or permission was changed during implementation.
The subsequent authorised local rollout is recorded below; this record does not assert publication
of a public image or release.

The latest 10 September follow-up is [Reserve-account compatibility fix](#reserve-account-compatibility-fix).
It supersedes the earlier unresolved-layout finding. Its subsequent
[authorised rollout](#authorised-reserve-fix-rollout) confirmed live collection recovery on
10 September; earlier deployment entries refer to previous builds.

## Corrections and scope

- An isolated regression reproduced a false Entry/Manipulation replacement under the old
  scoring: unsupported veto proposals received zero rather than the Baseline's losing return.
  Both contestants now use the same fallback as execution and independent participation.
  Winner-veto counts require a supported veto. Malformed actions and unknown outcomes do not
  receive a fabricated zero. Manual health/join checks share the corrected helper.
- Existing completed replays remain immutable. An ongoing comparison crossing the scoring
  change starts a partial recording with `action_scoring: baseline-fallback-v1`. This is separate
  from the unchanged `paired-skill-outcomes-v2` proof marker used by Exit upgrade validation.
  The broader suite caught a new-battle initialization edge case: the initial zero-evidence
  point also needs the scoring marker. Initialization now sets it, so new battles retain a
  complete recording while an actual upgrade across scoring rules remains explicitly partial.
- Nonlinear eligibility uses the most recent exact-context Linear/XGBoost training count and
  exposes its fit time. Tests cover a fall from 275 to 218, an old retained 250-row XGBoost,
  recovery to 250, a newer Coach artifact, missing Linear history, and Champion/suspension status.
- Familiar Policy cases may be kept or vetoed. Wording no longer implies a minimum keep quota.
- Collection telemetry uses fixed lanes, horizons and stages, scoped cumulative counters and
  two compact events per five minutes. It creates no per-attempt database writes or evidence.
  A full-payload regression caught an oversized interval design; the final event design fits
  existing interval/event limits alongside six proof events and all current skill families.

Training populations, point-in-time features, primary horizon, fees, missing-outcome denominators,
70% coverage, chronology, proof separation, live Baseline boundaries and permissions are unchanged.
The scoring correction improves selection integrity; it does not itself collect more outcomes.

## Controlled capacity comparison

`tests/test_collection_capacity.py` runs the real scheduler on identical synthetic arrivals:
258 Discovery trajectories over 30 minutes (one every seven seconds), a delayed Policy clock
on every fourth mint, all five original horizons and the 90-second grace window. Each batch
has a declared one-second request cost plus the existing ten-second interval. The pressure
variant skips the first 33 seconds of each five-minute block. Every fifth route is independently
unavailable. All compared cohorts finish their original windows before results are counted.

| Batch | Pressure windows | Requests | Discovery 5m usable | Unavailable | Expired |
|---:|:---:|---:|---:|---:|---:|
| 5 | No | 269 | 167 | 43 | 48 |
| 10 | No | 269 | 206 | 52 | 0 |
| 20 | No | 269 | 206 | 52 | 0 |
| 5 | Yes | 241 | 151 | 39 | 68 |
| 10 | Yes | 241 | 206 | 52 | 0 |
| 20 | Yes | 241 | 206 | 52 | 0 |

The test also checks every other horizon and Policy lane: cohort sizes remain equal, usable
counts do not fall and expirations do not increase for these workloads. Recovering a collection
opportunity can reveal a real unavailable outcome rather than a usable one.

These are scheduler-capacity counts, not wall-clock throughput, reconstructed live trades or a
forecast of reaching 70%. No network, main database, trained model or real provider timing is
involved. Batch 10/20 already exist; the default is 20. No new scheduler, larger limit, live
batch setting, shorter interval or primary-horizon priority was introduced. A small configured
batch is a candidate for controlled tuning after deployment, subject to provider and critical
work latency measurements. Larger responses and validation batches have costs this fixture
does not establish.

A separate bounded overhead sample alternated 24 instrumented/uninstrumented scheduler passes
over 2,000 synthetic pending trajectories. Median elapsed time was 25.38 ms with counters and
20.33 ms without (maxima 72.02/43.51 ms). This ran in a one-CPU container alongside the broader
test run, so absolute timings include scheduling noise. Telemetry has a measurable small cost;
it is not a throughput optimisation. It adds no network or database request, and its emitted
detail remains bounded. Live critical latency still needs observation after deployment.

## Verification and remaining observation

Isolated tests cover supported/unsupported positive, zero, negative and unknown outcomes;
false-crown prevention; manual health/join checks; restart and Exit proof compatibility;
unchanged shared-mint scheduling; request failures, cancellation, context and route changes;
single-count closure and expiry; telemetry reset and storage/readback; and proof-event priority.
Backend tests use temporary data in a network-disabled, CPU/memory-limited container with source
mounted read-only. Frontend checks use existing local dependencies.

Final checks on the completed source:

- Full backend: **1,457 passed** in 579.15 seconds. One existing Starlette/AnyIO deprecation warning.
  The earlier full run exposed the replay-initialization issue described above; after correction,
  all 144 affected learning/replay/recovery tests and this fresh complete run passed.
- Full frontend: **368 passed** across 21 files.
- Ruff lint and formatting: passed; 121 Python files formatted.
- Mypy: passed for all 41 backend source files. TypeScript compilation: passed.
- ESLint: no errors; existing Fast Refresh warning in unchanged `EquityChart.tsx`.
- Frontend production build: passed; existing large lazy-loaded scene-chunk warning remains.
- `git diff --check`: passed. Dependencies were unchanged. The subsequent release-preparation
  step updates version metadata to 1.10.10 without changing learning or trading logic.

Follow-up edge-case verification added four passing cases: late RPC results cannot reopen
expired checkpoints, duplicate RPC results cannot overwrite stream-collected evidence,
cancellation while waiting for the market lock applies no evidence and preserves the lock,
and diagnostic cadence uses monotonic time with immediate emission for a new learner scope.
The combined collection, scheduling, reserve-refresh, veto-scoring, replay and skill-recovery
run passed **158 tests** in 115.90 seconds, with the same existing deprecation warning. Ruff
lint and formatting passed again. This follow-up changed tests and documentation only;
no further runtime fix was indicated. The full-suite counts above precede these four new cases.
Diagnostics guidance now explicitly distinguishes learner-wide aggregate counters from
exact-context qualification coverage.

Release preparation aligns the backend version, Python package, root/frontend packages and
Docker image label at **1.10.10**. README highlights, the pinned image tag, changelog, upgrade
notes and this record describe the release. The README Compose example passed `docker compose
config`; its image version, data volume, read-only app, port and private AI connection were
checked without starting services. All 36 local links and release anchors in the README,
changelog and this record resolved. Historical screenshots retain their actual version labels.
This metadata/documentation step did not rerun the full application suites or claim publication.

Before the subsequently requested live rollout, no live restart, deployment, setting change or
push had been performed. Read-only inspection confirmed the prior packaged build and its `/data`
volume. There is no new database schema migration or data reset to reverse. Returning to earlier
source would also restore its incorrect unsupported-veto scoring.

No test or short observation guarantees long-term profitability or an Entry Champion. The next
useful live comparison requires the new build, matching collection scopes and mature cohorts;
older missing attempts remain unknown. Dependency audits were not repeated for this follow-up.

## Requested live rollout

The v1.10.10 image built successfully from the Dockerfile. Its packaged backend hashes match the
working source, both installed and API versions are 1.10.10, schema remains 16, and installed
dependency versions match the prior live image. A disposable, network-disabled smoke container
served the frontend, health, snapshot, diagnostics, Champion history, Results and Seasons routes;
all seven workers were running. The disposable container was removed after testing.

Live preflight observed a burst on the previous v1.10.9 build. The rollout waited for recovery;
a health request timed out before maintenance preparation or container replacement. Docker's
engine subsequently became unavailable. Restarting Docker Desktop and its stalled WSL runtime
did not restore the engine. Startup logs reported that the existing data disk was not visible
inside WSL; the virtual disk file remained present. A bare attachment attempt was rejected by
Windows with `Wsl/Service/AttachDisk/MountDisk/HCS/E_ACCESSDENIED`.

That first attempt ended before app maintenance, backup or replacement. Very low system-drive
space was also observed; its causal relationship to the host failure is unconfirmed. These
host observations do not establish an application regression or improved live coverage.

After the user recovered Docker, the authorised rollout completed on **9 September 2026 at
21:20 UTC**. Preflight confirmed the prior build was healthy and waited for two quiet observations.
Upgrade preparation settled with no open positions or pending orders. The app was stopped and
its full data volume archived through a read-only mount; reading the archive back verified all
five files against their source sizes and SHA-256 checksums. The 3.24 GiB compressed backup is
retained outside the repository. Only the app container was replaced; the existing data volume,
container environment, provider settings and AI companion were preserved.

The running image matches the tested v1.10.10 digest. Startup completed the recorded maintenance
operation and resumed all seven workers. Cash, reserved cash, starting bankroll, realised P/L,
positions, pending orders, season, retained observation counts and learning permissions matched
the prepared state. The paper execution audit remained verified. Sizing remained active and
healthy; Exit was already suspended before deployment and retained that state. Coach research
and contribution permissions resumed unchanged. No data reset or additional runtime change was
made during deployment.

Serial observations from 21:20 to 21:27 UTC confirmed active market processing, a verified paper
execution audit, unchanged permissions and no event shedding, expiry, worker exceptions or
container OOM/restart. Seven retained intervals recorded a maximum queue depth of 241, overall
lag of 2.35 seconds and critical lag of 0.72 seconds. This was ordinary observed traffic, not a
controlled peak-load comparison. The five-minute continuity gate initially held new enrollment;
after it passed, pending observations rose to 40. The new Discovery/Policy collection events
were persisted and read back, including fresh usable one-minute checkpoints. RPC account
validation rejections remained visible and were not converted to usable evidence. No new model
publication occurred during this short observation.

The observation was interrupted by a host restart. Windows recorded planned operating-system
update restarts, beginning at 21:28 UTC. On 10 September, the same image and data volume started
again. Cold startup briefly failed health probes before the HTTP service became ready; it then
recovered without an app restart or configuration change. Read-only checks confirmed all seven
workers, database health, verified paper accounting, the same season and saved learning/Coach
permissions. Sizing remained active and Exit retained its prior suspension. Retained diagnostics,
including the new collection events, survived and explicitly marked the recording gap.

All 41 backend files still matched the validated image after the host restart. Syntax checks
passed for all 121 backend/test Python files, release metadata and README remained at 1.10.10,
and `git diff --check` passed. The backup archive and verified manifest remained present. No
unfinished source change was found; only this observation record remained to be completed.
The full test suites above were not repeated because runtime source was unchanged.

The deployment and restart checks found no additional application fix to make. They do not
establish sustained burst capacity, improved Entry coverage, a new Champion or long-term trading
performance. An uninterrupted run with mature, comparable evidence is still needed for those
assessments; the host's recording gap must remain excluded from any claim of continuous operation.

## Reserve-validation follow-up

**Historical finding, 10 September 2026: release readiness was blocked by unresolved on-chain account compatibility.**
This later investigation supersedes the earlier short-observation conclusion above. The approved
follow-up implements fault visibility and independent regression fixtures, while retaining the
existing account-validation rejection. It does not claim that reserve collection has recovered.

At **07:53:39 UTC**, the running v1.10.10 process reported 378 refresh requests, 1,872 selected
routes, zero accepted snapshots/updates and 1,642 `unreviewed_account_extension` rejections.
Forty-six batches were discarded for context or pressure. These are attempt counts, not unique
lost outcomes. All core workers and model publications continued; a healthy HTTP response did
not establish healthy reserve refresh. Stream-collected evidence remains a separate path.

Retained minute diagnostics establish that acceptance stopped around **19:31–19:32 UTC on
9 September**, in the prior v1.10.9 boot. Accepted-route totals stayed at 7,485 while validation
rejections increased from 8 to 538 by 20:39 UTC. The v1.10.10 deployment was later, at 21:20 UTC;
the reserve decoder and pinned IDLs had not changed in that release. This timing does not identify
the exact on-chain transaction or establish that all expired observations were recoverable.

One bounded public `getMultipleAccounts` request at **08:14:51 UTC**, confirmed slot **445835852**,
captured four public shared configuration accounts. The fixture contains public addresses, owners,
raw base64, lengths and SHA-256 hashes; it contains no wallet secrets, credentials or private RPC
endpoint. Known prefixes parse, but each has nonzero bytes after that prefix:

| Venue/account | Raw bytes | Parsed prefix bytes |
| --- | ---: | ---: |
| Pump curve FeeConfig | 4,097 | 153 |
| Pump curve Global | 1,054 | 1,045 |
| PumpSwap FeeConfig | 4,097 | 2,073 |
| PumpSwap GlobalConfig | 949 | 940 |

The [official definitions at the reviewed commit](https://github.com/pump-fun/pump-public-docs/tree/9c82f61cb711b044a17f770ab8ce9f9bdf78f333/idl),
published Anchor IDLs and checked official SDK packages (pump-sdk 1.36.0, pump-swap-sdk 1.19.0)
did not explain these tails. Nonzero allocation bytes can also survive serialization of a shorter
variable-length account; byte presence alone does not prove new fee fields. The fixed global
tails and their economic meaning still require authoritative verification. Owner/PDA correctness
and plausible prefix fees are insufficient grounds to ignore the remainder.

Implemented scope:

- Preserve all acceptance conditions and reason strings; add account-type context to layout
  rejection exceptions. Both learning and the held-position watchdog report repeated shared-layout
  failures. No quote, checkpoint, fee, Baseline, permission or qualification rule changes.
- Keep four bounded process-local component states. Deduplicate routes within each request,
  use monotonic timing, require actual matching-component validation to clear a failure, and
  retain inactive faults without calling disabled/no-work paths unhealthy.
- Surface a separate system-status issue without failing process liveness or labelling it market
  lag. Fresh server responses, stale snapshots and missing optional fields cannot hide the issue.
- Store a compact summary in existing periodic collection events, with a one-event fallback for
  watchdog-only observations. Keep the original interval, event-size and proof-priority limits.
  An initial full interval representation failed the maximum-size test and was replaced before
  completion; no storage-budget increase or proof-event loss was accepted.
- Capture public configuration fixtures independently of the local IDL encoder. Each shared
  account fails independently, so a FeeConfig-only change cannot appear to solve both failures.

The five-route successful-path regression uses real quote calculations, learning writes and
governance, then reloads the saved checkpoints and repeats the batch. Both the control and monitored
case produce 20 updates, including five usable primary outcomes in each lane, without duplicated
outcomes or changes to live feature state. One isolated single-CPU run took 6.59 ms without status
recording and 7.66 ms with it. This small sample is a correctness/workload smoke check, not a
throughput estimate, a meaningful performance difference or a claim of improved live capacity.

The remaining safe sequence is to obtain an authoritative explanation of **both** shared account
layouts, independently verify fee results on supported curve/canonical/noncanonical/mayhem cases,
then implement only the justified decoder/quote change with malformed/future-layout regressions.
Successful refresh batches must then be measured under comparable isolated workloads. Do not
increase batches, whitelist arbitrary tails, reopen expired checkpoints, lower 70% coverage, omit
valid failures or reset learned history to obtain an Entry Champion.

This follow-up has not been deployed, restarted or pushed. The live app still runs the previously
reviewed image; no live settings or database records were changed. The visibility-only changes
introduce no database migration. Reverting them would remove the warning and its diagnostic
context; it would not resolve the underlying account rejection. An approved rollout and mature,
comparable live cohorts remain necessary after compatibility is actually resolved.

Follow-up validation: the full backend suite passed **1,479 tests** in 213.67 seconds, and all
**370 frontend tests** passed. Strict backend typing passed for 42 source files, Ruff lint and
formatting passed for 124 backend/test files, TypeScript compilation and the production frontend
build passed. Existing Starlette deprecation, Fast Refresh and large scene-chunk warnings remain.
The final caller review then added a current-status overlay when returning cached dashboard
snapshots, without changing the saved cache. Its new regression and surrounding API, burst,
collection, deadline and diagnostic tests passed **161 tests**; the full-suite count precedes this
one additional case. No dependency or schema change was made for the follow-up.

At **08:36:03 UTC**, a bounded live health check confirmed the unchanged image digest and zero
container restarts/OOM. All seven workers were running, queue depth was zero, current lag was
0.036 seconds and critical lag 0.040 seconds. Reserve refresh still showed zero acceptances in
564 requests and 2,431 extension rejections. This is continued impairment, not recovery.

The same check reported 1,893 expired candidate events. Twenty-two bounded retained intervals
located them in **08:30:31–08:31:51 UTC**: queue maximum 6,297, processing lag maximum 21.31
seconds and critical lag maximum 1.62 seconds. The next three intervals had no further expiry
and queue maxima below 540. This interval overlapped local validation work on the same host;
the backend test container was limited to one CPU, but frontend tests also used host resources.
No controlled comparison attributes the burst to application logic, market arrivals or testing.
These intervals must not be used as evidence of improved live capacity. Subsequent performance
assessment should run without concurrent development workloads before proposing another fix.

The subsequent edge-case recheck added six regression cases for replaced state, changed routes,
stale slots, both mixed-result orders, detached status copies and concurrent validator/status
readers. All **293 focused backend tests** passed in 27.98 seconds, including account rejection,
fees, checkpoint deadlines, cancellation, watchdog recovery and diagnostic export limits. Ruff
lint/formatting and `git diff --check` passed. This recheck changed tests and this record only;
it required no further runtime-code fix and did not alter the unresolved compatibility blocker.
All five targeted frontend warning/recovery cases also passed with one test worker; unrelated
frontend cases were deliberately skipped. No live requests, deployment or restart were needed
for this recheck.

## Reserve-account compatibility fix

The read-only follow-up located a newer authoritative reference that the initial investigation
had missed: `pump-rust-client` **0.1.13**, linked from the official Pump documentation and
published at **2026-09-09 11:18:35 UTC**. Its downloaded archive matches registry SHA-256
`29a237bca320b7bad7b4a9ca900dbf93236a1ca4527464b87777426a63de1a6d`.
The reviewed subset is retained in `tests/fixtures/pump_rust_account_contract_0_1_13.json`.
No Rust runtime, dependency or program binary is added to the app.

These definitions exactly explain all four previously rejected public shared accounts:

| Account | Newly understood fields | Complete parsed bytes |
| --- | --- | ---: |
| Pump FeeConfig | `exotic_flat_fees` | 177, then zero allocation padding |
| PumpSwap FeeConfig | `exotic_flat_fees` | 2,097, then zero allocation padding |
| Pump Global | `creator_fee_configurable`, `max_configurable_creator_fee_bps` | 1,054 |
| PumpSwap GlobalConfig | Same creator configuration fields | 949 |

Both observed global gates were enabled with a maximum configurable rate of 100 bps. The current
curve/pool contract also adds `creator_fee_bps` and `can_edit_creator_fee`. These are economic
fields; merely ignoring the old decoder's remainder would have missed the creator override.
The stream TradeEvent/BuyEvent/SellEvent fields match the earlier definitions. Create events have
appended fields, so replacing all shared IDLs would introduce unnecessary historical-decoding risk.

The authorised implementation therefore adds a small reserve-only adapter after the existing
pinned prefix decoder. It recognizes the documented fields, supports exact legacy prefixes,
validates boolean encodings, rejects partial extensions and retains rejection of subsequent
nonzero unknown data. It does not change stream/event decoding or request scheduling.

Fee selection follows the reviewed Rust source:

- `math/fees.rs`: a nonzero stored creator rate replaces the scheduled rate while the global
  gate is enabled. Zero selects the schedule; a missing creator incurs no creator fee. The
  configuration maximum and permission to edit are not trade-time clamps. Effective rates
  outside the application's existing safe range remain rejected.
- `sdk/mod.rs::fee_tier_supply`: Mayhem PumpSwap pools use fixed supply for fee-tier market cap;
  ordinary pools use current verified mint supply. This corrects a discrepancy with the older
  reference. A burned-supply regression crosses a fee-tier boundary and verifies the difference.
- `math/bonding_curve.rs::fee_for_quote`: curve sell supply selection remains unchanged:
  Mayhem uses current verified supply and ordinary curves use fixed supply.
- SOL schedules, noncanonical flat fees, component rounding, real quote-vault capacity and
  original network/priority costs remain enforced. Reading the exotic fee fields does not
  enable new quote currencies. Invalid mint supply is still rejected before fee selection.

New route receipts identify `learning-account-snapshot-v2` and `pump-rust-client-0.1.13`, with
the observed creator gate and stored rate. This is an audit recipe version, not a reset of
Champion proof or permission. Historical receipts, expired checkpoints, entry costs and
saved learning/Coach state are not rewritten; schema 16 is unchanged.

Stage evidence:

- Four public-account regressions failed under the earlier code with
  `unreviewed_account_extension`, then passed after the adapter. The first-stage set passed
  **158 tests**, including old layouts, all partial extension lengths, invalid booleans,
  unknown future tails, existing fee fixtures and stream decoding.
- A configured-creator regression reproduced the incorrect scheduled rate `(0, 5, 7)` where
  `(0, 5, 75)` was required. After the fee change, **211 focused tests passed**. Four new
  zero-supply checks initially expected the later fee guard; they were corrected to assert
  the existing earlier `mint_not_verified_safe` rejection. No safety rule was relaxed.
- The integration/pressure set passed **141 tests**. Current public shared configs combined
  with configured route fees produce durable outcomes in both Discovery and Policy lanes.
  Reload preserves receipts; repeated requests and late evidence do not rewrite checkpoints.
  Held-position refresh works with learning Off and rejects stale and future-unknown layouts.
- One independent six-account public PumpSwap snapshot at **09:06:56 UTC**, confirmed slot
  **445845789**, is retained in `pump_reserve_snapshot_20260910.json`. The complete mint,
  configs, pool and vault set passes validation without changing any bytes. All **9 public
  snapshot/integration checks passed**. This is offline validation, not proof of live recovery.

A bounded before/after comparison alternated the previous and revised validators on the same
five legacy routes, with real isolated learning writes and governance. Each batch produced
**20 checkpoint updates** and identical economic outcomes. After two warmups, ten samples each
gave median **7.37 ms before / 6.58 ms after**, with maxima **19.11 / 11.80 ms**. These small,
noisy, single-CPU samples do not establish a speedup or sustained burst capacity. They show no
obvious added bottleneck in this bounded workload. The fix's benefit is accepting verified current
accounts correctly; rejected live requests previously avoided the resulting learning writes.

Final release checks for this implementation:

- Full backend suite: **1,535 passed** in 175.93 seconds, using isolated temporary data,
  a read-only source mount, no network and one CPU. No production database was mounted.
- Full frontend suite: **370 passed** across 21 files, with one test worker.
- Strict backend typing passed for 42 source files. Ruff lint and formatting passed for
  127 backend/test files. ESLint and `git diff --check` passed.
- The release-candidate Docker build, TypeScript compilation and production frontend build
  passed. Its 44 packaged backend Python/JSON files match the current source hashes, and
  runtime dependency versions match the backend test environment.
- The packaged validator accepts the complete independent public PumpSwap snapshot and
  selects fee components `(20, 5, 35)` with the reviewed recipe.
- A fresh-data, network-disabled smoke container returned healthy service/database status
  and version **1.10.10**. The new reserve-health contract reported four components without
  an alert before collection starts, and the authenticated packaged frontend was served.
  The unauthenticated frontend correctly returned 401. No strategy was started for this
  startup check; it does not demonstrate sustained market processing. The test container
  was removed afterward without touching the live container.

Existing Starlette deprecation, frontend Fast Refresh and large scene-chunk warnings remain;
none failed these checks. The candidate image is
`signal-arcade:v1.10.10-reserve-compat-review`, digest
`4cfd9f7c1595eb37afea1927fb8fb8366f7b2120bffb00fff7ce2446b3c3788d`.

The live app was not restarted, deployed or changed during implementation. At that stage it ran
the prior image (`e87ea03911476fc0700bc61dfbef2812a760fa205e5755a0536fa91aa6681a03`), which rejected
the current shared layouts. The required approved rollout and collection verification were
completed subsequently, as recorded below. A longer observation across mature cohorts is still
required to assess coverage and learning performance. No Entry Champion or 70% result is promised.

Rollback requires no schema migration. Reverting to the previous image reintroduces the known
shared-account rejection and removes the new warnings; it is a containment option, not recovery.

### Final edge-case recheck

The additional recheck added eight fee-boundary cases: an effective total of 9,999 bps remains
within the existing validator limit, exactly 10,000 bps is rejected, and an inapplicable stored
creator rate cannot change the effective fee when its gate is off or its creator is absent.
Both venues preserve the original input state. These are validator boundary tests, not a
recommendation to trade markets with such fees; quote and Baseline checks remain separate.

All **311 focused tests passed** in 54.45 seconds, including the new cases, public and legacy
account layouts, malformed extensions, learning/held-position integration, stale and duplicate
results, checkpoint deadlines, collection counters, veto fallback, replay/restart continuity,
skill recovery and pressure/cancellation boundaries. No further runtime change was needed.
The earlier full backend/frontend results above still describe the same runtime source; the
eight new cases were verified in this focused run. Ruff lint/formatting and `git diff --check`
passed after formatting the added test code.

All six release version references (backend, Python package, both JavaScript packages, Docker
label default and README) agree on **1.10.10**. README local links/assets resolve, and its Docker
Compose example passes `docker compose config --quiet` with a test-only password substitution.
No services were started by that check. The 44 packaged backend Python/JSON files still match
the reviewed source exactly. README already records the current fix and the pending live
validation, so no additional README wording change was required. The live app was not updated,
restarted or used for testing during this recheck; the approval and rollout followed afterward.

## Authorised reserve-fix rollout

The user approved updating the live app after implementation and validation. The reviewed image
`4cfd9f7c1595eb37afea1927fb8fb8366f7b2120bffb00fff7ce2446b3c3788d` was deployed locally on
**10 September 2026**, with startup verification complete at **09:36:40 UTC**. Nothing was pushed
or published by this rollout. A final comparison confirmed that all 44 installed live backend
Python/JSON files match the reviewed source exactly.

The app's upgrade-preparation flow settled without cancelling any pending orders. Logs confirmed
graceful application shutdown. A complete stopped-volume backup was compressed and verified by
per-file size and SHA-256 before replacement: five files, a **2,901,013,037-byte** archive, and
449.41 seconds for backup plus verification. The original image remains available. No schema
migration or data restoration was performed.

The new container uses the same data volume and exactly the same container environment. Only the
local Compose image selection changed. The paper engine resumed on the same season; the execution
audit remained verified, learning stayed Active, and Champion/Coach permissions were preserved.
Sizing remained active and healthy. Exit was already suspended before the update and stayed
suspended; this rollout did not re-enable it or relax its proof requirements.

Serial observations through **09:49:03 UTC** confirmed the intended recovery:

| Observation | Accepted reserve snapshots | Checkpoint updates | Refresh worker errors |
| --- | ---: | ---: | ---: |
| Old build, preflight | 0 | 0 | 0 |
| 09:37:29 UTC | 18 | 18 | 0 |
| 09:39:41 UTC | 76 | 76 | 0 |
| 09:45:02 UTC | 150 | 150 | 0 |
| 09:49:03 UTC | 212 | 212 | 0 |

Counters start a new process scope on restart; this table demonstrates restored acceptance, not
an equivalent-load throughput comparison. By the final observation, both curve and swap routes
were verified for learning and for the held-position watchdog, with no shared-layout failures.
Four missing route identities and five context/pressure discards remained honestly reported.
An accepted snapshot or checkpoint update is not necessarily a usable economic outcome.

The existing five-minute clean-history safeguard delayed new enrollment after restart. Fresh
Discovery and Policy records appeared once that window completed. Bounded indexed read-only
samples then verified saved `learning-account-snapshot-v2` / `pump-rust-client-0.1.13` receipts
at one- and five-minute horizons. In a small mature sample, 16 of 22 Discovery primary outcomes
and both sampled Policy primary outcomes were usable. The Policy samples were stream-derived;
do not attribute them to RPC refresh. This selected, tiny sample is **not** the coverage metric.
The final rolling Entry activation coverage was **33.6% over 1,000 observations**, compared with
33.7% before the update. Downtime, retained history and immature new cohorts prevent a claim of
sustained coverage improvement. The 70% requirement remains intact and Entry remains unqualified.

A fresh training fit completed at **09:47:27 UTC**, with publication, no failure and no stale-job
discard. Another training request was queued at the final observation. Coach research/contribution
permission stayed enabled; Coach reported no error and waited for outcomes or yielded to market
work. No new Coach handoff or qualification is claimed.

Eleven retained diagnostic intervals covering the observed boot recorded **106,504 enqueued** and
**105,244 processed** events, with **zero shed and zero expired**. All interval worker-health
samples were healthy. Queue maximum was **863**, processing-lag maximum **4.268 seconds**, and
critical-lag maximum **3.977 seconds**. The largest delay occurred in **09:46:54–09:47:56 UTC**,
which also contained the training publication: event-persistence wait reached 3.417 seconds and
heartbeat wait 2.487 seconds. These overlapping wall-clock phases do not establish a single cause.
The delay recovered without event loss. At the final live snapshot, queue depth was 14, processing
lag 0.016 seconds and critical lag 0.026 seconds. There were no degraded reasons, container
restarts, OOM events, provider reconnects or warning/error lines in the bounded post-start log.

Diagnostics recording continued across the restart, retained previous history and wrote new
collection events. It reported zero dropped records and one deliberate collection deferral.
The final acknowledgement age was about four seconds. No full live export or database scan was
needed; historical reads used the existing bounded read-only diagnostic reader.

The desktop browser-control runtime failed to initialize, so an existing headless browser was
used for the UI check. All six main tabs and Challenger loaded without JavaScript errors, failed
HTTP responses or attempted state-changing requests; 61 WebSocket frames were received. A brief
initial Issue label cleared without intervention; subsequent views and the final mobile Arena
showed All good. The 390-pixel mobile layout had no horizontal overflow. These browser observations
and the light API checks add some load; no test suite, build or benchmark ran during observation.

The identified compatibility release blocker is resolved and live-verified. No additional blocker
was found in this bounded check. The release is ready for community push with the documented
operating limits. Longer observation across mature cohorts and busier markets remains necessary;
the short check cannot establish profitable learning, 70% coverage or issue-free long-term operation.

### Final release-readiness recheck — 10 September 2026

The final serial, read-only live sample at **10:08:23 UTC** was healthy: all seven workers were
running, the queue was empty, processing lag was **0.016 seconds** and critical lag was
**0.030 seconds**. All 44 installed backend Python/JSON files still matched the reviewed source.
The container had no restarts or OOM event, and the bounded post-start log contained no warning,
error or traceback lines. No restart, deployment, settings change or live test workload was
performed during this recheck.

Reserve refresh had accepted **509 snapshots and written 509 checkpoint updates**, with zero
refresh-worker errors. Both venues remained verified for learning and held-position refresh.
Training had completed **seven runs and seven model publications**, without failure or stale-job
discard. Diagnostics were recording with zero dropped records. Sizing remained active and healthy;
Exit retained its existing suspension. Coach permission remained enabled, with no error, while
research yielded to protection of open positions. Rolling Entry coverage was **36.0% over 1,000
observations** and remained unqualified. These observations confirm restored collection and
ongoing training, not a demonstrated path to 70% coverage or better trading returns.

The longer retained sample comprised **27 diagnostic intervals**, with no shed or expired events
and healthy worker samples throughout. It also exposed a larger transient delay: during
**10:02:19–10:03:19 UTC**, queue depth peaked at **2,086** and overall processing lag at
**11.585 seconds**. Critical lag in that interval peaked at **2.620 seconds**; the maximum across
the retained sample remained **3.977 seconds**. The queue returned to zero before the interval
ended and was also zero at the end of the following interval. The affected interval included a
6.563-second event batch, 2.844-second market-lock wait and 2.842-second snapshot phase. These
overlapping measurements do not isolate a cause, and review requests may contribute some load.
Burst latency therefore remains a documented performance limitation requiring longer observation,
even though this burst recovered without recorded event loss.

Ruff lint/format checks, release version consistency, README local links and `git diff --check`
were rechecked. The existing full and focused regression results above still apply to the
unchanged runtime source; no redundant full test run or new dependency audit is claimed. No
additional correctness or compatibility release blocker was identified. Community release remains
appropriate with these operating limits; issue-free long-term operation is not established.

## 12 September staged follow-up

Historical investigation below: the later **Holder rewards and dashboard recheck** section
supersedes the unknown-Global conclusion and records the newly verified official contract.

This section supersedes the historical release-readiness statements above. Version remains
**1.10.10**. Existing uncommitted work was preserved. This follow-up has made no live deployment,
restart, setting, permission or database changes. Tests use temporary databases in a separate,
network-disabled container limited to one CPU and 1,536 MiB, with source mounted read-only.

### Compatibility investigation: additional Global suffix remains blocked

A bounded mainnet read at **2026-09-12 15:54:09 UTC**, slot **446468460**, captured the public Pump
Global account. Its owner is the expected Pump program and it is not executable. It is **1,087
bytes**, with **33 nonzero suffix bytes beyond the 1,054-byte reviewed layout**. The fixture
`tests/fixtures/pump_global_unreviewed_20260912.json` records its bytes and SHA-256
`6afa5f43e71cf99644f62568a48666fe970f8396a4c4d6bd144e14bcc522cc6f`.

The checked official [`@pump-fun/pump-sdk` 1.37.0](https://www.npmjs.com/package/@pump-fun/pump-sdk/v/1.37.0)
was published on 10 September. Its Global definition ends with `creator_fee_configurable` and
`max_configurable_creator_fee_bps`; it does not explain the new suffix. The
[`pump-rust-client` 0.1.13](https://crates.io/crates/pump-rust-client/0.1.13) contract remains the
reviewed source for the earlier extensions. The program-owned Anchor IDL and checked
[official public IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json) are older.
SDK archives were inspected as data, not installed or executed. No semantic meaning is inferred
from the apparent shape of the unknown bytes.

The new public-account regression reproduces `unreviewed_account_extension`. The validator still
rejects it. Mixed five- and ten-route integration tests prove that affected curve snapshots
cannot write Discovery or Policy checkpoints, while independently valid PumpSwap routes proceed.
The rejection does not mutate live feature states. The earlier 10 September compatibility fix
remains useful for the reviewed layouts; it does not establish support for later fields.

**Remaining release blocker:** establish the new fields' authoritative semantics, then implement
and validate the minimal adapter change with fee, flag, legacy-layout and watchdog checks.
Accepting arbitrary trailing bytes or suppressing the warning is not a fix. A larger batch
cannot repair this compatibility failure.

### Implemented diagnostics and dispatch changes

- Shared-layout rejections retain fixed-size diagnostic context: account/known-layout lengths
  and a SHA-256 over at most the first 4,096 bytes. Four independent health components retain
  detached copies; a matching accepted snapshot clears only its own sample. No account body,
  provider URL or credential is added to diagnostics.
- A separate optional `reserve_layout` event runs at most once per five minutes per learner
  scope, leaves two collection slots free and yields to queued proof. Deferred samples can
  retry after the queue drains. Distinct hashes for all four components fit the unchanged
  768-byte compressed event budget and survive real storage/export reads.
- The Policy collection event adds bounded process-cumulative dispatch decisions and separate
  dispatch/resumption wait totals. Their boot scope and attempt units are explicit. Existing
  combined interval waits remain intact. A stress test caught excessive size when separate
  timings were initially added to core intervals; that approach was removed. The final design
  keeps existing interval/event budgets and existing metrics.
- Market events dispatch checkpoint work only when the pending mint has a due horizon or
  needs completion. Discovery and Policy use their own original clocks; no stale-route result,
  admission rule or outcome is cached. Due work, expiration and its honest missing denominator
  remain unchanged. Features, AI outcome handling, broker updates, pending orders, training,
  Champion/Coach permissions and all proof requirements retain their existing paths.

The before-change regression failed on the missing due-work guard. A differential test then
replayed the same **1,312 timestamps for four mints**, with duplicate/backward times, independent
Policy clocks, stale reserves, insufficient liquidity, a Discovery-only training record and a
midstream restart. Both cached and streamed paths produced **identical complete persisted
observations, Policy episodes, training rows and retained Policy identities**. Dispatches fell
from **4,942 to 551** in each case. This is a count of unnecessary handoffs avoided in that
declared workload, not an 89% improvement in live throughput or coverage.

Exact due instants, grace-window boundaries, overdue horizons, Policy-only mints and pending
completion were checked. Held-position feature/broker processing continues on non-due events.
Cancellation still holds the owner boundary until the worker finishes, including repeated
cancellation and worker errors. Counters saturate, nonfinite timing values are ignored, disabled
diagnostics remain inactive, and timings are aggregated only on the owner thread.

### Capacity assessment: no setting increase

Five- and ten-route batches passed real decoder, fee calculation, durable checkpoint, duplicate
response, expiration and restart checks using the reviewed 10 September account fixtures.
Single application samples were approximately **62 ms for five routes** and **105 ms for ten**;
expired-response samples were approximately 2 ms and 6 ms. These include isolated SQLite writes
and normal outcome handling but exclude RPC latency, production history size and sustained
load. Type checking was also using host resources during this sample. They establish bounded
functional behavior, not a safe production lock-duration limit or equivalent-load benchmark.

The unchanged scheduler experiment still found fewer deadline misses with ten slots under its
declared synthetic arrivals. It is conditional evidence, not a coverage forecast. The live
five-route setting, configured maximum, request cadence, provider limits and backpressure remain
unchanged. Revisit capacity only after account compatibility is restored and equivalent mature
cohorts show collection capacity remains limiting; validate urgent processing before rollout.

### Runtime interpretation and readiness

At **15:43:01 UTC** all seven live workers were healthy, queue depth was 60, critical lag was
0.099 seconds and overall lag 0.161 seconds. The learning refresh had accepted 58,196 snapshots
and updated 58,966 checkpoints since boot, with no refresh-worker errors. These totals span
earlier successful curve collection and current swap collection; they do not demonstrate that
the new Global account was accepted. Shared-Global failure counters were 64 learning batches
and 128 watchdog batches, while PumpSwap remained verified.

The retained **15:20:48–15:45:23 UTC** sample contained 23 intervals, 415,767 enqueued and 402,082
processed events, with zero new shed or expired events and healthy worker samples. Queue peak
was 3,377, critical-lag peak 7.609 seconds and overall-lag peak 14.542 seconds. Event learning
recorded 74,435 calls, 116.515 seconds of parent wall time, 36.769 seconds of worker CPU and
75.023 seconds of combined dispatch/resumption wait. Phases overlap; their sum is not total CPU
usage. Review requests overlap the sample, and not every measured call or wait is avoidable.

The matching Entry fits at **15:39:56–15:39:57 UTC** had 468 usable outcomes per 1,000, with 296
training and 156 validation rows. Linear's validation error was about 0.936, versus XGBoost's
0.940; both had positive top-group returns, but XGBoost had not earned its complexity gate.
Coverage remained below 70%. This newer fit supersedes earlier negative-top-return observations;
an Entry Champion is not promised by these changes.

Sizing v4's retained promotion and separate activation evidence were independently recomputed
with the exact retained Policy identities and bounded multipliers, matching the stored means
and conservative bounds. No Sizing promotion/activation defect was found. Exit remained
suspended following a failed fixed recovery trial; its missing advantage/harm proof is not
repaired by increasing collection counts or by retrying the same failed window.

The local improvements preserve schema and proof semantics, so rollback does not require
rewriting observations or resetting learning. Deployment and post-deployment observation remain
separate. The live app still runs the 10 September image; no live performance gain from this
follow-up is claimed. Community readiness remains on hold for the new Global compatibility gap.

### Final validation and live recheck

- Full backend invocation: **1,563 passed** in 644.20 seconds, with one harness failure because
  the version test's root manifests were not mounted. The unchanged version test then passed
  separately with those files mounted read-only: **all 1,564 collected backend tests passed
  across the two invocations**. The existing Starlette/AnyIO deprecation warning remains.
- Final scheduling/collection stage suite: **137 passed** in 50.61 seconds. The preceding
  diagnostics/cancellation suite passed **124 tests**. Full regression includes the added
  saturation, mixed-new-layout and differential evidence cases.
- Strict Mypy: **42 source files passed**. Ruff lint and formatting: **129 files passed**.
  `git diff --check`, release metadata consistency and documentation local-link checks passed.
- Frontend: **370 tests passed across 21 files** in 159.37 seconds. ESLint, TypeScript and the
  production build passed. Existing Fast Refresh and large lazy scene-chunk warnings remain.
  The host pnpm command could not resolve its local dependency setup; it aborted before lint.
  Validation instead copied the current frontend into a disposable offline container, after
  checking every installed direct dependency against its exact pinned version. No dependency,
  lockfile, source or build output was installed into the live app.

The final health request at **16:25:17 UTC** confirmed all seven workers running, a healthy
database, queue depth zero, overall lag **0.012 seconds** and critical lag **0.169 seconds**.
The live container still used `v1.10.10-reserve-compat-review`, started **10 September 09:36:18 UTC**,
with zero restarts and no OOM event. Its learning refresh had accepted 58,214 snapshots and
written 58,984 checkpoint updates since boot, with no refresh-worker errors. Curve Global
validation remained blocked for learning and the watchdog; swap validation remained verified.

This was **not an all-clear performance result**: cumulative candidate expirations increased
by **1,035** since the earlier health sample, with no additional admission shedding. Bounded
retained-history reads located 11 expirations in **15:56:35–15:57:51 UTC** and 1,024 in
**16:21:21–16:25:30 UTC**. The latter 249-second diagnostic interval carries `recording_gap`,
with 77,243 enqueued, 67,242 processed, queue peak 6,025, overall-lag peak **21.211 seconds** and
critical-lag peak **7.575 seconds**. Its event batches occupied 241.789 seconds, including 17.801
seconds of event learning; snapshots, persistence, heartbeat and training publication also
overlapped. This does not isolate a single cause or show that the dispatch change alone will
remove the bottleneck.

The larger loss interval overlaps isolated backend/frontend validation on the same host. Tests
were bounded and used no production data, but they still shared host resources. These intervals
must not be used as a clean before/after performance comparison or attributed solely to the
market, dashboard, Coach or Champions. No new changes were deployed during them. A future
rollout needs observation under comparable market load without concurrent validation, preferably
with heavy development checks on a separate host. The new diagnostics should help separate
avoidable dispatch waiting from remaining execution costs; it does not retroactively recover
lost events or prove sustained capacity.

### Follow-up edge-case recheck — 12 September

No runtime changes or live deployment were made in this recheck. Four additional test cases
strengthen the existing suite: the actual event handler resumes Discovery and Policy at their
separate due times while continuing AI and pending-order updates; a later indexed Policy
episode remains eligible even when an earlier one is complete or not yet due; and both maximal
diagnostic-family scenarios also accept five queued proof events, two collection events and a
layout event carrying four distinct hashes. The combined recorder input and compressed storage
bounds were checked together, with no proof displaced or new size allowance.

The focused suite passed **64 tests in 15.60 seconds**, including those additions, exact horizon
boundaries, stale/illiquid routes, restart equivalence, joined cancellation, counter limits,
layout rejection and mixed five-/ten-route batches. Ruff lint/format and `git diff --check` passed.
The earlier full backend/frontend results apply to unchanged runtime source; this was a focused
follow-up, not another full endurance run. No additional runtime defect was found. The Global
compatibility gap, conditional capacity decision and clean live burst validation remain open.


## Holder rewards and dashboard recheck — 12 September

This section supersedes the earlier unknown-Global conclusion. The direct official repository
revision check found the holder-rewards merge at **2026-09-12 15:58:18 UTC**, commit
`f216b6724c6ede79d7cef9ce210b741f7e17e93b`. The checked npm SDK 1.37.0 had not described the suffix.
The pinned [official holder-rewards documentation](https://github.com/pump-fun/pump-public-docs/blob/f216b6724c6ede79d7cef9ce210b741f7e17e93b/docs/HOLDER_REWARDS_README.md)
and account definitions now do. They explain the 33 bytes as a claim-authority public key and
creation-enable boolean; BondingCurve and Pool each append a holder-reward boolean.

Independent contract hashes are retained in `tests/fixtures/pump_holder_rewards_contract_20260912.json`:

- Pump IDL SHA-256: `ffe966c42f1af41652ee753fe2f1e3f7cd4077d7e6f49faf3138959c8b56064b`.
- PumpSwap IDL SHA-256: `2091433899b07d003d98118ae6cd3c628960fd393b40710b6e15bce6d0e7f2d1`.
- Holder-rewards documentation SHA-256: `9ee0be922393c75e5f359d5e222f3e112e3f7cb6b73446fdbc7da095461900c9`.

The original public Global fixture reproduces rejection before the adapter change and passes
after it. The historical fixture filename and original rejection metadata are retained as audit
context. A synthetic future byte added *after* the complete reviewed layout still fails, and
its bounded diagnostic reports 1,088 account bytes versus 1,087 reviewed bytes. Invalid boolean
values and nonzero partial claim-authority fields remain rejected. Earlier zero allocation
padding retains its existing meaning; absent legacy holder flags are false.

The official contract states that holder rewards redirect the existing creator fee without
changing trade instructions or fee amounts. Tests cover both fee-gate states, both creation
permission states and holder/non-holder routes on Pump and PumpSwap. Turning off creation does
not make existing routes untradeable. No holder income is fabricated, and the creator fee is not
charged twice. Receipts add the account-contract revision and holder flag while preserving the
fee recipe and proof version. Pinned stream IDLs, fee rounding, quote-currency restrictions,
request/slot/owner/PDA checks and previously saved outcomes remain intact.

Integration fixtures combine the independently captured Global with validated curve/pool route
fixtures. These are declared synthetic account sets, not same-slot mainnet captures. Five- and
ten-route tests cover due and expired Discovery/Policy checkpoints, duplicate responses, persisted
restart recovery and unchanged original state. The watchdog exercises holder-reward routes with
learning off, as well as stale and future-unknown account rejection. The live batch setting was
not changed.

### Dashboard work and remaining performance limits

The live reader still holds the market boundary throughout snapshot assembly. During the
read-only investigation, the **16:33:30–16:40:36 UTC** retained sample contained 127,364 enqueued
events (about 299/second), zero new shed/expired events and healthy worker samples. Overall lag
peaked at 17.491 seconds and critical lag at 7.825 seconds. A snapshot took 4.593 seconds inside
the boundary. These maxima do not establish one snapshot as the cause of the entire burst.
The last health read at **16:43:40 UTC** showed 0.929-second overall lag, 0.097-second critical
lag, queue depth 368 and unchanged loss counters, while curve account validation remained blocked.

An isolated synthetic status profile found repeated feature-vector completeness validation:
1,200 Discovery records were checked 3,600 times in one status response. A regression reproduced
three checks per vector before the fix. The response now reuses only those validation results
within the same synchronous owner-locked view. Temporary storage is thread-local and cleared
on completion/error; it is not shared with another response, training workspace or worker.
Standalone fitting/coverage paths select the original validator once and avoid per-row display
cache lookups. Outcomes, Policy identities, scope, permissions, health, coverage and activation
still use their normal checks. The market consistency/cancellation lock is unchanged.

Complete before/after responses matched on identical synthetic populations. A 4,200-Discovery /
200-Policy alternating wall-time sample was noisy: before median 0.256 seconds, after median
0.296 seconds; it does **not** demonstrate a latency improvement. A separate 1,200-Discovery
thread-CPU sample measured medians 0.0335 versus 0.0317 seconds. These small samples establish
less duplicate work and equal output, not a live throughput percentage or a complete burst fix.

The verified compatibility repair and the already-tested due-checkpoint dispatch change should
be assessed after controlled deployment, without simultaneous development test workloads.
If substantial snapshot stalls remain, isolate the expensive snapshot subcomponents before
moving any work outside the consistency boundary. Do not remove the lock, cache trading health,
weaken proof, enlarge the queue or increase the live collection batch merely to hide pressure.

No live deployment, restart, setting, permission or database change was made in this follow-up.
The live image remains the 10 September `v1.10.10-reserve-compat-review` build. Source validation
cannot establish live collection recovery or sustained burst performance for the new changes.
No Entry Champion, 70% coverage outcome or long-term trading improvement is guaranteed.


### Validation completed for this follow-up

- Compatibility stage: **149 passed**, covering the independent holder contract, public account
  captures, fees, original refresh checks, layout diagnostics and durable integration paths.
- Initial dashboard/proof/cancellation stage: **92 passed**.
- Broader relevant regression: **777 passed in 451.01 seconds**, with the existing Starlette/AnyIO
  deprecation warning. This covered learning, current collection, Policy identity, independent
  participation, Coach lifecycle, skill recovery, contextual Exit, API/security, provider safety,
  Results boundaries, diagnostics and market bursts. It was a relevant broader suite, not another
  full frontend/endurance run.
- After the final refinement keeping standalone validation on its original direct path and
  adding missing/nonfinite feature cases, **121 focused tests passed in 36.13 seconds**. This
  includes the final dashboard reuse, independent proof/health, due dispatch, holder contracts,
  durable collection/restart and diagnostic size/isolation checks.
- Ruff lint and formatting passed for all **131 backend/test files**; `git diff --check` and
  documentation local-target checks passed. Frontend source was not changed in this follow-up.
- Final strict Mypy check passed for **44 source files**, using a temporary container cache.

All validation used isolated synthetic data in an offline one-CPU container with no live-data
mount. Test workloads still shared host resources; they are not clean live performance samples.
The remaining release step is controlled deployment and confirmation that curve refresh actually
recovers and critical processing remains acceptable under comparable market load. No evidence
from this follow-up establishes sustained burst-free operation.

## Holder-rewards rollout — 12 September

The user authorised the update after another edge-case review. The final focused checks covered
dashboard reuse, due dispatch, reserve integration, holder contracts, validation health, skill
recovery and API/startup behaviour: **167 passed in 129.09 seconds**, with the existing test-client
deprecation warning. No additional runtime source change was needed in this rollout.

The built image is `signal-arcade:v1.10.10-holder-rewards-20260912`, image ID
`sha256:8e1af3058626a340d675fbab6a0c2aff784c8a05f04a2f907e2b9c32d8122a5e`.
An offline packaged-image smoke check matched all 44 source/resource files against the reviewed
backend, served the bundled frontend, started all workers and shut down cleanly with temporary
data. This also exercised the actual built image's dependency set.

Only the app service was recreated, at **17:21:12 UTC**; application startup completed at
**17:21:36 UTC**. Its named data volume, environment, ports, risk mode and permissions were
preserved. The ignored local Compose image pin now selects this build on subsequent starts.
The previous `v1.10.10-reserve-compat-review` image remains available for rollback. Ollama was not
recreated, and no public release was pushed. No database records were manually edited.

Before the update, both learning and watchdog curve validation reported the unsupported Global
layout. After startup, all four learning/watchdog and curve/swap components reached **verified**.
At **17:23:40 UTC**, learning refresh had accepted 52 routes and updated 53 checkpoints, and a
new training publication had completed without error. The fixed batch size remained five.

A bounded, indexed read sampled 24 pending observations with a 250 ms query deadline. Ten saved
checkpoints carried the new account-contract revision, including holder and non-holder routes.
The sample contained both usable outcomes and explicitly unavailable executable exits: account
compatibility does not invent liquidity or remove valid failures from coverage. Collection
diagnostics were retained across restart. The first new dispatch event recorded four due worker
handoffs and 1,436 idle handoffs avoided; these counters are per boot, not coverage percentages.

Season 46 and its original start time were retained. Automatic support and Coach contribution
permissions stayed enabled; the same Sizing artifact remained active. Coach stayed in Shadow
with no direct influence and initially deferred optional research to protect open positions.
Entry remained unqualified: the early dashboard showed 357/1,000 current usable outcomes, with
the 70% requirement unchanged. Most of this rolling cohort predates the repair.

These initial observations establish live compatibility recovery and retained state, not
sustained performance or future Champion qualification. The restart begins a smaller watch set;
post-update load must not be treated as equivalent to the previous long-running instance merely
because its queue is smaller. Build/test workloads finished before the post-update observation.

### Retained observation and final health

Eight retained intervals from **17:21:25 to 17:29:39 UTC** covered 493.86 seconds and 84,655
received events (about 171/second). They recorded zero shed or expired market events, healthy
worker samples, zero training errors and zero dropped diagnostic records. The first interval was
correctly marked partial; subsequent intervals had no gap flag. Peak overall lag was **4.694 s**,
peak critical lag **2.647 s**, and maximum queue depth **720**. Three requested snapshots took
0.694 to 2.422 seconds. Brief stalls still exist; this is not evidence that bursts are eliminated.

The **17:29:49 UTC** LAN health read reported all seven workers healthy, database healthy, queue
depth zero, 0.025-second overall lag and 0.012-second critical lag. All reserve-validation
components were verified, with no layout failures after restart. Learning had accepted **170
routes**, saved **172 checkpoint updates** and completed **two training publications**, without
worker or training errors. These counts include unavailable checkpoints and are not a claim of
172 usable Entry outcomes. Normal route-identity failures, context/pressure discards and protective
deferrals remained visible instead of being suppressed.

The second collection emission recorded 294 due handoffs and 9,826 idle handoffs avoided.
Checkpoint expiry counts in those collection events are separate from market-event expiry:
some overdue evidence still closed unavailable. Coach subsequently attempted evaluation at
17:26:21 UTC and returned to waiting for outcomes; its saved permissions and direct-influence
boundary were unchanged. A refreshed dashboard still showed Sizing v4 active, Exit v1 suspended,
and Entry collecting proof with current coverage 359/1,000. No recovery or activation was forced.

The live repair is working and the instance can continue observation. This short, lighter-load
sample does not establish the outcome of mature post-repair Entry cohorts or weeks of operation.
No additional source fix was justified by these rollout checks. Rollback, if needed, should use
the retained previous image and the same data volume; it would also restore that image's known
Global-layout rejection. Never reset evidence or the season to make the health view appear better.


## Collection guard recovery and expiry attribution — 12 September

The follow-up review found two separate classes of unavailable evidence. In a bounded
post-deployment Discovery cohort created 17:50–17:53 UTC, all 22 five-minute outcomes had closed:
nine were usable, eight expired with stale cached routes, and five failed executable-quote
checks (four exceeded real quote reserves; one had fees exceeding proceeds). This cohort
includes Policy counterparts and is not the Entry activation denominator. The 18:13 UTC health
read showed healthy workers, no shed/expired market events, 930 accepted reserve refreshes,
946 checkpoint updates and 16 training publications. These observations establish remaining
collection losses, not a causal attribution of every expiry.

### Implemented stages

- Add bounded last-known RPC-stage attribution for expired checkpoints, keeping separate
  observation/episode identities and horizons. Tracking starts at enrollment for new records;
  restored/evicted records have unknown prior history. Close/remove tracking independently of
  late request telemetry. No extra per-attempt database writes or evidence fields are introduced.
- Add worker-local heartbeat timings for positions, cached checkpoints, expiry, Coach, AI,
  profile transitions and season handling. Merge only after joined completion, including
  cancellation/error, and emit optional low-priority detail separately from core intervals.
- Recheck pre-selection temporary guards after alternating 1 and 1.25 seconds. Preserve the
  configured full wait after actual attempts, provider failures, discarded responses, empty
  selection, disabled collection and demo mode. No extra worker, parallel request, quota
  exemption, new outcome retry or checkpoint deadline change is introduced.

The regression was demonstrated before the scheduling change: the real worker loop made no
requests in a virtual 40-second run when 200ms maintenance windows coincided with every ten-second
poll. The corrected loop requests after one second in that scenario and keeps at least eleven
seconds between starts when each request costs one second and the configured wait is ten.
This is a controlled timing reproduction, not a prediction of live outcome coverage. Repeated
one-second maintenance alignment, sustained pressure and the 300-second interval limit are
also covered.

### Capacity decision

The existing equal-arrival synthetic scheduler experiment still shows fewer expired checkpoints
with larger batches, without removing independently unavailable routes or changing the five
horizons/Policy clocks. An additional real validation-and-persistence test used the same ten
routes with the same receipt time, fees and both evidence lanes. Batches of five and ten produced
identical saved five-minute checkpoints, and neither changed the live feature-state fixtures.

One offline, single-CPU sample measured two five-route applications at 0.040s and 0.089s; a single
ten-route application took 0.110s. The ten-route run had a smaller total in this sample,
but a longer uninterrupted application. The temporary database and ten-route
fixture do not represent the mature live database, active-Champion workload or provider latency.
Batch configuration/defaults therefore remain unchanged.

Retaining a fetched response remains conditional, not implemented: fresh post-scheduling
observations are needed to judge remaining discard losses. Buffering would need additional
receipt-time, changing-horizon, route/context, cancellation and deadline checks. It is not
necessary to ship the demonstrated guard-recovery correction and could add avoidable complexity.

All changes retain the 70% requirement, genuine failures, frozen costs, independent proof,
qualification/activation permissions, existing pause/drain behaviour and held-position protection.
No main-database migration or rewrite is required. No live setting, service, image or database
was changed during this follow-up. Live measurements above precede these new changes; later
validation workloads share the host and must not be treated as an equivalent live comparison.


### Final edge checks and validation

- The staged scheduling/evidence/quota/cancellation checks passed. The isolated new edge suite
  passed 30 tests covering prolonged pressure, disabled/idle/provider pacing, the maximum
  configured interval, restart attribution and repeated cancellation during a heartbeat.
- Full backend suite: **1,665 passed in 567.60 seconds**, in an offline one-CPU container with
  isolated temporary databases and no live-data mount. The existing Starlette/AnyIO test-client
  deprecation warning was the only warning.
- A final saturation check then demonstrated that varied counters near the existing 64-bit
  limit could exceed the 768-byte compressed event bound. Expiry detail now splits by disjoint
  horizon groups only when needed; exact counts, scope and timestamps survive, and each part
  can resume when proof events previously filled the queue. The recorder/storage limits are
  unchanged. This does not modify checkpoint records or core collection counters.
- After that final encoding refinement, **207 focused tests passed in 32.73 seconds**, including
  the new high-counter test, diagnostic storage/export, collection, scheduling, route validation,
  immutable outcomes and joined cancellation. The full suite preceded this small encoding
  refinement; the focused suite verifies the final implementation.
- Final Ruff lint and formatting passed for **134 backend/test files**. Strict Mypy passed for
  **42 source files**. `git diff --check`, version consistency (1.10.10), and local documentation
  target checks passed. Frontend source was unchanged in this follow-up.

No confirmed regression remains in these checks. The scheduling reproduction demonstrates
recovery of otherwise missed acquisition opportunities, not live 70% coverage or an Entry crown.
The new diagnostics identify last observed collection stages and heartbeat substeps; they are
not a complete replay or proof of causation. Batch size and response buffering remain unchanged.
A controlled live update and comparable mature cohorts are still needed to measure the live
effect and decide whether either conditional follow-up is warranted. No restart, deployment,
push, permission change or live setting change was made here.

Rollback remains an image/source rollback retaining the same volume; these changes introduce
no main-database schema change or outcome rewrite. Older diagnostics readers can ignore the
new optional event kinds. Never delete evidence, reset a season or weaken the qualification
requirements to make a comparison appear better.

### Follow-up edge review — 12 September

No further application-code fix was justified by this focused review. Four added regression
cases exercise the real selector, RPC worker, route validator and evidence persistence for
Pump Curve and PumpSwap. A request starts five seconds before the five-minute checkpoint's
90-second grace deadline and finishes either exactly at that deadline or one microsecond
after it. Both Discovery and Policy accept the exact boundary and retain an unavailable
outcome after it; later responses and reloads cannot overwrite the saved outcome. The
market feature state is unchanged.

The surrounding collection, guard retry, diagnostics, checkpoint scheduling, route integration
and joined-cancellation suite passed **139 tests in 28.14 seconds** in the isolated offline
container. Ruff lint, formatting (**134 files**) and `git diff --check` passed. Only regression
tests and this validation note changed during the follow-up. No live request, deployment,
restart or live-data change was made; the collection changes still await a controlled rollout
and comparable live observation before any claim of improved live coverage.

## Collection-recovery rollout — 12 September

The user authorised deployment after the read-only rollout review. An isolated deployment suite
passed **78 tests in 11.89 seconds**, covering upgrade preparation/recovery, joined cancellation,
the exact checkpoint deadline and transient-guard pacing. The existing Starlette/AnyIO test-client
deprecation warning remained. Ruff lint, formatting (134 files) and `git diff --check` passed.
No additional application-code fix was needed during the rollout.

The built and deployed image is `signal-arcade:v1.10.10-collection-recovery-20260912`, image ID
`sha256:8976d76cc569c304b6e4500e764e221cb8a98aa50ed37b7fd030eb19c21b9067`.
The packaged-image check verified all 44 source/resource files, served the bundled frontend,
started every monitored worker and completed graceful shutdown with isolated temporary data
and no external network. Uvicorn's normal re-raised SIGTERM was accepted only alongside a
completed shutdown and no traceback; the initial test-helper assertion expecting exit zero
was corrected without changing the application.

Upgrade preparation completed with no unfilled orders to cancel. The cached dashboard initially
still showed its earlier running state, so the deployment check used the authoritative health and
maintenance endpoints. The app shut down cleanly at **19:15:19 UTC**. A full stopped-volume archive
was read back and every file checksum verified before replacement. The app container started at
**19:24:39 UTC**, with application startup complete at **19:24:57 UTC**. Downtime can expire pending
checkpoint windows; no timestamps, unavailable outcomes or evidence were rewritten to hide it.

The same named volume and schema 16 were retained. All 28 resolved Compose environment settings
matched the previous deployment, and the complete environment fingerprint, ports, mounts and
project identity also matched after replacement. Collection remained enabled at five routes per
batch and a ten-second interval. Only the ignored local image pin and app container changed;
Ollama retained its container identity and start time. The prior holder-rewards image remains
available for rollback. No public image, commit or release was pushed.

Direct comparison verified season 46, its original start, the bankroll, both saved positions'
units/costs/entry identities, the same active Sizing artifact and Coach contribution permission.
Learning resumed in Active mode with automatic support allowed; Coach remained in Shadow and
Exit remained suspended. These checks did not enable additional authority or change the 70% gate.
All 44 deployed source/resource hashes matched the reviewed working tree.

Early live checks verified all four learning/watchdog and Curve/Swap reserve-validation components.
The new `collection_expiry` and `heartbeat_work` events were persisted and read through the normal
bounded diagnostics readers. Restored checkpoints correctly used unknown pre-restart attribution.
The first declared cohort (19:26:39–19:28:39 UTC) contained no enrollments. A fixed later cohort
(19:32:39–19:34:39 UTC) contained 20 Discovery observations, with no read truncation. Its one-minute
results included 14 usable outcomes and six explicitly unavailable executable exits. This cohort
includes Policy counterparts and is not the Entry activation denominator. Later horizons and
the final observation results are recorded below.

### Final live observation and limits

Serial, bounded health/diagnostics observations covered approximately 33 minutes, through
**19:58:05 UTC**. At that read, all monitored workers were healthy, the collection worker had
made 178 requests and saved **574 checkpoint updates**, and training had published **10 models**.
Both Linear and XGBoost artifacts had publication timestamps after the update. Collection and
training reported no worker error. Diagnostics were recording with zero dropped records, and
the market pipeline reported zero shed or expired events. These market-event counters do not
mean every learning outcome was usable.

The bounded retained read returned 32 intervals and 127 events without event-page truncation,
including 12 collection-expiry and six heartbeat-work detail events. Across those intervals,
queue depth peaked at **1,495**, overall lag at **6.594 seconds** and critical lag at **3.531 seconds**.
The maxima occurred in different intervals. Persistence and worker-wait delays occurred during
the burst; this evidence does not isolate a sole cause. The queue recovered without market-event
loss, reaching zero with 0.073-second overall and 0.048-second critical lag at 19:58:05 UTC.
This is successful recovery, not proof that all burst delays have been eliminated.

All horizons of the fixed 20-observation cohort had closed by **19:58:05 UTC**, including the
20-minute horizon and its existing grace deadline. No row was removed from the comparison:

| Horizon | Usable | Executable exit unavailable | Stale cached route |
| --- | ---: | ---: | ---: |
| 1 minute | 14 | 6 | 0 |
| 5 minutes | 13 | 7 | 0 |
| 10 minutes | 10 | 10 | 0 |
| 15 minutes | 10 | 10 | 0 |
| 20 minutes | 8 | 8 | 4 |

Every executable-exit failure in this small cohort recorded `sell output exceeds real quote
reserves`. The four stale 20-minute outcomes remain unavailable; their presence does not by
itself establish whether a scheduling change could have recovered them. RPC collection supplied
usable outcomes at every horizon. These records demonstrate collection and honest failure
accounting, not an equivalent before/after experiment or a complete explanation of Entry coverage.

The dashboard response at 19:58:06 UTC carried an explicit age of 562 seconds; its older learning
figures were not treated as current health. Snapshot refresh is request-driven and can return its
timestamped previous view while the shared refresh completes. A follow-up at **20:02:52 UTC**
returned a fresh view aged 0.58 seconds. Current executable Entry coverage was **480/1,000 (48.0%)**,
still below the unchanged 70% requirement. Health then reported 684 checkpoint updates, 12 model
publications, no worker errors or market-event losses, and queue depth 523 with overall/critical
lag of 2.010/1.335 seconds. Varying cohorts, restart effects and changing traffic prevent attributing
the rolling coverage increase to this change alone.

The season's `portfolio_drawdown_limit_reached` guard was already present in the old-build snapshot
generated at **19:12:13 UTC**, before upgrade preparation. It continued to prevent new paper entries;
learning and the normal automatic-season countdown continued. The rollout did not reset the season,
weaken the guard or grant a suspended skill permission to trade. This limited observation therefore
does not validate new trade execution under active entry conditions.

Final Docker inspection confirmed the expected image, healthy state, zero container restarts and
no OOM kill. The bounded startup-to-final logs contained 22 lines with no warning, error or traceback.
Ollama was unchanged, and the reviewed 44-file source/resource manifest still matched the working
tree. No additional application-code fix was justified by these checks. The verified backup and
prior image remain available; an image rollback would preserve the current volume and evidence.
Do not restore the older backup over newer evidence without a separate recovery decision.

The controlled rollout is complete. Longer observation of comparable mature cohorts and burst
intervals remains necessary before claiming improved sustained coverage or deciding on the
conditional batch-size/buffering ideas. Entry qualification, profitable results and issue-free
long-term operation are not guaranteed. No commit, public image or release was pushed.

### Post-rollout edge recheck — 12 September

A further source review and isolated offline run passed **122 focused tests**, covering guard
pacing, both collection lanes, exact/late deadlines, duplicate/backward observations, route/context
changes, durable restart recovery, saturation and joined cancellation. Six additional diagnostics
capacity/isolation tests passed in **4.86 seconds**. Test containers had read-only source mounts,
temporary test data, no network and no live-data mount. No application source or live setting was
changed during this recheck.

At **20:08:40 UTC**, authoritative live health reported all monitored workers healthy, zero queued
market events, 0.018-second overall lag, 0.040-second critical lag, **794 checkpoint updates** and
**14 model publications**. Collection/training errors and market-event shed/expiry counters remained
zero. The preceding dashboard view generated at 20:05:57 UTC reported Entry coverage of
**487/1,000 (48.7%)**; its age was explicitly checked rather than treating cached data as current.
The image, environment fingerprint and active Sizing identity still matched the verified rollout.

Diagnostics recorded **two additional dropped items since startup**, first visible in intervals
ending 19:59:28 and 20:07:44 UTC. Both intervals and their eight retained detail events survived;
interval sequence numbers remained continuous and both intervals carried `recording_gap` flags.
There were no compressed-event omissions in the inspected intervals. This is consistent with
the bounded detail queue filling, but the discarded payloads cannot be reconstructed from the
retained records. It is a diagnostic-detail limitation, not evidence of a lost learning outcome
or market event. Recording continued through 20:08:49 UTC, and bounded logs reported no warning,
error or traceback. Increasing the queue or suppressing its loss counter was not justified.

The retained 19:46–20:04 sample still contained short bursts (6.778-second overall lag,
2.795-second critical lag and queue depth 1,596 at their separate maxima), with healthy worker
samples and no market-event losses. Test workload and changing traffic prevent using this as a
controlled performance comparison. No new confirmed application defect was found; continued
observation should include both these delays and the frequency of diagnostic-detail loss.

## Coach extended-hold scheduling — 12 September

A targeted read at **20:56 UTC** found a healthy Coach worker waiting behind active positions
with fresh executable marks and `hold / adaptive_extension` assessments. Its prior admission
rule blocked every active position from 30 seconds before the normal review onward, even after
the broker had completed that review and approved an extension. The same snapshot retained
three successful historical screens with zero eligible candidates; waiting and failed screening
were separate conditions, and neither established an inference or learning error.

Three isolated regression cases reproduced the unnecessary block in Safe, Balanced and
Aggressive modes before the admission change. The corrected guard permits an extended hold
only when its assessment is current, belongs to the current season and exit policy, follows
process start and the latest mark, and was made after the effective normal review. Assessment
freshness is capped at 30 seconds or the configured mark limit, whichever is shorter. The
assessment's hold support, age and effective hard deadline must remain consistent. Malformed,
future, pre-restart and stale values fail closed.

Every active position must also leave more than the 75-second inference budget plus a 30-second
guard before its effective hard exit. A second isolated regression reproduced a provider call
outliving its requested timeout; Coach now enforces the budget around the entire asynchronous
inference request. The request's cancellation cleanup releases the provider generation lock.
Timeouts retain the existing failed-review and retry-backoff behaviour and create no hypothesis.

The existing admission checks still run before and after optional work. Pending orders,
unexecutable/stale active positions, incomplete normal reviews, market pressure, maintenance
and training can still defer Coach. A newer unassessed mark closes the extended-hold exception.
Multiple positions are checked independently; a single urgent position blocks new research.
Dormant inventory retains its previous behaviour. Admission uses only bounded in-memory state,
without database reads, fresh quotes, broker reassessment or model evaluation.

Validation on the final code:

- **235 tests passed in 171.11 seconds:** Coach admission, screening, pressure, scheduling,
  recovery, handoff, lifecycle and HTTP-provider behaviour. A complete real screening path
  now reaches fake inference under an eligible hold, preserves the position and order state,
  and resumes after injected pending-order, stale-mark, lag and hard-deadline deferrals.
- The deadline test uses the actual HTTP provider with a stalled mock transport. It verifies
  request cancellation, a released generation lock, a recorded failed review and no hypothesis.
- **111 broader tests passed in 50.70 seconds:** adaptive exits, broker work budgets, contextual
  Exit lifecycle, runtime pressure, risk profiles and API/security. The only warning was the
  existing Starlette test client's deprecated AnyIO alias.
- Repository-wide Ruff lint passed; all **135 Python files** passed formatting. Full backend
  Mypy checking passed for **44 source files**. `git diff --check` passed.

A further edge-case recheck added six regression cases without changing application code.
Cancellation during quota admission or the HTTP request propagates correctly, releases the
generation lock, records no partial review or hypothesis, and permits a successful later review.
The full request deadline also covers a stalled quota admission. Actual broker-produced adaptive
hold assessments allow Coach in all three risk modes; a subsequent creator-sell exit schedules
its order and blocks new research. The scheduling/pressure/recovery recheck passed **119 tests
in 28.27 seconds**; the final admission/exit-policy recheck passed **75 tests in 14.58 seconds**
(these suites overlap). The extended test file passed Ruff lint and formatting; `git diff
--check` passed. No additional application defect was found in this recheck.

Tests ran in temporary containers with network disabled, read-only source mounts, one CPU and
a 1,536 MiB memory limit. No live-data volume or real inference server was used. These were the
relevant focused/broader suites, not a new full-backend-suite run or a production benchmark.

This is a scheduling correction, not a change to trading, screening, proof, thresholds, fees,
Champion/Coach permissions or cohort identities. Schema 16 and version 1.10.10 are unchanged;
no new setting or data migration is required. README and learning documentation describe the
new opportunity and its guards. The Baseline-versus-Champions portfolio experiment remains
deferred and is not part of this change.

**Deployment is pending.** The live app was not restarted or updated in this implementation
step and remains on the previously verified collection-recovery image. A later controlled
rollout must check actual Coach opportunity, critical lag and host resource use. Cancelling an
HTTP request cannot prove a remote inference server has stopped computing. More opportunities
do not guarantee eligible experiments, new Champions or profits. A source/image rollback needs
no evidence reset; saved research and trading records retain their existing format.

## Champion impact — 13 September

Implemented the approved passive comparison in Learning Overview, with saved Champion portraits,
skill/team selection, paired outcomes, percentage-point differences, coverage and an approximate
uncertainty range. Longer methodology is collapsed under **How this works**. It displays collecting,
observed advantage/disadvantage or no clear advantage; a healthy worker or Champion is not treated
as proof of a positive outcome. This is a checkpoint comparison, not a second portfolio or realized
account profit. Both reported outcomes can be losses while their difference is positive.

The backend reuses the existing independent Policy selection within the locked status response.
It reads no extra database history, performs no inference or provider requests and writes no state.
At most 1,000 retained Policy rows feed up to five comparisons, each capped at 60 resolved cases.
The report requires the exact current season, profile, active versions and latest activation epoch.
Original actionable rows, frozen receipts, chronology, unavailable outcomes and actual saved sizing
clamps remain necessary. Suspended, missing, replaced and incompatible contexts cannot produce a
current-support claim. All authority, qualification, fees and trading code paths remain unchanged.

Team outcomes apply the ordered decisions once on shared opportunities; overlapping vetoes do
not earn multiple credits, and vetoed opportunities do not reach downstream roles. The team result
is not a sum of per-skill results. Exit uses its entry-frozen horizon and the same recorded size for
its normal-review reference. It does not claim to reproduce adaptive exits, later opportunities,
portfolio capacity or compounding. Approximate intervals are descriptive and do not account for
every market dependency or repeated inspection. Existing proof gates are separate and unchanged.

Validation:

- The focused tests cover paired losses/advantages, joint Sizing/Exit, overlapping vetoes,
  unsupported proposals, exact clamps, unavailable routes, missing and malformed receipts,
  timestamps, independent identity, out-of-order duplicates, pending evidence and bounded windows.
  Real Policy receipts from the existing activation fixture produce all three Sizing/Exit/team
  comparisons. Rendering selects the Policy population once and does not change active skills or
  write episodes/skill states.
- **299 backend regression tests passed in 236.08 seconds**, covering health and Policy scopes,
  status work, independent participation, suspension recovery, contextual Exit, risk profiles,
  API/security, veto scoring and the pending Coach admission fix. The sole warning was the existing
  Starlette test-client AnyIO deprecation. The final focused recheck passed **56 tests in 12.26
  seconds**, including added malformed-trial, horizon-timing and maximum-population cases.
  Restart reconstructs the same comparison from saved evidence; a newer activation cannot reuse
  the previous window. These focused suites overlap the broader run and are not additive totals.
- **388 frontend tests passed** across 22 files. Cases include old/missing responses, stale or
  changed contexts, paused/suspended support, negative/inconclusive results, team selection,
  disappearing support, unavailable numbers and collapsed method details.
- Frontend type checking and production build passed. Full frontend lint passed with the existing
  `EquityChart.tsx` Fast Refresh warning. The build retains the existing large lazy 3D-scene warning;
  the impact panel uses vector portraits and does not load the 3D renderer.
- Repository-wide Ruff lint and formatting passed for **137 Python files**; backend Mypy passed
  for **45 source files**. `git diff --check` passed. No live data was used by these checks.
- Local browser verification used synthetic fixtures with non-local requests blocked. Desktop,
  390 px mobile and 320 px narrow layouts had no browser errors or horizontal overflow, including
  expanded help. Temporary preview entries were removed from the repository afterward.
- In an offline container limited to one CPU and 1,536 MiB, 15 calculations over 1,000 synthetic
  four-skill rows measured median **5.434 ms** (maximum **11.246 ms**). An all-Entry-veto population,
  which requires scanning the retained rows to count downstream exclusions, measured median
  **16.909 ms** (maximum **27.366 ms**). These are isolated report costs, not end-to-end dashboard
  latency, a live load test or proof of sustained burst capacity.

Version **1.10.10** and schema **16** remain unchanged. README, changelog and learning documentation
describe the panel and its limits. A rollback removes this optional snapshot field and UI without
changing saved learning evidence or trading records. The full independent two-portfolio experiment
remains deferred.

**Deployment remains pending.** No restart, setting change, live database write or deployment was
performed for this feature. The live app still uses the previously verified collection-recovery
image. A controlled rollout should check snapshot cost and matching real Champion receipts before
claiming observed live benefit. Broader burst limits and longer-term learning observation remain;
this panel does not improve qualification performance or guarantee a Champion or profit.

## Dashboard reconnection — 13 September

The reported symptom was a page remaining in the fallback `Polling` state until manually reloaded.
That label identified periodic HTTP refreshes, not paused trading. Source review and three failing
frontend regressions independently reproduced a handshake that never completed, a closed socket
whose close event was missed before returning to the tab, and repeated failures postponing the
fallback poll timer. The screenshot alone does not identify which condition occurred on that client.

The client now retires a handshake after 15 seconds, reconnects with the existing 1/2/4/8/16/30-second
backoff, and repairs stale connections when returning from a long background suspension, changing
networks or restoring a page from browser history. Short tab switches retain a healthy connection.
Resume events share one scheduled retry; obsolete sockets have their handlers detached, and late
callbacks cannot change the current connection. Constructor/close failures and cleanup are guarded.

The fallback label is **Auto refresh**, with a brief tooltip explaining automatic reconnection.
Only an open socket earns **Live updates**. Failed reconnects cannot move an already due poll later.
Existing target polling intervals remain 5 seconds while disconnected, 15 seconds while connected,
and 30 seconds while hidden, with requests sharing the existing in-flight refresh. Visible socket
notifications remain coalesced to one scheduled refresh per three seconds; hidden notifications no
longer trigger that faster path. Returning to the page requests one catch-up view. No backend,
authentication, market-processing, learning, trading, configuration or database logic changed.

The three reproductions failed before the fix and passed afterward. The focused recovery run
passed 15 matching tests, including delayed/error-only handshakes, a late successful open, stale
callbacks, bounded backoff, concurrent resume events, secure-origin URLs, short/long tab switches,
100-notification bursts, hidden refresh pacing, pending HTTP work during unmount and React Strict
Mode cleanup. The initial complete frontend run passed **400 tests across 22 files in 58.06 seconds**.
Type checking and the production build passed; lint retained only the existing EquityChart Fast
Refresh warning, and the build retained its existing lazy 3D-scene size warning. `git diff --check`
passed. Tests used fake browser sockets, timers and HTTP responses, not the live service.

**Deployment remains pending.** This change was built locally without restarting or updating the
live app. The current live client cannot gain this behavior until the new frontend is deployed and
loaded. These regressions validate bounded recovery, not every browser/proxy failure or sustained
production burst performance. A source/image rollback requires no saved-data changes.

### Follow-up edge-case recheck

Two new reproductions found that an `online` or history-restored `pageshow` event arriving while
the document was still hidden could be forgotten before a short return to the tab. The client now
remembers that signal until the page becomes visible, applies one repair and consumes the signal.
It sends no additional hidden-tab requests, and a later short tab switch retains the recovered
connection. This changes only the client connection lifecycle.

Additional checks confirm that a snapshot timeout releases the shared refresh so recovery can
continue after the server returns, without overlapping HTTP requests, and that a browser exception
while closing an old socket does not prevent reconnection. The focused recovery suite passed
**19 matching tests**. The final full frontend run passed **404 tests across 22 files in 56.34
seconds**. Type checking, lint and production packaging passed with the same pre-existing warnings;
`git diff --check` passed. No backend changes, live requests or deployment were needed for this
recheck. Controlled live rollout remains pending.

## Coach, impact and reconnection rollout — 13 September

The user authorised the live update after the final edge-case checks. The image is
`signal-arcade:v1.10.10-coach-impact-reconnect-20260913`, with image ID
`sha256:2ef96ae1a552d2f2c15c4065ad6afe7fb72eff8e5fc1c64d317f313d5d55ff3e`.
The packaged app passed isolated, network-disabled startup and graceful shutdown checks.
All 45 installed backend/resource files and all six frontend files (excluding source maps)
matched the reviewed local build. The frontend build retained only its existing large 3D chunk
warning. The previous stage's 404 passing frontend tests, TypeScript and lint checks remain
applicable; no application code changed during this rollout.

Upgrade preparation reached Ready at **07:26:06 UTC**, with no pending orders to cancel.
Shutdown completed at **07:26:25 UTC**. A complete archive of the stopped volume was read back
and all five file checksums verified before replacement. The new container started at
**07:34:51 UTC** and application startup completed at **07:35:21 UTC**. Downtime can expire
pending evidence windows; the recorded unavailable outcomes were neither removed nor rewritten.

The same volume and schema 16 were retained. All 28 resolved Compose settings, the complete
environment fingerprint, ports, mounts and project identity matched. Ollama was not replaced
or restarted. Only the ignored local image pin and app container changed. The previous image
and the consistent backup remain available; rollback should normally use the earlier image
with the current schema-16 volume rather than discarding newer evidence by restoring old data.

The authoritative saved state showed season 48 had begun automatically at **07:10:39 UTC**,
before this update. Its identity and the active Sizing v4 artifact survived the restart, as did
learning mode, support consent and Coach contribution permission. The pre-upgrade dashboard
had returned an older cached season-47 view during cleanup, so it was not used as the state
preservation reference. All four saved positions were matched to normal `time_exit` sell
receipts at **07:35:28–07:35:30 UTC**, with the same token units and newly observed executable
reserves. No position was force-closed or fabricated by the deployment procedure.

The live browser check verified desktop and mobile rendering, the new Champion impact panel,
and recovery from a browser-only connection interruption: **Auto refresh → Live updates**
without reloading the page. There were no JavaScript errors or mobile document overflow after
layout settled. The initial test harness was adjusted because Chrome's offline emulation alone
does not reliably close an existing socket and the compact mobile header intentionally hides
the connection label. These were test setup corrections, not application fixes.

The panel displayed Sizing v4's actual current-season evidence: **6 usable / 8 resolved pairs,
75% paired coverage**, with four more pending in a later snapshot. It correctly stayed at
**Collecting comparisons**, rather than claiming a proven advantage from six pairs. Its modeled
mean difference was approximately **+7.7 percentage points**, while both the reference and
supported mean returns were negative. This is not a portfolio-profit result or an Entry coverage
measurement. Suspended Exit support remained suspended.

Bounded live observations through **07:43:28 UTC** found the database and all seven monitored
workers healthy, no restart or worker exception, and no candidate shedding or expiry after
startup. Collection advanced from **22 to 63 checkpoint updates** without worker errors.
Training published a fresh batch including Linear and XGBoost artifacts. Diagnostics were
recording with zero dropped records; two detail collections were deferred. A detached bounded
read retrieved six new intervals and 15 events without truncation, including training, proof,
collection and expiry attribution.

The retained **07:35:06–07:41:35 UTC** intervals contain **25,139 admitted events**, a queue peak
of **618**, and no candidate losses. They also contain a **7.82-second overall lag peak** and a
**7.01-second critical lag peak**, followed by recovery. At 07:43:28 the queue was empty and both
current lag measurements were approximately **0.07 seconds**. These short, unequal workloads
do not establish a performance improvement or identify which overlapping work caused the peak.
The observations included bounded browser checks, which must be considered when comparing load.

Fresh dashboard snapshots recovered automatically. Four serial five-second requests saw ages
of approximately **33.5, 5.0, 10.1 and 17.6 seconds**, including cleanup reuse and a queued refresh.
Brief stale-view warnings can therefore still occur under competing work; persistent recovery
failure was not reproduced. Follow-up observation should include snapshot age and critical-lag
tails, rather than relying only on a green health badge.

Entry operational coverage was approximately **65.1%** at the last sample, below the unchanged
70% gate. Fitted-cohort coverage, untouched model performance and independent proof are separate
requirements; neither a Champion nor future profit is promised. Coach was healthy and waiting
for four further outcomes, with no model error. Its newly allowed extended-hold opportunity and
75-second cancellation boundary are regression-tested, but this short live window did not
exercise a complete new research/inference cycle under that condition.

All agreed implementation stages are deployed. No additional release-blocking defect was
confirmed by this rollout; longer observation of burst recovery, mature Entry cohorts and
Coach opportunities remains necessary. No commit, public image or community release was pushed.

The closing **07:46:11 UTC** health/diagnostics sample remained healthy: queue **7**, current
overall lag **0.027 seconds**, critical lag **0.085 seconds**, **79 collection checkpoint updates**,
no training or collection worker errors, no candidate losses and zero dropped diagnostic records.
The two deferred diagnostic detail collections remained reported. This extends the startup
observation to approximately eleven minutes; it is not a long-duration reliability test.

## Stale reserve-warning follow-up — 13 September

A source review found a display mismatch: the server overlays current reserve-validation status
on cached dashboard responses, but the frontend skipped that status entirely when the heavier
snapshot was older than 15 seconds. Unverified routes were still rejected by the backend.

Five new frontend regressions first reproduced three failures: initial snapshots aged 15.001
and 120 seconds did not show a reserve fault, and a new reserve fault stayed hidden alongside an
existing market warning. The 14.999- and 15-second cases passed before the correction.

The five-line frontend correction surfaces an explicit reserve fault on a stale snapshot while
passing only that component to the status updater. Cached healthy market fields cannot clear an
unrelated market warning. Missing reserve fields and stale healthy reports cannot resolve a
known reserve fault; recovery still requires a fresh snapshot or the existing health fallback.
There are no added requests, timers, locks, database operations or backend execution changes.

Validation on the completed correction:

- All **409 frontend tests across 22 files passed** with one worker, including reconnection,
  hidden-tab behavior, status history, Champion impact, and the five new regressions. Focused
  checks also passed for concurrent warnings, repeated reports, missing fields and recovery.
- TypeScript checking, ESLint and the production build passed. The existing unchanged
  EquityChart Fast Refresh warning and large lazy 3D chunk warning remain.
- All **22 reserve-validation backend tests passed**, including the cached-response contract
  at both 2 and 30 seconds. Source was mounted read-only in an offline one-CPU container, with
  temporary synthetic databases and no live-data mount.
- The first backend test run used a 512 MiB temporary filesystem and correctly hit the existing
  512 MiB free-space guard in one export test. Repeating the same suite with a 2 GiB temporary
  filesystem passed. The application guard and backend execution code were not changed.

The pre-validation live review found 180 expired candidate events in the interval beginning
**08:13:52 UTC**, with a 20.13-second overall lag peak. Later completed intervals showed a
6.70-second critical peak. By **08:26:30 UTC**, the queue was empty, critical lag was 0.021 seconds,
and expired candidates remained at 180. Training had made 11 publications and reserve collection
had completed 641 checkpoint updates without worker errors. Diagnostics were recording with
one aggregate dropped count and nine deferred detail collections. The dropped counter combines
event/detail losses and record/writer rejection; it does not identify what was lost. Intervals
longer than 90 seconds can result from diagnostics intentionally yielding under pressure.

These observations justify continued performance investigation, not an assumed cause or a
speculative scheduler change. Frontend/backend validation also shared the live host, so periods
overlapping those checks must not be used as clean before/after performance comparisons.

Version 1.10.10, Baseline boundaries, permissions, fees, the 70% requirement, independent proof,
and all learning/trading behavior are unchanged by this follow-up. The local source and frontend
build contain the correction; the live container still runs the earlier 13 September rollout.

The closing bounded read at **08:41:53 UTC** found all seven workers and the database healthy,
queue depth 6, overall lag 0.016 seconds and critical lag 0.039 seconds. Training publications
reached 15 and checkpoint updates reached 877 without worker errors. Expired candidates stayed
at 180, and diagnostics stayed recording with the aggregate dropped count unchanged at one.
Thirteen retained intervals beginning 08:27:52 through 08:40:25 recorded no further candidate
expiry or diagnostic drops. They still include brief latency peaks and overlap local validation;
they establish continued operation, not a controlled performance improvement. No additional
engine change is justified by these observations alone. Host disk headroom remains a separate
operational follow-up; no files, images, backups or live records were deleted.

Final repository-wide Ruff lint/format checks passed for all 137 Python files, and
`git diff --check`, release-version consistency and local documentation-target checks passed.

## Final UI rollout — 13 September

The user authorised installing the remaining validated correction. The replacement image
retains the preceding runtime and dependencies, replacing the built frontend and bundled README.
All 45 backend source/resource hashes and all six served frontend file hashes match the local
validated build. This deployment adds no backend execution or schema change.

The new image passed an offline startup, health, frontend-serving and graceful-shutdown smoke
check with isolated temporary data. The existing app then completed its upgrade preparation,
with zero pending-order cancellations, and shut down cleanly. A fresh archive of all seven data
files, including the retained WAL and SHM files, was verified against their hashes before restart.
Saved-state verification used SQLite read-only mode with WAL visibility. Backup preparation
caused planned downtime; no observations are claimed for that stopped period.

The replacement container started at **09:06:32 UTC** using
`signal-arcade:v1.10.10-final-ui-20260913`. All 28 Compose environment values, the data volume,
ports and runtime configuration were preserved. The separate local-model service was unchanged.
Twelve retained settings matched after restart, including the season, learning permissions and
active Sizing identity. Schema version remained 16 and the retained learning count was 52,150.
The saved position resumed and received a normal Baseline stop-loss fill at **09:06:59 UTC**,
using a reserve snapshot from that same time; it was not discarded by the update.

The **09:07:31** and **09:09:16 UTC** observations found the database and all seven workers healthy,
learning active, Sizing active, no collection/training worker errors, and zero candidate losses
since this boot. Collection checkpoint updates increased from 18 to 32. Diagnostic recording was
healthy with no queued or dropped records in these observations. Training was idle awaiting
further qualifying outcomes, and Coach was healthy waiting for 13 further measured outcomes.
Entry operational coverage was 62.9%, below the unchanged 70% requirement.

The bounded browser check passed on desktop and mobile with no JavaScript errors or document
overflow. Champion impact and Coach rendered correctly, and a simulated browser disconnect
recovered from Auto refresh to Live updates without a page reload. All browser API requests
were reads. Fresh dashboard responses also regenerated automatically.

Retained diagnostics remained readable across the old and new boot identities, including the
old aggregate dropped count of one. Counters reset on restart, so the new zero counts do not
erase the earlier burst history or establish a performance improvement. The initial retained
startup interval was correctly marked partial. No new deployment defect was confirmed by these
checks; mature learning outcomes and sustained burst performance still need longer observation.
The previous image and verified backup are retained for rollback. No public image, commit or
community release was pushed.

The closing **09:11:38 UTC** health observation remained healthy: queue zero, overall lag
0.005 seconds, critical lag 0.142 seconds and 46 collection checkpoint updates. No worker error,
unexpected restart, OOM event or error-level startup/runtime log was found. At **09:12:28 UTC**,
five completed retained intervals since startup contained 29,201 admitted events, a queue peak
of 167, a 1.66-second overall lag peak and a 0.406-second critical lag peak, with no shed or
expired candidates and no diagnostic drops. All worker-health gauges were healthy.

Two serial snapshot reads five seconds apart recovered from a 44.7-second idle cached view to
a 3.94-second view without a browser reload. Fresh Entry operational coverage was 63.0%; no
qualification requirement changed. This approximately six-minute post-update observation
confirms startup and continued operation, not sustained performance under equivalent bursts
or completion of a new Coach research/training cycle. Low host system-drive headroom remains
an operational follow-up. No additional application fix was justified by the rollout evidence.

## Final learning review implementation — 13 September

This section records a later source change, after the live rollout described above. It is not
evidence that these changes have been deployed or have improved live market results.

Three reviewed causes were addressed in stages:

- Champion activation previously changed in-memory authority before its complete database
  commit. Injected failures reproduced the divergence. Grants now prepare detached state,
  commit the complete skill combination, mode and applicable manual consent, then publish
  into the existing state objects retained by tournament callers. Revocations remove affected
  support first and retain failed persistence for retry before another grant.
- Entry top-group scoring broke tied predictions using held-out outcomes. With six identical
  forecasts and returns from -30% to +20%, the old calculation reported +15%; the corrected
  equal-boundary weighting reports -5%, the full group's mean. Linear, XGBoost and Baseline
  comparisons use the same calculation. Native Entry fits record `entry-top-group-v2`.
  Older artifacts remain historical comparison references but cannot grant current Entry
  authority without a corrected fit. Other skills and Coach artifact contracts are unchanged.
- Coach research previously missed later actionable Policy entries when the token's original
  Discovery observation was a Pass. New studies collect canonical post-selection Policy
  identities, with exact context and dependency checks. Enrollment is bounded at 180, new
  reads at 64 keys per page, and unresolved enrollments persist across restart. Only the
  chronological resolved prefix contributes to qualification; missing or invalidated rows
  stay unknown. Unscanned retention gaps end a study as inconclusive, including when entries
  share a timestamp. Unfinished legacy studies close once with their old evidence retained.

Additional edge tests reproduced a numeric persistence defect: two valid Exit returns of
+10 and -1 produce a difference of +11 (and the reverse produces -11). The former Coach
summary limits made those saved studies unreadable. Finite differences and confidence bounds
are now preserved without clipping them to individual-return limits. The positive support and
non-positive rejection comparisons remain equivalent; no proof threshold or underlying outcome
changed. This correction also applies to size-normalized differences.

Validation of the final source:

- All **1,815 backend tests** passed across isolated runs. Final batches covered 1,105 and
  710 tests; the diagnostics export module was rerun separately, with all 27 tests passing.
  Earlier all-in-one runs encountered temporary-container memory exhaustion. A smaller
  temporary filesystem then exercised the recorder's existing free-space protection during
  its WAL stress fixture. Fresh isolated runs resolved the resource failures without changing
  production protections, skipping assertions or modifying unrelated runtime code.
- **409 frontend tests** passed. Frontend lint, TypeScript and production build passed, with
  the existing EquityChart fast-refresh warning and lazy 3D chunk-size warning unchanged.
- Ruff lint and formatting passed for all 140 Python files. Version markers remain 1.10.10,
  strict mypy passed for all 43 backend modules, and `git diff --check` passed. No dependencies
  were updated.
- An offline demo smoke check used the current runtime image with the changed backend and
  built frontend mounted read-only, isolated temporary data and external networking disabled.
  All eight runtime dependency versions matched `pyproject.toml`. Version, seven workers,
  health, frontend serving and graceful shutdown passed. This was not a deployment or a
  live-data benchmark.
- Regression cases include failures at separate activation commit steps, manual consent,
  upstream/downstream authority, suspension retries, tournament object references, old
  Linear/XGBoost activation and restart, tied and non-tied rankings, all four Coach research
  kinds, pre-proposal and repeated identities, future/pending checkpoints, context changes,
  chronological unknowns, meaningful seasons, the 180-enrollment limit, concurrent handoff,
  deferred reads, retention and legacy-study transition.

The existing 70% coverage requirement, minimum samples, independent proof, XGBoost comparison,
fees, hard exits, Baseline authority and Coach contribution permissions remain unchanged.
More truthful scoring can reduce a candidate's reported qualification; this is not evidence
of worse learning. These fixes do not establish improved profitability or promise an Entry
Champion. Conservative retention-gap handling can end a Coach study even when the missing
rows belonged to another context; that is an explicit safety tradeoff.

The live container was confirmed still running `signal-arcade:v1.10.10-final-ui-20260913`,
started at 09:06:32 UTC, with zero restarts. It has not received these later changes. No live
settings, evidence or services were modified, and nothing was committed or pushed. Deployment
verification and observation of new training and Coach studies remain separate next steps.
Older builds do not understand the new Coach study fields; retain a consistent backup and
check research and support state explicitly if rolling back. Do not discard newer trading
evidence merely to restore optional research.

### Additional edge-case recheck — 13 September

Added five focused failure-mode tests: a real SQLite COMMIT rejection during an upstream
Champion join; COMMIT rejection while saving Coach progress; Coach reads against a committed
WAL snapshot while both core locks and an uncommitted writer transaction are held; interruption
after the first record batch of a Policy page; and equal-timestamp pagination with persisted
cursor reloads. All passed. Failed commits retained prior authority/progress and remained
retryable, and page interruptions did not lose or double-count evidence.

A 300-test focused learning, Coach, activation, recovery and candidate-selection run passed.
Further inspection found one display inconsistency: the XGBoost status could still call an old
validation artifact qualified, queued or testing even though current eligibility rejected it.
The status calculation now uses the same validation contract, including its active label.
Historical Champion and suspension labels remain available. Six legacy/current status-role
cases cover this correction; all 96 relevant learning, activation and status tests passed
afterward. The old qualified-label failure was reproduced before the correction.
Ruff lint/format, strict typing for all 43 backend modules and `git diff --check` also passed.

This recheck changed the status calculation, regression tests and documentation only. It did
not change predictions, evidence enrollment, thresholds, fees, permissions or trading actions.
The live app was not restarted or updated. The broader validation above remains the preceding
full-suite result; these are additional targeted checks, not a new live performance claim.

### Deployment of the final learning changes — 13 September

The later learning changes and status correction above were deployed together in
`signal-arcade:v1.10.10-learning-final-20260913`. The container started at 12:48:12 UTC;
normal database initialization finished and the server became available at 12:48:33 UTC.
Initial probes before the listener opened returned connection refused; startup then completed
without an application error. This deployment supersedes the earlier not-yet-deployed status.

The local image reused the validated runtime dependencies and packaged the current backend,
frontend and runtime documentation. Exact file-set and SHA-256 checks verified all 45 backend
files/resources and six served frontend files, including the actual installed import location.
All eight runtime dependency versions and package version matched the repository. An isolated,
network-disabled demo smoke check passed startup, seven workers, frontend serving and graceful
shutdown before deployment.

Upgrade preparation cancelled one unfilled paper order and preserved two held positions.
After graceful shutdown, the complete stopped data volume was archived and every file's hash
verified, including the database WAL. The previous image and backups were retained. All 28
Compose environment values, ports and volume were preserved, and Ollama was unchanged. Bounded
read-only checks verified 12 saved settings, the season, schema 16, learning outcome counter
and Sizing identity. Both positions first survived with unchanged entry costs and quantities,
then closed through normal Baseline `time_exit` decisions with sell receipts after restart.

Serial live checks through 12:53:43 UTC found all seven workers and the database healthy, zero
container restarts, no out-of-memory event and no warning/error lines in the bounded startup
logs. Reserve collection advanced to 74 checkpoint updates without worker errors. Five retained
intervals ending at 12:53:35 UTC recorded 19,188 processed events, a queue peak of 178, overall
lag peak of 1.779 seconds and critical lag peak of 1.006 seconds. There were no shed or expired
candidate events and no diagnostics drops; the initial partial interval was explicitly flagged.

Read-only desktop/mobile browser checks passed live updates, Champion Impact rendering,
document width and reconnecting after a simulated browser-only network interruption. There
were no browser errors. Sparse API reads sometimes returned the timestamped idle/maintenance
cache; follow-up reads recovered fresh views. These cached reads were not treated as current
learning measurements.

Sizing v4 remained active; Exit remained suspended under its existing proof, and Entry and
Manipulation continued collecting proof. Fresh Entry operational coverage was 641/1,000
(64.1%), below the unchanged 70% requirement. The three retained unfinished legacy Coach
studies closed once as inconclusive with `evidence_contract_changed`, preserving their prior
counts. The Coach worker remained healthy with contribution permission retained. At the last
observation, training needed seven more usable outcomes and Coach review needed 25; no new fit
or Policy-v1 proposal had completed during this observation. Their next full cycles remain a
longer-observation check, not a result established by deployment.

For comparison, 27 retained pre-update intervals ending at 12:39:30 UTC included a queue peak
of 2,021, overall lag peak of 12.446 seconds, critical lag peak of 4.928 seconds and one flagged
recording gap. No candidate losses occurred in those intervals; diagnostics drops increased
from one to two. The shorter post-update period had different traffic and excludes upgrade
downtime, so its lower peaks are not an equivalent-load performance comparison. Low host
system-drive headroom also remains an operational follow-up. No further runtime source fix
was justified by these deployment checks. Nothing was committed or pushed.

A closing health and deployed-file check at 12:55:19 UTC again passed, with 95 reserve
checkpoint updates, no worker errors, no shed/expired candidates and no diagnostics drops.
The running source/asset hashes and unchanged Compose/Ollama configuration were reverified.

### Community release edge-case review — 13 September

Rechecked the final authority, scoring, Coach pagination and UI recovery paths against their
surrounding callers. The targeted backend run passed **185 tests**, covering real commit
rejection, restart recovery, legacy/current Entry qualification, chronological Coach proof,
retention, cancellation, held-position admission, unsupported vetoes and matched impact
comparisons. It used isolated temporary data, no network and a one-CPU container. The focused
frontend run passed **174 tests** across App, Champion Impact and system status; TypeScript
also passed. Ruff lint and formatting passed for all 140 Python files. These targeted results
supplement the earlier broad suites; the full suites were not repeated in this review.

Release markers remained 1.10.10, local documentation links resolved, and the checked
publishable files contained no private runtime/database files or matches for the credential
patterns checked. Git ignored the live environment, data, logs and generated frontend bundle.
The README Compose example parsed successfully both with its unchanged defaults and with the
documented optional reserve worker enabled. Two README clarifications were made: explain how
to pass that opt-in variable in the image-only Compose example, and distinguish the corrected
native Entry contract from other skills' normal activation checks. No runtime source or live
setting changed during this review; the source still matched the deployed manifest.

Bounded persisted-state reads at 13:02:55 UTC confirmed **two new training publications** since
deployment. Both the Linear and XGBoost Entry artifacts at 12:58 and 13:02 UTC carried
`entry-top-group-v2`. The persisted learning outcome counter advanced from 52,667 to 52,686;
the 12 checked settings and active Sizing identity remained unchanged. This verifies that
the corrected fitting path runs live, without implying that either candidate qualified.
The next complete Policy-v1 Coach study remains a longer-observation check.

Fourteen retained intervals through 13:02:53 UTC contained 71,028 processed events, no shed or
expired candidates and no diagnostics drops. Workers stayed healthy. Queue depth peaked at
548, overall lag at 7.099 seconds and critical lag at 3.008 seconds, then recovered. The only
interval flags were the initial partial interval and an hour boundary. Local tests shared host
resources during part of this observation; these measurements do not establish cause or an
equivalent-load performance improvement. A closing check at 13:04:51 UTC found no degradation,
zero queued events, 184 reserve checkpoint updates, and no errors, warnings, restarts or OOM
events in the bounded logs/container checks. Longer burst observation and low host drive
headroom remain follow-ups. No additional runtime defect or release blocker was established.
Nothing was committed, pushed or restarted during this review.

### Champion Impact Shadow state — 13 September

A live replacement crown exposed misleading empty-state wording. At 13:22 UTC, learning was
in Shadow, collecting from mainnet, with automatic support enabled and no active skill.
Sizing generation 5 had earned its crown at 13:18 UTC but its own activation proof was not ready.
Exit remained suspended. The impact panel treated every mode other than Active as paused,
masking both the waiting-for-support and suspended states. Learning itself had not been paused.

The frontend now reserves the paused label for learning Off or collection from another source.
Shadow displays waiting for active support, or the selected skill's suspension. An explicit
Active-mode guard still prevents retained comparison payloads from claiming current influence.
No backend, evidence, activation, permission or trading rule changed, and no new requests were added.

Two regressions reproduced the old label failure before the correction. All **176** focused
App, Champion Impact and system-status tests then passed, including tab selection, a replacement
crown, suspension, stale active payloads in Shadow, resuming Active, Off and source changes.
TypeScript, targeted ESLint and the production frontend build passed. The existing lazy 3D
chunk-size warning remains unchanged. This frontend correction was not deployed during that
check; the subsequent deployment is recorded below. Nothing was committed or pushed.

A follow-up checked stale Team results in Shadow and the complete replacement transition:
v4 active, v5 crowned but inactive, v5 activated with an old report, then fresh pending-only v5
comparisons. Old values stayed hidden and the selected Sizing tab remained selected. All **22**
impact-panel tests passed, along with TypeScript, targeted ESLint and the whitespace check.
Only tests and this validation note changed in the follow-up; no further application fix,
backend change or live update was needed or performed. The broader 176-test result above remains
the preceding run, not a new full-suite result.

### Deployment of the Shadow display correction — 13 September

The authorised live update used `signal-arcade:v1.10.10-impact-shadow-20260913`, starting at
13:35:15 UTC. It packages the corrected frontend and current README on the verified existing
runtime. All 45 backend files/resources remained identical; all six served frontend files
matched the validated local build. An isolated one-CPU, network-disabled smoke check passed
startup, frontend serving, all seven workers and graceful shutdown before the update.

Upgrade preparation cancelled no pending orders. The application shut down gracefully;
the verifier initially rejected the normal SIGTERM exit code 143, then confirmed the shutdown
log. A stopped SQLite read also required adaptation because its read-only volume could not
create sidecars. An immutable read was permitted only after confirming the app was stopped
and its WAL was absent or empty. It verified schema 16 and captured the saved state without
changing the database. The previous image and verified full-volume backup remain available;
this frontend-only update reused the current volume without a schema migration or another
full-database copy.

All 28 service environment values, port/volume bindings and Ollama instance remained unchanged.
Twelve saved settings matched after restart. The one held position retained its original entry
cost, quantity and fill identity, and season 48 and the Sizing generation-5 crown were preserved.
The upgrade operation completed normally and resumed the paper engine.

A read-only browser check verified live updates and the actual corrected states: Entry,
Manipulation and Sizing waited for active support; Exit showed support suspended. Desktop and
390-pixel mobile rendering passed without browser errors or horizontal overflow. The check
made two snapshot GET requests and did not change app settings.

At 13:38:07 UTC all seven workers and the database were healthy, the queue was empty, and
overall/critical lag was 0.025/0.029 seconds. Reserve collection had made 62 checkpoint updates
without worker errors or reserve-validation warnings. Two retained intervals through 13:37:41
contained 9,339 processed events, a queue peak of 262, overall lag peak of 2.953 seconds and
critical lag peak of 1.303 seconds. No candidate events were shed or expired and no diagnostics
records were dropped; the initial partial interval was explicitly flagged. Bounded startup
logs had no warnings or errors, and Docker reported no restart or out-of-memory event.

One new training publication completed at 13:37:37 UTC; the new Linear and XGBoost Entry fits
retained `entry-top-group-v2`. The persisted learning outcome counter advanced from 52,792 to 52,802. Entry
operational coverage was 65.0%, still below 70%; this display change cannot improve coverage.
Sizing v5 continued collecting its own activation proof rather than inheriting v4's authority.
Coach remained healthy and waiting for further outcomes. These short checks establish correct
deployment and resumed work, not sustained performance or eventual qualification. No new app
defect was established. Nothing was committed or pushed.
