# Learning Lab

Signal Arcade learns cautiously from its own live-paper observation history. The learner is a
small, CPU-only challenger to the transparent V1 baseline—not a claim that the app can guarantee
profit, discover a permanent edge, or safely trade real money.

The v1.10.11 contention follow-up reduces current feature-vector traversal overhead without
retaining validation or health results across outcomes. Checkpoint order, immediate governance,
Champion dependency checks, negative/failed outcomes and training/proof separation are unchanged.
Compact dashboard projection retains rolling-feature calculations and their cache effects; it
only omits construction of values the dashboard would discard. These are processing optimizations,
not a change to training populations, trading rules or evidence required for promotion.

## Configurable skill coverage (v1.10.11)

Settings → **Learning requirements** offers **70% (default), 65%, 60% and 55%**. The choice measures
the minimum fraction of eligible resolved observations with usable fee-inclusive outcomes. It
is not accuracy, win rate or a profit target. Lowering the requirement accepts more incomplete
evidence, including in ongoing health checks; these choices are not empirically proven optimum
cutoffs. No setting guarantees qualification or a Champion. **55% is the lowest supported choice**;
with 1,000 resolved observations it requires 550 usable outcomes before the chronological split
and embargo, not 550 training rows. Negative and zero returns count as usable outcomes.
The original 70/65/60 choices were deployed locally through Settings preparation on 19 September,
with 70% preserved during that initial rollout. The 55% extension was deployed locally through
Settings preparation on 20 September, preserving the existing 60% selection. Adding it does not
change an existing saved setting. Later selections are recorded separately
and do not change the community default. See the [original deployment checks](V1_10_11_VALIDATION.md#configurable-coverage-live-rollout--19-september-2026)
and [55% validation and limits](V1_10_11_VALIDATION.md#optional-55-coverage--20-september-2026).

| Proof or check | Requirement |
| --- | --- |
| New native Entry Linear/XGBoost and Manipulation fits | Selected requirement for both fitted Discovery and separate Policy coverage |
| New native Sizing and deterministic/contextual Exit fits | Selected requirement for applicable Policy/paired coverage, including contextual Exit's fixed reference |
| Native skill activation, ongoing health and recovery | The stricter of the current setting and the artifact/proof's saved requirement |
| A newly started native-versus-native battle | Current setting, frozen for both sides before new observations |
| Coach research, Coach-derived support and either side of a battle involving Coach | 70% |
| Legacy non-artifact hold-timing fallback and Champion-impact reporting | Their existing separate 70% requirement |

All sample minima, positive-return/advantage checks, uncertainty, familiarity, harm limits,
XGBoost complexity checks, fees, chronological embargoes and execution permissions remain in
force. Missing outcomes and valid quote failures stay in their original denominators; losses
and zero returns remain usable outcomes. Discovery, Policy, fitted coverage and operational
coverage remain distinct populations. The choice does not change collection, deadlines, provider
budgets, held-position priority, seasons, model features, fitting recipes or inference payloads.

Saving increments a separate policy revision and timestamps it. New generations cannot qualify
until their validation window starts at or after that change; existing historical training rows
can still be used before that boundary. Natural training readiness still applies, so saving is
not an immediate fit or promotion. In-flight jobs from an older revision cannot publish, even
after toggling back to the same percentage. Existing artifacts, their proof and their failures
are never rewritten. An old 70% artifact does not become a 65% artifact; a qualified new
generation must earn its place through the normal process.

Existing battles keep their frozen requirement when it is lowered. Raising it closes any
less-strict unfinished attempt without clearing its evidence or allowing a retry of that
candidate. Collecting or passed recovery trials below the raised requirement similarly remain
closed after another toggle. Failed recovery never restarts. Active Champions are checked at
the setting-save boundary; insufficient authority and dependent support step out atomically,
with saved crowns and permission preferences retained. This does not sell held positions or
enable support. Fresh proof for a replacement can still qualify normally.

An artifact fitted under 65% can activate while the current setting is 70% if all its evidence
passes. That activation keeps its 70% requirement for health and recovery even if the setting
is later lowered. Automatic and manual native-skill activation both retain this receipt;
malformed coverage metadata cannot authorize support.

The battle budgets remain **120 usable / 172 resolved common observations**, including at 55%,
60% and 65%. The minimum of 30 usable common outcomes also remains. Changing the threshold does
not extend an inconclusive trial. Saved receipts and
diagnostics retain their own requirement; the UI distinguishes it from a stricter current gate.
Stale saves from another browser tab are rejected, a failed database commit keeps the previous
setting and authority, and malformed saved policy blocks eligibility until repaired.

Unless an exception is explicitly named above, numerical 70% descriptions below describe the
default/legacy contract; new native proof uses its recorded selection. Previously deployed
reliability changes and their validation records remain historical observations, not evidence
that a lower requirement improves decisions.

Rollback to a coverage-policy-aware build can retain current data when its evidence and authority
contracts are compatible, including every recorded percentage. Once 55% has been saved or recorded
in proof, a reader accepting only 70/65/60 is not compatible, even after returning to a higher
setting. It rejects unsupported records rather than granting authority from them; do not relabel
old proof to make it load. An image predating this feature cannot safely interpret versioned
coverage proof, even if the setting has since returned to 70%. For that rollback, preserve the
current data separately and restore the matching pre-feature data and image together; restoring
an older backup loses newer evidence from the active app. See the [upgrade and rollback notes](../README.md#updating).

## What becomes a lesson

### v1.10.11 reliability and coverage

The 19 September idle-recovery follow-up fixes idle admission after a burst. Diagnostics may resume when
all admitted market work has drained, including the dequeue-to-consumer handoff. Local fitting
and publication may disregard a finite historical lag sample only after five monotonic seconds
of quiet following a successfully completed market batch. Unknown clocks, failed/cancelled
batches, newly admitted work, storage and maintenance still block recovery. Publication still
checks urgent arrivals, context and job lifetime after collection; no old job gains extra time.
The lag metric itself is retained. RPC and optional AI freshness guards are unchanged.

Collector deferrals and coherent slow-operation samples improve investigation but are never
training inputs. New paper receipts also carry optional fee provenance for arithmetic replay;
this is separate from learning proof and does not change execution. A bounded review reproduced
all 23 recorded quote failures in a sample of 60 completed observations (20 liquidity failures,
three fee failures). It does not establish the cause of every missing outcome or justify
reclassifying failures to pass the 70% gate.

Obsolete position-route probes are removed from memory at existing heartbeat/watchdog
boundaries. Current holdings and saved terminal evidence are preserved. Dashboard-section
and RPC timings, with post-fetch discard reasons, help distinguish collection pressure from
unavailable markets; these measurements never enter training or qualification.

Near the regular diagnostic collection deadline, an already-admitted publication boundary may
capture previous training/proof reports before the next publication. A bounded backlog now holds
up to four publication groups through short collection delays, handing off whole groups within
the unchanged eight-event interval limit. Original report times and missing indices remain
visible; overflow is counted, and pending or handed-off reports are not proof of durable storage.
Collection uses the same nominal minute cadence, requires writer handoff room, and yields
to market pressure and pending sells. It never postpones a terminal job for reporting, relaxes a
job's lifetime or reconstructs missed proof. The durable learning journal remains authoritative.

Optional admitted-RPC selection samples show due checkpoint eligibility by lane and horizon,
remaining deadline buckets, and the deduplicated route budget, measured at most once per minute.
They describe one sampled pass,
not unique lost outcomes or a cause of expiry. The measurement uses existing pending work and
does not alter eligibility, route order, deadlines or the three-Policy/one-Discovery rotation.
Blocked passes and cached-route selection are outside this measurement.

Policy proof selection filters ineligible contracts before sorting. It retains the same
chronological tie-break, durable identity reservations, earliest eligible observation per mint,
missing and negative outcomes, and latest 1,000 independent rows. There is no shared outcome
cache, new training evidence or deferred governance. The isolated speed measurement in the
validation record does not establish live burst throughput.

Optional worker detail separates local reserve validation, checkpoint persistence and immediate
governance from worker scheduling delays. Governance still runs at each original outcome boundary;
the app does not defer suspensions across an RPC batch. Equal-cohort 5/10/20 tests retain the same
outcomes, including failed/deadline cases, but do not establish that larger live batches are safe.
Batch defaults, request spacing, grace periods and qualification rules remain unchanged.

The default 70% requirement measures usable outcome coverage, not accuracy or win rate. Current
operational coverage and the cohort frozen into a fitted generation are distinct. Reaching
70% does not waive positive-return, advantage, familiarity, harm or other applicable proof
checks. A saved Champion still needs current activation proof and permission. Suspended
Exit Champions can be replaced through the normal process; a failed fixed recovery trial
cannot be restarted using more favourable later outcomes.

Collection priorities, five checkpoint horizons, grace windows, quote validation and batch
defaults are unchanged. Tests of larger existing batch options do not establish their effect
on a live provider. See [v1.10.11 validation](V1_10_11_VALIDATION.md).

The v1.10.11 follow-up allows routine storage cleanup to defer for an already admitted learning
request, for at most eight seconds across successive checks. It requires a completed capacity
check no more than 60 seconds old, a within-budget state and live pages at or below the cleanup target.
Unknown/urgent capacity, upgrade preparation or expiry of that deferral bypasses it. Every
existing post-fetch guard, route/context identity check, quote failure and checkpoint deadline
still applies. This reduces one avoidable collision in controlled tests; it does not make all
expired checkpoints recoverable. Held-position and Policy scheduling priorities are unchanged.

Coach studies, enrollment limits, contracts, chronology and terminal results are unchanged.
A prospective study spanning multiple meaningful seasons remains separate research work:
its enrollment rules and rollback compatibility require review before implementation.

### v1.10.6 independent support and performance

Automatic Champion support can start with any independently qualified skill. Saved permission,
current influence and candidate training are separate; each activation requires current composition
proof and a durable receipt. The consent, dependency and rollback contract below applies on restart
and when another skill joins. Existing sample, coverage, uncertainty and harm thresholds are unchanged.

Native Manipulation and Sizing proof continues while a downstream Champion is active. The proof
uses proposals and paired shadow outcomes frozen before downstream actions, and matches the exact
prospective upstream versions. Joining still removes downstream authority until the new combination
earns fresh proof. Automatic-support health starts from the current activation and its upstream
composition; a reused Champion cannot inherit health from an earlier activation.

Market-batch priority, native public-key decoding and bounded private training copies reduce repeated
work while retaining chronological evidence, original durable receipts and publication checks.
Diagnostics match the current Baseline and feature schema; diagnostics are never training evidence.

### v1.10.5 live-review refinements

Training checks its existing exact-cohort retraining threshold before freezing history. Reduced
fitting inputs omit Discovery sizing trials and prior Challenger evaluation receipts; full Policy
sizing trials remain, and original stored observations/receipts are untouched. Fitting and
publication retain their chronological split, context fence, atomic commit and qualification rules.
Worker diagnostics distinguish skipped jobs from published models and report each processing phase.

Skill-card gates describe `testing_candidate` when present, otherwise `latest_candidate`; the API
names that subject and artifact version. Champion availability, current activation and paired
forward tournament proof are separate states. A saved Champion does not qualify every new contender.

### v1.10.4 checkpoint and publication contract

Cached checkpoint selection filters for fresh executable routes before consuming its processing
budget. It rotates across eligible tokens, allocating three turns to Policy evidence for each
Discovery turn when both lanes have work. A stale oldest Discovery token cannot monopolize every
pass. Unknown and expired outcomes remain in the original qualification denominator.

The v1.10.7 collection refinement gives a checkpoint priority within its own lane during the
last 15 seconds of its existing grace window. Urgent failed attempts still rotate; the lane share,
batch size and request cadence do not change. Expired horizons are never reopened.
When a token has eligible checkpoints in both lanes, its single Policy-lane fetch keeps the
earliest eligible deadline from either lane. Deduplication does not hide an urgent Discovery clock.
A bounded 128-entry cache skips identities that cannot form a valid RPC request. A changed route
identity immediately becomes eligible again; missing tokens are removed and old entries evicted.
This cache affects only RPC selection, not cached fresh checkpoints, evidence enrollment, outcome
denominators or retries of transient provider/account-validation failures.

The 12 September dispatch refinement checks the pending mint under the existing event owner lock
before handing work to a thread. Each unresolved horizon uses its own Discovery creation or Policy
entry clock. Work at or after a horizon, including expired work, still runs; a pending record with
all checkpoints also retains its completion pass. Nothing about route freshness or availability
can suppress a due dispatch. Market feature updates, AI outcomes, held positions, order handling,
admission priorities and heartbeat/RPC collection retain their existing paths. No future work is
cached as unnecessary, so the next event after a horizon or a restart reevaluates the saved state.

The optional `learning_reserve_refresh_enabled` worker starts disabled. When enabled, it requests
one batch no more frequently than every ten seconds, with at most twenty routes and one hundred
unique accounts. It shares the configured provider quota and backoff, yields during maintenance,
season boundaries, pending sells, queue pressure and market lag, and times out each attempt after
eight seconds. Provider-unavailable, unsupported or malformed responses remain unknown. A target
with an implausible future slot cannot poison the slot requirement for the other targets.

Temporary guards are rechecked after alternating 1 and 1.25 seconds, without selecting candidates
or calling a provider while blocked. The stagger reduces repeated alignment with brief periodic
maintenance. Guards are checked again after acquiring the market boundary. Every actual attempt,
including discarded/unavailable responses and errors, retains the full configured wait after
completion. Empty selections, disabled collection and demo mode also keep that wait. This does
not change batch size, lane fairness, quota, checkpoint deadlines or the eight-second validity
window. The selectivity follow-up adds at most 0.5 seconds of lock-free scheduled waiting
for an already active storage chunk after fetching one batch. It neither delays cleanup nor
refreshes the response timestamp. Guards are rechecked during the wait and again at application;
unsafe or stale results are discarded. There is no background response queue or repeat fetch.
Handoff counters distinguish idle observed, timeout and interruption; none alone proves a
checkpoint completed. Stopping new learning still allows already-enrolled evidence to finish under its
existing rules, and held-position monitoring remains independent.

The local provider follow-up also fences requests across explicit provider configuration changes.
Old responses cannot impose or clear cooldowns on the replacement endpoint. Learning, held-position
and candidate-safety application recheck the request's configuration generation after waiting for
the market boundary. A changed learning context is a discarded batch within guard deferrals, not a
failed quote, a zero return or a new usable outcome. Provider configuration changes serialize with
threaded application; the existing settings/consent and historical evidence rules remain in force.

Ordinary WebSocket retry escalation resets only after both required subscriptions acknowledge
and a structurally valid notification arrives at least 60 monotonic seconds later. Merely opening
a connection, duplicate acknowledgements or a quiet connection does not qualify. Rate limits still
govern retry timing. This reconnect timer does **not** replace the five-minute clean-stream
enrollment window or establish mark freshness. The follow-up leaves RPC batch size, attempt spacing,
90-second grace, 3:1 Policy/Discovery rotation, fitted windows and all qualification checks unchanged.
See [local validation](V1_10_11_VALIDATION.md#provider-recovery-and-discovery-follow-up--local-validation)
and the [19 September rollout](V1_10_11_VALIDATION.md#provider-recovery-live-rollout--19-september-2026).

Snapshots must validate current mint safety, program owners, curve/pool PDAs, native-SOL quote
mapping, initialized unfrozen vaults, token-program extensions, fee configuration, slot fences and
request/observation times. v1.10.10's reserve adapter follows the reviewed account extensions and
fee rules in the official Rust client 0.1.13, without replacing the stream/event IDLs. Exact legacy
prefixes default the appended fields to zero; partial fields, invalid booleans and unknown nonzero
tails remain rejected. A nonzero per-coin creator fee replaces the scheduled creator rate only
while the global configuration gate is enabled. The maximum for setting a fee and permission to
edit it do not clamp a previously stored trade fee. An absent creator still receives no fee.
Mayhem bonding curves use current verified mint supply for sell fee tiers; ordinary curves use
fixed billion-token supply. PumpSwap uses the opposite supply selection: Mayhem pools use fixed
supply and ordinary pools use current verified mint supply. Noncanonical pools retain flat fees.
Unsupported quote currencies remain unsupported. The learning copy is
separate from the live feature cache and paper broker. Checkpoints record account hashes, slot,
reserves, fees and their observation time; the worker cannot fill a past horizon retroactively.
New receipts use `learning-account-snapshot-v2` and name `pump-rust-client-0.1.13` as the fee recipe.
Existing receipts, entry assumptions, expired checkpoints and Champion/Coach proof remain intact;
this receipt version does not restart tournaments or alter qualification thresholds.

The official holder-rewards contract published on 12 September, revision
`f216b6724c6ede79d7cef9ce210b741f7e17e93b`, explains the additional 33 Global bytes as
`holder_reward_claim_authority` and `is_holder_reward_enabled`. BondingCurve and Pool append
`is_holder_reward`. Legacy missing flags default to false, and existing zero allocation padding
remains supported; nonzero partial fields and invalid booleans remain rejected. The Global flag
controls creation, so disabling it does not block existing coin trades. Holder rewards redirect
the already-charged creator fee; they are not added again to costs or credited as paper income.
Receipts retain the fee recipe and also identify the account contract and holder-reward flag.
Historical event IDLs stay pinned because existing creator-fee event fields still report the
same costs. These account changes apply equally to learning and the position watchdog.
See the [follow-up validation](V1_10_10_VALIDATION.md#holder-rewards-and-dashboard-recheck--12-september).

Dashboard status reuses feature-vector completeness checks only inside its synchronous, locked
response, using thread-local temporary storage. Outcomes, exact Policy reservations, populations,
coverage and health retain their normal checks. The next response, standalone qualification and
trading work do not inherit the temporary results. Cancellation still waits for the worker before
releasing the market boundary; no unlocked access to mutable learning state was introduced.

The original network/priority fee budget is frozen for each new observation and Decision Lab
assessment. Validated sell quotes round fee components individually and account for LP fees
retained in an AMM vault. A fresh account with insufficient executable liquidity is still an unknown
learning outcome, not an invented zero-price trade. The held-position watchdog can separately use
repeated, fully verified empty-route observations as terminal-accounting evidence.

Exit tournaments use all required paired horizons, including evidence lacking the five-minute
checkpoint. Secondary checkpoints update governance without forcing an unnecessary model fit.
`paired-skill-outcomes-v2` distinguishes the corrected proof; older Exit promotions are suspended
until qualified under it. Decision Lab schema v5 prevents older, weaker outcome semantics from
silently qualifying new guarded authority.

Training runs against private copied inputs and an artifact reader. Fitting cannot publish models
or mutate live skill state. Publication rechecks configuration, risk, learning mode, consent,
Champion dependencies, learner identity, demo state, season and shutdown state. A failed, changed
or over-120-second job publishes no result and queues a current retry. The elapsed limit rejects
late output; it does not forcibly interrupt native fitting. Existing row, round and CPU bounds
remain necessary. Coach can study while holdings are dormant or healthy and executable. Pending
orders, stale/unexecutable active holdings, imminent/unassessed reviews, training and market pressure still
take priority. Its detached read/screening workers can pause between batches and resume the same
complete cohort within a 30-second deadline; interrupted work supplies no partial proof.

The v1.10.7 burst-performance follow-up filters otherwise unusable Discovery rows before checking
their reserved Policy identity. It also reuses the exact identity digest for unchanged contract
material in a process-local cache capped at 16,384 entries. The cache holds no observations,
coefficients, outcomes, eligibility or health decisions. Changed contract fields use a different
key; eviction or restart recomputes the same digest. Every proof check still reads the current
retained identity receipt, clocks and outcomes. This changes neither coverage denominators nor
training/independent-proof separation. See the [validation record](V1_10_7_BURST_VALIDATION.md).

Models, skill artifacts (including nonlinear payloads) and pending skill enrollment commit in one
SQLite transaction. The live candidate view changes only after that commit. An interrupted write
or failed commit leaves the previous generation intact and the fit retryable, including after
restart. Tournaments begin only after all candidate records have been committed.

### History, storage and rollout

Schema 14 imports embedded/sidecar Champion events into an indexed journal transactionally. UI
pages are bounded and each live skill retains only its latest 100 events in memory. Generation
and defence counts come from the journal, so paging does not rewrite a Champion's history.
Heavy artifacts use the existing retention cap while preserving active, testing, pending and
required dependency versions. Protected versions may exceed the target; authority is never deleted
to meet an arbitrary disk limit. Pruned versions retain hashes and audit metadata, but an archived
payload cannot be replayed from its hash alone. Storage targets still require operational monitoring.

v1.10.6's schema 15 adds a bounded per-season strategy-usage sidecar. It records actual
applied participants without feeding those descriptive labels into training or proof. Existing
season history remains unknown or partial; rollback requires the matching pre-upgrade data and image.

Start the optional reserve worker in Shadow and compare recovered outcomes, unknown reasons,
checkpoint deadlines, provider quota use and event lag across both lanes and venues. Its runtime
status is included under the event pipeline's learning reserve refresh diagnostics. A 48–72 hour
soak and later common-forward economic evidence are rollout validation, not results established by
unit tests. Keep the selected coverage contract and current activation consent. The separately versioned
prospective portfolio experiment from the improvement plan is not included in this release.

Coverage is the usable fraction of a moving evidence window, not progress that inevitably reaches
100% with time. Broad Discovery model coverage and actionable Policy proof coverage have different
populations. Faster collection may recover stale checkpoints, but cannot make an illiquid route
executable. Changing a training population requires separate validation; higher coverage alone does
not establish stronger predictions or better trading. Collection does not change the selected
gate or the missing-outcome denominator.

### Evidence lanes

Learning has three deliberately separate evidence lanes:

- **Discovery** keeps at most one eligible ENTER or PASS observation per mint. It finds broad
  associations and proposes bounded contenders, but does not by itself prove deployable policy.
- **Policy proof** stores one actionable Baseline ENTER trajectory per mint and paper season. For
  qualification and tournaments, only the earliest eligible trajectory for each mint in the exact
  cohort contributes; later seasons remain auditable but cannot multiply one token into proof. It is
  generation-bound, qualification-eligible evidence for the exact veto, sizing and exit behavior
  that could really have acted. If a mint was first observed as PASS, a later genuinely actionable
  ENTER may still begin this separate trajectory; repeated decisions in the same trajectory cannot
  manufacture sample size.
- **Paper execution** begins only at an actual fill and records actual fees, exits, returns and
  terminal disposition. It audits whole-system behavior but never substitutes selected fills for
  the untouched counterfactual policy evidence needed for qualification.

Every lane must come from Solana Mainnet mode and live market evidence. Synthetic Demo decisions,
structurally unsafe tokens, WATCH states, and repeated snapshots of the same eligible identity are
excluded. This avoids letting fast updates, selection effects or demo patterns dominate proof.

Schema 16 retains compact Policy identity reservations independently of the larger trajectory
payloads. The first eligible episode and exact UTC entry time remain the proof identity even after
its payload is pruned. Neither the same season nor a later season can substitute a second attempt
or release that mint's Discovery twin for fitting. Equivalent timezone offsets identify the same
instant; missing, naive or changed clocks cannot authorize a replacement proof episode.
The migration backfills retained records only: deleted pre-upgrade identities cannot be recovered.
The durable ledger grows with unique mint/contract identities in the main data volume. Only entries
needed by retained observations and episodes are cached in memory and copied into a training job.
Current Entry observability also requires the active source, feature schema and Baseline contract;
unavailable outcomes from that valid population remain in the denominator.

The saved lesson contains the exact point-in-time features and baseline action. Later live trades
for that mint add fee-inclusive paper outcomes at 1, 5, 10, 15, and 20 minutes. Each outcome uses
the same integer curve quote and configured protocol/network costs as the paper broker. If a
horizon has no usable future observation within its grace period, it stays **unknown**; it is never
silently treated as zero or as a loss.

The v1.10.11 activity follow-up adds a separate descriptive breakdown to **new saved decision
snapshots**: buy share of quote volume, signed net quote flow, trades of at least 0.01 SOL in
one/five minutes, wallets with at least one such trade, wallets net buying at least 0.01 SOL,
and positive-amount coverage. These are not added to the learned feature vector, proof
denominators or Baseline score. Existing feature/schema and policy versions stay unchanged.
Wallets are identifiers, not verified independent people. Gross wallet turnover can cross the
older `meaningful_wallet_ratio` cutoff through repeated tiny trades; that existing feature's
meaning is preserved. The new wallet counts are explicitly different measurements.

Signed flow is `(buy quote - sell quote) / gross quote`, in [-1, 1]. The existing
`net_quote_flow_ratio` remains an absolute fraction in [0, 1]. New quantitative flow/count
fields require complete positive amounts in the observed window; wallet counts also require
complete wallet identities. Empty windows and unsupported quote assets remain unknown.
Existing freshness, venue, one-second cache, continuity and buffer saturation evidence still
apply. These fields do not prove five minutes of uninterrupted observation, clean markets,
good entries or profitable holds. Historical snapshots are not backfilled. See
[activity evaluation](ACTIVITY_EVALUATION.md) before proposing strategy changes.

The enrollment follow-up, deployed locally on 20 September, also freezes a compact
`activity-evidence-v1` companion at each new Discovery or Policy parent's original decision.
It is separate from lesson JSON and training copies. Parent updates, later successful retries
and decision-history cleanup cannot replace it; deleting its learning parent cascades to the
companion. Historical parents remain unknown and receive no retrospective backfill. A failed
optional measurement is explicit, while serious storage failures retain the existing error path.
These records are research provenance, not new features, manipulation truth labels or proof of
better buying. [The offline research contract](ACTIVITY_EVALUATION.md#offline-prospective-screen)
keeps valid failures and missing outcomes in the population and does not grant Champion authority.
The standalone reader can export a compact period from one read-only snapshot. Persistent identity
receipts protect earlier opportunities; missing receipts, possible pruning overlap or selection
truncation prevent a positive screen. Recorded companions and usable inputs are reported separately.
This research tooling does not run in the trading loop or alter the training window or native proof.

Starting with the `stream-integrity-v6` contract, each eligible lesson also freezes structural
market evidence available from the same five-minute Solana stream: the share of one-trade
wallets, wallets that rapidly bought and sold, volume attributable to those round trips,
absolute net quote flow relative to gross volume, buy/sell alternation, two-significant-digit
amount clustering, slot concentration, price-direction consistency, dust-trade share, median
native-SOL trade size, meaningful volume and wallet participation, trade density, price-path
efficiency, and rapid reversals. Transaction-signature bundling remains available to deterministic
integrity and explanation when coverage is sufficient.

These are descriptive measurements, not a scam probability. Organic viral launches, market
makers, copy bots and legitimate bundled transactions can each produce one or more similar
patterns. Baseline v1.5 therefore requires complete economic/path fields and uninterrupted event
continuity, holds an entry when one isolated warning is extreme, and blocks a current entry only
after independent corroboration classifies it as suspicious or severe. Older locked
v1.1/v1.2/v1.3/v1.4 seasons retain their exact policy; v1.1 keeps
the original observational-only path, v1.2 keeps its original four integrity categories, and v1.3
adds one concentrated-dispersion category only when extreme wallet-volume
concentration and overwhelming one-trade participation occur together; either signal alone is
insufficient. v1.4 adds its mature-sample and isolated-warning treatment without adopting the new
economic/path gate. The challenger still receives the frozen raw measurements and
learns their relationship to later net outcomes, while the Coach may propose only an allowlisted
shadow veto experiment that must pass the same independent forward-evidence process as every
other coaching idea.

Wallet, amount, slot and price coverage must each be sufficient before a new learner row is
created. Process startup, a WebSocket reconnect, fallback activation or an explicit market-source
change begins a fresh five-minute source-wide continuity window only after provider recovery is
confirmed; disconnected time never ages the safeguard. Bounded queue shedding and an exceptional
worker-batch failure start the same clean-window requirement only for represented mints, so
unrelated tokens can continue to learn from complete evidence. A failed event with no identity or
a saturated bounded gap tracker fails closed for the whole source. Failed batches are not replayed,
avoiding duplicate broker side effects. Protected open-position and already-saved outcome events
continue normally. Missing evidence remains `unknown`; it is never converted to zero. The evidence
schema is included in the configuration fingerprint and the feature family is
`challenger-features-v5`, so all
older observations and models remain readable and auditable but cannot be mixed into the new
forward cohort as if those fields, continuity and strict per-mint causal ordering guarantees had
existed at the time. An impossible legacy execution is likewise retained for audit but cannot
become qualification evidence.

The five-minute net return remains the Entry skill's training target. The five horizons also
form conservative hold-timing comparisons against the exact normal review for each mode: 5 minutes
for Safe, 10 for Balanced, and 20 for Aggressive. Reported P/L remains unknown when no executable
quote exists, but horizon *utility* treats an unavailable exit as worst-case for selection only.
This lets a repeated pattern of vanishing liquidity favor an earlier review without claiming a
made-up sale price.

## Training and validation

After a restart, the source continuity safeguard must first establish five uninterrupted minutes
before new observations can enrol. Each new observation's primary outcome is due five minutes
after its own enrollment, not five minutes after startup. Retained pending observations can
progress sooner. One-minute or later-horizon checkpoint updates do not themselves advance the
primary-outcome retraining counter. New rows, checkpoints, usable primary outcomes and completed
publications are separate signs of progress; a healthy worker waiting for evidence is not a fit.
Elapsed time alone guarantees neither a usable quote nor enough qualifying samples.

Training begins after at least 80 usable live discovery outcomes and reruns after ten additional
outcomes. Eighty samples are only enough to attempt a challenger; they are not proof of an edge.
Requests are coalesced by exact risk/configuration cohort and fitted by one background worker only
when the market queue is empty, no batch is in flight, processing lag is low and maintenance is not
active. A slow fit therefore cannot hold the event-state lock. Shutdown waits for an already
running fit to finish before closing SQLite; it does not abandon a thread still using the database.
Immediate active-skill health checks and common-forward tournament updates remain on the outcome
boundary and are not deferred.
Database retention also yields to the market path and no longer performs routine full-journal row
counts. Due checkpoint events are reclassified when handled, so protection gained while waiting in
the queue is retained; maintenance performance cannot turn an incomplete sample into qualification
evidence or make a Champion gate easier.
Those safety and tournament decisions read the authoritative Policy-proof journal, not the
one-per-mint Discovery index. A later actionable ENTER can therefore advance honest Champion proof
even when an earlier PASS for the same mint has already completed. If both lanes exist for that
mint, its Discovery row is excluded from fitting, so the same trajectory cannot train a contender
and qualify it.

The primary local learner is a regularized Linear model implemented locally with no cloud AI or
GPU. Once at least 250 chronological training rows exist, one predeclared shallow XGBoost Entry
recipe may also be attempted on a single CPU thread. It must reduce untouched validation RMSE by at
least 2% relative to the matching Linear contender before its added complexity is eligible; a
marginal result loses to Linear. Both families use the same bounded, named point-in-time features,
including the stream integrity evidence. Older
observations form the training section and the newest third form a forward validation section,
with at least 20 validation examples. Validation is chronological, never randomly shuffled. Any
training outcome observed on or after the first validation decision is embargoed, so overlapping
five-minute labels cannot leak future information across the split.

The XGBoost eligibility display uses the latest matching Linear/XGBoost fit, not the maximum
sample count of retained artifacts or a live recount. Its measurement time appears in the
details. Older XGBoost or Coach artifacts cannot inflate a newer, smaller fitted cohort.

A model is fitted only within one exact risk mode and decision-relevant configuration, including
the Baseline, integrity and sizing-policy versions. A new deterministic policy therefore starts a
new forward cohort without deleting or relabelling older lessons or models. Risk
personality is the core learning cohort: Safer evidence cannot qualify Balanced or Aggressive,
and changing personality never deletes the older cohort. The season-profile fingerprint is a
separate comparison identity. Balanced Default DD, custom DD and DD Off seasons therefore share
the Balanced learning lineage because the override changes portfolio admission, not the saved
point-in-time token target, quote math, fees, feature vector or forward outcome. Each observation
still freezes its season ID and exact profile fingerprint. SOL and USDC bankrolls—and different
starting amounts—also share that personality lineage: denomination and funding size change Results
comparison and admission eligibility, not the forward token-return target. A candidate blocked by
drawdown, cash, exposure, capacity or
conversion is marked non-actionable instead of being credited to a Challenger veto.

A model
qualifies only when its untouched validation section:

- comes from a recent 1,000-observation window meeting its recorded coverage requirement
  (70% by default) for executable five-minute outcomes;
- beats a training-mean naive forecast on root-mean-square error by at least 2%;
- improves correlation over the saved baseline score by a margin;
- has at least a 1% mean outcome in its highest-ranked group; and
- improves that group over the baseline ranking by at least one percentage point.

Ranking is not enough. The `learning-evidence-v2` policy journal independently freezes whether a
Baseline ENTER was genuinely submittable under cash, exposure, capacity, and conversion gates.
Only episodes from the exact current risk, configuration, Baseline and feature generation count.
At least 20 usable policy outcomes, the recorded policy-outcome coverage (70% by default), ten familiar cases (within
learned support, whether kept or vetoed) and five proposed vetoes are required. No more than 35%
of tested vetoes may discard winners, and the
bounded fee-inclusive uplift must retain a positive conservative lower bound. At least 95% of the
broad validation section must also remain inside fitted feature support. An out-of-distribution
policy case is kept by the Baseline—it is never credited as a Challenger veto—and a later
unfamiliar decision always falls back to the transparent Baseline.

The same fallback applies to Entry/Manipulation shared-battle scoring and manual health/join
checks. A recorded `veto` proposal outside learned support earns the Baseline return, including
its losses, and is not counted as a winner veto. Unknown executable outcomes remain unknown.
An ongoing replay crossing this scoring correction restarts its displayed points as a partial
recording; contestants and evidence remain intact. Completed historical replays are preserved.
The correction does not change the shared Exit proof version or suspend an existing Exit Champion.

The persisted coefficients are the exact older-section candidate evaluated by those checks. The
app does not refit that artifact on the validation outcomes after it passes. This gives every
active version an honest correspondence between its saved metrics and its actual predictions.

Every trained version and its metrics are immutable in SQLite. A nonlinear payload is portable
XGBoost JSON in a separate application-owned SQLite table, limited to 8 MiB and verified by SHA-256
before loading. The metadata and payload commit together; missing, mismatched, oversized or corrupt
payloads fail closed and cannot activate. Heavy numerical libraries are loaded only when enough
evidence exists to fit nonlinear work or a saved nonlinear artifact must be evaluated. Failed challengers remain visible
instead of being hidden. Small samples, correlated token launches, regime changes, selection bias,
and many attempted versions can still overfit these checks, so qualification is a guardrail—not a
profit certificate.

## Four independent skills

The Challenger is a small team of separately versioned skills rather than one model receiving
blanket authority:

- **Entry** estimates the conservative five-minute outcome of an actionable Baseline ENTER. It may
  veto an entry, but never create one.
- **Manipulation** learns only from the frozen integrity feature family. Its veto policy must show
  adequate coverage, enough tested vetoes, positive conservative value and a bounded winner-veto
  rate. This keeps an attractive organic launch from being labelled bad because of one noisy clue.
- **Sizing** records exact 0.5×, 1×, 1.5× and 2× counterfactual curve quotes at entry and each later
  horizon. It learns normalized, fee-inclusive value so bankroll size is not mistaken for skill.
  It may recommend only those bounded multipliers, and may size above 1× only when the current
  deterministic integrity conclusion is Clean and the exact larger amount still fits every
  deterministic capacity and route-impact limit. Otherwise it records a capacity abstention and
  preserves the valid Baseline amount.
- **Exit** compares earlier normal-review checkpoints within the exact risk cohort. It may shorten
  the normal review, but never extend it or bypass stop loss, structural exits, trailing protection
  or the absolute hold ceiling.

### Contextual Exit timing (v1.10.9)

The existing deterministic fixed-horizon selector remains the simple reference. One additional
Linear family (`exit-context-v1`) fits small ridge models for the allowed checkpoints at or before
the risk profile's normal review: 60, 300, 600, 900 and 1,200 seconds where applicable. It uses ten
existing original-entry features, fixed regularisation and the existing clipped training targets
and recency weights. There is no new provider request, feature search or hyperparameter search.

Both families use the same newest-at-most-1,000 Policy rows and chronological split. All training
checkpoint timestamps must precede the held-out boundary. Missing returns cannot train a model,
but resolved unavailable outcomes stay in the validation denominator. Each horizon needs at
least 40 usable training rows. The contextual family requires at least 20 usable validation rows,
its recorded paired coverage (70% by default), a conservative advantage of at least one percentage point over both Baseline
and the fixed selector, at least 90% familiar entry contexts, five earlier-review choices and the
existing 35% harm limit. An identical fixed choice cannot qualify merely by adding complexity.

A qualified fit still needs the existing fresh battle and independent activation proof. Queued
versions cannot borrow receipts collected before their battle. Original Policy receipts freeze
the contextual choice and the reigning Champion's identity before outcomes exist. A contextual
contender's battle rows cannot activate it after promotion, including when it replaced a suspended
Champion. Activation needs observations frozen while it was already the Champion; unlabelled older
review-build receipts do not establish that stage. Unavailable outcomes in the eligible post-crown
population still reduce coverage. Upstream Entry
and Manipulation vetoes and exact Sizing quotes remain part of the composition proof. A contextual
Champion can face a later native or permitted Coach contender, be suspended, or earn recovery
through the same one-shot 60-entry trial. No trial reset or automatic crown is introduced.

When authorised, contextual timing is selected once from the actual entry decision and persisted
with the pending order and resulting position. Delayed fills and restart retain this record.
Every use checks current permission, Champion identity and digest, risk/configuration/Baseline,
health and upstream activation epochs. It never reruns prediction on later market features.
Missing or unfamiliar entry context, an old position without a plan, invalid payloads or revoked
authority use Baseline normal-review timing. Recovery or a changed composition does not retrofit
an old plan. These optional JSON fields leave schema 16 and existing bankroll/position data intact.

Exit qualification and battle values compare fee-inclusive checkpoints; they do not replay the
entire adaptive exit policy. Actual exits still respond to current evidence and hard safety rules.
A better checkpoint comparison therefore does not establish a live P/L improvement. This small
family adds bounded training cost in the existing private worker; it is not a burst-throughput fix.

Champion Arena distinguishes suspended trade support from continuing shadow comparison. Learning
Off or a different data source still pauses the live readout. Completed recovery details show
recorded failed checks when available; older trials do not acquire invented explanations.

Each artifact freezes its skill, feature schema, Baseline version, configuration fingerprint,
risk personality, parameters, evidence interval and proof metrics. Sizing and Exit do not inherit
Entry qualification; Manipulation does not inherit the broad model's score. This prevents one good
metric from granting unrelated permissions.

Pending checkpoints are sampled from the engine's already-cached route state on the normal
heartbeat, so long-running learning adds no extra provider requests. At most 20 are attempted per
tick, with currently usable routes ahead of stale ones so an old dead token cannot starve newer
lessons. A route with missing reserves, a stale or future timestamp, an unverified PumpSwap path,
an unconfirmed migration or an unsupported quote mint records the precise unavailable reason. It
never receives a fabricated return.

During queue pressure, held positions, pending orders and actual execution outcomes retain the
critical backpressure path. Routine discovery/policy checkpoints use the normal durable path and
rise to critical priority only from 15 seconds before a due horizon through its 90-second grace
window. Execution episodes alone do not keep dead candidate state resident: an actual open
position already supplies the authoritative retention reason.

Missing five-minute exits remain unknown and are never inserted into regression as fictional
losses. Once their grace window has resolved, they still count in the availability denominator, so
a survivor-only set of liquid tokens cannot qualify or activate an entry model. A horizon still
inside its observation window remains pending and is excluded until it actually resolves.

### Retention, training windows and saved evidence

For predictable long-running use on a small home server, pending lessons are always retained and
the newest 5,000 completed token lessons remain as full point-in-time records. Fitting and timing
selection use only the newest 1,000 comparable outcomes; entry fitting also exponentially
down-weights older examples with a 500-observation half-life. A separate monotonic outcome count
ensures new lessons still trigger retraining after the retained window fills. Model versions and
their validation metrics remain immutable while retained. Version history is bounded to the
newest 1,000 challengers; active, suspended, champion, latest-candidate and in-flight tournament
versions are protected from pruning.

The Entry limit is a **resolved observation window**, not the number of regression examples.
Usable fee-inclusive outcomes are split chronologically; the newest third (subject to the
minimum validation count) is held out, and training outcomes that were not known by the
validation boundary are excluded. A 1,000-observation window can therefore yield far fewer
training rows. Retaining 5,000 completed observations does not mean every new fit uses all 5,000,
and a rolling window covers a different time span as traffic changes.

Native independent activation/support and active-health checks have another recency boundary:
they select from at most 1,000 independent actionable **Policy** opportunities in the matching
contract, then apply the current composition, receipt and outcome requirements. Independent join
proof uses at most the latest 60 resolved eligible opportunities and still needs at least 30 usable
comparisons. These are different populations from Entry's resolved Discovery training window.
When an upstream Champion vetoes most opportunities, downstream support can grow slowly or shrink
as older eligible rows leave that Policy population. A falling counter alone does not establish
lost saved evidence. An isolated review reproduced 30 → 10 → 0 support with increasing newer
vetoed rows, regardless of those rows' positive or negative outcomes. The current selection rule
is unchanged; extending it would require a separately defined proof-policy and lifecycle review,
not retrospective retention of favorable examples. Recovery studies retain their own rules.

Expanded artifact details show only that generation's saved counts, period and cutoff. Entry
and Manipulation periods describe usable Discovery evidence, not all resolved observations in
the coverage denominator. Sizing's Policy window includes observations without usable targets;
those missing targets are separate from chronology exclusions. Contextual Exit inherits its
shared training-cohort count, while each horizon fits only its available outcomes; historical
per-horizon fit counts are not recorded. Coach counts refer to historical screening and a
separate forward study, not a regression split. Unknown formats or absent dates do not borrow
details from the current collection or another model. Malformed or impossible calendar dates
remain unavailable rather than being normalized into another date. Checklists explain saved proof and grant
no promotion or execution permission; Entry's coverage-freshness check appears once per family.

A local retrospective comparison of 1,000/2,000/3,000 windows did not establish a dependable
benefit from a blanket increase. Larger windows also move the newest-third validation boundary
further back, which can delay adaptation and prospective validation after a setting change.
The 1,000 default remains provisional, not a claim of universal optimality. Any future change
needs independent later evidence and an audit of shared proof selection and reporting bounds;
simply raising a constant would change more than training history.

Terminal policy and execution evidence is likewise bounded to the newest 5,000 records per lane;
pending trajectories are never pruned.

Paper-execution evidence is first committed inside the broker's accounting transaction. Only
after that commit succeeds is the learner's in-memory read model refreshed. A notification failure
cannot undo or repeat a fill, and restart or a paper-season boundary reloads the authoritative row
from SQLite, including provider-unknown and confirmed-write-off terminal states.

This is deliberately a bounded rolling memory rather than lossy compression. Aggregating old
tokens into a few averages would destroy tail events, missing-liquidity evidence, and the feature
combinations needed to reproduce a lesson. Keeping 5,000 compact JSON lessons is still small for
SQLite, while limiting the active model window prevents very old regimes from dominating current
decisions.

The legacy non-artifact hold-timing fallback has a separate fixed 70% gate; it does not inherit
the entry model's qualification or the configurable native Exit requirement. For each
exact risk mode and configuration, at least 60 complete comparable observations are split
chronologically with the same
outcome-overlap embargo. The older section selects a review horizon no later than that mode's
normal review. On the newest third, a conservative 1.96-standard-error lower bound of its utility
improvement must still exceed one percentage point, with at least 70% executable exit
availability. A timing choice
that fails any gate falls back to the deterministic normal review. Timing calculations are cached
until checkpoint evidence changes, so a long history does not add repeated work to every market
event.

## Candidate, champion and common-forward proof

A newly qualified artifact is a **candidate**, not automatically the best known skill. When Linear
and XGBoost finish from the same evidence cutoff, the initial Champion is selected only after both
are registered: XGBoost must show the predeclared material validation advantage without weaker
policy proof, while marginal comparisons prefer Linear. Job completion order cannot crown either
family. If no champion exists the selected candidate can become the initial saved champion.
Otherwise both candidate and champion
are frozen before the next outcomes arrive and are evaluated on those same common-forward cases.
Promotion requires at least 30 common cases, the battle's frozen coverage requirement (70% by default), positive
confidence-adjusted improvement and the skill's harm/winner guards. An inconclusive tournament is
closed after 120 usable common-forward cases, or after 172 resolved cases when executable coverage
remains below that requirement, rather than running forever or learning from a survivor-only subset. Candidate,
champion, counters and decisions are stored in SQLite, so restart cannot erase a loss or restart a
trial selectively. If the promoted champion is already influencing decisions, its exact proved version
replaces the old one; downstream skills step out and must re-prove beside the new dependency.
At most one untested generation per family waits behind an active tournament; a newer untested
generation supersedes the older one, while an in-flight comparison is never replaced. A queued
contender begins accumulating common-forward receipts only when its tournament starts.

The Learning tab presents the current Contender, best-proved Champion and actual influence
separately. A candidate can therefore have fewer passed gates than an older champion without
destroying that champion; that is healthy exploration, not forgotten learning. It also keeps the
complete durable sequence of recorded Champion milestones per skill cohort: first qualification,
promotion, defence or an inconclusive 120-case battle. The initial snapshot carries only the newest
eight events; older events are fetched in bounded cursor pages only when requested. Pagination is
locked to the exact active cohort, so a personality or decision-relevant configuration change
cannot mix two histories in one view. Each battle can show the actual Champion and contender,
model families, shared forward sample, outcome coverage, mean edge, conservative floor and the
engine's recorded resolution. A defence counts as a crown retention because the contender did not
prove the replacement margin; it is not presented as a guaranteed profit or outright trading win.
Per-skill reign records are calculated from the complete retained cohort history and distinguish
Active, Shadow and safely Suspended Champions.

Entry also exposes a compact nonlinear eligibility line. Its row count comes only from the newest
matching Linear artifact in the exact current risk, configuration, Baseline and feature cohort;
older large artifacts cannot inflate it. Reaching 250 rows means only that the fixed XGBoost recipe
may be attempted. The UI separately reports testing, qualification, Champion and active states, so
eligibility can never look like promotion progress; a safely suspended nonlinear Champion is
labelled separately as well. Detailed proof sections begin collapsed and
Entry's authoritative qualification gates are labelled **Entry's road to influence**; the other
three skills retain their own independent proof inside their skill cards.

Entry's waiting-family comparison requires matching Discovery cohorts, cutoffs, feature lists and
sample counts, plus the same recorded Policy population. That Policy fingerprint includes resolved
unavailable outcomes. Missing legacy provenance or different populations use chronological waiting
order; current journal data never invents a past comparison. The common-forward battle and all
qualification requirements still decide whether a contender earns authority.

Events are idempotent across restart and shown only for the exact current
personality/configuration cohort. Every referenced contender or Champion artifact is protected
from pruning, so lineage remains reconstructable. Deterministic codenames are derived from
immutable artifact identity and therefore remain stable across clients and restart; they never
replace the technical version. An installation upgraded from an older version keeps its existing
Champion but does not fabricate battles that were never recorded. The journey is stored beside,
rather than inside, the strict skill-state record so an older v11 reader can ignore the new
history safely. The state and sidecar are committed atomically.

## Consent, composition and rollback

Automatic Champion support is a separate, explicitly enabled preference, off by default. It can
wait while no skill is ready. Entry keeps its existing activation gates; Linear or XGBoost can
earn that crown. Manipulation, Sizing or Exit can also be the first active skill without Entry,
but only after independent qualification and fresh proof against the Baseline alone. Later joins
must match the exact prospective upstream versions and start after those versions joined. The
native proof comparison may ignore downstream roles because the saved upstream proposals and
paired shadow outcomes precede their actions. It cannot ignore an upstream mismatch, an already
active version of the skill being tested, or an unknown role. Coach research and its initial battle
retain their exact full-ensemble contract. A Coach that earns a crown starts a separate, durable
composition-proof window before activation, including for Entry; its immutable research artifact
does not change. After activation, receipts use its active version and upstream dependencies.
Missing expected receipts count as unavailable once the required outcomes have resolved; pending
outcomes do not cause premature suspension. The latest 60 resolved eligible cases must contain at least 30
usable outcomes, the applicable saved/current coverage requirement (70% by default),
a positive conservative incremental advantage and the existing harm guard. A saved crown alone
does not grant influence. The legacy manual Active API keeps its Entry-first contract and rejects
manual activation while automatic support is enabled, so the two authority policies cannot mix.

Each automatic activation stores a versioned receipt with its dependencies and proof. Restart
validates that receipt before restoring authority; missing or inconsistent receipts fall back
safely. New Sizing receipts freeze the actual integrity/capacity clamp. Exit alongside Sizing
uses that bounded size at both compared horizons. Missing old clamp or size/horizon evidence is
unknown and cannot qualify the combination. Training recipes and tournament results are unchanged.

Composition changes are treated symmetrically. If a newly proved upstream skill joins after a
downstream skill was already active, the downstream Champion and journey are preserved but its
authority is removed until that exact new ensemble earns fresh incremental proof. Runtime
assessment checks the saved version and required dependencies before application. Automatic
governance checks current health and the full activation receipt; restart validates that receipt
before restoring authority. Invalid authority falls back to the smaller proved ensemble.

Every eligible observation freezes the active skill versions and each skill's proposed action
before the future outcome exists. Entries that cash, exposure, capacity or conversion gates would
already block remain non-actionable, so a veto cannot claim credit for a trade the portfolio could
not have placed. Each final decision also carries a per-skill audit receipt describing whether the
skill abstained, vetoed, changed size or shortened review.

After 30 resolved cases, per-skill rolling health checks compare each active version with its
bounded counterfactual in the current activation and exact upstream composition. A downstream
join does not reset an upstream skill's health; reactivation starts a new health window.
Pending horizons do not count as failures; resolved unavailable outcomes
do count against coverage. A harmful or insufficiently observable skill is suspended. Downstream
dependants lose authority and need fresh composition proof; this does not mark them as harmful.
Unrelated upstream evidence and every immutable artifact remain intact. With automatic support,
the preference stays enabled: a newly proved replacement or another independently qualified skill
can join after the appropriate fresh proof. Without automatic permission, the legacy Entry-first
mode returns to Shadow when Entry is suspended.
A restart cannot silently substitute the newest artifact.

With automatic support enabled, a Champion suspended specifically for harm or insufficient
observability may earn its support back through one fixed prospective shadow trial. The first
60 new original eligible Policy entries are selected before outcomes exist, after suspension and
the artifact's creation, in the exact current upstream composition and activation epochs. No
earlier training, battle or active-health result counts. All 60 must resolve or reach their existing
checkpoint deadlines before a decision; missing receipts and lost rows remain unavailable in the
denominator. The trial requires at least 30 usable outcomes, its applicable coverage requirement
(70% by default), a positive conservative
advantage and the existing harm limit. Entry also retains its current Entry activation gates.

There is one trial per suspension, with no sliding window, early success or retry after failure.
A changed upstream composition invalidates that trial. Failed or invalidated trials wait for a
newly qualified replacement; training and normal battles continue. Missing, incompatible or corrupt
artifacts, obsolete comparison proof and unknown suspension reasons cannot use this recovery path.
Disabling support or pausing learning cannot reset a failed trial or restore authority. Coach
crowns keep their existing contribution provenance and use the same fresh composition boundaries.
Recovery restores the same immutable Champion and generation, starts new active-health monitoring,
and awards no new crown. The bounded recovery receipt and original suspension reason/time survive
restarts in compatible state JSON; diagnostics intervals retain a compact summary without Policy IDs.

Identical native deterministic Exit fits remain saved for audit but do not start redundant battles
or replace a different queued policy. Identity requires the complete executable policy contract,
including verified parameters/digest, risk, configuration, Baseline, feature schema and recipe.
Ongoing battles are preserved. This rule does not deduplicate learned Linear/XGBoost or Coach ideas.

Changing risk personality or a decision-relevant Baseline/provider/fee configuration returns an
active ensemble to Shadow and clears influence, while retaining the user's consent and all learning
history. A drawdown-only season transition within the same personality does not create a false
model generation. Older versions can contribute again only when their exact learning cohort is
compatible.

These bounds are cautious decision rules, not formal 95% guarantees: token launches can be
correlated and returns are not normally distributed. The automatic response to a false alarm is
only to restore the transparent baseline, never to take more risk.

## Modes and safety boundary

- **Off**, shown as **Pause learning & support**, stops new learning observations and removes
  Champion influence. Saved models and automatic-support preference remain. Already-started
  horizons and queued training may finish; resuming learning permits future qualification checks.
- **Shadow** is the default. It records outcomes and shows what the latest challenger thinks, but
  never changes a paper decision.
- **Active** means at least one proved skill has influence. Explicit automatic support can begin
  with any independently qualified skill under the composition gates above; the legacy manual
  activation API still requires Entry. Deterministic entry, fill-time route/integrity, cash,
  exposure, stop, structural exit, trailing and absolute-time controls always retain priority.
  Later unseen results monitor every active version and can automatically suspend only the unsafe
  part, returning to Shadow when no approved skill remains.

The learner cannot create an entry, exceed deterministic sizing capacity, weaken a permanent
safety gate, extend past the absolute ceiling, fabricate an exit, or touch a wallet.

## Separate local-AI experiments

### AI Coach research

The AI Coach is a slow, optional researcher that runs only when market and position work are
quiet. Deterministic code creates a small allowlist of Entry veto, Manipulation veto, Sizing and
earlier Exit-review ideas; the selected local model may choose one of those candidates or choose
none. It cannot invent a condition, submit an order, change a live decision, or weaken a safety
gate. Coach research can be paused independently without deleting its notebook or disabling saved
Shadow decision reviews.

After a position's normal review, a current `hold / adaptive_extension` assessment can allow
research to resume. It must match the current season and exit-policy version, follow process
start and the latest mark, and be no more than 30 seconds old (or the configured mark limit,
if shorter). The completed assessment must reach the position's effective normal review;
an earlier Champion review alone does not satisfy that check. Effective hard limits and hold
support are rechecked, with more than the 75-second inference budget plus a 30-second guard
remaining before any active position's hard exit. Missing, malformed or stale evidence keeps
the exception closed. The scheduling check uses bounded in-memory state; it does not reassess
positions, change orders, request quotes or read learning history. Dormant inventory retains
its existing scheduling behaviour, while any pending order still takes priority.
The complete Coach inference request has a 75-second deadline, including generation-lock and
quota waits. Timeouts retain the existing failed-review/backoff path and create no hypothesis.
Cancelling a local request does not prove that a remote inference server has already stopped
computing; resource sharing and burst behaviour still require observation on the deployment host.

Historical evidence may screen or reject an idea, but cannot prove it. Every selected study
freezes its risk personality, decision-configuration fingerprint, Baseline version, feature schema,
active skill dependencies and proposal cutoff. The cutoff is frozen after the model selects an
idea, not at the beginning of inference.
New `policy-v1` studies use canonical, Baseline-actionable Policy entries created after that
cutoff, including tokens whose earlier Discovery observation was a Pass. Matching risk, fees,
Baseline/features and active dependencies remain mandatory. Discovery remains the separate
historical screen and cannot supply forward proof to a new study.

Each study enrolls at most 180 independent identities in chronological order and reads at most
64 new journal keys per page, plus its bounded pending identities. Only the resolved prefix
contributes to qualification: later quick successes cannot jump over earlier pending outcomes.
Unavailable, missing or invalidated enrolled outcomes count as unknown. Persisted identities
and values survive restart and cleanup. If retention overtakes an unscanned page, the study closes as
inconclusive (`policy_history_gap`) instead of treating surviving records as a complete sample.
The watermark is deliberately conservative across contexts; a retention gap can end a study
without establishing that its own eligible outcomes were lost.
The cursor and pruning watermark both include time and episode identity, so entries sharing a
timestamp cannot hide a retention gap. Pending records are rechecked against their frozen
identity and dependencies before resolution.

Unfinished `discovery-v1` studies transition once to inconclusive (`evidence_contract_changed`),
preserving their old counts and values. A newly screened idea receives a fresh cutoff; no old
outcomes are retroactively credited. Terminal studies and existing contributed artifacts keep
normal history, permission, battle and activation rules. Older builds do not understand the new
research records; rollback must not overwrite newer trading evidence just to restore a study.

A supported study needs at least 60 usable outcomes, at least 70% executable coverage, two
independent seasons with at least ten usable outcomes each, and a confidence-adjusted improvement
above one percentage point. Clearly harmful evidence may reject a study after 120 usable outcomes.
A study that reaches 180 resolved observations or 90 days without enough support closes as
inconclusive, including quiet cohorts that never reached 60 samples; it cannot collect forever.
Coach reports the actual finite difference between alternatives. That difference and its
confidence bounds can exceed the range of either individual return; they are not clipped to
the single-return limits. This corrects storage/reporting without changing the support or
rejection thresholds, fees, or underlying outcomes.

Support still grants no trading authority. The Coach card's **Allow when ready** control saves
explicit permission in advance, even before an idea qualifies. The preference survives restart;
it does not resume paused learning/research or enable automatic Champion support. With permission
on, eligible supported ideas are handed to the matching Challenger skill automatically while
Local AI is on. Turning contribution off stops new handoffs; already admitted contenders and
Champions keep their normal proof and support rules. An idea waits until that skill has a saved
statistical Champion, then enters the ordinary common-forward tournament as one immutable
contender. It cannot create the first Champion, skip proof, replace a Champion directly, or act
outside its exact dependencies. A context change retires the stale contender while preserving the
existing Champion. The Challenger handoff independently revalidates the complete deterministic
allowlist—including policy kind, skill, conditions, multiplier or review horizons—so a malformed
or incompatible persisted Coach record cannot acquire tournament authority.

From v1.10.8, retained forward studies are processed in indexed pages independently of the
100-item recent notebook window. Current-contract lookups also find older active studies and
ready contributions. A durable retry cursor rotates waiting contributions, while newly ready
ideas still receive their first attempt first. This does not grant permission, create a first
Champion or change the research/activation gates. AI Off remains a stop for new handoffs.

Coach refreshes condition their writes on the saved study still matching, so they cannot replace
a newer contribution transition. Forward evaluation can yield under market pressure and resumes
from saved, complete evidence. Active Policy studies skip the historical screening read entirely. Inference backoff does not
pause their bounded forward collection. Saved `collection_counts` report enrollment, pending
work and exclusions; the full internal enrollment ledger is omitted from dashboard snapshots.

Dashboard Policy selection is reused only within one response. Tournament passes may share the
same contract's selected population, but qualification and health decisions remain fresh. A
repeated evaluation with unchanged skill state need not create another database write; pending
replay/history work and failed transactions still require persistence. Verified zero protocol
fees remain zero in new evidence, matching execution; historical recorded assumptions stay intact.

### AI Decision Lab

The optional Ollama AI Decision Lab does not replace this statistical learner or share its
qualification. It starts Off. Shadow asks one selected local model for a strict support/veto/
insufficient-evidence verdict on normalized evidence from a baseline ENTER, then measures the
opinion against a separately frozen five-minute paper outcome including entry/exit/network fees.
Unknown evidence citations, extra schema fields, unavailable models, timeouts, and malformed JSON
are invalid outcomes, never trading instructions.

The local burst follow-up avoids a worker dispatch when every saved assessment for a token is
still before its outcome horizon. It uses the same observation timestamp as the outcome handler
and retains a cooperative event-loop yield. Pending tokens keep their retention and priority;
already-saved outcomes still complete when new AI work is Off or paused. A queued/in-flight
assessment or incomparable legacy clock conservatively keeps the existing handler. Exact due
and grace boundaries, executable-route checks, original fees, negative outcomes and database
failure handling are unchanged. This dispatch optimization does not
change the statistical learner, Coach qualification or Champion requirements.

The assessment-save follow-up moves blocking persistence to a joined worker. A successful save
is registered for outcome collection before caller cancellation is allowed to escape. Failed
saves create no pending outcome; registration remains deduplicated by assessment identity.
A same-token trade waits for an in-flight save before inspecting pending outcomes, preserving its
original observation timestamp. Other-token settlement checks return immediately; the serial
market worker can still wait while handling the token whose save is unfinished. Settings preparation
waits for both inference and the ensuing save/registration; a timeout fails preparation rather
than declaring unsaved work ready. Model/configuration provenance, qualification and authority
stay unchanged. This candidate requires runtime acceptance before a release recommendation.

When registration first makes a token pending, its already queued events receive the same
critical priority as subsequent arrivals. The current bounded batch rechecks priority before
selecting more work. This prevents newly critical arrivals from overtaking that token's older
prefetched or queued ticks. It performs one bounded queue scan per new pending transition,
not per market event; sequence numbers, season boundaries, persistence-before-processing and
the rejection of genuinely stale events remain unchanged. No authority is granted before commit.

Guarded is locked to Shadow until that exact model digest and prompt/schema version have at least
200 measurable outcomes, 20 measurable high-confidence vetoes, 99% valid responses, a positive conservative
uplift lower bound, and p95 latency at or below 2.5 seconds. If it later qualifies, its only
possible action is a high-confidence veto of a baseline ENTER. Changing models returns it to Shadow. These records
include season and configuration provenance and survive a paper-bankroll reset.

## Deliberately deferred research

This generation keeps one fixed nonlinear Entry recipe and adds the small contextual Exit family
described above. It does not add market-regime
authority, hyperparameter search, calibrated return probabilities, reinforcement learning or a
PASS-to-ENTER override. Discovery continues to save eligible PASS counterfactuals for future
research, but no learned component can turn one into an entry. Any future family must use the
same point-in-time feature contract, chronological embargo, independent
policy journal, immutable payload validation and common-forward Champion process; added complexity
must always be allowed to lose to its simpler reference.

## Champion impact

Learning Overview includes a passive comparison of current Champion support against its reference.
It uses existing independent Policy episodes and entry-frozen Champion receipts. It never supplies
an input to training, activation, suspension, Coach admission or the broker.

The local follow-up adds original supported-entry/veto/fallback counts and a separate sample of
actual entries from at most 30 recent fills. Exact order/decision and parent-buy links, current
configuration/season/profile and matching Champion receipts govern attribution. Matched full
closes report proceeds minus entry cost; ambiguous, partial or missing closes remain unresolved.
A later-attempt origin link does not establish an earlier applied veto. These sampled results
are neither full account history nor extra Policy proof. See the separate
[selectivity and fallback study boundaries](SUPPORT_EVALUATION.md); neither study enables buying.
The completed fixed-window selectivity screen did not satisfy its support or economic
requirements. Its candidate remains inactive; this result does not change the incumbent,
coverage policy, training window or any skill's proof requirements.

Entry and Manipulation compare the recorded five-minute Baseline outcome against either that
outcome or cash preserved by a supported veto. Sizing compares the saved bounded multiplier with
the same opportunity at 1× after modeled fees. Exit compares its frozen timing choice with the
normal review at the same size. Team applies the current skills in order on the same opportunities
against a 1× reference at the normal review. Overlapping vetoes count once; a prior veto prevents
downstream roles from receiving credit. Individual deltas cannot be added to calculate team impact.
Unfamiliar cases retain their reference behavior, and unavailable quotes or unverifiable receipts
remain unknown rather than being assigned a profitable outcome.

Sizing and team outcomes are normalized by the reference entry cost, so **percentage points**
describe differences in the modeled outcome per opportunity. Both outcomes can be negative while
support reduces the loss. Exit uses saved checkpoints, not a replay of adaptive reviews, hard exits
or actual fill timing. This view does not simulate a second bankroll, freed capacity, later entries
or compounding. Account performance remains in Results.

The report shares the dashboard's bounded Policy selection (at most 1,000 independent rows) and
uses up to 60 recent resolved opportunities per comparison. It requires the exact current season,
profile and active versions, after the latest activation and artifact creation. It cannot import
results from an old reign, different composition or pre-activation evidence. Pending observations
and opportunities blocked by an earlier veto are reported separately. Counts are for this retained
comparison window, not lifetime activity.

An observed-advantage/disadvantage label needs 30 usable pairs, 70% coverage and an approximate
95% paired-mean interval wholly above/below zero. Otherwise the panel says collecting or no clear
advantage. This descriptive interval does not address all market dependence or repeated looks;
it is neither independent qualification proof nor a prediction of future profit. Existing proof
and health requirements are unchanged. Paused/suspended support, missing context and incompatible
or stale responses display no current performance claim. Method details are collapsed by default.

There are no new provider requests, inference, database writes, retention rules or polling loops.
The report is computed from existing records inside the normal snapshot; it remains bounded for
long seasons. A full independent two-portfolio experiment is still deferred.

## Fitted coverage explanations (v1.10.11)

New Entry Linear, Entry XGBoost and Manipulation artifacts retain a small numeric breakdown of
their exact fitted Discovery cohort. The denominator is the existing last 1,000 eligible resolved
primary-horizon observations, after the existing provenance and Policy-twin exclusions. Usable
outcomes include zero, losses and rows excluded from training by the chronological embargo.
The report does not change row eligibility, training/validation separation or the selected gate.

The mutually exclusive counts are usable, quote failures caused by insufficient real reserves,
quote failures caused by fees exceeding proceeds, other/unspecified quote failures, stale routes
at expiry, elapsed checkpoint windows and other/unknown missing outcomes. Detailed quote buckets
require the saved failure receipt; a generic missing reason alone never proves liquidity failure.
Checkpoint expiry does not prove that collection could have recovered a valid quote.

Counts travel with the artifact's optional numeric metrics, outside model parameters and payload
hashes. Training freezes only the bounded quote classifications, without bringing bulky route
receipts back into the fitting copy. The Entry family panels and diagnostic proof events use that
saved generation; they never substitute current operational coverage or the other family's cohort.
Old, incomplete, inconsistent or unsupported reports remain unavailable. Old artifacts are not
rewritten, and Policy proof, Champion authority and performance requirements remain separate.

## Bankroll growth

The portfolio always distinguishes total cash, cash reserved by pending orders, cash available for
new orders, and invested sell-side value. Closed profits return to the same bankroll; closed losses
reduce it. The order planner can compound only **realized** growth, scaling the selected risk-mode
size by the square root of bankroll growth and clamping it between 0.5× and 1.5× of the mode's base
size. It is also capped by the mode's exposure allowance. Unrealized paper gains never enlarge a
new order.

This keeps the accounting honest and makes growth visible without turning one lucky mark into an
aggressive bet. The main goal remains a truthful experiment: wait when evidence is weak, include
all modeled friction, and preserve enough history to learn whether the strategy helped or hurt.

### Entry validation and authority commit boundaries

The release reliability follow-up, deployed locally on 21 September, prepares Baseline order size,
evaluation, provenance and entry permission in one joined worker dispatch under the existing market boundary. The same
checks run in the same order; original feature clocks are not refreshed. Cancellation waits for
the worker before releasing that boundary, and the original actionable Baseline opportunity is
still enrolled before Manipulation or other skill influence. Reducing dispatch overhead does not
change the strategy, support bounds, training inputs, proof requirements or pending-fill checks.

Saved Entry, Manipulation and Sizing evaluation receipts can include version-1 support metadata.
It explains the existing verdict; it does not change the support bound, prediction, uncertainty
margin, qualification, training features, selected coverage or Champion permissions. Statistical
support failures record a count and the first failing feature in model order, its transformed value,
training mean/scale and signed standardized distance. The existing scale floor and inclusive
six-standard-deviation bound still apply. Invalid parameters, unavailable verified XGBoost payloads
and Coach support failures remain separate causes. Older receipts without this metadata are not
reconstructed. Frozen candidate receipts describe predictions, not an applied veto or actual fill.

Active decision receipts also link to the cached persistent first-Policy identity when known.
This is a diagnostic annotation, not a new independent sample: later attempts cannot replace that
opportunity, even across seasons, restarts or parent pruning. Missing cached origins remain unknown
without a database query; inconsistent/future clocks do not establish an ordering. A linked original
may no longer be retained. Model replacements do not inherit any new sticky veto or permission.

The saved decision UI separates skill influence, Baseline integrity and paper execution. Unfamiliar
inputs may leave a proposed veto unapplied while Baseline and the remaining guards still decide.
That is not evidence of legitimacy, manipulation or a successful fill. Age is computed from the
original measurement and decision timestamps; cached snapshot freshness can understate that age.
The snapshot reference clock can itself be market-event time, so this age includes queueing and
cached-window effects and must not be interpreted as CPU time. No clocks are refreshed or backdated.
The current freshness limits and shadow-study eligibility remain unchanged.

Native Linear and XGBoost Entry fits record `entry-top-group-v2` in their validation provenance.
The top third is selected by predictions alone. Scores strictly above the boundary are fully
included, and the remaining places are shared equally across the tied boundary group. With
identical forecasts this returns the whole group's mean, not the retrospectively best outcomes.
No-tie results and the applicable coverage, performance, independent-proof and complexity gates
remain intact. Old artifacts remain readable and can be frozen comparison references, but their
old qualification cannot restore, recover or newly activate native Entry support.

Champion activation prepares detached authority, atomically commits the affected states, active
map and mode, and then publishes into the existing state objects held by tournament callers.
Manual consent and legacy-model removal join that same commit. Failed grants retain the prior
safe authority. Suspension/deactivation instead removes affected support first; a failed write
is retained for retry and must commit before another grant. None of these changes move hard
exits, alter existing order execution or give Coach direct trading control.
