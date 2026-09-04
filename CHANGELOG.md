# Changelog

Signal Arcade uses semantic versions. Within the paper-trading generation, feature releases use
`1.x.0` and compatible fixes or fine tuning use `1.x.x`. Live execution is outside V1's scope and
would require a deliberate V2 release.

## Unreleased

## 1.10.1 - 2026-09-04

- Make the Challenger view easier to follow without changing model authority: Entry now shows its
  exact-cohort XGBoost eligibility and current state, Road to influence is explicitly identified as
  Entry proof, and detailed disclosures still begin collapsed.
- Add honest per-skill Champion reign records plus a bounded, paginated battle history. Recent
  rows identify both Champion and contender, while accessible battle details expose the shared
  forward sample, coverage, mean edge, conservative floor, model families and recorded resolution.
  Crown retentions are labelled as failed replacement proof—not guaranteed wins—and suspended
  Champions remain visibly distinct from inactive Shadow Champions.

- Preserve per-mint causality even when the bounded priority queue lets a held-position event pass
  older candidate traffic. Lower-slot, same-slot reorder and clock-regression events can no longer
  mutate features, paper fills, exits, learning or AI outcomes; verified PumpSwap routes also ignore
  late bonding-curve trades.
- Make every new fill independently reproducible with its exact reserve timestamp, event,
  signature, slot, source, route, quote mint, fee and reserve values. Database commits reject fills
  before their order, configured latency or paper position, while marks remain monotonic.
- Detect impossible legacy paper chronology on upgrade without rewriting history. The affected
  season stops safely, cannot auto-roll, rank, compare or qualify learning, and remains visible in
  Latest as **Not counted** until the user starts a clean season; Arena labels that preserved state
  explicitly instead of offering a resume control.
- Keep long-running public-feed memory bounded by pruning causal and decision caches with expired
  candidate features, while queued and saved Local AI outcomes remain protected until resolved.
- Start the `challenger-features-v5` / `learner-v6` authority cohort so evidence collected before
  strict causal execution stays preserved but cannot silently qualify a current Champion.

## 1.10.0 - 2026-09-03

- Add a fixed, single-thread CPU XGBoost Entry contender beside the native Linear learner. It is
  attempted only after 250 training rows, must beat the Linear validation error by at least 2%,
  and still passes every existing chronological, independent-policy and common-forward Champion
  gate; Linear wins marginal comparisons.
- Store nonlinear model JSON in a bounded, digest-verified SQLite artifact table and commit it
  atomically with immutable Challenger metadata. Missing, oversized, mismatched or corrupt payloads
  fail closed and cannot activate or participate in a tournament.
- Make first-Champion family selection independent of training completion order, keep at most one
  waiting generation per model family, and start each queued contender on fresh common-forward
  receipts. Training completed for a no-longer-current mode/configuration remains historical and
  cannot gain current authority.
- Add bounded 5-minute and 1-hour event-pipeline telemetry plus passive SQLite WAL pressure status,
  and show Baseline exact-cohort outcomes without converting unknown exits into losses or wins.
- Show the actual testing contender, model family, first unmet gate, bounded queue and collapsed
  artifact provenance in the Learning Lab while preserving its compact desktop and mobile layout;
  the prominent Demo-separation reminder appears only while Synthetic Demo is actually selected.
- Separate broad discovery observations from generation-bound, actionable policy proof and actual
  paper-execution audit episodes. A later actionable ENTER can now create honest policy evidence
  even when the same mint was first observed as PASS, while one mint-season trajectory remains
  idempotent and cannot inflate sample size.
- Commit evidence lifecycle changes atomically with paper orders, fills, ledger entries and
  positions. Confirmed terminal write-offs retain a conservative loss; provider-unknown dormant
  inventory remains unavailable rather than receiving fabricated P/L.
- Move statistical fitting to one coalesced quiet-time worker. Immediate Champion health and
  tournament safety remain synchronous, while held positions, pending orders and due outcomes keep
  priority over routine candidate learning during market bursts.
- Start `challenger-features-v4`, `learner-v5` and `challenger-skill-v2` qualification. New artifacts
  must prove the exact current `learning-evidence-v2` policy cohort with at least 70% outcome
  coverage, sufficient kept and vetoed cases, a bounded winner-veto rate and positive conservative
  value. Out-of-distribution evidence falls back to the Baseline and can never be counted as a
  successful veto.
- Preserve the complete, restart-safe Champion journey and every artifact it references while
  keeping the Learning view compact. Deterministic contender codenames, separated Discovery /
  Policy proof / Paper execution lanes and a visible current-generation boundary make progress
  easier to understand without changing promotion standards.
- Drive retraining, Champion tournaments, active-skill health and downstream joins from the
  authoritative Policy journal, including a later actionable entry after an earlier completed
  PASS. Requests arriving during an active quiet-time fit remain queued for the next run.
- Refresh the in-memory Paper execution lane only after its accounting transaction commits and
  reconcile unresolved boundary outcomes from SQLite. A display callback failure cannot undo or
  repeat a fill, and provider-unknown inventory never receives fabricated performance.
- Keep first-bankroll controls locked in a clear Creating state while the safe event boundary is
  pending, allow the initial request enough time to finish on a busy upgraded system, and reconcile
  the authoritative snapshot before presenting a lost response as a failed creation.

## 1.9.2 - 2026-09-01

- Add Baseline v1.5 / integrity gates v3: raw trade count and wallet breadth now receive only the
  economic credit supported by meaningful on-chain quote flow, while dust-trade share, median
  size, meaningful volume/wallet participation, path efficiency and rapid reversals become
  coverage-aware evidence. No single small trade or chart shape is a manipulation verdict;
  current entries wait or pass only when sufficiently complete independent evidence corroborates.
- Make the same uninterrupted five-minute candidate window authoritative for current Baseline
  decisions, Challenger lessons, the local Critic and Coach research. Reconnects, represented
  queue shedding, venue changes and a saturated bounded trade buffer fail closed without
  rewriting old v1.1–v1.4 seasons, positions, observations or artifacts.
- Keep structural computation bounded during event bursts with a one-second venue-local cache,
  exclude pre-migration trades from post-migration measurements, and preserve exact freshness and
  missing-data provenance. Held, pending and saved-outcome events keep their protected queue path.
- Prevent synthetic-looking raw activity from earning a long adaptive hold or a larger paper size
  in the new strategy. Persistent corroborated warnings may still request an exit only across
  time-separated fresh executable checkpoints; one burst can neither buy nor force a sale.
- Start `challenger-features-v3`, Coach research v4 and AI Critic v4 forward cohorts. Older evidence
  remains readable and auditable but cannot silently qualify under fields it never observed.

## 1.9.1 - 2026-09-01

- Add Baseline v1.4 uncertainty handling: a new entry waits until integrity evidence reaches its
  minimum time, trade and coverage sample; an extreme isolated warning must clear or gain
  corroboration; and moderate unresolved evidence receives only 70% of the cautious reference
  size. Mature clean evidence may still scale inside every hard cap, while locked v1.3 seasons,
  pending fills, positions and Challenger cohorts retain their exact previous behavior.
- Add Baseline v1.3 / integrity gates v2: extreme wallet-volume concentration combined with
  overwhelming one-trade participation is now an independent concentrated-dispersion category.
  Alone it prevents a size-up; only separate corroboration can reduce or veto an entry. Locked
  v1.2 seasons, pending fills, positions and Challenger cohorts retain their exact prior policy.
- Correct Challenger skill presentation so an unqualified contender with no Champion is shown as
  collecting proof, while a genuinely suspended non-null Champion remains explicitly suspended.
- Replace the static auto-season delay badge with server-authoritative live states for remaining
  verified time, paused progress, due rollover, position management, settlement and data waits.
- Skip the sparse-event batching delay whenever feed work is already queued, reducing recovery
  latency during public-RPC bursts without reordering events, weakening evidence gates or changing
  the protected critical-event backpressure path.

## 1.9.0 - 2026-08-31

- Split the statistical Challenger into independently versioned Entry, Manipulation, Sizing and
  Exit skills with immutable candidates, saved champions and restart-safe common-forward
  tournaments; a weaker new candidate no longer replaces the best proved artifact.
- Add one explicit activation consent, bounded per-skill composition, exact decision audit
  receipts and rolling health suspension. Later skills can join only after incremental forward
  proof beside the active ensemble, and no skill can create an entry or bypass permanent safety.
- Sample due outcomes fairly from fresh cached route state without extra RPC traffic, retain exact
  unavailable-route reasons, and add fee/impact-aware 0.5–2× sizing trials plus conservative
  earlier-review proof without fabricating fills or returns.
- Show Contender, best-proved Champion, influence and shared-forward progress independently for all
  four Challenger skills, plus a bounded, restart-safe Champion journey of honest promotions,
  defences and inconclusive battles. Existing Champions are preserved without fabricated history.
- Close a Challenger battle as inconclusive when prolonged route unavailability prevents the 70%
  coverage gate from recovering, retain the saved Champion, and store its journey in a rollback-
  readable sidecar rather than extending the strict skill-state payload.
- Add Baseline v1.2 with coverage-aware, multi-category market-integrity conclusions; preserve the
  exact v1.1 path for already-locked legacy seasons and start a new learning/configuration cohort.
- Add deterministic realized-bankroll sizing receipts: only mature clean evidence can size above
  the personality reference, within per-position/total exposure, cash, reservation and impact caps.
- Keep an active Sizing recommendation at the Baseline amount when its exact larger multiplier no
  longer fits every hard cap, and validate its immutable receipt again at submission and fill.
- Route each newly resolved outcome to its exact retraining cohort, exclude still-pending horizons
  from availability-health denominators, carry a promoted active champion forward safely, and make
  dependent skills re-prove beside that new version.
- Remove downstream authority when a new upstream skill joins, preserve its Champion and journey,
  and require fresh proof for the exact new ensemble before it can influence again.
- Protect in-flight tournament artifacts during bounded retention and restore only the exact saved
  active dependency chain after restart; incomplete or inconsistent state fails back to Baseline.
- Revalidate the exact entry thesis at fill time without ever increasing a pending order, and
  require persistent time-separated manipulation evidence before an adaptive exit.
- Replace separate profile controls with one responsive next-season editor for currency, exact
  virtual bankroll, personality, drawdown policy and safe or bounded immediate transition.
- Persist the complete target through restart and apply an unstarted edit atomically without
  archiving an empty season or altering retained learning.
- Version season-boundary accounting as complete, confirmed write-off, provider-unknown, empty or
  legacy; require two distinct, fresh position-specific route probes before recording a zero-value
  write-off, then count that terminal disposition as a loss without inventing a sell fill.
- Compare Results only within the same currency, starting bankroll, exact profile and terminal
  accounting policy, while keeping mixed, manual, empty and legacy history visible without
  unsupported aggregate claims.
- Add a Helius Economy preset that uses paced keyed HTTP for safety lookups and the configured
  default/public WebSocket for the high-volume stream, with explicit route-source telemetry.
- Keep long position evidence and values readable on narrow screens without hiding paper P/L or
  changing execution, strategy, Challenger, or AI Coach behavior.
- Expand the optional AI Coach into four bounded Entry, Manipulation, Sizing and Exit research
  lanes, selected only from deterministic allowlists while market work is quiet.
- Persist exact post-proposal Coach evidence and per-context lifetime outcome clocks so restart,
  pruning and rolling history cannot replay proof or reset a study; close unsupported work as
  rejected or inconclusive after bounded evidence or time.
- Keep the Coach research-only and independently pausable. A supported idea needs explicit user
  permission, an existing matching Challenger Champion and a fresh common-forward tournament;
  it can never trade, create the first Champion or replace one directly.
- Revalidate every contributed Coach policy against the deterministic allowlist at the Challenger
  boundary so malformed or incompatible persisted research fails closed before a tournament.
- Show Coach lane activity, exact proof milestones, an honest research notebook and the guarded
  road to contribution in the Learning tab, with responsive layouts and durable milestone alerts.
- Replace the native season-comparison select with an accessible responsive picker, distinguish
  otherwise identical bankroll/profile rows by strategy generation, accounting boundary, finish
  type and season range, and avoid repeating the current exact group as a second choice.

## 1.8.1 - 2026-08-30

- Freeze the current personality's canonical profile when an automatic rollover follows a legacy
  season, while preserving the historical season's honest legacy/unknown provenance.
- Compare season performance only within the same currency and exact risk profile; mixed or
  legacy history remains visible without producing unsupported best-season or improvement claims.

## 1.8.0 - 2026-08-30

- Freeze each paper season to one immutable, versioned risk profile and use a restart-safe
  exits-only transition for personality or drawdown changes.
- Add backend-derived Safer, Balanced and Aggressive setup/Arena controls plus exact-profile
  Results filtering, legacy-safe history and auditable terminal reasons.
- Add typed Default, Custom and Disabled portfolio-drawdown policies; Off preserves every other
  permanent safety gate and rolls only after genuine, healthy-evidence bankroll exhaustion.
- Keep Challenger learning separated by personality rather than drawdown experiment, while
  persisting exact season/profile provenance and excluding non-actionable entries from influence
  proof.
- Add explicit Finish Safely and End Season Now profile transitions. The bounded manual path uses
  real paper exits only, archives untradeable inventory without fabricated fills, and excludes
  user-forced or unresolved endings from like-for-like Results claims.

## 1.7.6 - 2026-08-30

- Add a compact Replay summary for the currently visible receipts, including buy/sell mix,
  combined simulated fees, average recorded impact, and median paper-fill latency.
- Make receipt cash direction explicit with signed net flow, show gross value plus separate protocol
  and simulated network fees, and include the local calendar date beside every fill time.
- State that Replay is current-season and transparently bound its live receipt list to the newest 30
  while Results continues to summarize the complete current season.
- Replace hidden narrow-screen receipt columns with accessible two-column cards so fees, impact,
  latency, cash flow, token, side, and time remain available on phones and tablets.

## 1.7.5 - 2026-08-30

- Reorganize Learning into Overview, Baseline, Challenger, AI Coach, Shadow Reviews, and Safety
  sub-tabs so only the selected player's information is visible at one time.
- Start every device on the compact Overview, keep Challenger proof and evidence collapsed by
  default, and remember the selected sub-tab and opened details locally on that device.
- Preserve learning milestone attention until the Overview that contains it is actually visited,
  with keyboard-accessible tabs and a horizontally scrollable narrow-screen layout.
- Migrate the previous Learning layout safely without changing trading, learning, Coach, season,
  provider, or stored evidence behavior.

## 1.7.4 - 2026-08-30

- Recompose Learning into clear Fast Baseline, Statistical Challenger, and Local AI Lab sections,
  with per-device collapse preferences and compact always-visible player states.
- Report the Challenger, AI Coach, and Shadow decision-review proof gates directly from the
  backend so evaluation timing can never be mistaken for qualification or activation.
- Add stable, acknowledged learning milestones and a subtle Learning-tab indicator for meaningful
  proof, activation, suspension, and Coach experiment changes without replaying historical alerts.
- Keep Qualified Coach and Live Critic explicitly unavailable: Coach Shadow progress is visible,
  while Live Critic makes no readiness claim before that future feature exists.

## 1.7.3 - 2026-08-30

- Clarify that detailed trade results belong to the current season and show realized net P/L,
  simulated fees, win/loss context and saved exit-audit coverage without changing execution.
- Keep exit evidence and per-trade fees accessible on narrow mobile screens, explain when open
  positions appear, and disclose when a bounded Results list is showing only part of a season.
- Add the best completed season to the existing season read while preserving every scorecard.
- Bound the all-season SVG to representative extrema-aware trend points, preserve missing-data
  breaks and exact endpoints, and keep every exact season value available in the table below.

## 1.7.2 - 2026-08-30

- Start the five-minute source-integrity horizon only after a healthy WebSocket recovery is
  confirmed, so a long outage can never age the safeguard while no evidence is arriving.
- Fail closed for challenger and AI Coach learning after an exceptional event-worker batch
  failure by marking every represented mint incomplete without replaying possible broker effects.
- Escalate an unidentified failed event or bounded tracking saturation to a source-wide clean
  window, while clean unrelated tokens remain eligible after identified token-local failures.
- Start the corrected `stream-integrity-v4` forward cohort while retaining all previous evidence
  and models for audit.

## 1.7.1 - 2026-08-30

- Require a complete fresh five-minute integrity window after process startup, WebSocket
  reconnects, fallback activation and explicit market-source changes before the challenger or AI
  Coach may accept a new lesson.
- Track shed or expired candidate evidence per mint so an incomplete token is excluded without
  unnecessarily pausing clean learning for every unrelated token.
- Fail closed with a source-wide continuity reset if missing evidence has no mint or the bounded
  per-mint tracker reaches its safety limit.
- Start the corrected `stream-integrity-v3` forward cohort while retaining every earlier
  observation and model for audit without mixing them into the corrected learner.

## 1.7.0 - 2026-08-30

- Add point-in-time market-integrity evidence from the existing Solana event stream: one-trade
  wallet share, rapid wallet round trips, round-trip volume, gross-versus-net flow, side
  alternation, clustered sizing, slot concentration, price-direction consistency and bundled
  signature activity.
- Keep these measures observational: they do not label a token as a scam and do not change the
  transparent baseline, a safety gate, position size or exit policy.
- Start a new forward-only learner cohort and `learner-v4` model family so older lessons remain
  auditable without being zero-filled or retroactively reinterpreted under the new feature schema.
- After a provider burst sheds low-priority candidate ticks, wait for a complete clean five-minute
  stream window before starting a new challenger or local-AI assessment; the baseline and all
  protected position, pending-order and saved-outcome processing continue unchanged.
- Let the bounded AI Coach screen the new deterministic measures only as shadow entry-veto
  experiments; every proposal still needs later fee-inclusive outcomes, coverage and independent
  seasons before it can qualify.
- Show the frozen integrity evidence and coverage in decision explanations, including explicit
  unknown states when wallet, amount, slot, price or signature data is incomplete.

## 1.6.7 - 2026-08-29

- Preserve verified automatic-season countdown time through brief provider, queue and processing
  interruptions instead of restarting the full delay after a transient data-health wobble.
- Pause rollover while evidence is unhealthy, invalidate the observation window only after a
  sustained five-minute interruption, and resume with an explicit verified-time status.
- Reset the countdown when a holding genuinely revives, an exit fills, an order is pending, the
  risk guard clears or the engine stops; a due rollover still waits for queued evidence safely.
- Persist pause and continuity checkpoints across restarts and upgrade preparation so offline or
  paused time cannot be mistaken for verified dormant-market observation.

## 1.6.6 - 2026-08-29

- Add a two-step **Prepare for upgrade** workflow under Settings that quiesces paper actions at an
  atomic boundary, cancels only unfilled orders, pauses optional Coach/model work, waits for a
  bounded storage chunk, and verifies the ledger before declaring the stack ready.
- Preserve open positions, bankroll configuration, engine preference, automatic-season countdown,
  seasons, learning, provider settings and downloaded models; after a container replacement the
  durable operation reconciles and resumes only the engine state that existed before preparation.
- Serialize all web mutations against the preparation boundary, keep repeat preparation requests
  idempotent, provide a safe cancel-and-resume path, and restore normal operation if any readiness
  check fails.
- Show global progress, explicit Docker Compose commands, preserved-state details and a bounded
  expected-restart status in the responsive UI without mounting or exposing the Docker socket.
- Let large storage cleanup stop between committed chunks and allow Compose up to 45 seconds for a
  direct graceful shutdown, while normal clean exits still complete immediately.

## 1.6.5 - 2026-08-29

- Batch exact mint-safety and PumpSwap pool-account checks so one quota-governed Solana request
  can verify many independent candidates without weakening any entry gate.
- Prioritize near-actionable candidates while reserving bounded capacity for aging candidates,
  preventing busy-market churn from indefinitely starving verification.
- Keep held and pending route checks on the critical path, isolate partial, stale, malformed and
  mismatched batch results per token, pin exact PumpSwap quotes until the pool changes, and discard
  exact or optional metadata responses that cross a market-source switch.
- Run optional DEX metadata concurrently only after exact checks, so a slow metadata endpoint can
  no longer serialize or delay safety verification. Trading thresholds and retained learning are
  unchanged.

## 1.6.4 - 2026-08-29

- Add Journey and Real-time equity views to Arena and Replay so long unchanged periods no longer
  hide meaningful season moves, while stored timestamps and audit evidence remain untouched.
- Render System Status in a viewport-level, keyboard-contained dialog with mobile safe-area,
  long-message, focus-return, and narrow-screen handling.
- Make the guarded automatic-season delay configurable from 1 to 24 hours, defaulting to 24,
  persisted across restarts, locked while a countdown is enabled, and serialized when concurrent
  API clients try to enable different delays.
- Add durable, single-flight season operation progress for reset, bankroll creation, and engine
  start; duplicate controls are blocked, reset returns promptly, and interrupted operations
  reconcile against the committed ledger without erasing seasons or learning.
- Give the season win-rate chart a dedicated bottom label gutter so signed return percentages stay
  fully visible on desktop and narrow screens.

## 1.6.3 - 2026-08-28

- Keep every season and complete scorecard available while showing the newest 20 rows first, with
  compact controls to reveal another 20 or the full retained history.
- Add Latest 10, Latest 25, and All chart ranges once history grows; recent ranges keep readable
  bars and open on the current season, while All switches to a bounded trend that scales beyond
  100 seasons without widening the page.
- Preserve honest gaps for seasons without closed outcomes, sample only axis labels rather than
  data, distinguish the current season, and remove the chart's unintended vertical scrollbar.
- Add 105-season, missing-outcome, sorting, full-history, accessibility, and responsive regression
  coverage without changing trading, learning, Coach, season, or storage behavior.

## 1.6.2 - 2026-08-28

- Keep the Learning page's live state, outcome totals, and active Coach experiment visible while
  collapsing detailed AI assessments, validation diagnostics, lessons, and permanent boundaries
  until requested.
- Add accessible expand/collapse controls and regression coverage so the information-dense Learning
  page stays tidy on desktop and mobile without hiding whether learning or coaching is active.

## 1.6.1 - 2026-08-28

- Rename the AI Decision Lab roadmap stages to Shadow, Qualified Coach, and Live Critic so the UI
  matches the intended evidence-led progression.
- Keep Qualified Coach and Live Critic visibly marked as future stages, disabled and explained by
  accessible hover/focus help; only Off and Shadow are selectable in this release.
- Relabel legacy guarded qualification counts as Shadow evidence and clarify that observation alone
  never grants trading influence.

## 1.6.0 - 2026-08-28

- Add an asynchronous AI Coach Shadow that studies completed, fee-inclusive learning outcomes
  without entering the market-processing, decision, position-management, or dashboard fast paths.
- Allow the local model to select only from deterministic, allowlisted entry-veto and earlier-review
  experiments; strict structured output cannot create a rule, action, size, or safety exception.
- Separate historical discovery from a durable forward cutoff so old outcomes may screen or reject
  an idea but can never qualify it; forward support requires at least 60 usable outcomes, 70%
  availability, two seasons, and a positive conservative uplift floor.
- Keep low-coverage experiments inconclusive and reject unsupported ideas after a larger forward
  sample, while isolating all evidence by risk mode and decision-relevant configuration.
- Defer optional coach inference during open-position management, pending orders, event backlog,
  processing lag, in-flight batches, or other Ollama work, with bounded retry and retained evidence
  across restarts and upgrades.
- Add an AI Coach Room to Learning that clearly shows zero influence, the active bounded experiment,
  historical screen, new forward evidence, outcome coverage, independent seasons, and guardrails.
- Persist bounded coach reviews and hypotheses under a schema migration without changing existing
  season history, learning evidence, provider settings, or the paper-only boundary.

## 1.5.0 - 2026-08-28

- Added one quota-governed `getMultipleAccounts` watchdog for all held positions so an exact
  program-owned curve or pool can refresh an executable paper mark when the trade stream is quiet.
- Keep RPC reserve freshness separate from trade freshness: watchdog observations cannot create a
  trade, qualify an entry, inflate market activity, or enter learning outcomes.
- Validate Pump bonding-curve discriminators and owners, and PumpSwap pool mints, quote routes,
  token-account owners, authorities and balances before any refreshed reserve is accepted.
- Pace free providers from their configured monthly routine allowance with an eight-second floor,
  allow explicitly capped paid plans to run faster, batch all holdings, and make no watchdog calls
  without open positions.
- Preserve a critical pending-exit lane while keeping provider cooldown endpoint-specific, so a
  keyed RPC `429` can use the public fallback without disabling it or starting a retry storm.
- Persist exact position route metadata for restart recovery; missing, partial, malformed, old-slot
  or unavailable RPC evidence remains stale and can never manufacture a fill or a portfolio gain.
- Isolate each holding's slot watermark and split long-lived portfolios at Solana's 100-account
  ceiling, prioritizing pending exits so one anomalous route cannot stall every other position.
- Cap every executable paper sell and mark by the exact observed Pump/PumpSwap quote liquidity;
  virtual pricing reserves can no longer imply SOL that the real curve or vault does not hold.
- Preserve an exit recommendation when liquidity is insufficient without repeatedly creating
  doomed pending orders; the next verified executable reserve state retries the policy normally.
- Discard a live watchdog response that was already in flight when the user switched to the fully
  reset demo source, preventing evidence from crossing source boundaries.
- Require a genuinely newer RPC context slot before renewing reserve freshness, so a cached or
  stalled provider response cannot keep an old executable mark looking current indefinitely.

## 1.4.4 - 2026-08-28

- Separate total usable learning outcomes from the minimum-training gate so exceeding the first
  80 samples can no longer look like proof that a challenger qualified.
- Show the bounded 10-outcome progress cycle toward the next challenger after the first model
  exists, including accessible progress semantics and singular/plural status copy.
- Expose the challenger retraining interval in the snapshot instead of duplicating a backend
  learning constant in the browser.

## 1.4.3 - 2026-08-28

- Reserve a bounded dashboard lane for recent ENTER/WATCH checkpoints so a high-volume abstain
  burst cannot push every useful signal out of the Decisions tab before the browser refreshes.
- Reconcile each reserved positive checkpoint with that mint's latest recorded state, preventing a
  superseded WATCH from appearing beside a newer PASS or ABSTAIN.
- Preserve the measured market-freshness field in compact decision payloads so the browser can
  validate current signals instead of rejecting every real checkpoint as missing freshness.
- Explain an empty Best signals group using the live Passed count, and clear decision-view memory
  at manual season/data-source resets so checkpoints never bleed between seasons.

## 1.4.2 - 2026-08-27

- Keep manual paper-season stop, pending-order cancellation, and atomic archive/reset persistence
  off the HTTP event loop so storage contention cannot make the app server appear unavailable.
- Give the explicitly confirmed reset action a dedicated 60-second client window and visible
  in-progress state, avoiding a false failure while a safe archive finishes.
- Added a maintenance-writer contention regression proving health and the event loop remain
  responsive while reset waits, with the season reset completing once storage becomes available.

## 1.4.1 - 2026-08-27

- Defer a due automatic rollover while any queued or in-flight market batch could contain a
  last-moment holding revival; the earned countdown remains intact and retries when processing is
  idle.
- Save the automation preference and cleared countdown in one database transaction, updating
  runtime state only after it succeeds so a storage fault cannot leave the UI and durable policy
  disagreeing; the write also runs off the HTTP event loop during storage contention.
- Clear previous-season route retry backoff after a successful rollover so any token rediscovered
  with fresh evidence in the next season receives a fresh route assessment.
- Keep HTTP liveness bounded during abnormal SQLite or filesystem waits by probing through the
  low-timeout reader off the event loop; dashboard work and maintenance lock contention fail fast.
- Added failure-injection, queued/in-flight evidence, and database-contention regression coverage
  for these boundaries.

## 1.4.0 - 2026-08-27

- Added an opt-in **Auto new season** control to the Arena's Risk card for genuinely unattended
  multi-week paper experiments; it remains off on new and upgraded installations.
- Require a continuous 24-hour drawdown pause, no pending orders, only dormant holdings, current
  market data, low queue pressure, and bounded processing lag before a rollover can occur. A
  revived holding, stopped engine, or unhealthy feed cancels the countdown.
- Archive the completed scorecard and create the next numbered season in one SQLite transaction,
  restoring the exact same starting paper bankroll and quote currency while retaining market,
  learning, AI-audit, provider-quota, and incident history.
- Serialize the UI toggle with the heartbeat worker so disabling automation cannot race a due
  rollover, and persist countdown/last-rollover state for clear status and crash recovery.
- Added fault-injection, policy-gate, persistence, API, accessibility, and responsive UI regression
  coverage for automatic seasons.

## 1.3.0 - 2026-08-27

- Added a dedicated Seasons view beside the existing default trade rankings, with comparable
  win-rate, net-return, drawdown, fee, bankroll and duration scorecards.
- Added a compact win-rate progression chart and an evidence-bounded comparison between the two
  latest completed seasons; a single run is presented as a baseline rather than a trend.
- Persist completed season summaries atomically before a portfolio reset. Learning and retained
  market evidence continue as before, while a new bankroll receives the next season number.
- Kept cross-currency comparisons percentage-based so SOL and USDC seasons are never added into a
  misleading money total.
- Added reset-safety, season numbering, API and responsive Results-view regression coverage.

## 1.2.17 - 2026-08-27

- Prevented a delayed initial Results request from rendering the false `No paper results yet`
  state while saved trades still existed.
- Retained the last successful Results table during background refresh and sort retries, with a
  compact honest progress message until the requested order arrives.
- Added regression coverage for initial request failure and last-good-table retention.

## 1.2.16 - 2026-08-27

- Fixed header compression after the global strategy-pause indicator was introduced: the brand
  remains intact, wide layouts use available space, and tablet navigation wraps deliberately.
- Kept the risk state visible while lower-priority connection copy yields first on narrower
  screens, avoiding clipped or crowded controls.

## 1.2.15 - 2026-08-27

- Added a compact global `Risk paused` strategy badge so an intentional drawdown halt remains
  visible from Results, Replay, Decisions, Learning and Settings without being reported as a
  service incident.
- Added regression coverage proving a pending entry cannot cross the drawdown boundary while
  existing positions retain unrestricted exit management.

## 1.2.14 - 2026-08-27

- Replaced unavailable `?` token symbols with a stable shortened mint throughout Decision feed,
  the full journal, explanations, Results, positions, fills and local-AI audits.
- Kept the complete address available through hover, copy controls and research links, including
  accessible labels, so an identity still being enriched looks deliberate rather than broken.
- Added regression coverage for unknown-token decisions across the compact feed and journal.

## 1.2.13 - 2026-08-27

- Added recovery grace periods so brief Solana reconnects and self-healed candidate bursts stay
  auditable in resolved history without flashing a misleading current outage.
- Coalesced repeated recovered episodes into bounded history records while sustained stream or
  processing failures still become visible current incidents and resolve after verified recovery.
- Decoupled Results refreshes from high-frequency dashboard updates, kept one request in flight,
  retained the last good table, and quietly retried one transient failure before raising an issue.

## 1.2.12 - 2026-08-27

- Made Results refresh safely from live snapshots without blocking the market loop: concurrent
  tabs now share a short-lived history scan based on an immutable copy of open positions.
- Added bounded WebSocket reconnection after app, proxy, or network interruptions while retaining
  the slower HTTP polling fallback, so an open browser returns to efficient live updates itself.
- Added regression coverage for concurrent Results readers and browser reconnection timing.

## 1.2.11 - 2026-08-27

- Kept Results-board history parsing and ranking off the HTTP event loop so a mature multi-month
  season cannot delay health checks, dashboard refreshes, or other connected browser tabs.
- Live-load verified the shared snapshot cache under 24 simultaneous readers while market-event
  priority processing continued; held positions, pending orders, and saved outcomes remain
  protected during exceptional candidate bursts.

## 1.2.10 - 2026-08-27

- Isolated learner fitting, activation, and hold-timing validation to the exact risk mode and
  decision-relevant configuration that produced each point-in-time lesson.
- Added forward validation of the actual actionable-entry veto policy, including minimum policy
  samples/vetoes and a positive conservative fee-inclusive uplift bound before activation.
- Saved baseline actionability during Shadow learning and added an out-of-distribution fallback,
  so unfamiliar evidence leaves the transparent baseline in control instead of extrapolating.
- Automatically returns an Active learner to Shadow after a risk or provider-policy change while
  preserving all observations and immutable older model audits.

## 1.2.9 - 2026-08-27

- Replaced the local critic's free-form explanation field with schema-constrained verdicts,
  supported risk flags and exact saved-evidence references; concise UI summaries are now derived
  deterministically from those bounded values.
- Reduced CPU inference work with rounded compact evidence, a 1K context, a 96-token ceiling and
  one unresolved five-minute assessment per actionable token instead of correlated repeat calls.
- Added an app-side single-inference gate: Shadow work cannot create a hidden Ollama queue, while
  interactive explanations immediately use the complete deterministic fallback if AI is busy.
- Applied every structured-call timeout to lock waiting and generation together, so a busy Shadow
  critic cannot make a Guarded check exceed its measured end-to-end latency budget.
- Bounded and freshness-checked the app-side Shadow queue, and discard obsolete queued work when
  AI is turned off or its model changes instead of evaluating stale market bursts.
- Bounded llama.cpp's independent-prompt cache to 512 MiB by default instead of allowing it to
  grow toward 8 GiB, while preserving the selected model in memory for responsive reuse.
- Reworded optional AI failures as safely ignored timeouts/deferred work and exposed whether the
  selected CPU/GPU runtime is ready or actively working.

## 1.2.8 - 2026-08-27

- Gave every installed local model a stable, separated action area so Selected, Select and Remove
  controls no longer collide or shift between rows.
- Kept Data Health and Storage Budget visible while making Local AI Models and Data Providers
  compact, accessible disclosures with useful selected-model and connection summaries.
- Automatically opens Local AI Models for first-time setup, active downloads and runtime problems,
  so tidier settings never hide progress or an issue that needs attention.

## 1.2.7 - 2026-08-27

- Made the shared dashboard snapshot compact and short-lived cached, while keeping complete saved
  decision evidence available on demand.
- Prevented multiple open browser tabs from multiplying expensive dashboard reads or waiting behind
  a long market/AI operation; stale fallback views are explicitly timestamped.
- Reduced live refresh churn, slowed hidden-tab polling, and distinguished a delayed dashboard from
  an unavailable trading engine by checking the lightweight health path.
- Kept dashboard reads responsive while multi-gigabyte storage maintenance runs, and removed the
  unnecessary cleanup pass that previously competed with the first page load after every restart.
- Removed repeated full scans of pending learning outcomes from the market hot path, and made burst
  recovery skip only expired candidate ticks while preserving holdings, orders and saved outcomes.
- Adapted candidate re-scoring frequency under exceptional queue pressure so the engine favors
  current actionable evidence over an increasingly stale backlog.
- Kept health checks and browser requests schedulable while a provider delivers a dense run of
  already-buffered WebSocket messages.
- Added compressed API responses and returned complete evidence with on-demand explanations.

## 1.2.6 - 2026-08-27

- Removed minimum-width navigation overflow and improved selected-control accessibility.
- Kept only the newest checkpoint for each token in the Arena feed.
- Added responsive provider-save feedback and friendlier Data Health values.

## 1.2.5 - 2026-08-27

- Made storage-policy saves persist and respond immediately instead of holding the browser open
  while multi-gigabyte pruning and budget enforcement run.
- Moved requested cleanup onto the recoverable maintenance worker, with a follow-up pass guaranteed
  when a newer policy arrives during active maintenance.
- Added clear Saving/Saved feedback and honest timeout wording so an interactive write never looks
  unresponsive or claims an automatic retry that does not occur.

## 1.2.4 - 2026-08-27

- Made on-demand local-AI explanations start directly with the saved action and cite two or three
  decisive values in one short, complete plain-text answer.
- Removed generated disclaimers, Markdown, meta-commentary, and incomplete trailing sentences;
  invalid model prose now falls back to the concise deterministic explanation.
- Kept the single unobtrusive paper-education notice at the bottom of the explanation drawer.

## 1.2.3 - 2026-08-27

- Isolated dashboard and decision reads from the storage-maintenance writer with a dedicated
  SQLite WAL reader, so bounded cleanup cannot stall the trading-state lock.
- Kept UI portfolio snapshots atomic and read-only while equity-peak persistence remains on the
  broker's trading and heartbeat paths.
- Added contention regressions proving database reads and complete authenticated-style snapshots
  remain available while the maintenance writer owns its connection lock.

## 1.2.2 - 2026-08-27

- Kept read-only mint-safety verification available through the configured public Solana RPC
  whenever a keyed RPC is rate-limited or unavailable, without weakening the fail-closed checks.
- Made dormant holdings compact by default and stated explicitly that they remain monitored while
  no longer consuming active trading slots.

## 1.2.1 - 2026-08-27

- Kept unexpected or malformed Ollama responses behind the optional-provider boundary and
  automatically returned stale Guarded configurations to non-influential Shadow mode.
- Added bounded retry/backoff with honest streamed errors for transient model-registry failures.
- Corrected nominal Docker RAM-tier guidance and added confirmed Web UI removal for unused models;
  deleting the selected model safely turns the AI critic off.
- Disabled default model thinking, bounded context/output, and compacted saved evidence so the
  CPU-first 2B default can provide explanations without starving the paper engine.

## 1.2.0 - 2026-08-27

- Bundled a private, persistent, CPU-first Ollama companion service in both source and image-only
  Compose stacks; local AI no longer requires a separate host installation.
- Added optional NVIDIA and AMD ROCm overlays while keeping the ordinary stack as a safe CPU
  fallback that never makes paper trading depend on GPU availability.
- Added honest AI runtime reachability, pinned Ollama version, configured/actual compute, and
  background model-refresh status to the web UI.
- Kept model downloads serialized, RAM-aware, progress-visible, local-only, cloud-disabled, and
  stored in a separate Docker volume outside the trading database budget.

## 1.1.5 - 2026-08-27

- Migrated legacy equity-peak watermarks onto the executable-route valuation basis using only
  trustworthy recorded cash and current executable equity.
- Prevented historical indicative token marks from falsely holding the paper engine at its
  drawdown limit after upgrading, while preserving genuine cash-peak risk protection.
- Released active slot and exposure capacity when a holding becomes dormant, while retaining it
  for revival monitoring and counting it again whenever a fresh market returns.

## 1.1.4 - 2026-08-27

- Verified migrated PumpSwap exit routes from program-owned on-chain Pool accounts before treating
  reserve marks or paper exits as executable.
- Separated active, exit-blocked, and dormant positions; executable equity now excludes indicative
  or stale values while preserving last-known context and revival monitoring.
- Corrected PumpSwap fee interpretation so buyback and cashback redistribution are not charged a
  second time against simulated sell proceeds.
- Prioritized held-position and saved-outcome events with lossless backpressure while processing
  high-volume candidate ticks ephemerally instead of growing raw history without bound.
- Increased bounded legacy cleanup throughput, exposed event-pipeline degradation honestly, and
  added client request timeouts so one slow snapshot cannot permanently stop UI polling.

## 1.1.3 - 2026-08-27

- Made storage/enrichment and risk-heartbeat workers recover after unexpected runtime failures.
- Added persistent worker incidents and core background-loop liveness to health responses.
- Kept fill accounting and portfolio snapshots on one atomic UI boundary for consistent P/L views.

## 1.1.2 - 2026-08-27

- Added compact mint-copy and GMGN research actions to positions, decision feeds, and results.
- Added the full token research handoff to saved decision explanations as well as expanded details.
- Kept external research links isolated from the paper engine; opening GMGN never places a trade.

## 1.1.1 - 2026-08-27

- Fixed a live market/UI race that could mutate a rolling trade window during snapshot assembly.
- Kept paused streams bounded to positions and unresolved learning evidence instead of future entries.
- Avoided rebuilding full candidate feature snapshots between decision-cooldown checkpoints.
- Verified the active engine through sustained public-stream load and scheduled maintenance with no
  queue drops, incidents, restarts, or snapshot failures.

## 1.1.0 - 2026-08-27

- Added the opt-in local AI Decision Lab with Off, Shadow, and qualification-locked Guarded modes.
- Added curated local-model downloads and resource guidance in Settings.
- Added adaptive hold/exit review, forward-only learning safeguards, and persistent audit evidence.
- Added the Results leaderboard, richer decision explanations, and a review-friendly decision UI.
- Added persistent incident status, bounded event ingestion, storage budgets, and long-run rollups.
- Added guided RPC key setup, quota pacing, stronger secret redaction, and provider edge handling.
- Added rate-limit-aware Solana reconnects and a visible public-stream fallback for keyed RPC 429s.
- Isolated recurring SQLite work from HTTP, with responsive bounded maintenance on large histories.
- Added the running release badge and cross-project version-alignment tests.

## 1.0.0

- Initial self-hosted, paper-only Solana trading simulator.
