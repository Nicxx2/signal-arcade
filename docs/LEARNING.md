# Learning Lab

Signal Arcade learns cautiously from its own live-paper observation history. The learner is a
small, CPU-only challenger to the transparent V1 baseline—not a claim that the app can guarantee
profit, discover a permanent edge, or safely trade real money.

## What becomes a lesson

One eligible decision per mint can become a learning observation. The decision must come from
Solana Mainnet mode, use live market evidence, and have enough age, trades, and wallet breadth to
be an ENTER or PASS candidate. Synthetic Demo decisions, structurally unsafe tokens, WATCH states,
and repeated snapshots of the same mint are excluded. This avoids letting fast updates or demo
patterns dominate the history.

The saved lesson contains the exact point-in-time features and baseline action. Later live trades
for that mint add fee-inclusive paper outcomes at 1, 5, 10, 15, and 20 minutes. Each outcome uses
the same integer curve quote and configured protocol/network costs as the paper broker. If a
horizon has no usable future observation within its grace period, it stays **unknown**; it is never
silently treated as zero or as a loss.

Starting with the `stream-integrity-v4` cohort, each eligible lesson also freezes structural
market evidence available from the same five-minute Solana stream: the share of one-trade
wallets, wallets that rapidly bought and sold, volume attributable to those round trips,
absolute net quote flow relative to gross volume, buy/sell alternation, two-significant-digit
amount clustering, slot concentration, and price-direction consistency. Transaction-signature
bundling is retained for explanation when signature coverage is sufficient, but is not required
by the first learner model.

These are descriptive measurements, not a scam probability. Organic viral launches, market
makers, copy bots and legitimate bundled transactions can each produce one or more similar
patterns. The baseline therefore does not use the new measurements as a gate or score change.
The challenger learns their relationship to later net outcomes, while the Coach may propose only
an allowlisted shadow veto experiment that must pass the same independent forward-evidence
process as every other coaching idea.

Wallet, amount, slot and price coverage must each be sufficient before a new learner row is
created. Process startup, a WebSocket reconnect, fallback activation or an explicit market-source
change begins a fresh five-minute source-wide continuity window only after provider recovery is
confirmed; disconnected time never ages the safeguard. Bounded queue shedding and an exceptional
worker-batch failure start the same clean-window requirement only for represented mints, so
unrelated tokens can continue to learn from complete evidence. A failed event with no identity or
a saturated bounded gap tracker fails closed for the whole source. Failed batches are not replayed,
avoiding duplicate broker side effects. Protected open-position and already-saved outcome events
continue normally. Missing evidence remains `unknown`; it is never converted to zero. The evidence
schema is included in the configuration fingerprint and the model family is `learner-v4`, so all
older observations and models remain readable and auditable but cannot be mixed into the new
forward cohort as if those fields and continuity guarantees had existed at the time.

The five-minute net return remains the entry challenger's training target. The five horizons also
form conservative hold-timing comparisons against the exact normal review for each mode: 5 minutes
for Safe, 10 for Balanced, and 20 for Aggressive. Reported P/L remains unknown when no executable
quote exists, but horizon *utility* treats an unavailable exit as worst-case for selection only.
This lets a repeated pattern of vanishing liquidity favor an earlier review without claiming a
made-up sale price.

## Training and validation

Training begins after at least 80 usable live outcomes and reruns after ten additional outcomes.
Eighty samples are only enough to attempt a challenger; they are not proof of an edge.

The local learner is a regularized linear model implemented locally with no cloud AI, GPU, or extra
Python dependency. It uses bounded, named point-in-time features, including the new stream
integrity evidence. Older
observations form the training section and the newest third form a forward validation section,
with at least 20 validation examples. Validation is chronological, never randomly shuffled. Any
training outcome observed on or after the first validation decision is embargoed, so overlapping
five-minute labels cannot leak future information across the split.

A model is fitted only within one exact risk mode and decision-relevant configuration. Risk
personality is the core learning cohort: Safer evidence cannot qualify Balanced or Aggressive,
and changing personality never deletes the older cohort. The season-profile fingerprint is a
separate comparison identity. Balanced Default DD, custom DD and DD Off seasons therefore share
the Balanced learning lineage because the override changes portfolio admission, not the saved
point-in-time token target, quote math, fees, feature vector or forward outcome. Each observation
still freezes its season ID and exact profile fingerprint, and a candidate blocked by drawdown,
cash, exposure, capacity or conversion is marked non-actionable instead of being credited to a
Challenger veto.

A model
qualifies only when its untouched validation section:

- comes from a recent 1,000-observation window with at least 70% executable five-minute outcomes;
- beats a training-mean naive forecast on root-mean-square error by at least 2%;
- improves correlation over the saved baseline score by a margin;
- has at least a 1% mean outcome in its highest-ranked group; and
- improves that group over the baseline ranking by at least one percentage point.

Ranking is not enough. Shadow observations also freeze whether a baseline ENTER was genuinely
submittable under cash, exposure, capacity, and conversion gates. At least 20 such actionable
validation entries and five proposed vetoes must show a positive conservative fee-inclusive
uplift bound for the exact veto-only policy. At least 95% of the whole validation section must also
remain inside the fitted feature distribution. A later out-of-distribution decision always falls
back to the transparent baseline.

The persisted coefficients are the exact older-section candidate evaluated by those checks. The
app does not refit that artifact on the validation outcomes after it passes. This gives every
active version an honest correspondence between its saved metrics and its actual predictions.

Every trained version and its metrics are immutable in SQLite. Failed challengers remain visible
instead of being hidden. Small samples, correlated token launches, regime changes, selection bias,
and many attempted versions can still overfit these checks, so qualification is a guardrail—not a
profit certificate.

Missing five-minute exits remain unknown and are never inserted into regression as fictional
losses. They still count in the availability denominator, so a survivor-only set of liquid tokens
cannot qualify or activate an entry model.

For predictable long-running use on a small home server, pending lessons are always retained and
the newest 5,000 completed token lessons remain as full point-in-time records. Fitting and timing
selection use only the newest 1,000 comparable outcomes; entry fitting also exponentially
down-weights older examples with a 500-observation half-life. A separate monotonic outcome count
ensures new lessons still trigger retraining after the retained window fills. Model versions and
their validation metrics remain immutable while retained. Version history is bounded to the
newest 1,000 challengers; the active version and every version disabled by the live-health guard
are protected from pruning.

This is deliberately a bounded rolling memory rather than lossy compression. Aggregating old
tokens into a few averages would destroy tail events, missing-liquidity evidence, and the feature
combinations needed to reproduce a lesson. Keeping 5,000 compact JSON lessons is still small for
SQLite, while limiting the active model window prevents very old regimes from dominating current
decisions.

Hold timing has a separate gate; it does not inherit the entry model's qualification. For each
exact risk mode and configuration, at least 60 complete comparable observations are split
chronologically with the same
outcome-overlap embargo. The older section selects a review horizon no later than that mode's
normal review. On the newest third, a conservative 1.96-standard-error lower bound of its utility
improvement must still exceed one percentage point, with at least 70% executable exit
availability. A timing choice
that fails any gate falls back to the deterministic normal review. Timing calculations are cached
until checkpoint evidence changes, so a long history does not add repeated work to every market
event.

## Live progression and rollback

When the user enables Active mode, the model version and prediction are frozen into every later
eligible, portfolio-actionable baseline ENTER before its five-minute outcome exists. Entries that
cash, exposure, capacity, or conversion gates would already block are excluded, so their outcomes
cannot be vetoed or falsely credited to the learner. This is prequential evidence: it was genuinely
unseen by that active model, not another historical rescore.

After 30 resolved eligible entries, a rolling 60-entry health guard compares the baseline's
five-minute result with the learner's veto-only counterfactual (a veto preserves cash at zero
return). The app automatically returns to Shadow and permanently blocks that version when either:

- a conservative 1.96-standard-error upper bound still indicates more than 1% harm versus the
  baseline; or
- fewer than 70% of at least 30 resolved observations have executable outcomes, making the
  learner unverifiable.

After a suspension, only a newly trained, newly qualified version based on later outcomes can be
activated. While Active remains healthy, a newer qualified challenger is promoted only after the
current version has accumulated 30 unseen usable outcomes. This prevents a ten-outcome model
carousel while still allowing the learner to adapt over time.

Changing risk mode or a decision-relevant provider/fee configuration immediately returns an
Active learner to Shadow. A drawdown-only season transition within the same personality does not
create a false model generation or turn old observations into new evidence; compatible Active
monitoring continues normally. Older model versions remain immutable audit records, while their
saved observations can train a new generation only when their risk/configuration provenance
matches.

These bounds are cautious decision rules, not formal 95% guarantees: token launches can be
correlated and returns are not normally distributed. The automatic response to a false alarm is
only to restore the transparent baseline, never to take more risk.

## Modes and safety boundary

- **Off** stops starting new learning observations. Already-started horizons may still resolve so
  they are not falsified by a setting change.
- **Shadow** is the default. It records outcomes and shows what the latest challenger thinks, but
  never changes a paper decision.
- **Active** is unavailable until a qualified model exists. Even then, the learner can only veto a
  baseline ENTER whose conservative forecast (prediction minus validation error) is non-positive.
  A separately qualified timing challenger may shorten—but never postpone—the normal hold review
  using the eligible 1/5/10/15/20-minute checkpoints. Deterministic stop, structural exits,
  trailing protection, and the absolute time ceiling always retain priority. Later unseen results
  monitor the active version and can automatically restore Shadow mode.

The learner cannot create an entry, increase an order, weaken a permanent safety gate, extend past
the absolute ceiling, fabricate an exit, or touch a wallet.

## Separate local-AI experiment

The optional Ollama AI Decision Lab does not replace this statistical learner or share its
qualification. It starts Off. Shadow asks one selected local model for a strict support/veto/
insufficient-evidence verdict on normalized evidence from a baseline ENTER, then measures the
opinion against a separately frozen five-minute paper outcome including entry/exit/network fees.
Unknown evidence citations, extra schema fields, unavailable models, timeouts, and malformed JSON
are invalid outcomes, never trading instructions.

Guarded is locked to Shadow until that exact model digest and prompt/schema version have at least
200 measurable outcomes, 20 measurable high-confidence vetoes, 99% valid responses, a positive conservative
uplift lower bound, and p95 latency at or below 2.5 seconds. If it later qualifies, its only
possible action is a high-confidence veto of a baseline ENTER. Changing models returns it to Shadow. These records
include season and configuration provenance and survive a paper-bankroll reset.

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
