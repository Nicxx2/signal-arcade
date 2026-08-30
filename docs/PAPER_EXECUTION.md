# Paper execution semantics

## Lifecycle

A fresh database has no virtual cash and the paper engine is stopped. The user first creates a
SOL or USDC bankroll, chooses Safer, Balanced or Aggressive and may leave the advanced portfolio
drawdown halt at its personality default, set a custom 1–99% value, or disable that halt. The
resulting profile remains editable only until the first season genuinely starts. The user then
explicitly starts the engine. Stopping is non-destructive: pending
orders are cancelled, no decision or fill can be created, and cash, fills, and token quantities
remain in SQLite. The market feed continues updating retained token state and sell-side position
marks. Resume clears decision cooldowns, reassesses every holding against the freshest non-stale
state and restores exit risk management.

One season always has one immutable profile. After lock, changing either personality or drawdown
policy starts a durable exits-only transition rather than mutating the running experiment. New
entries stop, unfilled buys cancel, and active/dormant positions plus pending sells remain attached
to the exact policy context that opened them. The old season archives only when it is legitimately
settleable; its successor receives the canonical fresh bankroll. A normal automatic rollover
inherits the exact profile unless the user explicitly requested a different one.

The confirmation offers two explicit boundaries. **Finish safely** keeps the original exit policy
in control and gives dormant inventory the configured recovery window. **End season now** gives
fresh executable holdings a bounded 90-second opportunity to produce ordinary latency-, fee- and
impact-aware paper sell receipts. It never turns a last-known mark into a sale. Any holding still
untradeable at that boundary is archived as immutable unresolved inventory with its token units,
book cost, last-known indication, evidence time and blockers. The season remains visible but is
excluded from best-season and performance comparisons; a user-requested exit is also excluded from
exit-policy proof. The archive, unresolved records and clean successor season commit atomically and
the durable deadline survives restart.

## Fill timing

An ENTER decision creates a pending order with `fill_after = decision_time + entry_latency`.
Once that clock time passes, the order uses the newest observed reserves only while they are still
fresh and structurally executable. A later event updates that state, but an unrelated future trade
is not required: a real transaction can execute against unchanged on-chain reserves even when no
other trader acts. Exit orders use their own latency. If no fresh executable state exists within
90 seconds after eligibility, the order fails instead of inventing a fill.

Pending buys reserve an open-position slot, exposure, and account-currency cash. This prevents a
burst of qualifying coins from bypassing the selected risk limits before their delayed fills.
Capacity, drawdown, exposure, conversion, and available cash are checked again at fill time in
case the risk mode, SOL/USDC rate, or portfolio changed while the order waited.

## Price and rounding

Pump curve and PumpSwap offset-AMM states are quoted with integer constant-product arithmetic.
Buys round conservatively and cannot exceed real reserves. Sells deduct observed/configured
protocol fees plus simulated network and priority fees. Marks use the executable sell-side
estimate, so opening equity immediately reflects round-trip friction.

Every receipt records gross quote amount, token units, protocol fee, network fee, price impact,
latency, source event, venue, and its assumptions. A sell receipt also freezes the full exit
assessment, entry mode, realized return, best executable mark, and peak return before the position
is removed. Results can therefore explain a closed trade from immutable evidence instead of a
reconstructed or current-state story. Older receipts remain readable and are labelled as legacy
when that newer context is absent. Fee-free or instant fills are never implied.

## Accounting

Every virtual cash movement is balanced in a double-entry ledger. Buy cost becomes inventory;
network fees become expense. Sell proceeds remove book inventory and record gain or loss. The
portfolio survives restart from SQLite. Each fill and all of its order, ledger, position, and
realized-P/L effects commit atomically, so a process failure cannot leave a half-applied fill.

The UI separates total cash from pending-order reservations, available cash, and freshly marked
sell-side value. A mark older than the configured 90-second position window is shown as last-known
but excluded from headline equity; this prevents hours-old prices from being reported as current
profit. Closed proceeds return to the bankroll, so the next decision always plans from
what is actually available. Only realized bankroll growth can adjust future order size: a bounded
square-root multiplier compounds slowly and remains subject to the selected mode's exposure cap.
Unrealized marks cannot enlarge a new order.

SOL bankrolls use lamports. USDC bankrolls use micro-USDC and conservatively convert each
SOL-denominated paper cost, fee, proceed, and mark with the fresh observed `price_usd / price_sol`
relationship saved on the receipt. If the conversion is absent or older than 120 seconds, new
USDC entries abstain and an existing mark retains its last trustworthy value. Synthetic Demo uses
an explicit fixed assumption of 150 USDC per SOL so it remains deterministic and offline.

## Exits

The selected mode's normal hold time is a review point, not an unconditional sale. At every fresh
executable state, a transparent exit policy recomputes continuation support from buy balance,
momentum, wallet breadth, trading velocity, recent drawdown, concentration, and data confidence.
A position with sufficiently complete, strong evidence may continue until the mode's separate
absolute ceiling. The latest assessment, support score, evidence, entry mode, and executable peak
mark persist with the position and survive restart.

Stop loss, a recent creator sale, a newly failed mint-safety check, pre-migration route protection,
multi-signal deterioration, trailing profit after a mode-specific gain, and the absolute ceiling
schedule exits without learner discretion. A profit target starts protection rather than imposing
a fixed ceiling: a healthy winner can run, while a retracement from its saved peak locks the exit.
If the evidence set is incomplete or weak at the normal review point, the broker exits instead of
granting an extension.

Stale state or an unconfirmed route never creates a fabricated fill. A position can therefore
remain open past any clock threshold when no trustworthy executable route exists; it is labelled
as waiting, conservatively excluded from current equity after the mark-staleness window, and
retried when fresh route evidence returns. Pump-curve holdings exit before the configured
migration boundary when possible; a completed curve waits until a decoded PumpSwap state confirms
the new route.

Changing risk personality never rewrites a live position. Entry mode and policy provenance stay
with the holding across its normal reassessment, heartbeat/watchdog, stop, trailing, learned
timing, pending-sell and restart paths. The requested profile becomes active only after the clean
season boundary.

Each mint can be entered once per paper season. This prevents repeated qualification during one
trend from turning evaluation into churn. Resetting the paper portfolio clears that guard and
returns to stopped bankroll setup. Switching between synthetic Demo and Solana Mainnet does the
same so synthetic and real-data paper performance cannot be mixed.

There is deliberately no mid-season cash top-up because it would blur strategy P/L with a new
capital contribution. Open positions continue to be supervised even when available cash is low;
new entries fail closed at the exposure, drawdown, or cash gate. To add more paper runway, start a
new season and choose a fresh bankroll. The season's portfolio journal resets, while live Learning
Lab observations and immutable model versions remain available to the next season.

Disabling portfolio drawdown does not disable stop loss, trailing protection, maximum hold,
position/exposure caps, stale-data, mint, route, execution or accounting safety. It lets the
season continue until the broker can prove that current cash cannot fund any permitted minimum
entry and no active position, pending order or still-recoverable dormant holding can restore that
capacity. Dormant assets keep their existing recovery/grace opportunity and never receive an
invented zero exit. Missing conversion, provider health or executable evidence is unknown—not
bankruptcy—and pauses the test. Only healthy, sustained proof may end such a season as
`bankroll_exhausted`; an ordinary enforced halt ends as `auto_drawdown`.

Results defaults to the current currency and exact profile. SOL and USDC, custom drawdown variants,
disabled drawdown and other personalities remain separate for every count, chart, trend and
summary. All Seasons is chronological mixed-comparison history, not a single-strategy aggregate.
Pre-migration seasons whose profile cannot be proven are retained by currency as Legacy / Unknown
and excluded from modern like-for-like claims. Manually ended seasons and any season with
unresolved inventory are likewise retained for audit but excluded from improvement, best-return,
profitability and average-win-rate claims.

The scanner does not wait for current positions to close. Every incoming event first refreshes
the matching open position and applies the adaptive exit and permanent risk rules;
unowned candidates are scored in parallel. Safe/Balanced/Aggressive allow at most 2/4/6 occupied
or reserved slots. When full, otherwise-qualified candidates are recorded as PASS with
`portfolio_capacity_reached`, and can qualify again on a later event after a slot is freed.

V1 intentionally does not sell a valid holding merely because a newer coin has a higher snapshot
score. Scores observed at different times are not guaranteed comparable, and automatic rotation
would add another sell plus buy, price impact, fees, and churn. A future rotation strategy should
only be introduced with out-of-sample evidence that its net uplift exceeds those costs.

## Not modeled completely

MEV ordering, leader geography, RPC propagation gaps, compute-unit variability, account creation
rent, route competition, blockhash expiry, transaction failure, and malicious UI/metadata effects
can make real execution worse. V2 must model and validate these before any live capability exists.
