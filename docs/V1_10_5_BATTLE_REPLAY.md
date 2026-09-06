# Recorded battle playback — v1.10.5

This extension adds prospective recording of actual tournament comparison checkpoints. It does
not recover a battle's unrecorded past. Older events retain their final-result recap, and first
Champions retain a single-fighter coronation.

## Data and safety boundaries

- The recorder copies the counts, coverage, mean and uncertainty bounds already calculated by
  the tournament evaluator. No extra scoring, model fitting, provider calls or live-trading work.
- At most 32 checkpoints per battle, capped at 32 KiB per stored recording. Unchanged evidence
  is not appended. Compaction keeps endpoints and favors real turning points; every retained
  value is exact. Selected recordings are labelled, without claiming every intermediate update.
- A new pair starts a fresh recording. Starting capture mid-battle or loading it after a restart
  marks it partial. Unknown values remain unknown; invalid values and backward clocks are skipped.
- Active recordings and frozen event recordings use a separate indexed SQLite table. Writes join
  the existing state/event transaction. State JSON, event JSON and schema version 14 stay compatible
  with the preceding runtime. No season reset or qualification changes are required.
- One optional GET loads the completed event's recording. It checks cohort, skill, both versions,
  counts, finite values, time ordering and exact final-result agreement. Incorrect, missing,
  oversized or corrupt recordings fail closed to the saved result. No backfill or viewer polling.
- Per-event storage is bounded; retained historical events still accumulate over time. Storage
  headroom must be observed during the longer paper run.

## Watching

The dialog starts at the saved result. **Replay comparison** walks through recorded checkpoints
at two seconds per checkpoint, with time compression explicitly labelled. It is not a reconstruction
of market events or a recording of actual fighter moves. A single rendering scene receives the
same current checkpoint as both comparison bars; only the final checkpoint carries the result.
The bar displays average modeled-value difference, not win probability. A higher average can
still end in a defence when the required safety checks were not met.

Valid intermediate averages are displayed as preliminary even below 30 usable outcomes or 70%
coverage. Those thresholds still apply before calling a supported edge; uncertainty crossing zero
cannot establish a safe replacement. A bounded chart shows only checkpoints reached in playback,
with breaks for unknown estimates. Level results show the evidence count increasing rather than
inventing a lead. See the [replay-progress checks](V1_10_5_REPLAY_PROGRESS.md).

Pause, previous/next, the keyboard-accessible slider and **Result** work without network requests.
Reduced motion permits manual stepping in 2D. Hidden tabs and offscreen playback stop advancing;
closing cancels pending reads/timers and disposes graphics. Switching pairs or cohorts cannot
apply a late response to the new view. A final result remains usable if the optional request fails.

## Validation

- Frontend: all **261 tests across 15 files passed**, including exact lead changes, level defences,
  unknown estimates, premature-winner suppression, microsecond ordering, stale responses, hidden
  tabs, offscreen timers, renderer reuse, legacy fallback and reduced-motion controls.
- Backend: **495 of 496 cases passed in the full run**. One existing quota test depended on ten
  disk writes finishing before token refill. After freezing its test clock and checking actual
  refill separately, all **30 targeted quota, replay and real-tournament cases passed**. This
  covers all 496 original backend cases plus two additional malformed-record cases; application quota code was unchanged.
- TypeScript, ESLint, Ruff and strict mypy checks passed. The existing optional 3D bundle warning
  remains: main JavaScript ~432.6 kB, lazy Arena ~30.3 kB, lazy 3D ~564.2 kB (before gzip).
- Browser fixtures: **81 checkpoint views** at 1440, 390 and 320 pixels, with no horizontal
  overflow, browser errors or write requests. Desktop and mobile 3D reused one canvas during
  playback and released it on close. The tested pair used 55 draw calls, 4,348 triangles,
  29 geometries and no textures. Fixtures are examples, not live learning evidence.
- Real tournament tests verify that both a 30-outcome defence and a 120-outcome inconclusive
  comparison persist matching final checkpoints. Persistence tests cover restart gaps, bounded
  compaction, corrupt records, cohort isolation and transaction rollback.
- The staged image's 33 imported Python files and all built frontend files match workspace
  hashes. Installed runtime dependencies match the previous verified image. No packages changed.
- A disposable schema-14 database written by this version was opened and saved by the preceding
  runtime, with integrity checks passing. This tests data compatibility, not every rollback scenario.

Verified image: `sha256:28ec98999af4df5b992cfae60f65e3e780888a958395ecffaee37f2738c4e8ff`.
The local image layers the verified source and UI over the preceding runtime. The repository's
normal Dockerfile remains the complete source-build path.

Previews: [desktop](screenshots/v1.10.5/recorded-battle-1440.png) and
[mobile](screenshots/v1.10.5/recorded-battle-390.png).

Longer-run learning coverage, storage and market-processing performance still need observation.
Checkpoint playback does not establish improved profitability or guarantee all-device behavior.


## Final live verification

The final image was applied through the maintenance API, completing at **09:31 UTC on
2026-09-05**. Season 31, its 400 USDC starting bankroll, Balanced mode, custom 25% drawdown,
Shadow learning, automatic-season preference and the existing data mount were preserved.
All six core workers were healthy; paper ledger imbalances and orphan fills remained zero.
The previous runtime is retained locally for rollback.

Live checkpoint capture resumed after restart: the active Exit recording increased from one to
two checkpoints and correctly remained labelled partial. Eight older historical API reads
returned no timeline, and the real saved Steady Trailkeeper/Calm Navigator defence rendered its
level final result with an explicit final-only note. No past lead changes were invented.
The four deployed skill views passed 12 desktop/mobile checks; the historical dialog's optional
GET returned 200. No browser errors, horizontal overflow or write requests were observed.

A final six-sample observation over 51.6 seconds processed **5,790 additional events**, with
zero dropped events, zero degraded samples, a maximum sampled queue of 2, and a maximum sampled
critical processing lag of 0.337 seconds. These are sampled short-run checks, not a long-term
performance guarantee. The planned multi-hour paper observation remains the next step.
