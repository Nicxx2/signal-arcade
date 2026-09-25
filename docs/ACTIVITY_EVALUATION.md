# Trade-activity evidence and evaluation boundary

The 20 September 2026 local v1.10.11 follow-up reduces a dashboard query cost and records
additional descriptive evidence. It does not introduce a new entry filter, manipulation verdict,
recovery cooldown, sizing rule or exit policy. It was deployed locally through Settings preparation
on 20 September; [rollout checks](V1_10_11_VALIDATION.md#activity-evidence-live-rollout--20-september-2026)
and prospective trading evaluation remain separate.

## What the reviewed examples establish

Two manually selected holdings motivated the review. One contained many tiny trades alongside
larger trades accounting for almost all quote volume. The other had an earlier suspicious window,
a failed attempt when evidence was immature, then a later usable entry window. Its buy-count
share exceeded its buy-volume share. These distinctions justify clearer evidence, not a universal
"dust means reject" or "many buys means hold" rule. Both inspected positions eventually respected
their absolute holding ceiling. Small positive after-fee results in two selected trades neither
prove the strategy is good nor show that earlier exits would improve it.

The first eligible Policy episode must remain first even if its order fails and a later attempt
fills. Retrospective investigation must not replace missing, negative or failed evidence with the
successful attempt. An earlier rejected Discovery snapshot and a later actual fill are different
cohorts. Entry-time raw trades were not fully retained for both examples, so later windows cannot
be substituted for the entry window or treated as a complete replay.

## New measurements

All measurements use the existing bounded, venue-local window and its at-most-one-second cache.
They are calculated lazily for full decision snapshots, using the cached window's own timestamp.
Compact dashboard cards and held-position marks skip the calculation and additional value objects.
Held/pending market updates, pending-order heartbeats, resume checks and conversion-price lookups
also omit this optional breakdown while preserving their existing trading and exit evidence.
There are no new provider requests or separate per-token histories. Saved decision details retain
the measurements; existing decision retention still applies. Compact dashboard responses and
diagnostic proof events do not gain full trade histories. Added JSON fields and the action/time
index have a storage/write cost; live retention and disk headroom must be checked after deployment.

| Measurement | Meaning and limit |
| --- | --- |
| Buy share of volume | Positive buy quote amount divided by positive gross quote amount. Count share remains separately labelled. |
| Signed net flow | (Buy minus sell quote amount) / gross. Negative means more observed sell value. The old absolute-flow feature is unchanged. |
| Trades ≥ 0.01 SOL | Individual trades meeting the existing descriptive amount cutoff, for 60/300-second inclusive windows. It is not a new gate. |
| Wallets with a trade ≥ 0.01 SOL | Distinct known wallets with at least one individually qualifying trade; accumulated dust does not qualify. |
| Wallets net buying ≥ 0.01 SOL | Known wallets whose observed buy-minus-sell quote amount meets that cutoff. Several small buys can qualify; offsetting loops do not. This is not a holdings/ownership calculation. |
| Amount coverage | Positive-amount trades / all observed trades. Zero/negative amounts remain unavailable amounts, not zero-value observations. |

New quantitative fields require complete observed amounts; wallet counts require complete wallet
identities too. Empty windows are unknown. Unsupported quote mints do not use SOL thresholds.
Even 100% amount coverage describes only observed trades: stream gaps, saturation, stale evidence,
missing earlier activity and shared wallet ownership remain separate limitations.

## Before any strategy experiment

1. Verify the deployed build and fresh timestamps. Compare token/decision/learning section timings,
   snapshot duration/CPU, market lock waits, lag, expiry, checkpoint completion, publication and
   recording gaps across comparable natural traffic. The indexed query is bounded in isolated
   tests; this does not establish that whole-app burst pressure is solved.
2. Freeze an evaluation specification before examining future outcomes. Candidate hypotheses are
   value-flow corroboration for count-heavy activity and sustained deterioration for hold reviews.
   Thresholds, observation intervals, cohort membership and stopping criteria need to be fixed in
   that specification. Do not tune them on the two motivating coins.
3. Use decision-time evidence with known completeness and a chronological, embargoed split.
   Keep independent Policy proof separate from Discovery proposals. Include negative outcomes,
   valid quote failures, unavailable liquidity and missed winners. Compare matched risk mode,
   season profile, currency, fees and policy versions; report sample sizes and uncertainty.
4. A checkpoint comparison can screen an entry hypothesis but cannot replay all path-dependent
   adaptive exits. An exit experiment needs fresh review-time evidence, executable routes and
   fee-aware outcomes. Existing retained snapshots may be insufficient; say so rather than
   inventing intermediate prices or trades. Compare after-fee return, drawdown and opportunity
   cost, not only selected winners or a short profitable period.
5. Promote a change into policy only if independent evidence supports it. Give changed Baseline,
   feature or exit semantics explicit versions and fresh proof. Preserve prior-policy dispatch for
   held positions and existing seasons. No retrofit of saved candidates or inherited Champions.

Required counterexamples include all-dust traffic, legitimate small traders, a whale mixed with
dust, large sells hidden by many small buys, repeated same-wallet round trips, split orders,
wallets with unknown ownership, missing amounts, future/out-of-order timestamps, migration,
reconnect/restart, buffer truncation, unavailable exit routes and genuinely slow winners.
A recent suspicious window is not proof of permanent manipulation; a reconnect or expiry of
that window is not proof of recovery. A repeated cached sample must not count as multiple
warnings. A cooldown or faster exit remains a hypothesis until those cases and prospective
outcomes support it.

The selected coverage floor, sample minima, valid failures, chronological separation, held-position
and Policy priority, Champion permissions and hard exits remain unchanged. This patch offers
better evidence for the next decision, not a promise of Champions or profit.

## Durable enrollment evidence

The follow-up deployed locally through Settings preparation on 20 September adds
`learning_activity_discovery` and `learning_activity_policy`, keyed to their respective learning
parents. Each optional record is inserted only with the parent's initial transaction. Existing
parents are never backfilled, and checkpoint updates do not write the companion. The original
Discovery decision and a later first actionable Policy decision remain separate. Failed orders
and later successful retries cannot replace that first Policy evidence.

`activity-evidence-v1` preserves original parent/decision/mint identity, decision time, venue and
quote, Baseline/feature/configuration/season/profile context, the seven descriptive metrics,
continuity and coverage fields, and the original integrity receipt and allowlisted raw operands.
It does not preserve wallet identities or complete raw trade histories. The cutoff is 10,000,000
lamports and the windows are inclusive 60/300 seconds. Metric cells contain
`[value, quality, clock_index, missing_reason]`; `clocks` stores distinct original timestamps.
Freshness is the decision timestamp minus that measurement's clock. Repeated cached measurements
are not independent observations. Values are not rounded or reconstructed from model features.

Records have a hard 4 KiB UTF-8 cap. Missing fields remain explicit unknowns; invalid, contradictory
or oversized captures become unavailable summaries. `complete` means all projected values and an
original integrity assessment were recorded without missing reasons, not that the market was
legitimate or every quality or continuity requirement passed. Serious SQLite failures and
cancellation still propagate;
recoverable optional-statement failures preserve the parent only when its transaction is intact.
Diagnostics report cumulative attempts, committed complete/partial/unavailable records, existing
parent skips and failures at the existing collection cadence. Counters reset at process boot and
do not count retained records. A committed unavailable summary is not usable feature evidence.

The companion's primary key is an indexed foreign key with deletion cascading. Pending parent
retention and existing completed-parent limits remain unchanged. Season rotation of decisions
does not remove learning companions. Physical database capacity accounting includes these pages;
bounded storage inventory also names the two tables. No startup history scan or new maintenance
worker is added. The schema-16 addition leaves parent JSON and frozen training inputs unchanged.
Compatibility was tested against the preceding activity build's actual reader on disposable data,
including 55% coverage, Champion state, parent updates/deletes and reopening with the new reader.
This is not a compatibility claim for v1.10.10 or a full backup restore rehearsal.

## Offline prospective screen

The local tool runs only when invoked. It can extract a compact study dataset from a
read-only SQLite source, then evaluate that private dataset without the running service:

```console
python -m signal_arcade.intelligence.activity_research SOURCE.sqlite SPEC.json --export PRIVATE.json
python -m signal_arcade.intelligence.activity_research PRIVATE.json SPEC.json --from-bundle
```

It opens SQLite read-only/query-only and never constructs a live learner, migrates a database,
fits a model, changes a setting or grants authority. For live-source extraction, use a separate
resource-limited process/container with the source volume mounted read-only; an active WAL database
must retain its companion files. Do not copy just its main SQLite file or use `immutable=1` on a
changing source. A consistent disposable copy remains supported. A whole-database backup is not
needed for this research read, and the compact dataset is not a backup or restore mechanism.

The reader uses the existing Policy/time index to scope metadata to the declared period before
loading parent JSON by primary key. It takes one SQLite read transaction for parents, companions,
identity receipts and the pruning watermark, then closes it before evaluating or exporting.
Broad ISO calendar bounds and a padded SQLite date filter avoid relying on textual timezone
order or millisecond rounding; aware Python timestamps decide exact inclusive-start/exclusive-end
membership and the native selector resolves ties. Unsupported or contradictory in-scope clocks
abort the read. This contract assumes the app's original ISO timestamps: it does not search for
arbitrary corrupt timestamps outside the indexed envelope or recover manual deletions.
SQL boundary parameters are normalized to UTC because Python accepts some timezone offsets
outside SQLite's parser range; those offsets must not silently remove otherwise valid records.

Reads are capped at 5,000 candidate metadata rows (including the small boundary padding),
64 MiB of parent JSON, 8 MiB per SQLite value and a cooperative five-second query/read budget.
The metadata counter is not a count of every index entry visited. Busy/locked/interrupted reads
and exceeded budgets fail without a partial report. Old terminal and pending history outside the
period cannot consume the parent-row budget merely because it is retained. Exported bundles have
a 96 MiB cap, require space for their actual bytes plus a 16 MiB reserve, and are published
atomically to a new path without overwriting another file. Unsupported atomic publication fails
closed. Partial files, mismatched specifications and altered payload digests are rejected on
import. The digest detects changes, not authenticity: keep trusted capture provenance separately.
An oversized optional companion is represented as invalid evidence, not copied beyond its cap.
The source parents and original identity reservations are retained exactly.

The current independent Policy selector still
caps selected opportunities at 1,000. If that cap could remove opportunities inside the declared
study period, the screen is inconclusive even if numeric returns look favorable. A cap that only
removes pre-study history cannot change study membership. Persistent identity receipts prevent
an old first opportunity from being replaced by a later retry without loading old parent JSON.
Missing/malformed receipts or an absent original parent inside the study make it inconclusive.
Exact venue/fee/profile filters are applied after native selection, so they cannot bypass its cap.
The pruning watermark is checked conservatively, including a two-day offset-ordering allowance
because the source watermark is lexical. An absent watermark means no recorded pruning, not a
certified population; invalid or possibly overlapping pruning evidence prevents a positive screen.
Retention may already have removed opportunities; the tool cannot reconstruct them or certify a
complete historical population. Use a sufficiently short prospectively specified period. It does not evaluate
Discovery or tokens that the existing learner did not admit.

Before collecting the evaluation cohort, freeze and retain the specification and its digest.
Required fields are `frozen_at`, `start`, `end`, `outcome_cutoff`, `risk_mode`,
`configuration_fingerprint`, `baseline_version`, `season_profile_fingerprint`, `fee_bps`,
`network_fee_lamports`, `venue`, `quote_mint`, and `selected_coverage_percent`. Times must be
timezone-aware and ordered; the outcome cutoff must be at least 900 seconds after enrollment
ends. Context fields must match the original Policy records, including nulls. The fixed recipe is
`count-value-participation-screen-v1`. Declaring an early `frozen_at` is not independent proof that
the specification was actually frozen; retain the original dated specification before outcomes
exist. Invoking the tool does not itself start or schedule a study. Store specifications, capture
manifests and datasets in a private ignored directory, never in a community release. Freeze one
future period after extraction and report validation; do not relabel a pilot as prospective.

The single screening hypothesis proposes avoiding an entry only when buy-count share is at least
70%, buy-value share is at most 45%, there are at most three meaningful trades in the last minute
and at most two net-buying wallets in five minutes. It requires fresh complete amounts, wallet
and signature coverage, an uninterrupted window, no buffer saturation, at least 24 trades and
30 seconds of age. These research thresholds are not demonstrated optima or production guards.
Unknown evidence retains the unchanged Baseline action in the research comparison. Buy-value
share and signed flow are one algebraic signal, not independent confirmations. This pattern
describes weak demand; it does not label manipulation or infer common wallet ownership.

The report excludes post-period and future-dated entries before reusing the current independent
Policy selector, keeping earlier identities so an old first opportunity cannot be replaced by a
later retry. It then applies the declared start and exact fee/profile/venue context. Later traffic
cannot displace a fixed study through the rolling selection cap. It reports feature availability
separately from recorded companion status and outcome coverage. A complete but stale capture
remains an unknown input. First failing input reasons, pending/unknown/failed-quote outcomes,
changed decisions, positive trades missed
and losses avoided. A profitable rejected example is an economic cost, even if its activity looks
suspicious. The input digest binds the specification, selected parent records, exact companions
and original identity reservations. It does not retrofit native artifact digests.

Companions must match the Policy parent's original entry time and route as well as its identity.
Malformed numeric or oversized optional records remain unknown; their parents stay in the
opportunity denominator. Oversized parent records abort the bounded read without a partial report.
Only a checkpoint explicitly identified as 300 seconds, with a numeric outcome observed from
300 through 390 seconds after entry, contributes usable five-minute returns. Unknown outcomes
recorded after that grace period remain missing; a failed quote is not converted to a numeric loss.

Default research minima are 200 independent opportunities and 30 changed decisions with usable
outcomes, at least 90% feature availability and the specified native coverage floor. They cannot
be reduced through this tool. Its economic screen requires a positive lower bound of a labelled
normal-approximation paired interval and winner-veto fraction at most 35%. This is an initial
screen, not sufficient proof: available outcomes can be biased, market observations correlated,
and removed history unknown. No independent manipulation labels are supplied, so the report
cannot claim detection accuracy. Fixed 300-second after-fee returns cannot reproduce actual
fills, adaptive exits, capital constraints, portfolio drawdown or realized profitability.

`activation_allowed` is always false. A positive screen still requires independent integrity
review, acceptable false alerts and opportunity cost, prospective robustness, and the existing
chronological/native proof and permission checks. Inconclusive results mean no buying change.
Any later change needs deliberate input normalization, versioned policy/model contracts and
pending-fill revalidation. Existing Champions and held positions do not inherit new rules.

### Prospective feasibility decision

For the first six-hour enrollment period, allow at least another 15 minutes for final outcomes.
Keep the recipe, exact context and minima fixed. Evaluate once after maturity; insufficient
opportunities, too few changed usable outcomes, poor availability, retention uncertainty or
zero matches are inconclusive. Six hours is a collection window, not a guarantee of enough
evidence. If the pattern remains rare, report that result instead of extending the window until
it passes or loosening thresholds after viewing outcomes. A revised hypothesis needs a separate
future specification and independent review. Stage 4 is the evidence review; Stage 5 buying or
model activation remains conditional on the additional proof described above. This entry study
does not answer whether later holding deterioration calls for an earlier exit.

### First prospective study result

The first frozen study enrolled from **15:45 through 21:45 UTC on 20 September 2026**, with
an outcome cutoff at **22:00 UTC**. The completed Stage 4 review is **inconclusive**; conditional
Stage 5 buying-rule activation remains off. Of 348 read Policy parents, 273 met the exact context
and independent-opportunity rules, 74 belonged to other contexts and one was ineligible.

- 261 of 273 had usable five-minute outcomes (95.6%); 12 had valid quote failures.
- 205 of 273 had fresh usable inputs (75.1%), below the frozen 90% minimum; 68 were stale.
- No opportunity matched all four pattern conditions, leaving zero changed usable outcomes
  against the fixed minimum of 30. This cannot establish either benefit or harm from the rule.
- All 273 had a companion record; one was partial. Availability of a record does not establish
  fresh inputs. No reported identity/retention overlap or selection cap affected this read.

The bounded read stayed within its five-second, 5,000-parent and 64 MiB limits. The frozen
evaluator completed and a separate scalar cross-check agreed with the aggregate counts; a later
full replay in a constrained container failed allocation, so successful full replay is not claimed.
The original specification, archived sources and private evidence were preserved.

Saved diagnostics across the outcome window contained 52 recording gaps, up to 208.56 seconds,
and observed candidate loss. Gap intervals do not provide healthy observations, and their boundary
counts cannot be equated to unique missing study outcomes. Policy outcomes can remain available
while original input freshness fails. More enrollment alone does not resolve a pattern with no
matches. A different pattern, freshness limit or recovery rule requires a separate future
specification; this completed window must not be tuned or extended into a pass.

### Separate support-fallback investigation

The entry receipt follow-up adds explanations and original-opportunity links, not a second buying
rule. It was deployed locally through Settings preparation on 21 September. The completed six-hour
study retains its original archived reader/native contract and unchanged specification; source work done later
must not silently replace the frozen evaluator. Its fixed window and minima remain binding.

A later study of **prior applied veto → unsupported later attempt → Baseline entry** needs its own
future specification and exact model/context provenance. First establish frequencies and support
failure causes, then define any recovery requirement before collecting its evaluation cohort.
Do not choose a recovery interval or feature threshold from a few losing examples. Distinguish a
feature outlier from a missing verified model, upstream blocker, original integrity warning,
modeled return and actual fill. Group repeated attempts by the persistent original opportunity;
they are not independent proof. Missing original records or clocks remain limitations.

Required edge cases before considering an entry-policy change include legitimate busy launches,
small independent buyers, a large buy among dust trades, repeated sizes, round trips and genuine
recovery. Trade counts, value and net buying describe observed activity; multiple addresses do not
establish independent ownership. Cached repeats do not count as new recovery evidence. Missing,
stale, interrupted or saturated inputs cannot establish recovery, and an old warning cannot become
an indefinite cross-model ban. Preserve positive after-fee outcomes as positive economic outcomes,
even when activity is suspicious; review integrity separately. Measure missed profitable entries
as well as avoided losses. Quote-only 300-second returns do not establish portfolio benefit.

Any eventual production rule needs a versioned policy/input contract, fresh independent native
proof where applicable, unchanged permission checks and equivalent pending-fill revalidation.
Preserve old orders, held-position exits and Policy priority. Verify restart, model replacement,
season/configuration changes, bounded burst costs and compatibility on disposable data before a
Settings rollout. Neither this instrumentation nor a positive preliminary screen permits automatic
activation. Stage 4 remains an evidence decision; Stage 5 remains conditional.
