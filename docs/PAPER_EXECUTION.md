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

One season always has one immutable target: account currency, exact starting bankroll, personality
and drawdown policy. Before activity, the complete target can be replaced atomically without
creating an empty archived scorecard. After lock, changing any part starts a durable exits-only
transition rather than mutating the running experiment. New
entries stop, unfilled buys cancel, and active/dormant positions plus pending sells remain attached
to the exact policy context that opened them. The old season archives only when it is legitimately
settleable; its successor receives the exact requested currency and bankroll. A normal automatic
rollover inherits the exact target unless the user explicitly requested a different one. The
durable operation fingerprints the full target, so a retry is idempotent and a conflicting
mid-transition edit is rejected rather than partially applied.

The confirmation offers two explicit boundaries. **Finish safely** keeps the original exit policy
in control and gives dormant inventory the configured recovery window. **End season now** gives
fresh executable holdings a bounded 90-second opportunity to produce ordinary latency-, fee- and
impact-aware paper sell receipts. It never turns a last-known mark into a sale. After the recovery
or settlement window, a zero-value write-off requires healthy global data plus two fresh,
position-specific route-unavailable observations. A provider gap, restart without fresh proof, or
still-executable holding remains `incomplete_unknown` and defers a safe/automatic boundary; the
explicit end-now path instead honours its deadline, archives that unknown record and excludes the
manual season from comparison claims. Each
retired holding keeps token units, book cost, last-known indication, evidence time and blockers.
`End season now` stays visible but is excluded from best-season and performance comparisons; a
user-requested exit is also excluded from exit-policy proof. The archive, terminal records and
clean successor season commit atomically, and the durable deadline and exact target survive
restart.

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
case the risk mode, SOL/USDC rate, or portfolio changed while the order waited. A current Baseline
buy also reruns the deterministic entry thesis at its exact requested size against the fill-time
snapshot. The broker can cancel a deteriorated order but can never increase it during fill; a
scaled entry additionally requires market integrity to remain clean.

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
what is actually available. Baseline v1.5 starts from the personality's cautious reference size.
Only mature clean evidence with economically meaningful participation may target more of the
realized bankroll, and every selected amount is bounded by per-position exposure, remaining total
exposure, reserved/available cash and observed price impact. Current suspicious evidence blocks;
moderate unresolved evidence uses 70% of the reference; incomplete or extremely ambiguous evidence
waits instead of entering. Unrealized marks cannot enlarge a new order, and the policy never tries
to consume unused exposure merely because capacity exists. Older positions and seasons retain
their exact entry-generation behavior.

If the user has explicitly activated a qualified Challenger, its Sizing skill remains subordinate
to that planner. It can choose only a previously proved 0.5×, 1×, 1.5× or 2× counterfactual and can
size above 1× only while the current deterministic integrity assessment is Clean. The resulting
amount applies only when that exact multiplier still fits realized cash, reservations,
per-position and total exposure, fresh route depth and price impact; otherwise a capacity
abstention leaves the deterministic Baseline amount unchanged. Submission and fill then validate
the exact frozen receipt and thesis again. A suspended Sizing version also leaves Baseline sizing
unchanged.

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

For Baseline v1.5 positions, buy balance, momentum, wallet breadth and velocity earn hold support
only in proportion to economically meaningful volume and wallet participation. A synthetic-looking
wall of dust activity therefore cannot extend a position by itself. Earlier positions retain their
entry-generation behavior.

Stop loss, a recent creator sale, a newly failed mint-safety check, pre-migration route protection,
multi-signal deterioration, trailing profit after a mode-specific gain, and the absolute ceiling
schedule exits without learner discretion. A profit target starts protection rather than imposing
a fixed ceiling: a healthy winner can run, while a retracement from its saved peak locks the exit.
If the evidence set is incomplete or weak at the normal review point, the broker exits instead of
granting an extension.

For positions opened by Baseline v1.2, v1.3, v1.4 or v1.5, manipulation evidence can also request
an exit only after it persists across time-separated checkpoints. One alarming snapshot cannot
sell a position; uncertain evidence neither advances the warning nor pretends recovery, while a
mature clean sample resets it. The counters and timestamps persist across restart. Existing route
safety still decides whether the requested exit can produce a real paper fill.

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

A qualified active Challenger Exit skill may recommend an earlier normal review learned from the
same risk cohort's exact executable checkpoints. It cannot postpone the Baseline review, change a
hard stop or structural exit, extend the absolute ceiling, or turn a stale mark into a paper sale.
Each learning observation freezes the exact candidate/champion Exit recommendation before its
future checkpoints, while the broker persists the actual review assessment used on a position. A
later health suspension removes future Exit influence without rewriting completed evidence.

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

Results defaults to the current exact comparison: currency, starting bankroll, immutable profile
and terminal-accounting policy. Different amounts, currencies, drawdown variants or personalities
remain separate for every count, chart, trend and summary. Currency-wide and All Seasons views are
chronological mixed-comparison history, not one strategy aggregate. Pre-migration seasons remain
Legacy / Unknown. Empty seasons, manual boundaries and provider-unknown endings remain visible but
cannot support improvement, best-return, profitability or average-win-rate claims. A safe or
automatic season with meaningful activity and independently confirmed write-offs remains an honest
complete paper result—the lost entry cost is part of its outcome and the write-off counts as a
terminal loss, without inventing a sell fill or learning outcome.

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
