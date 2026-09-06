# v1.10.5 Champion Arena implementation and verification

The subsequent live review and fixes are documented in
[v1.10.5 live-review fixes](V1_10_5_LIVE_FIXES.md). That record and the current asset manifest
describe the rebuilt version. The implementation measurements below refer to the earlier build.
The [community-readiness review](V1_10_5_COMMUNITY_REVIEW.md) records later authentication,
model-resource fixes, current image verification and the remaining endurance checks.
The [Arena explanation review](V1_10_5_ARENA_READOUT.md) records the subsequent advantage bars,
plain-language results, first-Champion progress and desktop/mobile edge-case checks.
The [fighter-variety review](V1_10_5_FIGHTER_VARIETY.md) records the later `arc-details-v1`
and `arc-motion-v2` cosmetic extension and its resource checks; the measurements below are historical.

Implementation date: 2026-09-04. Baseline: the verified v1.10.4 working tree (460 backend and
120 frontend tests). This release adds an optional spectator experience. The separate production
application and its data were not modified, restarted or upgraded during this work.

## Delivered behavior

- Four skill-card entry points, stable artifact-based robot portraits, original articulated 3D
  fighters, skill accents, short introductions/exchanges and recorded Champion ceremonies.
- Actual testing candidate and opponent identities, separately labelled influence, honest unknown
  metrics, and distinct first-Champion, promotion, retained-crown and inconclusive results.
- Frozen final recaps, source/cohort fencing, a 15-second freshness pause and at most two bounded
  history pages when a watched comparison disappears between snapshots.
- Auto/High/Medium/Low/Off, reduced motion, visible 2D loading/failure content, one explicit GPU
  retry per page session, keyboard focus handling, scrolling phone layouts and resource cleanup.
- Bounded manual history navigation (64 older records plus the current recent snapshot window).
  Back to latest restarts navigation; no stored history is deleted.

There are no server-side arena settings, database migrations, model generations, training jobs,
promotion rules, Solana calls or AI calls added by this feature. A hash comparison of every backend
Python source file against the saved v1.10.4 baseline found only the release version in
`backend/signal_arcade/__init__.py` changed. Risk, learning and season fingerprints are unchanged.

## Implementation adaptations from the proposal

- Direct Three.js 0.185.1 is isolated inside a React-managed lazy module. React Three Fiber/Drei
  were unnecessary for this bounded scene. All geometry, segmented joints and static portraits are
  original application code; there are no downloaded models, textures or audio assets.
- One renderer may exist at a time per document. Changing a pair disposes the previous renderer
  before creating the selected scene. No dormant renderer or asset cache is retained on close.
- A renderer has one current animation and drops/coalesces intervening evidence updates. It renders
  on demand and stops at the end of each short motion instead of running a permanent idle loop.
- `arc-forged-v1` freezes appearance generation; `arc-motion-v1` seeds recap variation from its
  immutable event identity. Full artifact IDs remain authoritative; suffix collisions show full IDs.
- The scene uses explicitly lit Phong materials. A heap investigation found that the pinned
  library's shared PBR `DFG_LUT` texture retained disposal listeners and closed contexts when using
  Standard materials. The simpler material path avoids that global texture entirely. This was
  verified by repeating the lifecycle test and inspecting the resulting heap snapshot.

## Edge cases checked

The automated tests cover tiny/unknown/invalid evidence, insufficient coverage, inconsistent counts,
wrong testing metadata, missing artifacts, self-comparisons, off/suspended learning, unknown dates,
all terminal result kinds, next-contender races, disappearance without a result, stale/future
snapshot timestamps, source/risk/cohort changes and same-cohort season rollovers.

Lifecycle checks cover Graphics Off, reduced motion initially and mid-view, hidden documents,
freshness expiry/recovery, stale-data historical recaps, Escape/focus restoration, Strict Mode,
closing before a lazy import completes, aborted history, failed history without retries, bounded
history reconciliation and persistent GPU fallback across reopenings. Browser checks also exercise
slow and rejected chunks, WebGL denial, actual context loss, 320/390/768/1440-pixel layouts and a
recap surviving eviction from the recent journal before a cohort change closes it.

A second edge-case review reproduced and fixed six additional UI cases: scrolling the stage out
of view, a hidden tab exhausting its loading timeout, Skip being lost before lazy readiness,
incomplete historical identities receiving misleading outcome text or ceremony sides, interrupted
comparisons being labelled as paused learning, and focus escaping after the focused Use 2D control
disappeared. Nine additional component regressions cover these cases, including each saved winner
kind, a missing opponent and commands not carrying into a different recap. The loading timeout now
counts eight seconds of visible time; graphics are created only while the stage is visible.
Seven browser regressions passed on the final build, including a download completing while hidden,
cumulative visible-time timeout, early Skip followed by Resume/Replay, keyboard focus recovery and
a saved promotion with a missing opponent. The full Edge/Firefox/WebKit matrix was repeated, followed
by another 200-cycle resource run: nodes stayed at 759 and listeners at 199 through every checkpoint,
with zero scene textures and no write requests. No backend source or dependency changed in this review.

The subsequent coronation/card review clarified first-Champion actions as **View qualification** and
**View coronation**, with **Replay coronation** inside the single-fighter scene. History uses “events”
where it includes both qualifications and comparisons. Reigning Champions now reuse the same static
artifact portrait as the skill card and Arena; a missing ID receives a neutral badge. Thirteen new
component cases and strengthened app integration checks cover the four result kinds, actual versus
missing/self testing pairs, suspended influence, portrait stability and absent IDs. These are
presentation changes only; the renderer lifecycle and backend logic are unchanged.
Browser checks on Edge, Firefox and WebKit also cover the card's zero/one/many retentions,
inconclusive counts, suspended status, long names, missing IDs and the single-fighter ceremony.
The final cards have no horizontal overflow at 320, 390, 768 or 1440 CSS pixels. Viewing their
portraits requests no renderer chunk or new data stream. Updated screenshots document the result.
The same review fixed reverse-Tab focus escaping the older details dialog on its initial focus;
qualification details now cycle focus within the dialog in both directions, with a regression check.

The normal page requests no renderer chunk and creates no WebGL context. Arena interaction in the
fixture checks sent no write requests. The existing app snapshot subscription remains the only
regular update stream.

## Verification results

The final backend recheck passed all 460 tests against the v1.10.5 runtime in 88.82 seconds, with one
upstream Starlette/AnyIO deprecation warning. Early harness runs inherited a non-local bind address
or omitted copied IDL fixtures; both harness issues were corrected before the successful run.
Release-version alignment is included in the suite.

The complete frontend suite passed 203 tests across 12 files, including 83 additional tests over
v1.10.4. The final browser matrix passed again on Edge, Firefox and WebKit after the material and
focus fixes. TypeScript, ESLint, the Vite production build and Git whitespace checks passed.

The final release recheck rebuilt the current source to the exact same five JS/CSS asset hashes
recorded in the manifest and packaged image. The README's release versions and local links were
checked, and its packaged copy matches the working tree. The 203 frontend tests, TypeScript,
ESLint, three-browser Champion card/coronation checks and isolated container smoke test passed
again. Backend source isolation and unchanged runtime dependency versions were also reconfirmed.
No additional application change was needed in this recheck; the rollout limits below still apply.

The final local `signal-arcade:v1.10.5` image is
`sha256:6ea5d081217bb49f8288e1462ee0f7e24611c5088d5c638713ad9c2cd918fa7f`.
It started as the unprivileged app user with a read-only filesystem, no network, one CPU, a 1 GiB
memory limit and temporary Demo data. Health reported v1.10.5 and healthy background tasks.
Snapshot, seasons, Champion history and Decision Lab endpoints passed, schema stayed at 14, and
all three JavaScript assets (including both lazy chunks) loaded. All five packaged JS/CSS assets
matched the final build manifest. Installed Python dependency versions match the v1.10.4 image.
The production container remained healthy on its original v1.10.3 image throughout.

| Check | Evidence |
|---|---|
| Browser engines | Edge 152.0.4191.62, Firefox 153.0 and Playwright WebKit 26.5 exercised the rendered arena and complete 2D fallback on Windows |
| Responsive layout | No dialog horizontal overflow at 320, 390, 768 or 1440 pixels; controls and metrics scroll vertically |
| Scene complexity | Representative two-fighter scene: 54 calls, 4,212 triangles, 28 geometries; zero textures after the material fix |
| Initial JavaScript | About 126.52 kB gzip versus 120.55 kB for v1.10.4; about 5.97 kB added, below the proposed 15 KiB budget |
| Optional downloads | About 144.56 kB gzip for 3D, 5.23 kB for its dialog and 3.21 kB for its CSS; loaded on demand |
| Owned graphics buffers | Approximately 357 kB for the representative scene; released on disposal; this excludes browser/driver overhead |
| Repeated lifecycle | 100 instrumented cycles: maximum one active context and zero active contexts/buffers after close; context-loss recovery remained bounded |
| Retained objects after fix | 200 further cycles: DOM nodes held at 877 and listeners at 194 after warm-up; final heap contained zero arena canvas objects |
| JavaScript heap after fix | Approximately 6.0 MB at cycle 20, 6.3 MB at 60, 6.6 MB at 100 and 7.0 MB at 200; no continuing canvas/context retention |
| Static/hidden motion | No further arena draw calls after a motion finished, while the document was hidden or while scrolling fully clipped the stage |
| Production dependency audit | Pinned frontend production dependency graph: no published advisories reported by pnpm audit |

A controlled 45-second synthetic-stream sample for each mode made seven snapshot GETs and zero
writes in v1.10.4 closed, v1.10.5 closed, 2D and 3D. JavaScript execution time was respectively
0.045, 0.044, 0.072 and 0.590 seconds. The optional view's shell painted in about 14 ms; local 3D
readiness was about 0.62 seconds. Edge reported ANGLE/Direct3D11 on Intel HD Graphics 530.
Browser task time varied from 5.0 to 7.2 seconds across samples, so these runs do not establish a
precise whole-machine CPU regression percentage. They demonstrate unchanged request cadence and
bounded incremental script work on this host, not latency certification under live market load.

The final 100-cycle instrumented rerun also held native DOM nodes at 878 and listeners at 207
through cycles 20, 60 and 100, with every created context disposed and zero owned buffers after close.
Instrumentation adds its own objects; compare counts within the same run rather than between probes.
Built asset hashes and cosmetic recipe versions are recorded in [V1_10_5_ASSETS.json](V1_10_5_ASSETS.json).

The checked-in resource regression then passed its own 200-cycle run: nodes stayed at 759 and
listeners at 199 for all recorded checkpoints. A final cold-load check with a simulated 20 Mbps,
80 ms connection reached 3D in 1.50 seconds. Desktop/mobile screenshots and all four saved-result
ceremonies were reviewed; the crown framing and phone touch targets were adjusted before the final
image. The footer and full evidence remained reachable at 320 CSS pixels.

The first material implementation was rejected: its native canvas count grew by one per opening.
Zero active GPU buffers alone was insufficient to detect that retention. The final regression tool
also checks detached DOM growth and zero scene textures:

```bash
node scripts/check-arena-resources.mjs http://127.0.0.1:8875/
```

Run this against a stable isolated fixture with an available Champion skill and an installed
Playwright/Chromium runtime. `PLAYWRIGHT_MODULE` can point to an external test-runtime module;
`PLAYWRIGHT_CHANNEL=msedge` selects installed Edge. No browser automation dependency is shipped in
the application. The script fails if 200 visits accumulate detached nodes/listeners, exceed the
scene budget, reintroduce the shared texture or send a write request.

Vite reports a minified chunk-size warning for the lazy renderer (approximately 564 kB before
compression). It is deliberately separate from startup and comfortably below the optional-download
budget. The warning was not suppressed.

## Scope of confidence and rollout

Browser automation establishes behavior on the tested Windows engines. It does not certify real
Android phones, iPhones/iPads, every integrated GPU, screen-reader behavior or all driver versions.
WebKit automation on Windows is not a physical Safari/iOS test. A controlled comparison of market-processing tail latency under concurrent fitting/Coach load,
including two visible windows, remains a rollout check. The original two-hour active and
overnight hidden/closed endurance targets remain additional rollout checks; short lifecycle and
heap tests do not stand in for those observations. Exact all-device GPU allocation cannot be read
reliably from these browser measurements.

The UI is ready for staged testing with the separately built image; the remaining rollout checks
are listed above.
Start with Auto or Low on a shared Docker host and verify its real event lag and learning progress.
Use Off for a complete static view if graphics compete for resources. Multiple visible windows can
each render a scene; the one-renderer limit is per document, not per machine.

Keep the validated v1.10.4 image available. Both versions use schema 14, so reverting this spectator
release requires no reverse migration. Upgrading from the still-running v1.10.3 baseline must also
follow v1.10.4's backup, schema and staged reserve-refresh guidance. No profitability, universal
performance or indefinite unattended reliability claim follows from an animated Champion.

## Subsequent local deployment — 2026-09-05

After the implementation checks above, the existing v1.10.3 installation was upgraded through
its Prepare for upgrade API. A stopped-data backup passed SQLite quick_check and verification
of every archived file hash. The complete folder included older backups: approximately 34.6 GB
of source files compressed to 8.1 GB. The original data mount, Compose project, credentials and
Ollama model volume were preserved.

The Compose-built deployment image is
`sha256:d8165375bde0971bc0447638a6edc232971a217ececdcce11fda887ba97c1899`.
Its filesystem layers exactly match the verified image above; only Compose's image labels differ.
The app reached healthy status without a restart loop and completed migration to schema 14.
The 30 existing seasons, 1,479 evidence episodes, 1,000 learning models, 1,000 skill artifacts
and saved Coach hypothesis remained present. The journal contains 17 events across cohorts,
including the same nine in the current cohort. The normal completed-observation retention rule
reduced 5,094 observations to its 5,000-record limit; the learning/profile fingerprints stayed equal.

Both preserved holdings closed through normal sell fills after restart. The previous season was
then archived through the requested manual reset, and season 31 was created and started with
400 USDC, Balanced and a custom 25% drawdown limit. The one-hour auto-season setting, learning
Shadow mode, AI Shadow mode and Coach research setting were retained. Coach contribution remains
disabled, and the optional learning reserve-refresh worker remains disabled for the initial rollout.

Post-start checks found all background workers healthy, a verified paper-execution audit, no
degraded state and continuing market processing. One sample showed 9,746 processed events,
an empty queue and 0.014 seconds of latest processing lag. Startup logs contained no errors.
These are initial deployment observations; the extended load, endurance and device checks above
remain outstanding. Earlier references to the untouched v1.10.3 container describe the preceding
implementation and test phase, not this subsequent authorized deployment.
