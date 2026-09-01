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

Starting with the `stream-integrity-v5` cohort, each eligible lesson also freezes structural
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
`challenger-features-v3`, so all
older observations and models remain readable and auditable but cannot be mixed into the new
forward cohort as if those fields and continuity guarantees had existed at the time.

The five-minute net return remains the Entry skill's training target. The five horizons also
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

Missing five-minute exits remain unknown and are never inserted into regression as fictional
losses. Once their grace window has resolved, they still count in the availability denominator, so
a survivor-only set of liquid tokens cannot qualify or activate an entry model. A horizon still
inside its observation window remains pending and is excluded until it actually resolves.

For predictable long-running use on a small home server, pending lessons are always retained and
the newest 5,000 completed token lessons remain as full point-in-time records. Fitting and timing
selection use only the newest 1,000 comparable outcomes; entry fitting also exponentially
down-weights older examples with a 500-observation half-life. A separate monotonic outcome count
ensures new lessons still trigger retraining after the retained window fills. Model versions and
their validation metrics remain immutable while retained. Version history is bounded to the
newest 1,000 challengers; active, suspended, champion, latest-candidate and in-flight tournament
versions are protected from pruning.

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

## Candidate, champion and common-forward proof

A newly qualified artifact is a **candidate**, not automatically the best known skill. If no
champion exists it can become the initial saved champion. Otherwise both candidate and champion
are frozen before the next outcomes arrive and are evaluated on those same common-forward cases.
Promotion requires at least 30 common cases, at least 70% executable coverage, positive
confidence-adjusted improvement and the skill's harm/winner guards. An inconclusive tournament is
closed after 120 usable common-forward cases, or after 172 resolved cases when executable coverage
remains below 70%, rather than running forever or learning from a survivor-only subset. Candidate,
champion, counters and decisions are stored in SQLite, so restart cannot erase a loss or restart a
trial selectively. If the promoted champion is already influencing decisions, its exact proved version
replaces the old one; downstream skills step out and must re-prove beside the new dependency.

The Learning tab presents the current Contender, best-proved Champion and actual influence
separately. A candidate can therefore have fewer passed gates than an older champion without
destroying that champion; that is healthy exploration, not forgotten learning. It also keeps the
newest 12 completed Champion milestones per skill cohort: first qualification, promotion, defence
or an inconclusive 120-case battle. Events are idempotent across restart and shown only for the
exact current personality/configuration cohort. An installation upgraded from an older version
keeps its existing Champion but does not fabricate battles that were never recorded.
The bounded journey is stored beside, rather than inside, the strict skill-state record so an older
v11 reader can ignore the new history safely. The state and sidecar are committed atomically.

## Consent, composition and rollback

Active influence is unavailable until a qualified Entry champion exists. The user's one explicit
activation grants consent to that exact Entry version. Manipulation, Sizing and Exit do not gain
immediate control from that click. Each later skill must first collect at least 30 fresh common-
forward outcomes beside the exact active upstream ensemble, retain at least 70% availability, show
positive conservative incremental value and pass its harm guard. Only then can that exact version
join automatically.

Composition changes are treated symmetrically. If a newly proved upstream skill joins after a
downstream skill was already active, the downstream Champion and journey are preserved but its
authority is removed until that exact new ensemble earns fresh incremental proof. Runtime
assessment also rechecks the saved version, health state and full dependency map before every
application, so inconsistent persisted state fails closed to the smaller proved ensemble.

Every eligible observation freezes the active skill versions and each skill's proposed action
before the future outcome exists. Entries that cash, exposure, capacity or conversion gates would
already block remain non-actionable, so a veto cannot claim credit for a trade the portfolio could
not have placed. Each final decision also carries a per-skill audit receipt describing whether the
skill abstained, vetoed, changed size or shortened review.

After 30 resolved cases, per-skill rolling health checks compare each active version with its
bounded counterfactual. Pending horizons do not count as failures; resolved unavailable outcomes
do count against coverage. A harmful or insufficiently observable skill is suspended. Its
downstream dependants are suspended as well because their proof assumed that upstream ensemble;
unrelated upstream evidence and every immutable artifact remain intact. If Entry is suspended,
influence returns to Shadow and the Baseline resumes sole control. A restart restores only exact
healthy, dependency-compatible versions; it cannot silently substitute the newest artifact.

Changing risk personality or a decision-relevant Baseline/provider/fee configuration returns an
active ensemble to Shadow and clears influence, while retaining the user's consent and all learning
history. A drawdown-only season transition within the same personality does not create a false
model generation. Older versions can contribute again only when their exact learning cohort is
compatible.

These bounds are cautious decision rules, not formal 95% guarantees: token launches can be
correlated and returns are not normally distributed. The automatic response to a false alarm is
only to restore the transparent baseline, never to take more risk.

## Modes and safety boundary

- **Off** stops starting new learning observations. Already-started horizons may still resolve so
  they are not falsified by a setting change.
- **Shadow** is the default. It records outcomes and shows what the latest challenger thinks, but
  never changes a paper decision.
- **Active** is unavailable until a qualified Entry champion exists. It begins with the exact Entry
  version the user approved. Independently proved Manipulation, Sizing and Exit champions may join
  later under the composition gates above. Deterministic entry, fill-time route/integrity, cash,
  exposure, stop, structural exit, trailing and absolute-time controls always retain priority.
  Later unseen results monitor every active version and can automatically suspend only the unsafe
  part—or restore Shadow when Entry itself is no longer trustworthy.

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

Historical evidence may screen or reject an idea, but cannot prove it. Every selected study
freezes its risk personality, decision-configuration fingerprint, Baseline version, feature schema,
active skill dependencies and proposal cutoff. Only exact-cohort, fee-inclusive outcomes created
after that cutoff contribute to forward proof. Observation IDs, measured values and meaningful
season counts are stored durably, so restart, history pruning or a rolling observation window
cannot replay evidence or silently reset the proof clock. Legacy and incompatible rows stay
readable but do not enter a current study.

A supported study needs at least 60 usable outcomes, at least 70% executable coverage, two
independent seasons with at least ten usable outcomes each, and a confidence-adjusted improvement
above one percentage point. Clearly harmful evidence may reject a study after 120 usable outcomes.
A study that reaches 180 resolved observations or 90 days without enough support closes as
inconclusive, including quiet cohorts that never reached 60 samples; it cannot collect forever.

Support still grants no trading authority. Only after explicit user permission may a supported
idea be handed to the matching Challenger skill. It waits until that skill already has a saved
statistical Champion, then enters the ordinary common-forward tournament as one immutable
contender. It cannot create the first Champion, skip proof, replace a Champion directly, or act
outside its exact dependencies. A context change retires the stale contender while preserving the
existing Champion. The Challenger handoff independently revalidates the complete deterministic
allowlist—including policy kind, skill, conditions, multiplier or review horizons—so a malformed
or incompatible persisted Coach record cannot acquire tournament authority.

### AI Decision Lab

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
