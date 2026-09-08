# Learning collection review — 7 September 2026

These changes were developed against v1.10.6 and are included in v1.10.7. They improve evidence
collection and diagnostics. They do not establish better trading returns or guarantee an Entry
Champion. See the [v1.10.7 release verification](V1_10_7_VALIDATION.md) for the packaged release.

## Evidence and training decision

A live review found approximately 51% usable five-minute outcomes in Entry's current Discovery
fitting population, alongside much higher coverage in the separate actionable Policy population.
In a reconstructed 1,000-row fitting window, 336 sell quotes exceeded recorded real reserves, 25
could not cover sell fees, and 133 checkpoints had stale routes or elapsed collection windows.
Integer quote recalculation confirmed the liquidity and fee failures. Even recovering all 133
stale/missed checkpoints would only have brought that window to 63.9% usable coverage.

An offline exploratory comparison then used the shared retained time span, reserving its last
third for mint-disjoint Policy evaluation. Within earlier evidence it retained chronological
validation, the outcome-time embargo, complete missing-outcome denominators and the existing
fixed Linear/XGBoost recipes. No parameter search or model publication was performed.

| Earlier fitting population | Resolved | Usable | Coverage | Linear validation RMSE | XGBoost validation RMSE | Naive RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Existing Discovery selection | 1,000 | 509 | 50.9% | 0.3283 | 0.2644 | 0.3853 |
| Historical Baseline-actionable Policy | 476 | 457 | 96.0% | 0.7412 | 0.7188 | 0.6874 |

These validation populations are different, so their raw errors are not a direct model ranking.
The actionable-only alternative failed to improve over its own naive reference for either family.
Both populations also had negative top-group validation returns. Later evaluation used the same
193 Policy episodes, of which 188 had usable outcomes. The actionable-trained models had lower
forecast error there, but lower feature-support coverage and lower measured veto-policy utility.
This mixed historical result does not justify replacing the current training contract.

The live training populations, model recipes and qualification thresholds therefore remain
unchanged. Future population research needs an explicit versioned contract and new independent
evidence; raising the displayed coverage percentage alone is not success. Policy proof must not
silently be recycled into the fitting set it is supposed to validate.

## Implemented changes

- A pending checkpoint gets priority **within its evidence lane** during the final 15 seconds of
  its original 90-second grace window. The 3:1 Policy/Discovery share and rotation within urgency
  groups remain. No horizon is extended or reopened, and no additional request budget is granted.
  A follow-up edge-case review found that a shared Policy/Discovery token could lose Discovery's
  earlier deadline during deduplication. Its single Policy-lane fetch now retains the earliest
  eligible clock from either lane. An expired clock grants no priority or extra time.
- Initial live diagnostics exposed repeated selection of locally invalid RPC identities after
  restart. A bounded 128-entry identity cache prevents repeated impossible requests from consuming
  selection slots. Changed identities retry immediately; fresh cached checkpoints and transient
  provider/account-validation failures are unaffected. Enrollment and coverage denominators stay
  intact, including when an unqueryable checkpoint eventually expires.
- A diagnostics attempt that cannot acquire the event boundary within 50 ms remains due for the
  next five-second poll. It records a deferral without consuming source counters or incrementing
  lost records. Actual collector failures and long gaps remain explicit. Cancellation cannot
  leave the market lock owned by the recorder.
- Compact refresh diagnostics retain guard deferrals, requests, selected/accepted routes,
  checkpoint updates, rejected batches, invalid routes and errors. A response discarded because
  conditions changed reports `yielding`; a completed successful request clears the old error.
  These facts use the existing separate diagnostics store and its existing size limits.

Market, sell, maintenance and provider-health guards remain unchanged before and after RPC work.
Network requests remain outside the event lock. Account validation and checkpoint persistence
remain inside their existing boundary, and refreshed reserves never enter the live feature cache
or paper broker. The refresh interval and live batch size were not increased.

## Verification

- Regression tests reproduced missed last-chance scheduling and false diagnostic-loss reporting
  before the fixes.
- All 905 backend tests passed, with no failures, errors or skips. New coverage includes expired
  windows, lane fairness, repeated urgent failures, all refresh guards, mid-request context/lag
  changes, durable diagnostic readback, cancellation and genuine collector exceptions. Invalid
  identities free later RPC selection slots, repaired identities retry, the cache stays bounded,
  and RPC exclusions cannot suppress fresh cached checkpoints or remove enrolled observations.
  The shared-clock regression failed in four boundary cases before its fix. Ten additional
  cases cover shared-mint urgency/expiry boundaries in both collection paths and recovery after
  provider unavailability or missing accounts without incorrectly caching a valid identity.
- Ruff lint/format and strict mypy checks passed. Formatting validation used a temporary
  LF-normalized source copy to match Linux CI without editing unrelated Windows files.
- Worst-case six-artifact diagnostics and proof events still fit the existing record limits.
- A synthetic 1,000-pending-mint workload measured median scheduler CPU time of 11.56 ms before
  and 11.18 ms after the initial urgency change, with overlapping samples. This showed no
  material overhead in that test;
  it is not evidence of a general speedup.
- Syntax-tree comparison confirmed that checkpoint scheduling is the only changed learning
  function; the other 145 learning functions and nonlinear recipe are unchanged.
- The repository Docker build retained schema 15, the same dependency versions and identical
  frontend files. Only the intended diagnostics, orchestrator and learning backend files changed.

The guarded local update preserved the data mount, current season, configuration, participation
permission and Coach permissions. Sizing and Exit remained active after restart. Initial live
checks found healthy core workers and paper accounting, renewed Coach activity, and new durable
diagnostics records with no dropped records. Longer observation is required to measure any
improvement in checkpoint coverage; early health checks are not a months-long endurance test.

During first-stage observation, training published two new models without errors. A later burst
expired 1,313 low-priority candidate events, with a maximum measured critical-event lag of 14.3
seconds in the affected interval. The following intervals recovered, reaching a maximum critical
lag below one second with no additional expirations. This happened while local validation work
also ran; the records do not establish one cause. The burst remains a performance observation,
not evidence that overload is eliminated. The new counters show when collection yields to market
pressure, so future reviews can distinguish it from invalid routes or unavailable liquidity.

At the collection-update capture (13:16:33 UTC), about three minutes after that container restart:

- All seven core workers were healthy, with no current degraded status and verified paper accounting.
- Training had published two new models without errors or stale-job discards; the last fit took
  approximately 2.83 seconds. Sizing and Exit still supported Baseline.
- 27,585 market events had been processed, with no dropped, shed or expired candidates in this
  new boot. Latest processing lag was 0.059 seconds. Two saved diagnostic intervals covered
  18,713 events, with a 95th-percentile histogram upper bound of one second for both overall and
  critical-event lag. This short, different workload is not a controlled before/after comparison.
- Sixteen reserve-refresh requests accepted 76 routes and recorded 78 checkpoint updates, with
  no worker errors. Durable records contained the new deferral and invalid-identity cache facts.
- Diagnostics used approximately 11.8 MB of the existing 512 MiB allowance, with no dropped
  records, write errors or early evictions. Coach had made a new review attempt and was waiting
  for more outcomes, with no reported error.
- The latest fitted Entry model still had 49.0% model outcome coverage; the separate current
  executable-coverage measure was 54.9%. Both were below 70%, and the Linear top-group return
  gate also failed. Entry staying in shadow was the correct result.

The shared-clock follow-up passed 102 targeted tests and all 905 backend tests, plus lint,
formatting and strict type checks. Its image differed from the preceding local image only in
`intelligence/learning.py`; dependencies, frontend and schema remained identical. The maintenance
update again preserved the season, data mount and permissions. At 13:26:28 UTC, both existing
supporting Champions and all core workers were healthy, paper accounting was verified, and 30
checkpoint updates had completed after restart. There were no expired or shed candidates among
13,886 processed events. A real diagnostics lock deferral retried successfully and produced a
saved interval without incrementing lost records. Training was checking readiness without errors;
no new fit was due yet in that short boot. Entry remained unqualified, with 49.2% fitted-model
coverage and 54.8% separate current executable coverage.

No public image or GitHub release was published by this work.
