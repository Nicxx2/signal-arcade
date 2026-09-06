# PumpSwap quote recovery — 6 September 2026

## Cause and scope

STONK, HOOD and BABYZCAT were shown as fresh but exit-blocked with
`unsupported_quote_mint_v1`. A read-only six-account RPC batch verified that each exact
PumpSwap Pool account and its quote vault used wrapped SOL, while the app retained the
curve's native-SOL marker. Their pool ownership, base mints and quote-vault mappings matched.

The full reserve validator verified the Pool and vault correctly but copied the old quote
from the input state. The watchdog then committed `route_verified = true` without correcting
that quote. Once verified, the log guard correctly prevented subsequent logs from replacing
the pinned identity, leaving these inconsistent states blocked. An isolated fixture against
the deployed image reproduced the same false unsupported-quote flag.

## Correction

- Copy the decoded Pool's quote into the separate validated reserve state, after the existing
  pool, PDA, ownership, vault, mint, sell-permission and reserve checks pass.
- Commit that account-verified quote atomically with watchdog reserves, fees and proof.
  Existing inconsistent states recover on a fresh valid account response, including after restart.
- Preserve rejection of unsupported on-chain quotes, invalid vaults and stale/reordered responses.
  Empty pools can establish non-executability, but cannot produce an executable mark or sell.
- Keep the existing event-log guard and revalidation requirement when the pool changes.
  The normal exit policy resumes once the route is executable; no sale is backdated.

No additional RPC requests, polling loops, schema migration, risk changes or model changes are
introduced. Learning-only refresh still returns a separate state. Existing fills, checkpoints,
unknown outcomes, Champion proof and season results are not rewritten. Subsequent evidence uses
the corrected verified identity; coverage and profitability requirements remain unchanged.

## Verification

- 22 new regression cases cover native-marker recovery with both verification states, account
  and vault failures, disabled sells, stale slots/timestamps, pool changes, duplicate snapshots,
  log pinning, restart, persistence, stopped-engine behavior and resumed exit scheduling.
- The complete backend suite passes: **745 tests**, no failures, errors or skips.
- Backend/test lint, formatting and type checking pass (all 37 backend source files).
  The only full-suite warning is an existing dependency deprecation in
  Starlette's test client.

## Live recovery

The maintenance API reached its safe upgrade boundary before replacement. The new image started
at **07:48:14 UTC on 6 September 2026**. Its 37 backend source hashes match the working repository;
only `intelligence/features.py` and `intelligence/reserve_refresh.py` changed from the prior image.
All nine frontend assets and the runtime environment were unchanged. The same data volume and
season 33 were retained: 400 USDC, Balanced, custom 25% drawdown, automatic seasons enabled,
paper engine running and Challenger in Shadow mode. The previous image is retained for rollback.

| Affected holding | Normal paper exit, UTC | Configured execution latency observed |
| --- | --- | --- |
| STONK | 07:48:16.483 | 1,255 ms |
| HOOD | 07:48:17.758 | 2,197 ms |
| BABYZCAT | 07:48:18.072 | 1,940 ms |

All three receipts use fresh PumpSwap event reserves with the verified wrapped-SOL quote and
the existing `absolute_time_exit` rule. Their exit assessments and fills occurred after restart;
no exit was backdated. All 30 pre-deployment receipts in the captured dashboard remain unchanged.
The three dormant holdings remain non-executable, with no fabricated sales; the remaining BEAST
holding's old quote marker also recovered without pretending that an uneconomic exit could fill.

At the 07:51:35 UTC check, all seven workers were healthy, accounting was verified, and no
route-blocked positions remained. There were **21,978 processed events**, no dropped or expired
events, **two successful model publications**, 48 accepted learning reserve routes and 49
checkpoint updates since restart. No training error was reported. Read-only database checks
found no unbalanced ledger transactions or orphan fills. These are short post-deployment
observations, not a long-run performance result.

Follow-up reads through 07:55:11 UTC reached 48,322 processed events with no dropped or expired
events. No errors were found in the bounded recent container-log check. Dashboard freshness is
still a watchpoint: the first request after an idle viewing interval could return the timestamped
cached view while refresh completed, and repeated polling included 15.2–16.3-second-old views
during cleanup. A strict under-15-second check did not pass every sample. Fresh views did arrive
(including a 3.1-second-old view), so this did not establish a stuck refresh, but it also does not
establish consistently fresh presentation. The existing Arena keeps the evidence timestamp and
pauses live exchanges when delayed. This scoped quote correction does not change dashboard
scheduling; include presentation freshness and cleanup pressure in the soak review.

Headless Chrome checks at 1440-pixel desktop and 390-pixel mobile widths found no page errors,
failed requests or horizontal overflow, and made no state-changing requests. The README's Arena,
mobile Arena and receipts images now use a separate
[post-recovery capture folder](screenshots/v1.10.5-quote-recovery-2026-09-06/README.md).

The deployment image is `signal-arcade:v1.10.5-quote-recovery`, with digest
`sha256:cba8f1bf633115331320ddefb3e13df570fb088c20ea8aa225565138f2058f05`.

The separate
[runtime review](V1_10_5_FINAL_RELEASE_REVIEW.md) and
[processing-pressure follow-up](V1_10_5_ARENA_CONTINUITY.md) still require the planned soak and
natural rollover observation before making long-term reliability claims.

## Follow-up edge-case review

A second review on 6 September reran **185 focused tests**, with no failures, errors or skips,
covering quote recovery, account rejection, empty-pool revival, stale and changed routes,
bounded season handover, Mayhem fees and dashboard cancellation/retry behavior. The executed
test modules match the repository, and all 37 deployed backend source hashes remain unchanged.
No additional production-code change or restart was needed for this recheck.

Live reads confirmed balanced accounting, no orphan fills and the same season/settings. The
watch from 07:57:20 through 07:58:10 UTC observed 7,802 additional processed events and ten
additional learning checkpoint updates, with every worker healthy and no dropped or expired
events. A native-SOL quote on an active bonding-curve position remained valid; the correction
is specific to the account-verified PumpSwap route.

Dashboard generation timestamps advanced four times during that watch. The first two requests
returned the old idle-view cache (69.9 and 75.8 seconds old); the next view was 4.2 seconds old.
Later polling included 15.1- and 16.9-second views before fresh generations arrived. The final
view was 10.1 seconds old. This confirms recovery during the observed window, not consistently
sub-15-second freshness. Keep this existing presentation-delay watchpoint in the soak review;
it is not grounds to weaken trading or learning freshness requirements.
