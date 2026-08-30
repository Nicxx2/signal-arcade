# Architecture

## Runtime flow

```text
Pump + PumpSwap logs ──> pinned Anchor decoder ──> bounded priority queue
                                                        │ batched SQLite journal
                                                        v
                                              point-in-time features
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
- `intelligence/learning.py`: live-only outcome checkpoints, chronological validation, immutable
  challenger versions, optional veto-only entry guard, and bounded hold-horizon utility.
- `paper/`: integer curve quotes, delayed orders, persistent adaptive exit assessments, receipts,
  positions, and accounting.
- `ai_lab.py`: optional structured local-model critic, serialized catalog downloads, runtime
  monitoring, strict evidence validation, independent counterfactual outcomes, and per-model
  qualification. Compose supplies a private CPU-first Ollama service with separate model storage.
- `database.py`: versioned SQLite schema, WAL, batched deduplication, incidents, equity rollups,
  quota and retention state.
- `orchestrator.py`: one event-time coordinator and fan-out bus.
- `api.py`: local security middleware, API routes, WebSocket, and built static UI.
- `frontend/`: minimal React/Vite dashboard; it contains no provider credentials.

## Failure behavior

Provider failures do not stop the ledger or UI. The stream reconnects with bounded exponential
backoff. Optional HTTP failures remain unknown. Market events enter a bounded queue and are
persisted in batches. When overwhelmed, the app retains held/pending/learning-critical activity,
sheds untracked low-priority trades, and records a persistent incident rather than allowing
unbounded memory or database pressure. UI notifications have their own bounded queue and the
normal five-second snapshot poll repairs missed notifications. Duplicate events are ignored.
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
risk-limit values and policy version, typed portfolio-drawdown policy, effective threshold, and a
stable profile fingerprint. A unique partial index permits only one current season. A locked
profile change is a durable `profile_transition` operation: new buys freeze, unfilled buys cancel,
owned positions and pending exits continue under their entry provenance, and the completed-season
archive plus successor creation commit atomically. Restart reconciliation treats the old profile
as authoritative before that boundary and the new profile as authoritative after it, so retries
cannot create two current seasons. Pre-profile history remains visible as Legacy / Unknown rather
than being guessed into a modern cohort.

An explicit `end_now` transition stores a bounded settlement deadline in that same operation.
Executable positions receive normal paper sell orders; any remaining position is copied into the
append-only `unresolved_paper_positions` audit before live paper tables are cleared. Season rows
carry separate result-quality and comparability fields, so a real manual fill remains accounting
truth while neither user-selected timing nor unresolved inventory can be credited as strategy
performance. Unknown transition values fail closed to the normal safe-drain behavior.

Learning observations, model versions, AI assessments, and operational incidents also recover
from SQLite. Learning and AI audit records intentionally survive a paper-bankroll reset. Demo
events never train the statistical learner or qualify Guarded AI. Missing future observations
remain unknown rather than becoming invented returns.

Season and learning identity are deliberately separate. The season-profile fingerprint includes
the drawdown experiment for apples-to-apples portfolio comparison. The decision-configuration
fingerprint includes the risk personality and trade-learning inputs, but not the portfolio
drawdown override. Default, custom and disabled drawdown seasons can therefore contribute honest
forward evidence to the same personality Challenger while every observation retains its exact
season and profile provenance. A portfolio-blocked entry is frozen as non-actionable and cannot be
credited to a veto policy.

## Trust boundaries

Raw chain/provider payloads are untrusted. Pydantic contracts, bounded Anchor decoding, account
layout checks, integer reserve limits, HTTP timeouts, no redirects, and fail-closed decision gates
sit between external data and simulated execution. The local statistical learner receives only
normalized saved features. In active mode it may veto a baseline entry after qualification, but
cannot originate an order, increase size, or bypass any safety gate. Local AI explanations remain
downstream. The separate AI critic receives only an allowlisted evidence document and cannot
originate an order; after its own independent Shadow qualification, Guarded may only veto a
baseline entry. Worker failures are contained and recorded without stopping deterministic market
processing.
