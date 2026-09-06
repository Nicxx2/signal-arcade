# v1.10.5 release review — 6 September 2026

## Latest release check — 08:01 UTC

The current live image is the [verified quote-recovery build](V1_10_5_QUOTE_RECOVERY.md),
`sha256:cba8f1bf633115331320ddefb3e13df570fb088c20ea8aa225565138f2058f05`.
Its container is healthy with zero automatic restarts; all 37 backend files and nine built
frontend assets match the repository. Version declarations agree on 1.10.5. The release-input
check inspected 254 Git-visible files and found no live credentials, local environment file,
database or runtime data. README and verification links resolve, and screenshot sets remain
separate from older captures.

The applicable validation results are **745 backend tests**, **321 frontend tests**, successful
lint/type/build checks, and the subsequent **185-case focused edge review**. Unchanged broad
suites were not rerun in this final check. Current live accounting balances with no orphan
fills; season 33 and its 400-USDC Balanced/custom-25%-drawdown settings remain intact.
At 08:01:31 UTC the engine had processed 101,775 events without drops or expiry since restart,
and four model fits had published without errors. Current Entry coverage was 631/1,000 (63.1%);
the required 70% and other qualification gates remain in force. This is evidence of ongoing
operation, not proof of improved returns or a guaranteed forthcoming Champion.

**Release decision:** no new code-packaging, quote-recovery or accounting fault was found.
The code and documentation are ready for review or a paper-testing push. A stable community
release remains pending the planned 3–6-hour observation after the latest runtime change,
including dashboard freshness, cleanup progress and a natural automatic rollover. Only about
13 minutes of this image's operation had elapsed at this check. Brief dashboard delays remain
documented; the three closing snapshot ages were 4.4, 7.4 and 10.5 seconds. Do not convert these
short healthy samples into a claim that all performance or long-term edge cases are resolved.

### Git and Docker exclusion follow-up

The final ignore-rule review found two packaging gaps: SQLite copies outside `data/` were not
ignored by Git, and Docker's unqualified patterns allowed nested environment files, bytecode,
caches and database copies into its build context. Git now excludes database files and sidecars
at any depth. Docker now uses recursive patterns for local environment, cache, dependency,
database and log files; `.env.example`, source, tests, CI and screenshots remain eligible for Git.

Verification used Git's actual ignore matcher and offline Docker scratch exports. All 13 Git
exclusion cases and 14 Git inclusion cases passed, with no already tracked private/runtime files.
All 27 Docker exclusion cases passed; before the correction, 15 nested cases were included.
The actual repository build context retained all 104 required files byte-for-byte, including
37 backend Python files and both program IDLs. No private or generated files were found in that
context, whose exported tar was 2,875,392 bytes. This changed packaging rules only; it did not
restart the live app or alter trading, learning or settings. Pattern semantics follow the
[Docker build-context documentation](https://docs.docker.com/build/concepts/context/#syntax).

## Earlier review — 06:44–06:49 UTC

Review window: 06:44–06:49 UTC. This records the check of image
`sha256:197672dc40e20457dd5a31e324ccd1036c9dbccfd476a338daa629363791c69c`,
started at 06:27:37 UTC. Earlier findings and corrections remain documented in
[overnight fixes](V1_10_5_OVERNIGHT_FIXES.md).

Subsequent mobile reports identified an Arena display issue. See the
[evidence continuity correction and its verification](V1_10_5_ARENA_CONTINUITY.md).
That follow-up also records later processing pressure; the earlier healthy sample below
must not be read as a guarantee of uninterrupted operation.

**Decision:** no additional runtime defect or required UI correction was found in this
check. Continue the planned paper-testing soak. A stable community release and claims of
long-term reliability remain pending sustained operation and a natural post-fix rollover.
This review did not change runtime code, settings, mode, seasons or deployment.

## Learning and execution

- Baseline is executing the paper portfolio. Ledger transactions balance, fills have matching
  orders, and the execution audit reports verified. Season 33 retains 400 USDC, Balanced,
  25% drawdown and automatic seasons. Challenger and Local AI remain Shadow.
- Four fits have published since this boot, without a training error or discarded stale job.
  The latest completed in 2.71 seconds. The reviewed Linear and XGBoost artifacts share the
  exact cohort digest, training cutoff, 351 training rows, 177 validation rows and four
  embargoed observations. The XGBoost comparison references its paired Linear error.
- That reviewed XGBoost artifact had validation error 0.4556 versus Linear's 0.4383. Its
  complexity gate correctly failed. Both families also lacked sufficient coverage and other
  value proof. Training successfully is not evidence that either currently improves trading.
- The saved 72,846-byte XGBoost JSON payload matched both stored and published digests,
  reloaded with 28 features and one execution thread, and returned finite values for two
  synthetic probe rows. Those probes verify loading/inference only, not forecast quality.
- Current Entry coverage at the closing snapshot was **589/1,000 (58.9%)**. The reviewed
  artifact's fitted-cohort coverage was separately 53.2%; these are different windows.
  The unchanged 70% gate remains unmet. Unknown outcomes still count against coverage.
- Manipulation is collecting independent proof. Sizing and Exit have saved Champions and
  active comparisons, with no active influence. Their shared usable counts advanced from
  116 to 117 and from 19 to 20 respectively during this review. Sizing's uncertainty interval
  still spans zero; reaching the 30-outcome minimum alone does not settle a comparison.
  Exit's equal measured values match the identical selected horizons, rather than a made-up win.
- Coach saved a valid screening review at 06:38:46. No experiment cleared its historical
  screening floor. It subsequently waited for new outcomes and deferred for open-position
  work, with no Coach error. The separate Local AI assessment system still fails reliability,
  latency and value requirements: its current cohort p95 was about 25 seconds against the
  2.5-second target. Its guarded influence remains unavailable.

The retained Baseline scorecard and reviewed model top groups still show negative returns.
The app has not demonstrated a profitable edge. Failed quality gates are expected protective
behavior; earning an Entry Champion is an activation requirement, not itself a software-release test.

## UI, packaging and dependency checks

- All 37 deployed Python files and all nine frontend files match the repository build.
- Authenticated, read-only browser checks covered 32 live views at 1440 and 390 px, including
  Arena, Decisions, Results, Learning subsections, Replay, Settings and all four Champion dialogs.
  No horizontal overflow, browser errors, failed requests or attempted app mutations occurred.
  All dialogs rendered in 3D and left zero Arena canvases after closing. Desktop Challenger,
  mobile Sizing and mobile Settings captures were also inspected visually.
- Current production advisory checks reported no known vulnerabilities for all 29 installed
  third-party Python distributions and five frontend production dependencies. No Python package
  was skipped. This covers those dependency advisories, not an audit of every OS package or device.
- README behavior and version information match the implementation. Git/Docker exclusions
  keep the local environment and data out of the release inputs.
- The existing validation baseline is 721 backend tests and 314 frontend tests, plus lint,
  typing and production build checks. The two subsequently added storage regressions passed
  within the eight-case storage run. Broad suites were not repeated unchanged during this
  live check, avoiding unnecessary load on the same host.

## Performance and remaining observation

The closing snapshot recorded 203,389 processed events since deployment, including 49,677
during this review. There were zero dropped events, logged errors, warnings, restarts or OOMs.
All seven monitored workers were healthy. Queue depth was zero and latest-event lag was
0.016 seconds; the five-minute p95 was in the two-second bucket.

Cleanup reclaimed 75,385 old raw trades since boot. Used SQLite pages were about 15.14 GB,
below the configured 16 GiB allowance. The oldest retained raw trade advanced to 3 September
14:31 UTC, but the roughly 64-hour backlog still exceeds the 24-hour retention target. The
short window does not establish that cleanup will keep pace over days or months.

The preceding edge check recorded a transient 6.10-second processing-lag maximum and later
recovery. Keep that performance watchpoint visible during the soak. The current season has
not reached a rollover condition, so the next natural automatic rollover remains unobserved
on this image. Its isolated transaction, restart, cancellation and backlog tests have passed.

Before a stable community release, review the planned 3–6-hour run and a natural rollover
for event freshness, continuing fits, accurate unknown outcomes, cleanup progress and accounting.
For a long-term reliability claim, the earlier review's 48–72-hour endurance recommendation
still applies. No short checklist can establish an absence of all defects or future profitability.
