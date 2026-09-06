# Arena explanation and advantage display — 2026-09-05

This document records the initial UI-only refinement. The later
[recorded battle playback](V1_10_5_BATTLE_REPLAY.md) extension adds optional backend checkpoint
capture and supersedes the final-result-only limitation for newly recorded battles.
The later [replay-progress refinement](V1_10_5_REPLAY_PROGRESS.md) also supersedes the initial
small-sample marker suppression: valid early averages are now labelled preliminary.

This UI refinement follows the [community review](V1_10_5_COMMUNITY_REVIEW.md). It adds no
backend changes, dependencies, polling, model fitting, provider requests or learning writes.
Qualification rules and the 70% coverage requirements remain unchanged.

## What viewers see

- A live verdict names the fighter with a supported advantage. A range crossing zero remains
  **Too close to call**, even if the contender has a higher average. Missing, insufficient,
  inconsistent, stale or paused live evidence hides the directional marker.
- The bar plots the contender's average modeled-value difference against the Champion on a
  fixed −5 to +5 percentage-point scale. A live band shows the available uncertainty range.
  Out-of-scale values retain their real numerical labels; tiny signed values do not round to
  exact zero. The bar is not a probability, elapsed-time countdown or promotion score.
- Shared-outcome progress counts evidence toward the minimum sample. A full bar does not bypass
  coverage, conservative advantage or the other safety checks. Extra samples retain their true
  count while the visual bar stops at its maximum.
- A first contender shows independent checks passing, the next unmet check and the possibility
  of regression. Missing or mismatched checks do not appear complete. Passing every displayed
  check still waits for a recorded result. A first coronation has no opponent or battle meter.
  The next check explains the remaining requirement in plain language and shows its current value
  against the target, instead of repeating the backend's technical proof description.
- Saved results explicitly distinguish a new Champion, a defended crown and no replacement.
  An exact tie explains that no advantage was demonstrated. A positive contender average with
  a recorded defence does not reverse the saved result or imply the Champion's average was higher.
  Historical records lack an upper uncertainty bound, so recaps show the average and saved
  conservative estimate without inventing a full range.
- Detailed counts, coverage, units and estimates expand under **Comparison numbers**. Fighter
  profiles, results and progress remain accessible in static 2D and reduced motion.

## Verification

- Full frontend suite: **231 tests across 13 files passed**. New cases cover ties, positive-average
  defences, inconclusive results, live direction, unsupported/malformed bounds, small samples,
  stale recovery, out-of-range values, missing identities/metrics and first-proof regression.
  After the final next-check wording refinement, all **106 Arena tests** passed, including a new
  case for numeric targets, coverage, unknown values and boolean qualification requirements.
- TypeScript build and ESLint passed. The existing lazy 3D bundle-size warning remains.
- Browser fixtures: **42 scenarios** across 1440, 390 and 320 pixels, including long names,
  expanded detail panels, unknown data and first-Champion states. No horizontal overflow,
  browser errors or write requests occurred. Fixture values are illustrative, not live performance
  or learning evidence.
- Desktop and mobile 3D retained 54 draw calls, 4,212 triangles, 28 geometries and zero textures
  for the tested pair. Both released all canvases on close; reduced motion created no canvas.
- The new content stays in the lazy Arena chunk. The main application bundle remains approximately
  432 kB, and the optional 3D bundle remains approximately 564 kB. No new continuously running work
  was added. These checks do not establish all-device support or long-term runtime performance.

Verified UI image: `sha256:779c5c5b1474aaa7433f31fc7fde44698c187a5d9b97d21af8f7c90a18cb8911`.
The image replaces only the built frontend and README on the previously verified runtime.
All 32 packaged Python files and installed runtime dependencies are unchanged, and frontend
hashes match the workspace build. The normal repository Dockerfile remains the full source-build
path. The UI refinement requires no database migration or season reset.

The final live upgrade completed through the maintenance API at 08:43 UTC. All six core workers
were healthy afterward. Season 31, its 400 USDC starting bankroll, Balanced settings, custom
25% drawdown, Shadow learning and the data mount were preserved. Paper ledger imbalances and
orphan fills remained zero. The four deployed skill views passed another **12 browser checks**
at 1440, 390 and 320 pixels with no horizontal overflow, browser errors or write requests.
The original runtime and preceding UI build remain available as local rollback images.

Previews: [desktop](screenshots/v1.10.5/advantage-readout-1440.png) and
[mobile](screenshots/v1.10.5/advantage-readout-390.png).

The longer-run learning-coverage, latency and storage observations in the community review remain
open; presentation improvements do not establish better trading performance.
