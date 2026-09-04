# Architecture

## Runtime flow

```text
Pump + PumpSwap logs ──> pinned Anchor decoder ──> bounded priority queue
                                                        │ batched SQLite journal
                                                        v
                                   venue-local, bounded point-in-time features
                                      │        │                │
                            learning outcome   decision journal WebSocket UI
                                      │        │
                              shadow challenger│<── optional AI Shadow critic
                                               │
                                      explicit engine gate
                                  (stopped by default; persisted)
                                               │
                                      delayed paper order
                                               │
                           elapsed latency + fresh observed reserves
                                               │
                                    fill receipt + ledger + P/L
```

The WebSocket provider uses one connection and two `logsSubscribe` calls because Solana's
`mentions` filter accepts one public key per subscription. Events are deduplicated by a stable
hash of signature, slot, program, log index, and event name. The runtime invocation stack is
tracked for every transaction, and `Program data` is decoded only while the active program is
the pinned Pump or PumpSwap address; discriminator collisions from other programs are ignored.

Only trades for a token created during the active observation window (or held/pending tokens)
are retained. Inactive in-memory candidates expire after 30 minutes by default. Raw trades age
out after 6 hours by default. Repeated unchanged non-entry checkpoints are compacted; creates,
ENTER evidence, orders, fills, positions, ledger history, and learned models remain. A live-data
budget is adjustable in the web UI, and SQLite reuses freed pages without requiring risky online
vacuum operations. Hourly equity rollups preserve long-run chart continuity after dense raw points
are pruned. Ollama model files remain in Ollama's separate store and never count toward this limit.

## Components

- `providers/`: official event decoding, Solana RPC mint inspection, DEX/Jupiter/Ollama adapters.
- `intelligence/`: rolling point-in-time token state, features, risk flags, and baseline score.
- `intelligence/learning.py`: route-aware live-only outcome checkpoints; independent Entry,
  Manipulation, Sizing and Exit artifacts; chronological validation; restart-safe common-forward
  candidate/champion tournaments; generation-bound policy evidence; coalesced quiet-time fitting;
  bounded composition and per-skill health suspension.
- `intelligence/nonlinear.py`: one lazy-loaded, single-thread CPU XGBoost recipe with deterministic
  training, finite-input validation and portable JSON serialization. Linear remains the preferred
  family unless the nonlinear contender earns a material untouched-validation advantage.
- `paper/`: integer curve quotes, delayed orders, persistent adaptive exit assessments, receipts,
  positions, and accounting.
- `ai_lab.py`: optional structured local-model critic, serialized catalog downloads, runtime
  monitoring, strict evidence validation, independent counterfactual outcomes, and per-model
  qualification. Compose supplies a private CPU-first Ollama service with separate model storage.
- `coach.py`: quiet-time, allowlisted Entry, Manipulation, Sizing and Exit research with
  exact-cohort forward studies, bounded terminal outcomes and an explicit Challenger handoff.
- `database.py`: versioned SQLite schema, WAL, batched deduplication, incidents, equity rollups,
  bounded digest-verified statistical model payloads,
  quota and retention state.
- `orchestrator.py`: one event-time coordinator and fan-out bus.
- `api.py`: local security middleware, API routes, WebSocket, and built static UI.
- `frontend/`: minimal React/Vite dashboard; it contains no provider credentials.

## Failure behavior

Provider failures do not stop the ledger or UI. The stream reconnects with bounded exponential
backoff. Optional HTTP failures remain unknown. Market events enter a bounded queue and are
persisted in batches. A short sparse-feed batching wait is skipped whenever backlog already exists,
so a recovered public feed drains immediately. When overwhelmed, the app retains
held/pending/learning-critical activity,
sheds untracked low-priority trades, and records a persistent incident rather than allowing
unbounded memory or database pressure. Baseline v1.5 treats a represented candidate drop, source
reconnect or live five-minute trade-buffer eviction as incomplete integrity evidence; that mint
waits through a fresh continuity window rather than learning from or trading on a partial sample.
Operational status reports processed, transient, saved, capacity-shed and expired candidate events
as distinct counters; transient processing is never presented as lost data, and expiry is not
mislabelled as queue shedding.
Priority never becomes market time: a per-mint cursor uses Solana slot first and observed enqueue
order within the same or slot-less stream, rejecting regressions before they can reach features,
paper execution, learning or AI. Restart recovery unions tracked and recent raw events, deduplicates
them and replays live evidence by authoritative Solana slot before rebuilding state; deterministic
Demo evidence retains arrival order. A successfully decoded held-position RPC snapshot advances the
same mint boundary, while partial or invalid account responses advance nothing. Reserve and event
timestamps remain monotonic across host-clock correction. A verified PumpSwap route cannot be
overwritten by a late bonding-curve trade.
Rolling structural metrics are cached for at most one second during bursts, while reserve/route
state and critical position events remain authoritative. UI notifications have their own bounded
queue and the normal five-second snapshot poll repairs missed notifications. Duplicate events are
ignored. Each new fill embeds its complete reserve snapshot—including an exact RPC observation ID
when the watchdog supplied it—and atomic database commits independently enforce order, latency and
position chronology. The broker first defers any fill whose reserve lies in its future without
mutating the pending order or accounting. Impossible legacy timing is quarantined without rewriting
immutable receipts or ledger history.
The feature window and its per-mint causal/cooldown indexes share one bounded pruning lifecycle.
Held positions, pending orders, statistical checkpoints, and queued or saved Local AI outcomes are
retained until their work resolves; inactive entry candidates and their indexes expire together.
Routine learner checkpoints use durable normal priority and rise to critical priority only around
their due window. Statistical fitting is coalesced per cohort and runs in one background thread
only while the market queue is empty, processing lag is low and no event batch or maintenance work
is active. Immediate health suspension and common-forward tournament accounting remain on the
outcome boundary.
Ollama reachability is monitored independently; its absence disables local assessments and
explanations without stopping market processing, the baseline strategy, exits, or accounting.

Health requests use a constant-time SQLite liveness query. Full integrity scans are explicit
maintenance operations, never part of Docker health polling or normal UI snapshots.

SQLite is the source of truth. The bankroll currency, engine state, pending orders, open
positions, and PumpSwap pool mappings recover on restart. Stopping cancels pending orders without
removing positions; the observation feed remains online so Resume can reassess fresh marks. A
fill, filled order, balanced ledger entries, position change, and realized P/L are
one SQLite transaction; an injected failure rolls every effect back before in-memory state moves.

Every modern paper season also stores one immutable profile snapshot: risk personality, the exact
risk-limit values, Baseline/integrity/sizing policy versions, typed portfolio-drawdown policy,
effective threshold, and a stable profile fingerprint. A unique partial index permits only one
current season. A locked
profile change is a durable `profile_transition` operation: new buys freeze, unfilled buys cancel,
owned positions and pending exits continue under their entry provenance, and the completed-season
archive plus successor creation commit atomically. Restart reconciliation treats the old profile
as authoritative before that boundary and the new profile as authoritative after it, so retries
cannot create two current seasons. Pre-profile history remains visible as Legacy / Unknown rather
than being guessed into a modern cohort.

Results uses a separate comparison key composed of quote currency, exact starting bankroll, the
immutable profile fingerprint and terminal-accounting policy version. Different funding amounts,
SOL/USDC or policy experiments therefore never share a best-season or improvement claim. Currency
and all-history views retain every row but suppress aggregate claims whenever any comparison
identity is mixed or unknown.

An explicit `end_now` transition stores a bounded settlement deadline in that same operation.
Executable positions receive normal paper sell orders. A remaining non-executable position becomes
a zero-value write-off only after two fresh route-specific failures while global data is healthy;
otherwise it remains provider-unknown. Safe/automatic boundaries defer, while end-now honours its
deadline and keeps the manual result outside comparison claims. Terminal inventory is
copied into the append-only `unresolved_paper_positions` audit before live paper tables are cleared.
Season rows distinguish complete, confirmed-write-off, provider-unknown, empty and legacy
accounting. A real manual fill remains accounting truth, while user-selected timing cannot be
credited as strategy performance. Unknown transition values fail closed to the normal safe-drain
behavior, and route proof is deliberately recollected after restart.

Learning observations, generation-bound policy episodes, actual execution episodes, exact route
checkpoint attempts, sizing trials, immutable skill artifacts, candidate/champion state, active
skill versions, AI assessments, Coach studies, and operational incidents also recover from SQLite.
An actionable policy episode is linked to its order atomically, while actual execution evidence is
committed in the same transaction as each fill, ledger and position change. Confirmed terminal
write-offs retain conservative loss evidence; provider-unknown inventory remains unavailable.
The learner's execution-lane read model refreshes only after that transaction commits; callback
failure is isolated from accounting, and restart or season-boundary reconciliation reloads SQLite.
Champion tournaments, active-skill health and downstream join proof read generation-bound Policy
episodes rather than the Discovery mint index, so a later actionable entry remains eligible after
an earlier completed PASS without duplicating either trajectory.
Coach selection saves its review and hypothesis atomically;
exact forward observation IDs, values, meaningful-season counts and a per-context lifetime outcome
clock prevent replay or reset after pruning. Active and contribution-ready studies plus their
referenced reviews are protected by bounded retention, while an invalid optional Coach row is
skipped without blocking deterministic startup. Learning and AI audit records intentionally survive
a paper-bankroll reset. Demo events never train the statistical learner or qualify Guarded AI.
Missing future observations remain unknown rather than becoming invented returns. Terminal
evidence lanes are bounded while pending trajectories are retained. Artifact pruning protects
every version referenced by durable tournament, active state or Champion history.

Season and learning identity are deliberately separate. The season-profile fingerprint includes
the drawdown experiment for apples-to-apples portfolio comparison. The decision-configuration
fingerprint includes the risk personality, deterministic strategy versions and trade-learning
inputs, but not the portfolio
drawdown override or bankroll currency. Default, custom and disabled drawdown seasons—and SOL or
USDC bankrolls—can therefore contribute honest forward evidence to the same personality Challenger
while every observation retains its exact season and profile provenance. A portfolio-blocked entry
is frozen as non-actionable and cannot be credited to a veto policy.

## Trust boundaries

Raw chain/provider payloads are untrusted. Pydantic contracts, bounded Anchor decoding, account
layout checks, integer reserve limits, HTTP timeouts, no redirects, and fail-closed decision gates
sit between external data and simulated execution. The local statistical learner receives only
normalized saved features. Active Entry and Manipulation may only veto a Baseline entry. Active
Sizing may select only 0.5–2× and may exceed 1× only for a current deterministic Clean integrity
conclusion; an exact multiplier that no longer fits cash, reservations, per-position/total
exposure or route impact abstains back to Baseline size, and fill-time revalidation stays
authoritative. Active Exit may only shorten the normal review. A failed or unverifiable skill and
its dependants are suspended without granting authority to another version. Local AI explanations
remain downstream. The separate AI critic receives only an allowlisted evidence document and
cannot originate an order; after its own independent Shadow qualification, Guarded may only veto
a baseline entry. The AI Coach can select only deterministic allowlisted studies and always has
zero direct authority. A supported study needs explicit contribution permission, an existing
same-skill Champion and a fresh normal Challenger tournament; it cannot create the first Champion,
skip common-forward proof, replace a Champion directly or survive an incompatible dependency
change. A newly joined upstream skill also removes downstream authority until the exact new
composition earns fresh forward proof, while preserving its Champion and history. The Challenger
boundary revalidates every Coach policy against the deterministic allowlist rather than trusting
the persisted research row. Worker failures are contained and recorded without stopping
deterministic market processing.
