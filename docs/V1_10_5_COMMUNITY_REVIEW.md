# v1.10.5 community-readiness review — 2026-09-05

This review extends [the live-fix checks](V1_10_5_LIVE_FIXES.md). Passing local tests does not
establish a trading edge, sustained coverage, all-device support or unattended endurance.

Later review: [release polish and market-status verification](V1_10_5_RELEASE_POLISH.md).
The image identifiers and samples below describe this earlier review, not the latest deployment.

## Additional fixes

- UTF-8 Basic-auth credentials previously raised a server error in Python's string comparison.
  Authentication now compares UTF-8 bytes in constant time and advertises UTF-8 in the challenge.
  Correct passwords work; incorrect passwords reject cleanly for HTTP and WebSockets.
- Decoded XGBoost objects were cached indefinitely as different contenders were evaluated. The
  runtime cache now keeps eight recently used entries, including failed-load entries, and removes
  archived versions. Saved models, evidence, qualifications and training recipes are unchanged.
  Evicted models reload through the existing payload-validation path if needed again.
- Portable XGBoost JSON does not preserve the runtime thread setting. A reload regression found
  `nthread=0` instead of the intended `1`. Loading now reapplies that budget, and both training
  and prediction DMatrix construction explicitly use one thread. This is an execution-resource
  correction, not a model recipe, qualification or trading-rule change.

All four new regression cases failed before their respective corrections and passed afterward. They also cover cache
recency, object reclamation, reloading, negative-cache bounds and pruning. The final full backend
suite passed 477 tests; the frontend passed 206 tests across 12 files. The existing Starlette/AnyIO
deprecation warning remains. Focused security, nonlinear learning, training-publication faults and
frozen-input parity tests passed as well. After the final thread-budget correction, all 79
directly affected learning/cache/API regression cases passed again.

Initial review image: `sha256:56cef597ecab013c638c47365774d654421d7a073d110ca36ef193371548def8`.
All 32 packaged Python source files match the workspace. Runtime dependencies and frontend asset
hashes match the preceding image. Disposable-data health, schema 14, API and static/lazy asset
checks passed without network access or the live data volume.

## Live observations and limits

The first 36 samples spanned approximately six minutes and overlapped builds/tests on the same
host. They processed 35,942 additional events. The queue peaked at 2,322/10,000; sampled latest-event
lag peaked at 9.32 s and protected-event lag at 5.28 s. The app expired 683 stale candidate events
and reported degraded status accordingly. These results cannot establish unloaded performance.

All workers remained live. Training published a model and the reserve worker recorded 68 checkpoint
updates since that restart. Invalid route identities, unsupported Mayhem state and changed contexts
remained unknown/rejected. Entry coverage was 34.0%, below the unchanged 70% requirement; learning
remained Shadow. A new model or saved Champion is not proof of improved forward performance.

Used SQLite pages grew from 10,715,525,120 to 10,753,847,296 bytes during the sampled window. The
database remained below the configured 16 GiB budget and cleanup completed small passes. However,
reclamation keeping up with new writes has not been established. The large inherited backlog,
protected evidence and filesystem capacity must be assessed over a longer run; the storage budget
is not permission to delete accounting records or learning proof.

The UI check covered 44 main/learning/Arena views, nine fully loaded detail views and six
settled phone views. No browser errors or app mutations occurred. Every 3D view released its
canvas on close. Immediate resize measurements briefly exceeded the viewport, but fresh
phone loads and settled 320/390-pixel checks fit correctly. Results data loaded in all three
sort orders; the initial desktop screenshot captured its honest loading state.

Ruff lint and strict type checks passed. The formatter accepted all 61 Python files after
normalizing line endings to match Git checkout on Linux CI. Mixed Windows line endings
were the only differences reported by the direct local formatter check.

Fresh external dependency-advisory checks were not completed in this review. The installed
dependency graph is unchanged, but that does not prove the advisory database is unchanged.

## Normal-load follow-up

With builds and full test suites stopped, 36 samples over 361 seconds processed another
44,290 events with zero drops. The queue peaked at 909/10,000; latest-event lag peaked at
6.97 seconds and protected-event lag at 2.88 seconds. Brief spikes therefore persist during
ordinary use; the earlier shedding cannot be attributed solely to the app or solely to build
contention. The UI navigation checks and brief formatting checks overlapped this window.

The worker recovered 37 checkpoints since this restart. Coverage was 34.7%, with 201 of the
250 eligible rows needed for a live XGBoost fit; no nonlinear artifact was yet present. Used
SQLite pages increased by 11,595,776 bytes during the sampled window. Its first scheduled
cleanup was deferred for market throughput; this window does not prove cleanup catches up.

## Release decision

Do not describe this as a proven profitable learner or as having no remaining issues. A stable
community release still needs a 48–72-hour endurance run and evidence that cleanup keeps pace
with new writes,
including storage growth, event freshness, provider backoff, training progress and automatic-season
recovery. Real phones/GPUs and current dependency advisories remain separate checks.

Final verified image, including the reload thread-limit correction:
`sha256:795f85cc4765836338b0be212605b31aa7c033b9bf96e01ca048c4be40ee4fb9`.
All 32 packaged source files match; dependencies and frontend assets remain unchanged. The final
isolated smoke, lint, type and CI-normalized formatting checks passed. The version and schema
remain 1.10.5 and 14. The earlier verified images and data backup remain available for rollback.

The final image was applied through the upgrade API. The retained database took longer than
the helper's 45-second startup wait, then started successfully; a separate final API check
confirmed healthy workers, a completed upgrade operation, no restart/OOM, balanced ledger
transactions and no orphan fill/order references. Season 31, 400 USDC Balanced with custom
25% drawdown, Shadow modes and the staged reserve refresh settings remained preserved.
No season reset, schema migration or data restore occurred.
