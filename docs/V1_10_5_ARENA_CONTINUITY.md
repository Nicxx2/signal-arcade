# Arena evidence continuity review — 6 September 2026

The Arena previously removed measured advantage and candidate proof whenever the dashboard
snapshot exceeded 15 seconds. The dashboard may reuse a complete snapshot for 5–12 seconds
under load, with delivery and refresh work adding time. Crossing the presentation threshold
therefore repeatedly replaced useful evidence with a waiting message.

## Changes

- Keep the last received, internally valid comparison and independent checks visible. Show
  its snapshot timestamp and a compact delayed-update notice; live exchanges still pause
  after 15 seconds or when provenance is uncertain. Fresh measurements update the existing
  display. Missing or inconsistent estimates remain unknown. Explicitly paused learning and
  interrupted pairs retain their separate states.
- Retain one selected profile and its most recently displayed evidence when a newer model
  generation appears. Do not swap its fighter, revert to modal-opening proof, or describe a
  replaced candidate profile as a battle result. A candidate that earns a first crown becomes
  a Champion profile; an opened Champion profile can link to its newly started comparison.
- Show a model signature beside the launcher name. The frozen appearance/detail recipes,
  model IDs and move styles are unchanged. Duplicate names and cosmetic combinations remain
  possible; the full artifact version is authoritative. Clarify family chest marks, XGBoost
  antennae and the separate decorative armor/handheld shields.

## Verification

- 321 frontend tests pass, including delayed/fresh recovery, missing estimates, exact zero,
  first-Champion proof regression, saved results, selected-profile replacement, latest-proof
  retention and graphics lifecycle checks. Type checking, ESLint and the production build pass.
- 48 isolated browser cases across 320, 390, 768 and 1440 pixel widths had no overflow or script
  errors. Repeated delayed/fresh transitions kept the same bar position, fighter IDs and portrait.
  A real fixture change from +2.4 to −0.4 pp moved the marker from 74% to 46% on the fixed scale.
- Low-graphics transitions reused the same canvas: 56 draw calls, 4,816 triangles, 40 geometries
  and zero textures in the paired fixture. Changing graphics quality preserved fighter identity;
  closing released the canvas. The isolated spectator cases made no API requests.
- The bundle retains lazy loading for the optional 3D renderer. No polling loops, providers,
  training calls, dependencies or backend changes were added. The existing large optional
  renderer bundle still produces Vite's size advisory.

The authenticated pre-deployment check preserved season 33, 400 USDC, Balanced, 25% drawdown,
automatic seasons and Shadow learning. Accounting balanced with no orphan fills, and proof
gate artifact IDs matched their candidates. A 15.3-second snapshot reproduced the delay boundary.

The same live sample recorded expired Discovery events during recent processing pressure,
although its queue had recovered to zero and latest lag was 0.22 seconds. This UI correction
does not conceal that health signal or establish long-term runtime readiness. Continue the
soak review, including event-pressure diagnostics, coverage and a natural season rollover.
The 70% gate and all trading, learning, qualification and activation rules remain unchanged.

## Live verification

The maintenance API prepared operation `f96a33c7f0fd473a9da5c6ef2f31b2f3` before deploying
`sha256:b9e6f672631e223953ac9f2960ce8c1c9dc4844d85f1602c5e20d82ff81d5f0a`.
All 37 backend source files were verified identical to the preceding image and workspace;
all nine staged frontend files matched the built output. Environment and data mounts match.
The previous image is retained locally as `signal-arcade:v1.10.5-before-arena-continuity`.

The deployed browser check covered 32 views across the main tabs, Learning sub-tabs and all
four Arena dialogs on desktop and mobile: no script errors, failed HTTP responses, mutation
requests or page overflow. All four dialogs rendered in 3D and released their canvases on close.
Evidence timestamps appeared on the deployed views, and the former blank waiting message
was absent. Post-deployment accounting/proof checks passed with season 33 and its settings intact.

The diagnostics localized 6,768 expired candidate events to the 07:04:13–07:06:04 UTC interval
on the preceding image, with peak critical lag of 8.03 seconds and a recording gap. Four later
complete intervals on that same image had no expired events. No single cause is established
by those counters; do not attribute recovery to this UI-only deployment or suppress the incident.
