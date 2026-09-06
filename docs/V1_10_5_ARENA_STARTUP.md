# v1.10.5 Arena startup and switching review

Reviewed 5 September 2026. This change is confined to the browser renderer lifecycle and local
graphics preferences. Trading, learning, evidence, qualification, API contracts and database schema
are unchanged.

## Behaviour

- Opening a selected 3D Arena uses a neutral preparation state until its canvas is ready. It no
  longer presents 2D fighters as the temporary loading screen. The first load still needs the
  optional renderer download and GPU initialization; instantaneous startup is not promised.
- Switching skills or battle pairs within the open dialog reuses one canvas, platform and quality
  governor. The old fighters' geometries and materials are disposed as the new pair is installed.
  The visible pair changes before paint, and readiness is tied to that pair's identity key.
- Auto starts at Low without a valid saved tier. Subsequent visits resume its last measured tier
  from local browser storage. Explicit High, Medium, Low or Off choices take precedence. Auto still
  adapts, and every 3D tier retains the existing poor-performance safeguards. Storage failures
  cannot prevent opening the Arena; blocked writes retain the adaptive tier only for that session.
- Preferences belong to a browser and site origin, not an account. Different devices, browsers or
  addresses may have separate preferences. No server settings or user data are transmitted.
- Hidden or scrolled-out stages defer initialization and pair changes. Hidden time does not consume
  the eight-second loading timeout. Closing, choosing Off or enabling reduced motion disposes the
  renderer. No hidden GPU cache is kept after close.
- Reduced motion, incomplete historical identities, load failure and context loss retain the full
  2D evidence view. The existing one-explicit-retry limit per page session remains in place.

## Verification

- Full frontend regression suite: 302 tests passed across 17 files. TypeScript, ESLint and the
  production build passed. The existing optional Three.js bundle still triggers Vite's size notice;
  it remains lazy-loaded only for an opened 3D stage. No dependencies were installed or changed.
- Lifecycle regressions cover cold loading, Off-to-Auto, rapid selection during a pending import,
  visible canvas reuse, hidden pair replacement, skip/replay scoping and disposal.
- Quality regressions cover remembered Auto tiers, explicit choices, invalid/unavailable storage,
  downgrade persistence and the existing cooldown/headroom limits.
- Real Edge browser checks covered 36 views/tab selections across 1440, 390 and 320 CSS-pixel widths:
  training, saved Champion, testing pair, coronation, promotion, retention, inconclusive and paused
  states. No horizontal overflow, browser errors or mutation requests were observed.
- Delaying the real lazy import confirmed the neutral loading state has no 2D fighter elements and
  resolves to the latest selected pair. Reopening retained explicit Low and Off settings; cached
  Auto resumed Medium. Reduced motion, incomplete identity and actual WebGL context loss/retry
  retained their expected fallbacks.
- One hundred pair replacements reused the same canvas. Returning to the same comparison at
  iterations 20, 50 and 100 gave 40 geometries, zero textures, 450 DOM nodes and 190 event listeners
  each time. Garbage-collected JavaScript heap was approximately 22.4, 22.6 and 22.9 MB. This checks
  bounded repeated switching, not multi-hour endurance on every phone or GPU.
- Tested scenes remained below the existing 80-draw-call and 50,000-triangle ceilings (observed
  maxima: 56 draw calls and 4,916 triangles). No new rendering loop, remote request or backend work
  was introduced.

The fixture screenshots and raw browser reports use synthetic evidence for reproducibility. They
do not establish model performance or profitability.

## Live deployment verification

- Deployed via the app's prepare-for-upgrade flow, operation
  `6ea2dd84cf5b46fe9bea80a6e005da52`, with the existing data mount preserved. The UI-only image is
  `signal-arcade:v1.10.5-arena-startup`; rollback image is
  `signal-arcade:v1.10.5-before-arena-startup`. All 33 backend files are byte-identical to the previous
  live image; all nine deployed UI files match the production build.
- Live browser checks observed `loading → 3d` with no intervening `2d` state. All four skill tabs at
  1440, 390 and 320 CSS-pixel widths reused one canvas, showed no 2D fallback elements or horizontal
  overflow, and preserved explicit Low/Off preferences across closing and reopening. All four mobile
  labels were also checked in a paused view. No browser errors or write requests were observed.
- The saved Exit comparison against Bright Harbormaster still replayed its 12 real checkpoints.
  At four selected steps on each of the three widths, the centred zero-edge marker, accumulating
  chart points, usable evidence and final retained-Champion wording matched the recorded data.
  There was one successful replay read, no write requests and no browser errors.
- Season 31 retained its identity, 400 USDC starting balance, Balanced profile, 25% drawdown setting
  and Shadow learning. Schema remains 14; accounting inspection found no imbalanced ledger
  transactions or orphan fills. All six background workers were healthy and restart count was zero.
- A 30-second post-upgrade sample processed 2,283 market events with no new drops and no degraded
  reasons. The maximum observed queue was 65 and critical processing lag 0.322 seconds; sampled
  snapshot ages were under 4.3 seconds. These are short checks, not a completed endurance test.
