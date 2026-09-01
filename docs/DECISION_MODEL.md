# Decision model V1

The V1 baseline is intentionally transparent. It is a testable hypothesis, not an opaque claim
of intelligence or profitability.

## Evidence

Each `DataValue` stores its value, unit, observation time, sources, freshness, quality, and a
missing-data reason. Rolling features include trade velocity, buy/sell balance, unique wallets,
wallet-volume concentration, repeated amounts, same-slot coordination, creator sells, curve
progress, momentum, drawdown, reserves, observed fees, and optional DEX context. Baseline v1.5
also records native-SOL median trade size, dust-trade share, economically meaningful volume and
wallet participation, trade density, price-path efficiency, rapid reversals, venue-local window
span and bounded-buffer saturation.

Decision explanations retain a separate market-integrity evidence layer derived only from
the already-received five-minute stream: one-trade wallet share, wallet round trips and their
volume, net flow versus gross activity, side alternation, clustered sizing, slot concentration,
price-direction consistency and multi-trade signatures. Coverage and missing reasons are saved
with each value. Baseline v1.5 adds an economic-activity category only when several size/flow
measurements agree, plus a separate rapid-reversion category. It requires minimum time, trades,
field coverage and an uninterrupted five-minute event window; queue shedding, a reconnect or a
still-live bounded-buffer eviction remains Unknown rather than looking clean. One isolated
pattern remains uncertain; an extreme isolated warning must clear or gain corroboration before
entry. Suspicious and severe current conclusions block entry. Conclusions require corroboration
across independent wallet-loop, concentrated-dispersion, net-flow, trade-structure, economic-flow
and price-path categories. Concentrated dispersion itself requires both
extreme wallet-volume concentration and overwhelming one-trade participation, so neither a lone
whale nor an organic broad launch is condemned. Both suspicious and severe evidence block a new
v1.5 entry and raise deterministic danger. Locked v1.1/v1.2/v1.3/v1.4 seasons retain their frozen
behavior until a legitimate successor season begins.

## Scores

- Opportunity combines velocity, participation, buy balance, curve progress, and non-extreme
  momentum. In v1.5 raw velocity and wallet breadth are discounted unless meaningful economic
  participation supports them, so thousands of dust transfers cannot manufacture a top score.
- Danger combines concentration, repetition, same-slot coordination, creator selling,
  drawdown, and parabolic momentum.
- Execution estimates the selected paper size relative to effective quote reserves.
- Confidence combines sample count, distinct participation, freshness, and reserve evidence.
- The net-edge index subtracts danger, price impact, observed or fallback round-trip protocol
  fees, and size-relative simulated network/priority fees from the opportunity estimate. Its
  value is a dimensionless ranking heuristic, not a calibrated expected return, probability,
  price target, or promise of profit.

The weights and thresholds are explicit, hand-selected V1 hypotheses. They are legitimate
market and risk features, but they have not yet earned the label of validated alpha. The model
must be judged on untouched forward paper data before any tuning or stronger performance claim.

The local Learning Lab is a deliberately subordinate Challenger with four independently versioned
skills. Entry and Manipulation may only veto an actionable Baseline ENTER. Sizing may select a
bounded 0.5×, 1×, 1.5× or 2× counterfactual size, with size-up allowed only when current
deterministic integrity is Clean and every portfolio/execution cap still passes. Exit may only
shorten the normal review. No skill can create a trade, weaken a gate, lengthen a hold or fabricate
a fill. Each candidate validates chronologically and must then beat its saved champion on the same
later common-forward outcomes before replacement; unfamiliar evidence falls back to the Baseline.
One explicit consent activates the qualified Entry champion, while later skills join only after
separate incremental proof beside the active ensemble. See [LEARNING.md](LEARNING.md) for the exact
lifecycle and caveats.

The optional Ollama AI Decision Lab is a second, independent experiment. Off is the default.
Shadow reviews only actionable baseline ENTER candidates and has no control path. It keeps at most
one unresolved five-minute assessment per token, so repeated snapshots cannot inflate the sample
or monopolize a CPU. Its bounded queue discards work older than one minute, and changing mode or
model clears queued work that no longer matches the selected experiment. The model returns only a
schema-bounded verdict, confidence, supported risk
flags, and exact references to supplied evidence; displayed prose is derived deterministically.
It is judged on frozen,
fee-inclusive five-minute counterfactuals tied to an exact model digest, prompt/schema version,
input hash, season, and configuration fingerprint. Guarded remains locked until a conservative
forward evidence gate qualifies that exact model; if qualified, it can only turn ENTER into PASS.
It cannot add score, create a trade, increase size, manage an exit, or bypass a permanent gate.

The Safe/Balanced/Aggressive slider changes the reference size, evidence thresholds, acceptable
danger and impact, portfolio exposure, drawdown stop, and exit widths. Baseline v1.5 may size a
mature clean entry above that reference from realized bankroll only. It remains bounded by the
mode's per-position and total exposure, available cash, pending reservations and observed reserve
depth; economic activity also bounds any increase. Moderate uncertain evidence is reduced to 70%
of the reference and cannot size up. It never disables structural safety gates.

## Permanent abstention gates

- missing or stale curve state;
- completed curve without a confirmed AMM route;
- a quote mint other than native SOL on Pump curves or wrapped SOL on PumpSwap;
- unsupported token program;
- unverified or unsafe live mint account;
- active mint/freeze authority, wrong decimals, unsupported owner, or transfer-affecting/
  unreviewed Token-2022 extensions.

Learning gates first produce WATCH. Valid but unattractive candidates produce PASS. Only a
candidate with no blocker produces ENTER.

## Why these ideas are here

- Short-horizon momentum and participation breadth are candidate demand signals, while the
  non-extreme momentum term deliberately avoids rewarding an unlimited vertical move.
- Concentration, repeated sizing, same-slot coordination, creator selling, and parabolic moves
  are manipulation/crowding warnings. Empirical cryptocurrency pump-and-dump research reports
  identifiable pre-pump and pump patterns, and US regulators specifically warn that thinly
  traded tokens and memecoins are vulnerable to promotion followed by rapid dumping.
- Fees, network cost, liquidity, and size-relative price impact are charged before a candidate
  can qualify. Research on momentum with transaction costs supports evaluating the net strategy,
  not a frictionless headline return.
- Position caps, exposure caps, portfolio drawdown limits, stop loss, trailing profit, migration
  protection, evidence-based hold review, and an absolute hold ceiling are risk controls. They
  bound a paper experiment; they do not prove that its entries have an edge.

Primary references:

- [Li, Shin and Wang, *The Anatomy of a Cryptocurrency Pump-and-Dump Scheme*](https://arxiv.org/abs/1811.10109).
- [CFTC customer advisory on virtual-currency pump-and-dumps](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/beware_virtual_currency_pump_dump.html).
- [SEC Investor.gov crypto scam alert](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/crypto-scams).
- [Frazzini, Israel and Moskowitz, *Trading Costs of Asset Pricing Anomalies*](https://www.nber.org/papers/w20984) and [Daniel and Moskowitz, *Momentum Crashes*](https://www.nber.org/papers/w20660).

## Validation

All decisions retain the exact feature snapshot and model version. A meaningful strategy review
must compare later outcomes for entered and rejected candidates, include fees, avoid survivorship
bias, split tuning from evaluation periods, and report drawdown—not only win rate.
