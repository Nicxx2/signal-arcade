# v1.10.5 live and code review — 5 September 2026

This is an additional review of the running v1.10.5 build after the Arena startup and Entry
proof improvements. It supplements the earlier community review; it does not replace an
endurance run or establish profitable trading performance.

## Finding and correction

The header could display **All good** while Settings reported degraded market processing.
Successful HTTP responses established server/ledger liveness but did not incorporate the
engine's separate market-processing warning.

The header now reads that warning from existing fresh snapshots and fallback health responses.
Known reasons have plain-language descriptions; missing or unfamiliar reason lists still show
a useful warning. Successful HTTP responses, absent status and stale healthy snapshots cannot
clear a known market warning. Fresh explicit recovery clears it and retains the browser history.
Historical drop totals alone do not keep a recovered system in warning.

This correction adds no polling, dependencies, provider requests or backend changes. Trading,
training, qualification, activation, season automation and storage behaviour remain unchanged.

## Checks completed before deployment

- 307 frontend tests passed, including regressions that failed against the previous status
  behaviour. TypeScript, ESLint and the production build passed. The existing large lazy-loaded
  Three.js chunk warning remains; this change does not add scene code or increase its size.
- 63 targeted backend tests passed in a network-disabled, resource-limited container with
  isolated temporary data. Coverage includes season deadlines, evidence and reserve validation,
  learning publication, Entry proof attribution, snapshot recovery and release safeguards.
  The first test invocation used the image's public bind default and was rejected by the test
  configuration guard; rerunning with the required loopback bind passed. No live data was mounted.
- Live browser checks covered 44 main/Learning/Arena views, nine detail views and six settled
  phone views at 320/390 pixels. No browser errors or mutations were observed. Arena canvases
  were released on close. Immediate resize measurements briefly overflowed; fresh and settled
  phone layouts fit correctly.
- The new production UI passed 18 additional desktop/phone status views: healthy, degraded,
  missing status, stale status, recovered and health fallback. Warning and recovery were checked
  at 1440, 390 and 320 pixels with read-only fixture responses. No browser errors, horizontal
  overflow or app mutations occurred; warning/history screenshots were visually reviewed.
- Read-only accounting checks found zero ledger imbalances and zero orphan fill references.
  Schema 14 and season 31 remained in place: 400 USDC, Balanced, custom 25% drawdown, Shadow
  learning and the enabled one-hour automatic-season rule. The rule was monitoring normally;
  there was no sustained drawdown pause requiring a rollover during this review.
- Code review covered bounded storage cleanup and contention, snapshot cancellation/recovery,
  automatic-season drain/deadline handling, frozen training/publication context, route identity
  validation, Entry family selection and bounded replay data/lifecycles. No additional concrete
  correctness defect was established in those reviewed paths. This is not an exhaustive proof.

## Performance observations

During 36 samples over 382 seconds, overlapping browser and offline test activity, the live
queue reached 4,958/10,000 and latest-event processing lag reached 19.50 seconds. Another
3,222 stale candidate events expired; the queue subsequently recovered. The oldest sampled
dashboard snapshot was 22.27 seconds. No evidence establishes that test load was the sole cause.

A separate quieter window, with those tests and browser checks stopped, sampled 234 seconds.
It processed 33,438 events with **zero new drops**. The queue peaked at 1,016/10,000, latest-event
lag at 5.06 seconds and protected-event lag at 4.10 seconds. Degradation cleared. These delays
are relevant to freshness even when the process is healthy; they should not be described as
zero performance impact.

Learning continued publishing models (the published counter reached five), with no reported
training error. Reserve refresh had recovered 181 checkpoints by the end of the mixed window.
Unsupported/identity-unavailable routes remained unknown. Current proof failures remain
qualification failures; no thresholds were lowered or model superiority inferred from activity.

Used SQLite pages grew by 14,950,400 bytes between the quiet window's snapshot samples, to
11,855,613,952 bytes, below the configured 16 GiB budget. Cleanup yielded for market throughput
and had completed earlier passes. This short window does **not** establish that reclamation
keeps pace with incoming data or that the inherited database can run indefinitely within budget.

## Release disposition

Suitable for the next monitored 3–6-hour observation period after deployment verification.
Keep community release conditional on the longer endurance checks already documented in
`V1_10_5_COMMUNITY_REVIEW.md`: sustained event freshness, storage growth and reclamation,
training/publication progress, provider backoff and automatic-season recovery. Real-device/GPU
coverage and current dependency advisories remain separate checks.

## Deployment verification

Applied through maintenance operation `7c5718d3ccfb44fbbce1e9a759795098` to image
`sha256:8fa5ded4bd78d02431cec67b7a298ff6a3c2f592e6cd43b1f3269b406931e4e2`.
The existing data mount was preserved. Rollback image:
`signal-arcade:v1.10.5-before-market-status`.

All 33 packaged backend files remained byte-identical, and all nine served frontend files
matched the tested build. All six workers were healthy after startup with no container restart.
Accounting, season settings, Shadow mode and schema checks passed again. Twelve live Arena
skill views across desktop and both phone widths passed: neutral loading followed by 3D,
one canvas through skill changes, explicit preferences preserved and canvas released on close.
No browser errors or app mutations occurred in those live UI checks.

The final post-browser sample processed 3,101 events over 30 seconds with zero new drops,
queue depth at most 19 and no degraded status. Snapshot ages were 1.63–3.78 seconds. The
new container's available logs contained no tracebacks, ERROR/CRITICAL records or HTTP 5xx.
The provider was connected without reconnects; training had published another model without
an error and reserve refresh had updated another 19 checkpoints since restart. Both latest
Entry families still reported `proof_not_met`, correctly leaving activation unavailable.
Maintenance completed and automatic-season monitoring resumed. These are short post-upgrade
checks; the earlier latency and storage observations remain relevant to the endurance decision.
