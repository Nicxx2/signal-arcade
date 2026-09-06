# Replay progress and preliminary evidence — 2026-09-05

The reported Exit battle had 12 valid saved checkpoints, from 19 to 30 usable outcomes. Both
policies selected 60 seconds and their paired values were exactly equal. The initial UI hid the
average marker until 30 usable outcomes, making valid early measurements look absent.

This UI-only refinement separates descriptive results from qualification:

- Valid early means and uncertainty ranges remain visible, labelled preliminary. Insufficient
  samples or coverage never produce a supported-edge claim. Missing, malformed, stale or paused
  live estimates still hide the marker. An exact zero reads **Level so far**.
- The stage includes usable evidence counts beside the same measured value as the full readout.
- The replay chart shows at most 32 saved points and only the portion already reached in playback.
  Unknown estimates break the trail; it does not bridge gaps or draw future points. Lines connect
  adjacent recorded values as a visual guide; no intervening measurements are reconstructed.
- The fixed ±5 pp scale clips only visual coordinates. Current numeric values retain their true
  magnitude and very small signs. Summary text describes the shown checkpoints only, including
  partial recordings, rather than claiming a complete history.
- Final playback names the recorded retention, promotion or inconclusive result. Equal results
  cannot imply identical policy logic without additional metadata, so the UI says **Level result**.

Qualification, scoring, guarded fighter momentum and recorded backend results are unchanged.
No additional requests, polling, fitting, timers, WebGL resources or dependencies are introduced.
The SVG chart updates with the existing two-second replay clock or manual checkpoint navigation.

## Validation

- All 264 frontend tests in 15 files passed, including the reported early zero-difference case,
  preliminary leads, unchanged qualification requirements, gap preservation and hidden future points.
- TypeScript, frontend ESLint and the production build passed. The existing large lazy 3D chunk
  warning remains; the replay UI adds about 1 KiB of compressed JavaScript and 0.25 KiB of CSS.
- 162 checkpoint views passed at 1440, 390 and 320 pixels, including the exact 12-point Exit
  recording, early reversals, zero/unknown values, out-of-scale and tiny values, partial/sampled
  records, first crowns, legacy recaps, long names and paused/stale/malformed live views.
- No horizontal overflow, browser exceptions or API mutations were observed. The two comparison
  bars agreed at every tested point. Unknown points did not connect across gaps.
- Desktop and mobile 3D playback reused one canvas (54 draw calls, 4,212 triangles, 29 geometries,
  zero textures in the tested pair). Closing disposed it. Reduced motion supported manual stepping
  without a canvas. The saved screenshots use a synthetic reversal fixture to exercise that case.

Backend files and stored recordings are unchanged by this refinement; the deployment validates
their source hashes against the current runtime before preparing maintenance.

## Live deployment check

Deployed through safe maintenance as image
`sha256:32ee91153c3cfb17faaf0030a84942c01319b7be4769e83ef3f3af194540e1a6`.
The running backend and built UI matched the workspace; the prior image is retained for rollback.
Season 31 preserved its 400 USDC starting bankroll, Balanced profile, custom 25% drawdown and Shadow
learning. The accounting check found no imbalanced ledger transactions or orphan fills.

The exact reported Exit event was replayed in the live app at 1440, 390 and 320 pixels (12 views).
It retained its 12 original checkpoints and final result. One successful recording request served
all playback navigation, with no browser errors or API writes. All six workers and the container
were healthy. A 30.9-second sample processed 1,977 additional events with no new drops; maximum
sampled queue depth was 131/10,000 and critical processing lag was 0.0843 seconds. This is a short
deployment check, not evidence of long-term performance or profitability.
