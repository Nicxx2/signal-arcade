# Changelog

Signal Arcade uses semantic versions. Within the paper-trading generation, feature releases use
`1.x.0` and compatible fixes or fine tuning use `1.x.x`. Live execution is outside V1's scope and
would require a deliberate V2 release.

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
