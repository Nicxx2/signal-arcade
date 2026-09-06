# v1.10.5 — Champion Arena release plan

> This is the initial Arena design. The implemented, bounded historical checkpoint extension is
> documented in [Recorded battle playback](V1_10_5_BATTLE_REPLAY.md). It supplements final-result
> recaps with real recorded evidence; reconstructing historical market events remains out of scope.

Status: implementation reference. The original proposal was reviewed against the v1.10.4 working
tree on 2026-09-04 and subsequently implemented. The measured results, implementation adaptations,
remaining device/endurance checks and deployment status are tracked in
[V1_10_5_VALIDATION.md](V1_10_5_VALIDATION.md). Targets below are not automatically passed benchmarks.

The user's desktop `signal-arcade-champion-battle-arena-plan-final.md` is an idea source. This plan
adapts it to the existing application, rather than treating every instruction in it as a requirement
to execute. Keep v1.10.4's runtime validation separate from the arena release.

## 1. Release decision and scope

Build an optional spectator arena over the four existing Challenger skills: Entry, Manipulation,
Sizing and Exit. Make evidence progression recognisable through permanent fighters, short exchanges,
Champion ceremonies and a useful history gallery. Normal Learning remains complete on its own.

The v1.10.5 scope is:

- Normal skill cards with static identities and state-appropriate Watch/View buttons.
- One selected arena, a polished shared stage and two readable, stylised low-poly fighters.
- A small compatible rig/animation set: introduction, idle, advance, strike, block, reaction,
  neutral resolution, defence and coronation. Several seeded variations prevent obvious repetition.
- Stable appearance, modest equipment variation and skill-specific palette/stage accents.
- Live evidence presentation, Champion and contender views, and explicitly labelled result recaps.
- A lightweight gallery built on paged Champion Journey, with crown retention, inconclusive results,
  qualification and current influence clearly distinguished.
- Auto/High/Medium/Low/Off graphics, reduced motion, complete 2D presentation and lifecycle cleanup.

Defer full historical exchange replays, extensive equipment libraries, multiple elaborate arenas,
combat physics, sound, automatic arena opening and elaborate cinematic cameras. No additional LLM
calls for commentary, graphics or fight decisions. Coach-origin contenders may carry a factual origin
badge when existing artifact metadata supports it; Coach does not become an invented third combatant.

## 2. What the current app actually provides

Inspected sources include `frontend/src/App.tsx`, `frontend/src/types.ts`,
`backend/signal_arcade/intelligence/learning.py`, `models.py`, `database.py`, `orchestrator.py`
and `api.py`.

| Existing fact | Consequence for the arena |
|---|---|
| Four skill cards, Champion records and a battle-details dialog already exist | Extend these; avoid a second competing Learning dashboard |
| `_challenger_codename` derives names from immutable skill/artifact identity | Preserve existing names; its 32 combinations per skill are not globally unique |
| Skill status separates latest candidate, testing candidate, saved Champion and active version | Show the actual testing pair; never substitute the newest fitted candidate |
| The overall skill state may read `active` while a testing candidate also exists | Influence and tournament activity are independent; show both |
| Tournament state includes counts, coverage, mean uplift, lower/upper bounds and guard counts | Display available values; do not derive a win probability or financial payout |
| Journal kinds are `first_champion`, `promoted`, `defended`, `inconclusive` | These are the authoritative terminal presentation outcomes |
| A tournament can settle and immediately start another contender | A single status poll can miss the finishing pair; terminal ceremonies use its journal record |
| Missing payloads or changed Coach dependencies can interrupt testing | Disappearance is not a defeat; show interrupted/unavailable/context changed |
| Journal records contain final summaries, not every intermediate update | Offer result recaps; exact historical choreography is not recoverable |
| History is paged, scoped to the current cohort, and rejects obsolete cursors with HTTP 409 | Reset gallery requests on context changes; never mix pages from different modes |
| Snapshot responses refresh `server_time` even for cached data | Freshness must use `snapshot_generated_at` and `snapshot_age_seconds` |
| Existing refreshes are shared and coalesced; WebSocket messages request normal snapshots | Reuse the current subscription; no arena polling loop or per-frame requests |
| Frontend uses React 19, ES2022 and Vite; no 3D packages are installed | Verify compatible pinned packages and bundle separation before adding assets |
| CSS reduced motion already exists | Add explicit JavaScript animation handling; CSS does not stop a WebGL loop |

There is no persisted tournament-attempt identifier exposed for the frontend. The existing journal
deduplicates a given cohort/skill/candidate/opponent/result identity. Do not assume `joined_at` or a
general state update timestamp is a stable, per-battle start time.

## 3. Statistical and product rules

The viewer has no command path into training, qualification, activation, consent, trading, settings,
season transitions or evidence capture. No cosmetic setting enters learning fingerprints. No new
learning generation or database schema migration is planned for this release.

| Authoritative situation | Presentation |
|---|---|
| No meaningful artifact | Normal collection card; optional static empty stage |
| Latest artifact still collecting proof | Contender training view, with its actual blockers |
| First qualified Champion | Founder ceremony; do not invent a defeated opponent or claim a common-forward victory |
| Two artifacts testing | Selected pair, evidence count, coverage, bounds and influence badges |
| Small sample or missing bounds | Balanced short exchanges and “Too early to call” |
| Current evidence shifts | Modest evidence-driven momentum, explicitly provisional |
| `promoted` | New Champion ceremony based on the saved event |
| `defended` | “Crown retained — replacement advantage not established”; no claim of decisive superiority unless supplied by proof |
| `inconclusive` | Neutral finish, distinct from a successful defence |
| Suspended or unavailable artifact | Clear state notice; no ongoing victory presentation implying active influence |
| Lost connection or stale snapshot | Last known statistics with age; live exchanges pause |
| Historical recap of a now-suspended Champion | Historical result remains intact; current suspension shown separately |

Sample minimums are eligibility thresholds, not a countdown to a guaranteed verdict. A positive
mean, or even a positive lower bound, is not sufficient for the frontend to declare victory: coverage
and harm guards also matter. Never reinterpret missing data as zero. Never force progress to increase
when the authoritative value changes or resets.

Use the existing metric definitions and show the contender-relative sign consistently. Do not turn
normalised policy-value differences into earned portfolio profit, a percentage chance of winning,
hit points, ELO or a global ranking across different skills/risk cohorts. Challenger qualification and
actual activation remain separate. Cosmetics do not make XGBoost appear intrinsically superior to
Linear or make Aggressive appear more successful than Safer.

## 4. Identity, updates and race handling

### Display contract

Create a small, pure adapter from existing Learning data to an `ArenaViewModel`. It contains selected
skill, cohort, immutable artifact identities, current testing pair, observed/usable counts, coverage,
available metrics, learning/influence/health state, snapshot provenance and an optional frozen final
journal event. A recap is a separate view mode with a frozen event, not a mutable live skill object.

If needed, add only small read-only fields to the existing status/event serializers: exact cohort key
and a deterministic battle key derived from cohort, skill, candidate and opponent artifact IDs.
This matches current pair semantics. If rematches of the identical pair are introduced later, they
will need an explicit attempt identity; do not silently collapse those future attempts here.
Do not compute fresh tournament scores, load model payloads or scan history for each animation.

Terminal events keep their existing immutable `event_id`. Match a terminal event to the selected pair
using its previous Champion and candidate IDs; the promoted candidate is now also its final Champion.
Never infer the finishing opponent from the current card after promotion.

### Update rules

- Repeated snapshots do not create repeated hits or ceremonies. Deduplicate by pair plus observed
  content/provenance, and terminal events by `event_id`.
- Reject stale asynchronous completions using a local selection/request epoch. Changing skill,
  cohort, source, view mode or closing the arena invalidates pending loads and page requests.
- Use the existing single-flight snapshot stream. Account for cached snapshot age plus monotonic
  time since receipt; `server_time` alone is insufficient. Above 15 seconds show delayed state and
  pause evidence choreography. Quiet evidence with fresh snapshots means waiting, not disconnection.
- Restart or an authoritative context reset clears transient animation state and reconciles from
  current data. Do not use a changed clock or smaller count to manufacture a comeback.
- Switching a risk/configuration cohort cancels the selected live battle and old history requests.
  A normal season rollover with the same learning cohort must not invent a new battle.
  Close any open recap on a cohort/source change and explain that the context changed; do not quietly
  relabel old history with the new mode. Invalid/future snapshot provenance shows uncertain freshness
  and pauses live exchanges rather than manufacturing a current timestamp.
- When a watched pair disappears, look for its saved result in the current Journey payload. A single
  user-visible reconciliation may read at most two existing history pages of up to 50 events each,
  coalesced and cancelled on context change. Do not create recurrent reconciliation polling.
  If absent, report “Result not loaded / battle changed” and leave manual history navigation available.
  Never fabricate a result or scan an unbounded journal automatically.
- Gallery paging remains user driven and bounded in memory. On HTTP 409, reset the cursor and show
  the new cohort. On authentication failure, stop requests and retain the normal app login flow.
- While a recap plays, new live updates affect the cards only. Provide an explicit return-to-live
  action. A saved recap must not acquire a new opponent halfway through.
- After tab sleep or reconnection, display the latest state directly. Do not replay a backlog of
  hours of exchanges. Animation work is capped at one active exchange and one coalesced pending
  exchange; a final authoritative result takes priority. All other results remain in Journey.

“All missed results are retained” refers to the authoritative history. It does not promise that every
result receives an automatic notification or a frame-by-frame reconstruction on every device.

## 5. Permanent fighters and honest recaps

Use a versioned cosmetic manifest and deterministic appearance generator based on full artifact and
skill identity. Store neither model weights nor evidence in the browser for appearance generation.
Keep current friendly names; add a stable short identity suffix for disambiguation and expose the full
artifact ID in details. Friendly labels are not database keys. Avoid name assignment that depends on
which browser happened to see a fighter first.
If short identity suffixes collide, lengthen the displayed suffix while preserving full artifact IDs
and existing friendly names; do not promise global uniqueness from a small display vocabulary.

Freeze `appearance-v1`, its vocabulary ordering, approved assets, rig mapping and fallback rules.
Future changes must preserve v1 mapping or explicitly provide a new cosmetic version. Stable names,
appearance parts and major recap beats should match across restarts and devices. Pixel-identical
rendering across different GPUs is not a promise. Missing assets use a recognisable static portrait
and name, rather than generating a different identity.

Label v1.10.5 history playback “Animated result recap” and explain once that choreography illustrates
the saved result. Use event ID and choreography version to choose a repeatable short sequence.
Intro, neutral exchange and terminal ceremony are enough; do not invent a measured intermediate lead.
Support pause, skip-to-result and close. Archived model payloads are not required: existing retained
metadata and the journal suffice. Unknown family/date/generation remains visibly unknown.

True historical exchange replays require a separate future design for bounded milestone capture,
storage retention and versioning. Do not backfill fabricated events or add evidence writes for this
release's recap feature. A gallery must label incomplete historical records and must not compute an
all-time record from only the latest page.

## 6. Rendering and device contract

The support promise is complete Learning and arena information on supported modern browsers, with
3D when compatible and 2D/static presentation otherwise. The existing ES2022 app already has browser
requirements. “Every device gets full 3D” and “every browser ever made is supported” are not credible
release criteria.

- Lazy-load the 3D module and assets only after the user opens a 3D view. No automatic opening,
  eager preload, hidden card canvases or GPU-generated thumbnail farm.
- One renderer per app document, shared between selected skills and recap modes. Clone each
  fighter's skeleton/animation state correctly while sharing immutable geometry/material resources
  where safe. Sharing a skeleton must not make both fighters perform the same movement.
- Prefer a compatible pinned Three.js/React Three Fiber stack; use Drei only for justified helpers.
  No physics engine, remote scripts or unneeded post-processing. Validate peer dependencies against
  the actual React version at implementation time.
- One stage with palette accents, readable silhouettes, restrained camera motion and a maximum of
  two fighters. Keep statistics and controls in accessible HTML outside the canvas.
- Static 2D comes first in loading and error states. Close and “Use 2D” remain available throughout
  module/asset loading. Failed chunk loads after an upgrade show a recoverable message, not a blank app.
- One local error boundary protects the arena. Handle rejected asset loads and renderer/context
  errors explicitly; React boundaries alone do not catch every asynchronous or GPU failure.
- On context loss, stop and show 2D. Allow one explicit reconstruction attempt using the same model;
  repeated failure stays in 2D for the session. No automatic context recreation loop.
- Tab hidden, arena off-screen or closed: stop arena animation/timers and do no continuous render
  work. Pause on browser page lifecycle events, then reconcile before resuming. Clamped frame delta
  prevents a large post-sleep animation jump.
- On close, unmount the renderer, stop mixers and release GPU resources. Bound CPU-side shared asset
  caches; evict when idle. Cancel fetches where possible and dispose late results when cancellation
  cannot stop parsing. Account for shared ownership before disposing a shared material or texture.
- Private browsing/storage denial leaves preferences functional for the current session. Persist
  cosmetics per browser only. Browser preferences must never reset learning or alter server risk mode.
- The one-renderer limit is per document. Hidden tabs pause; two visible browser windows can still
  consume resources. Include that case in testing and degrade locally if necessary; do not claim a
  browser-wide or machine-wide renderer guarantee.

Device signals are hints, not proof of a GPU's speed. No vendor-name classification, required battery
API, hardware fingerprint upload or claim that the browser can reliably detect overheating. Actual
render timing drives adaptation. WebGL support alone cannot detect every visual driver defect, so
the manual 2D switch remains essential.

## 7. Quality and performance budgets

These are proposed acceptance targets to measure during implementation, not achieved benchmarks.
If the first approved assets exceed them, simplify assets/effects or document an explicit revision
before release; do not quietly remove the limits.

| Area | Proposed target |
|---|---|
| Closed normal Learning page | Zero requested 3D chunks/assets, zero WebGL contexts; arena entry UI adds at most 15 KiB gzip of initial JavaScript |
| Initial optional 3D download | At most 6 MiB transferred, including runtime, two fighters and shared animations; static previews are separate and small |
| Loading response | HTML shell and usable close/2D controls within 200 ms on reference devices; informative fallback always visible |
| Ready time | Warm view within 1 second; cold view target 5 seconds on the defined 20 Mbps/80 ms test connection; after 8 seconds keep 2D and offer retry |
| Low / Auto starting point | 30 FPS cap, device-pixel-ratio cap 1, simple materials, no dynamic shadows or post-processing |
| Medium | 30 FPS initially, DPR cap 1.25; effects within budget |
| High | At most 60 FPS, DPR cap 1.5; optional limited shadows, no unbounded particles |
| Low scene working targets | At most 50,000 visible triangles and 80 draw calls; validate skinning, texture and shader costs as well |
| Memory working targets | Low: estimated GPU allocations under 64 MiB and measured browser-memory increase under 150 MiB over the same app without arena |
| Animation work | One active exchange, one replaceable pending exchange; no growing command/event/particle queues |
| Idle and close | No ongoing arena RAF/timer loop when static, hidden, off-screen or closed |
| Backend | No extra Solana/LLM calls, no changed periodic API cadence, no arena-triggered learning writes or fitting |
| Added status metadata | At most 2 KiB uncompressed per snapshot; no new history or payload scans in its normal assembly |

Use measured frame *work* and missed-frame rate, not intentional 30 FPS waiting time, to evaluate
performance. Start Auto conservatively. Three bad 2-second windows trigger a lower tier; allow at
least 10 seconds between quality changes. An upgrade requires 30 seconds of stable headroom and no
recent context failure; exclude hidden/loading periods. If Low cannot sustain approximately 20 FPS,
switch to 2D with a clear explanation. Manual High remains a preference, not permission to crash or
trap the user in an unusable scene. Scale resolution before adding complexity.

Prefer the same base assets across tiers to avoid repeated downloads and decode spikes. Runtime
texture/geometry counters are estimates, not a universal GPU memory meter. Record browser-process
memory and resource counts on reference machines; do not falsely label missing measurements as zero.

Measure closed/open/loading/recap cases on the same computer running Docker, using a controlled
recorded feed, fixed settings and repeatable training/Coach load. In at least three alternating runs,
target p95 market-processing lag and snapshot latency within baseline plus max(5%, 20 ms), with no
additional dropped protected events, worker incidents or persistent queue growth. Explain noisy
measurements rather than inferring causation from unmatched live traffic. Include simultaneous model
fitting and two visible windows. Backend isolation is an architectural aim; shared hardware still
requires measurement.

## 8. Accessibility, security and asset acceptance

Support 320 CSS-pixel portrait width, phone landscape, tablet and desktop layouts, browser safe areas,
dynamic toolbar height, 200%/400% zoom and long names. Keep a 44-pixel minimum target for main touch
controls. Do not require hover, fullscreen, pointer lock or camera gestures; preserve page pinch zoom.
Dialog focus is trapped appropriately, Escape closes, focus returns to the triggering card, and
switching views does not strand keyboard users.
Target at least 14 CSS pixels for explanatory text and 16 for the primary evidence values on phones;
fit the layout by stacking content, not by shrinking it to unreadable labels.

Respect reduced motion in JavaScript from first mount and when the preference changes. Default to
static/2D for that preference; do not quietly re-enable movement. Keep camera shake and flashes off
in v1.10.5. Convey sides, outcomes and influence using text/icons as well as colour. Screen readers
receive brief meaningful milestones, never announcements per frame or every metric tick.

Select assets by exact licence, redistribution permission, size and rig compatibility. Record source,
licence and required notices for each included asset; a pack's marketing description is not enough.
Validate clips, joint counts, attachment points and animation bounds. Prevent intersecting equipment,
off-screen attacks, floor penetration and framing that cuts off phone-sized silhouettes.

Bundle approved assets locally with the release; verify their hashes in the build manifest. Reject
external GLB texture/URI dependencies or package them locally. No arbitrary model uploads, remote
asset fetches, unpinned CDN scripts or HTML generated from fighter names. Reuse the app's authentication
and content-security policy; do not weaken them to make a viewer or decoder work. Prefer simple
assets over introducing a fragile worker/WASM decoder unless measured benefits justify it.

## 9. Required edge-case matrix

Each row needs a recorded passing check, or an explicit unsupported-device limitation, before release.

| Case | Expected result |
|---|---|
| No Champion, no candidate | Useful collection text, no invented fighter or battle |
| Latest candidate differs from testing candidate | Actual testing pair shown |
| Overall skill is active while a contender is testing | Active influence and live battle are both visible |
| First Champion followed immediately by next tournament | Founder event preserved; new pair never used in the founder ceremony |
| All four skills testing simultaneously | One arena; all existing backend tournaments continue |
| Fast Entry/Exit switching during asset load | Late loads ignored/disposed; correct identity and controls |
| Promotion while arena closed/loading | Cards/history update; user can open saved result; no auto-open |
| Finish then next contender in one snapshot | Old result matched through journal, never inferred from new pair |
| Defence, inconclusive, failed harm guard | Correct distinct explanations and endings |
| Suspended Champion or missing candidate payload | Pause/interruption; no fabricated win |
| Context-stale Coach contender | Interruption state; no extra Coach work or reassignment of credit |
| Risk/configuration/source switch during view/history request | Old response discarded; new context labelled |
| Same-cohort auto-season rollover | Learning battle identity preserved |
| Duplicate, cached or delayed snapshots | No double animation; age visible; no false fresh-state indication |
| Quiet evidence, fresh server snapshots | Calm waiting view, not a server failure |
| Null/NaN/invalid metrics, missing version or malformed status | Bounded text fallback; no score-derived outcome |
| Disconnect, sleep, bfcache restore or backend restart | Latest state reconciled; no catch-up animation storm |
| Client clock changes | No artificial progression; monotonic elapsed age locally |
| More missed events than the recent page | Bounded reconciliation and manual paged history; no invented result |
| HTTP 401/403/409/500 while paging | Normal auth/error handling, cursor reset only for changed context |
| Name collision, archived payload, missing family | Stable identity; short disambiguator; unknown metadata honest |
| Appearance manifest changes in later release | v1 identity compatibility fixture stays stable |
| Recap while another battle finishes | Frozen recap unchanged; live result available separately |
| WebGL unavailable, WebGL1-only, software rendering | Complete 2D fallback; no unnecessary legacy renderer bundle |
| WebGL reports support but scene corrupts | Visible manual 2D escape and tested compatibility mode |
| Context loss, out-of-memory, shader/clip/texture failure | Controlled fallback without repeated allocation/retry |
| Slow/failed assets, interrupted import, old tab after deployment | HTML controls remain; clear retry/reload option; no reload loop |
| Graphics Off or Reduced Motion selected mid-exchange | All movement stops; final authoritative text remains |
| Scroll off-screen, hide tab, close modal, navigate away | Mixers, RAF, timers, observers and listeners cleaned up |
| Reopen/switch/recap 100 times, including React Strict Mode | No duplicate renderer/listeners, no rising resource baseline |
| Two visible windows, Docker training, thermal slowdown | Local downgrade/fallback; benchmark shared-machine impact |
| Private browsing or corrupted preference storage | Safe defaults, working controls, no server-setting writes |
| Phone rotation, keyboard focus, screen reader, high zoom | Controls and statistics remain reachable and understandable |

## 10. Implementation stages and evidence required

1. **Baseline and fixtures.** Record v1.10.4 behavior, load timings, request counts and host performance.
   Create representative saved input fixtures for every state above; do not manipulate live learning
   to produce a cinematic test. Establish independent v1.10.4 runtime evidence before arena rollout.
2. **Pure adapter and 2D experience.** Build the state mapping, identity rules, loading/error shell,
   result recap semantics and paged gallery. Test races, freshness, exact-cohort mapping, accessibility
   and no command/API-cadence changes. Review wording with real fixture values.
3. **Asset and renderer prototype.** Verify licences and rig compatibility. Implement one shared
   renderer with two fighters and the smallest animation library. Prove lazy-loading, cleanup,
   context-loss fallback and budgets before expanding animation variety.
4. **Evidence choreography and polish.** Add bounded exchanges, modest camera direction, stable
   appearance, founder/defence/inconclusive/coronation sequences and deterministic recaps. Check that
   text and final outcomes remain identical at every quality setting and in 2D.
5. **Compatibility and endurance.** Run functional tests in Chromium, Firefox and WebKit. Test real
   Windows Intel-integrated graphics, Android Chrome, and iPhone/iPad Safari where hardware is
   available, plus a stronger desktop GPU. Automation/emulation alone is not hardware verification.
   Record actual browser/OS/GPU versions and every untested device; never mark them passed by assumption.
6. **Release verification.** Run the existing backend/frontend suites plus new arena tests, types,
   lint, production build, dependency/licence audit and container checks. Use identical recorded
   events/configuration, controlled time and fixed model seeds to compare core decisions, learning
   artifacts and promotion outcomes with arena on/off, normalising only incidental timestamps/IDs.
   Never normalise away differences in P/L, evidence, risk/cohort identity or qualification.
   Observe a 2-hour active-session
   soak and an overnight hidden/closed session on a shared Docker host; memory must stabilise after
   warm-up, with resource counts returning to a bounded baseline after repeated cycles.

For memory cycling, record measurements after warm-up and after cycles 20, 60 and 100. Require no
continuing growth in owned GPU resources/listeners/timers. Use heap snapshots and process memory to
investigate retained objects; do not claim a leak solely from a browser's reserved-memory plateau.

At release time, bump version metadata to 1.10.5 and update README, CHANGELOG, third-party notices
and a separate validation record. Preserve current database/schema and learning fingerprints. Build
and smoke-test separately from the live app. Deploy only through the normal reviewed release flow.
Closing/turning graphics Off is the first fallback; because no schema change is planned, retaining
the validated v1.10.4 image also provides a straightforward application rollback path.

## 11. Readiness statement

The idea is sufficiently specified to begin staged implementation. No arena performance, device
compatibility or endurance result has been established yet. The exact asset set and tested device
inventory are implementation deliverables, not hidden assumptions. v1.10.5 is complete only when
the useful 2D experience, honest state mapping, optional 3D and recorded acceptance checks all agree.

## Technical references

The proposed one-renderer approach avoids duplicated contexts/resources as described in
[Three.js: Multiple scenes](https://threejs.org/manual/en/multiple-scenes.html). Resource ownership
and explicit disposal follow [Three.js: Cleanup](https://threejs.org/manual/en/cleanup.html).

On-demand idle rendering is supported by
[React Three Fiber: Scaling performance](https://r3f.docs.pmnd.rs/advanced/scaling-performance).
Capability checks, memory budgeting and avoiding blocking graphics queries are informed by
[MDN: WebGL best practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices).

Lifecycle and accessibility behavior use
[MDN: Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API),
[MDN: Context loss](https://developer.mozilla.org/en-US/docs/Web/API/WebGLRenderingContext/isContextLost)
and [MDN: Reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion).
These references support implementation techniques; they do not certify performance on our devices.
