# Fighter variety — 2026-09-05

This cosmetic refinement extends the unreleased v1.10.5 Arena. It changes no backend source,
saved artifacts, training recipes, scoring, qualification, trading configuration or API.

## Stable identity and family cues

`arc-forged-v1` still selects the original palette, build, crest and signature. The separately
versioned `arc-details-v1` adds four helmet details, four visor patterns, four shoulder details,
four emblem frames and three trim patterns. Its independent deterministic lanes use the complete
artifact ID and skill; renaming, changing influence, switching device or reopening the Arena
does not reroll the details. No growing cache, saved browser recipe or network asset is required.
Finite combinations and hash collisions remain possible. The full artifact ID is the identity;
the existing visible-signature collision fallback remains in place.

The same normalized visor/emblem/family line segments appear in the SVG portrait and 3D rig.
Linear wears parallel bars, XGBoost a branching mark and antennae, and deterministic policies a
shield. Missing or unknown family metadata uses a neutral diamond, without guessing model type.
Family appearance never implies qualification, influence, profitability or superior performance.
Existing colours, main crests and build are preserved while the new details become visible.

## Repeatable, bounded movement

`arc-motion-v2` defines four strike styles, three defences, three profile poses and three saved
Champion celebrations. Each fighter has a preferred strike and a secondary variant. The battle
identity, fighter ID and checkpoint timestamp (with a bounded index/count fallback) choose the
variation and hand. Scrubbing to a checkpoint or reopening its recording gives the same motion.
This updates the illustration recipe; it does not claim to reproduce previously displayed moves.

The existing evidence gates still control directional emphasis. Cosmetics never produce a metric
or result. Equal evidence remains equal; both fighters may illustrate a neutral exchange. Unknown
evidence cannot award a crown. An inconclusive recap has no winner pose; a first Champion has no
opponent or strike sequence. Only the saved result selects the final crown and celebration.

The shared articulated rig, short clips, coalesced live updates, one canvas, lazy scene import,
adaptive quality, Off/2D, reduced motion and hidden/offscreen suspension remain. New rigid details
merge into existing joint/material batches; no textures, particles, extra timers, polling, audio,
AI generation, downloads or dependency changes are added. Signature style descriptions stay in
the expandable identity section to keep the primary interface compact.

## Verification

- All 277 frontend tests in 16 files passed. The final SVG alignment polish also passed 28
  portrait/dialog tests. Tests cover preserved core identities, frozen detail mapping, bounded
  variation across 1,000 sequential IDs, actual differences between move styles, finite joint
  limits, repeatable playback, solo coronations and truthful winner handling.
- TypeScript, frontend ESLint, whitespace checks and the production build passed before staging. No temporary
  fixture entry point ships in the build. The existing large lazy 3D chunk warning is unchanged.
  Compared with the previous deployed UI, JavaScript adds 2,345 compressed bytes and CSS 28 bytes.
- 99 browser views covered 1440, 390 and 320 pixel widths, all four family states, multiple
  generated kits, long names, first crowns, retained/promoted/inconclusive results, legacy history,
  live/paused/stale views and missing historical identities. A further 39 views rechecked the
  antenna adjustment. One reduced-motion phone view checked the corrected shield side in SVG.
- Scrubbing reused the existing canvas; Off disposed it and switching back restored 3D. Reduced
  motion retained manual checkpoint stepping with no canvas. No browser exceptions, API writes
  or horizontal overflow were observed.
- Tested scenes reached at most 57 draw calls and 4,960 triangles, within the existing 80-call /
  50,000-triangle budget, with zero textures. The former replay test pair used 54 calls / 4,212
  triangles; these are different fixture pairs, so this is a budget check, not an exact benchmark.
- Across 100 open/close cycles after the expansion, warmed samples at cycles 20, 50 and 100 held
  exactly 996 DOM nodes and 196 event listeners; sampled JS heap ended below its first sample.
  Every closed scene removed its canvas. This is a bounded cleanup regression, not a long-term
  guarantee across all browsers or physical GPUs.
- Example screenshots are synthetic QA fixtures, not claims about live model performance:
  [desktop](screenshots/v1.10.5/fighter-variety-1440.png),
  [phone](screenshots/v1.10.5/fighter-variety-390.png), and
  [reduced motion](screenshots/v1.10.5/fighter-variety-2d-390.png).


## Deployment

Staged as `signal-arcade:v1.10.5-fighter-variety`, image
`sha256:89219e24f2d62e9b7469f91c3b5e5f9159ac2acaac5c29cbbee9d9d9bd5439a8`.
Safe maintenance operation `14511d4932d6426abe8c6cfcce9fb36f` prepared the running app before
replacement. The previous image is retained as `signal-arcade:v1.10.5-before-fighter-variety`.
Preflight compared all installed backend Python files and every built UI file with the workspace;
backend files were unchanged and the staged UI matched. The existing `/data` mount was preserved.

The pre-update 30.9-second sample processed 2,216 events, with no new drops, a maximum sampled
queue of 85 and critical processing lag of 0.0852 seconds. All six workers were healthy. It retained
an earlier `recent_candidate_shedding` warning and snapshot ages of 13.3 / 26.4 seconds; this was
observed on the previous image and is not evidence of a regression from the cosmetic patch.

Post-deployment verification confirmed the running image, all 33 backend files and all nine built
UI files. Container health and all six workers were healthy, with no restart loop. Maintenance
completed and trading resumed. Season 31 retained its 400 USDC start, Balanced profile, 25% custom
drawdown, Shadow learning and original data mount. Schema remained 14; the accounting check found
zero imbalanced transactions and zero orphan fills.

The real 12-checkpoint Exit recording was checked in 12 live views at 1440, 390 and 320 pixels.
Its exact zero-difference measurements, evidence counts and saved retention were preserved.
Playback reused a single canvas, made one successful replay GET and no writes, and displayed the
new signature-style explanations. No browser errors or horizontal overflow were observed.

The final 30.1-second health sample processed 1,772 additional events with zero new drops, at most
eight queued events, critical lag at most 0.0634 seconds, no degraded reasons, and snapshot ages of
1.5 / 1.8 seconds. These are short deployment checks; a longer observation run and real-device
coverage remain necessary for claims about endurance or hardware performance.
