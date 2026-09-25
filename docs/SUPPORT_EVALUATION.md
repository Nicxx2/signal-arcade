# Champion selectivity and fallback research

This follow-up separates three questions: whether the current Champion improves the same quoted
opportunities, whether it selects entries rather than preserving cash on almost everything, and
what happens when an unsupported later attempt falls back to Baseline. These are different cohorts.
The completed activity-pattern study remains inconclusive; its specification and archived reader
are not replaced by this work. No experimental buying rule is enabled.

## Engineering boundary

Champion Impact now reports supported entries, supported vetoes, Baseline fallbacks and unknown
receipts over its existing resolved Policy window. Its separate actual-entry sample uses at most
30 recent fills, exact order/decision links and indexed parent-buy lookups. It counts a realized
result only for an unambiguous full close with matching mint, entry time, units, currency and
decimals. Net account proceeds minus entry cost preserve fees and negative results. Open, partial,
ambiguous or missing closes remain unresolved. Old season, configuration, profile, activation and
Champion receipts cannot receive current credit. An original-opportunity link alone does not prove
that an earlier veto was applied. Neither report feeds training, proof, health or trading.

The RPC worker may retain its one already-fetched batch for at most 0.5 seconds of scheduled
waiting while a storage chunk completes. It owns no event/database lock during that wait and
does not pause cleanup. Stop, upgrade, provider/learner replacement and market guards abort the
wait; final admission and route/deadline validation still apply. Original request clocks remain
unchanged. A delayed event loop can make elapsed wall time exceed the requested wait, so freshness
is checked independently. Idle observed is not an accepted route or a completed checkpoint.
New counters stay outside the fixed interval payload. If cumulative runtime detail outgrows
the existing event byte limit, it splits into finite `guards`, `snapshot` and `rpc` lanes, each
with its own optional admission/cadence. Match boot/scope and timestamps when correlating parts;
under pressure they may be saved at different times. Do not add overlapping cumulative samples.
Core and proof event priority, byte limits and honest loss reporting remain unchanged.

## Study A: fixed shadow selectivity screen

`python -m signal_arcade.intelligence.support_research SOURCE.sqlite SPEC.json` runs separately
from the app and opens a bounded read-only snapshot. `--export PRIVATE.json` creates a new private
replay bundle; `--from-bundle` replays it. It shares the established activity reader's five-second
cooperative SQL budget, 5,000-parent/64 MiB limit, persistent first-opportunity identities, digest
checks and retention checks. The native selector remains capped at 1,000; reaching its cap makes
this screen inconclusive. No service starts, fitting occurs or permission changes.

Before enrollment, retain a dated specification, exact artifact bytes and their SHA-256 digest,
and an archive/digest of the evaluator. Declaring `frozen_at` in JSON is not independent proof of
when the hypothesis was frozen. The specification requires an exact season, risk mode, profile,
configuration, Baseline version, complete active Champion map, artifact digest, validation RMSE,
venue, quote mint, fees and selected coverage requirement. Context changes are reported/excluded;
they cannot inherit the previous cohort. A source artifact must be verified against the declared
digest separately; the reader validates frozen receipt consistency, not authenticity of a file
supplied by an operator.

The single research recipe, `manipulation-sign-shadow-v1`, compares the current conservative
rule (`prediction - frozen validation RMSE > 0`) with the sign of the **same frozen prediction**
(`prediction > 0`). Both retain the existing feature-support boundary and Baseline fallback on
unsupported inputs. Inconsistent/missing receipts remain unknown; the reader never refits a model
or computes predictions using future information. This candidate is a hypothesis about an overly
conservative return rule, not an established improvement or a manipulation detector.

Use one fixed six-hour future enrollment period, then allow at least 15 minutes for final outcomes.
Select independent original Policy opportunities with their own fee-inclusive 300-second outcomes,
observed from 300 through 390 seconds after entry. Pending, failed quotes, missing receipts and
retention uncertainty do not become zero or favorable returns. Positive outcomes remain positive
even when a token's activity looks suspicious. Later retries cannot replace original proof.

Prespecified minimums are 200 independent opportunities, 60 changed usable outcomes (at least
30 in each temporal half), 90% consistent receipt availability, and both outcome and paired
coverage at or above the frozen configured requirement. Counts may be made stricter, never lower.
The candidate must show a positive lower approximate interval against **each** of incumbent,
Baseline and cash, a positive paired mean in both temporal halves, and veto no more than 35% of
observed winning opportunities. Three comparisons use a conservative 2.40 standard-error multiplier
(a Bonferroni normal approximation). The report includes admitted losses and missed winners.

These are preliminary screens. They do not resolve market dependence, missing-outcome bias,
tail risk, changing liquidity, capital constraints, adaptive exits or portfolio drawdown. An
always-cash rule cannot pass the cash comparison; an always-Baseline rule cannot pass its Baseline
comparison. Do not extend a window until it passes, choose an RMSE multiplier after seeing outcomes,
or call a retrospective pilot prospective. An insufficient or unfavorable period leaves trading
unchanged. Invoking the tool does not schedule or start a future review.

### Completed fixed-window result — 21 September 2026

The frozen six-hour enrollment period ran from **12:00 to 18:00 UTC**, with an **18:15 UTC**
outcome cutoff. The archived evaluator, artifact digest and bounded replay were verified. Of 344
parents read, 298 matched the frozen context; 284 had usable outcomes (95.30%), with consistent
receipts for all 298 opportunities. The retained sample was not truncated by the selection cap.

The incumbent vetoed all 298 opportunities; the proposed sign rule vetoed 297 and changed only
one usable action, which lost money. Changed usable counts were zero and one in the two temporal
halves, below the prespecified 30 in each half. The candidate still vetoed all 92 positive quoted
outcomes. Its mean difference from the incumbent/cash was approximately -0.074 percentage points,
with an approximate interval spanning zero; neither the support requirements nor economic screen
passed. `activation_allowed` remains false. Do not extend this cohort or retune the rule against it.

This result supports keeping the current rule while considering separately designed research.
It does not prove that the incumbent selectively recognizes legitimate coins: avoiding exposure
can beat a losing Baseline cohort without identifying good entries. These are fixed-horizon,
fee-inclusive Policy quotes, not realized portfolio returns, drawdown measurements or fraud labels.
Private specifications, datasets and replay bundles are not community-release artifacts.

## Study B: fallback transition feasibility, kept separate

Before testing a fallback rule, collect a separately frozen future period of exact
**applied original veto → unsupported later attempt** transitions. Freeze the same context as
Study A and group by original persistent opportunity, taking only the first eligible later attempt.
Report first support-failure reason, elapsed time, activity freshness, original integrity state and
whether the later attempt actually filled. A proposed but unapplied veto is not an applied veto.
Model unavailability and an upstream rejection are different from a feature outlier.

This is initially a feasibility study, not a trial of a new buying restriction. The current
Policy journal cannot be reused to supply a later attempt's price or 300-second outcome. Its
original checkpoint belongs to a different decision. Existing actual matched fills can describe
realized paper results, including losses and missed profitable opportunities, but cannot certify
a complete fixed-horizon cohort or the result of an unexecuted delayed entry.

A candidate reassessment/cooldown rule therefore needs a separately reviewed, bounded shadow
quote capture path and exact later-attempt outcome before an efficacy screen can run. It must
preserve Policy/held-position priority, quota, original clocks and honest capture-loss counters.
Do not insert retries as additional native proof. Require at least 60 independent affected usable
opportunities and freeze the recovery rule, horizon, missing-data treatment, costs and endpoints
before that cohort exists. No recovery interval is selected from the historical losing examples.

Missing/stale/cached/interrupted/saturated observations do not establish recovery. Independent
small buyers, legitimate launches, a single large trade among dust, repeated amounts and genuine
recovery need explicit review. Wallet count does not establish independent ownership. An old
warning must never become an indefinite cross-model or cross-season ban. This second study is
not an output of `support_research`, and has no positive efficacy result at this stage.

## Activation and release gate

Both studies have `activation_allowed = false` as a policy boundary. Study A's executable report
always emits false. Fresh evidence can justify another implementation decision; it cannot mutate
the incumbent Champion. Any later behavior change requires a new versioned policy/native recipe,
fresh chronological qualification and common-forward proof, unchanged user permissions, and the
same rule in fitting, proof, live receipts, battles, health, recovery and pending-fill checks.
Dependency changes require the existing downstream requalification. Existing orders and held
positions must retain their original contracts and safe exits.

The reporting and bounded RPC handoff can be validated and released independently of an
unproven trading change. Before live rollout, run regression/static checks, disposable restart
and source-to-artifact checks; use Settings upgrade preparation when deployment is authorized.
After rollout, inspect natural traffic for snapshot cost, handoff timing/expiry, cleanup progress,
diagnostic loss and worker health. A passing test suite or a few profitable trades is not evidence
of better trading. These engineering results do not establish a successful study, satisfy the
activation stages, or demonstrate long-term unattended readiness by themselves.
