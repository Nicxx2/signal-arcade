# v1.10.6 release verification

Review date: 7 September 2026. This release packages the independent Champion support,
season/chart improvements and performance fixes reviewed on 6–7 September. The release-number
update itself does not change learning, risk thresholds, Baseline version or feature schema.

## Scope and regression evidence

- The final live review found a recovered enrichment dictionary-iteration error in earlier history.
  Its old traceback was no longer available, but a concurrency review reproduced enrichment
  pruning a token before an in-flight market worker committed its pending learning observation.
  Candidate pruning and selection now share the market update boundary; provider I/O remains
  outside it. All **169 focused backend tests** passed, including four new checks for pending
  evidence preservation, cancellation, source switching and releasing the boundary before I/O.
  Existing provider, burst, training, Champion participation and Coach checks also passed.
  No learning formulas, proof thresholds or trading permissions changed.
  After the local update, all workers were healthy, Sizing and Exit retained support, a new fit
  published successfully and Coach completed a fresh screening review. The short follow-up
  processed 7,495 events without shedding or expiry and recorded no new worker incident.
- The Coach permission follow-up makes **Allow when ready** available before a study qualifies
  and keeps the explanation in a collapsed **How Coach contributes** panel. A reproduced setter
  regression showed that saving contribution permission resumed paused learning; that side effect
  is removed. Research, proof, tournament and activation logic are unchanged. All **70 focused
  backend tests** and **347 frontend tests** passed, along with TypeScript, lint, formatting and
  the production build. Coverage includes advance permission without proof, repeated requests,
  restart persistence, paused research/learning, Local AI Off, revocation and failed saves.
  One existing Arena cross-tab layout test failed intermittently during an intermediate run;
  it passed in the final complete run without a production layout change.
- An additional Coach edge-case review reproduced a saved permission still displaying its old
  state when the dashboard refresh failed. The UI now applies the server-confirmed permission
  after any older in-flight read, then accepts subsequent fresh server state. Lost save responses
  trigger a status refresh without claiming the permission was unchanged. All **355 frontend
  tests**, including eight new save/response regressions, and **75 focused backend tests** passed.
  Checks cover opt-in and revocation, duplicate clicks, failed refreshes, older responses, another
  client's later change, restart/pruning, absent Champions, duplicate handoff, stale context and
  disallowed Coach policies. TypeScript and lint pass. This correction changes only the permission
  UI; the backend, proof thresholds, dependencies and schema are unchanged.
- A further handoff review added four restart regressions, one for each Coach skill. They verify
  waiting for an existing Champion, rejecting stale dependencies, duplicate-safe handoff while
  learning is Off, and preservation of the Champion, paused mode and saved automatic-support
  permission after restart. Resuming learning still grants no activation without proof. All
  **nine focused boundary checks** passed, including pressure, active-fit priority and interrupted
  research. Test lint and formatting pass. This pass changed tests and notes only; no production
  code, live permissions or running containers were changed.
- A follow-up learning review found two activation-order gaps: an active downstream Champion
  blocked fresh native upstream activation evidence, and health could mix a reused artifact's
  earlier activation/composition into its current health window. Both are corrected. The full
  suite now passes **859 backend tests**, including 31 new progression regressions, against the
  corrected production image's runtime. The original failing cases were reproduced before the fix.
  Lint, formatting and backend type checks pass. Runtime dependencies and schema 15 are unchanged.
  Wrong upstream versions, stale join times, duplicate mints, missing/clamped size evidence,
  pending outcomes, exact 30-sample/70%-coverage boundaries, harm, suspension, restart and downstream
  requalification are covered. Coach artifacts keep their separate full-context proof contract.
- A second edge-case pass added six regressions for the most recent 60 resolved health outcomes,
  pending outcomes not displacing completed evidence, and missing, nonfinite or mismatched
  activation proof. All **52 focused participation tests** passed, including those six additions.
  This pass changed tests and verification notes only; the deployed learning logic is unchanged.
- The initial 828 backend tests passed after the v1.10.6 version update, including version consistency,
  independent skill activation, persisted consent, dependency changes, restart recovery,
  season strategy records, diagnostics context, event priority and interrupted-batch accounting.
- The same 828 tests also passed against a helper built from the exact v1.10.6 production image,
  checking its newly resolved NumPy 2.5.3 and AnyIO 4.15.1 dependencies. The installed package,
  API version and Docker version label all agree on 1.10.6. An offline startup test used empty
  temporary storage and no live volume.
- The unchanged frontend implementation previously passed 343 tests, TypeScript and lint.
  The release Docker build also runs TypeScript and the frontend production build.
- Previous checks covered keyboard/touch chart inspection, equal timestamps, bounded and partial
  history, stale evidence, interrupted graphics loading, graphics preference persistence,
  recorded versus live battle results and narrow layouts.
- The README's pinned Compose example is validated separately from the source-build stack.
  Version metadata is aligned across Python, both JavaScript packages, Docker and the README.

The one backend-suite warning is an upstream Starlette/AnyIO deprecation. The existing lazy 3D
bundle-size advisory remains; it is loaded only for the spectator view. Neither warning is a
test failure. Dependency/security checks and other supported platforms remain part of release CI.

## Observed operation

The permission-confirmation UI correction was deployed at 08:27 UTC. At 08:28 UTC all seven
core workers and the Coach worker were healthy, and the paper execution audit remained verified.
Sizing and Exit were already active before this update and retained their exact versions after
it. Coach research remained on and contribution permission remained off. All 38 backend files
were byte-identical to the preceding image. Desktop/mobile browser checks recorded no page errors
or attempted mutations; the existing screenshots still represent the unchanged layout.

The Coach permission follow-up was deployed locally on 7 September at 08:18 UTC using the existing
maintenance handoff. All seven core workers became healthy, the paper audit remained verified,
and the season, settings, data mount and active Sizing identity were preserved. Coach contribution
remained disabled; research and automatic Champion support retained their existing settings.
Dependencies and schema 15 are identical to the preceding image. Read-only browser checks used
1440-pixel desktop and 390-pixel mobile views; the Coach card also passed a 320-pixel overflow check.
No page exceptions or attempted API mutations occurred during capture. This is a bounded release
check, not a measurement of future Coach benefit.

The activation-order correction was deployed locally on 7 September at 07:27 UTC through the
existing maintenance handoff. It preserved schema, season, risk settings, automatic permission and
saved Champion identities. Sizing activated automatically from 60/60 usable cases with a positive
conservative advantage. Exit kept its crown and returned to Shadow to prove the new Sizing/Exit
composition. Three new Baseline-approved buys were checked against saved orders, fees and receipts;
one used the Champion's 0.5x adjustment (0.102787236 SOL to 0.051393618 SOL), and two kept Baseline
size. New Policy records contain the frozen bounded Sizing and shadow Exit proposals; their first
60-second checkpoints were recorded. Later horizons and sufficient new health/join samples still
need to develop. At 07:35 UTC all seven workers were healthy, two fit cycles had published after
restart, 56,363 events had processed without candidate expiry/shedding, and the paper audit passed.
This short follow-up verifies application and evidence collection, not long-term trading benefit.

At 07:43 UTC the next review independently matched the live arithmetic to copied receipts:
Sizing health had 7 usable outcomes from 8 observed, and Exit's new composition proof had advanced
to 3/30 usable comparisons. The unavailable Sizing outcome had no executable exit quote and was
excluded from the average. Eleven new buys passed Baseline, size-limit, fee and provenance checks;
three applied a bounded Sizing adjustment. All seven core workers remained healthy, five training
cycles had published, and 115,175 events had processed with no candidate shedding or expiry since
the restart. These small new samples do not yet establish a trading benefit or qualify Exit to rejoin.

The final pre-release build ran for about 4 hours 55 minutes after the last local update.
265 saved intervals recorded approximately 3.59 million processed market events with no candidate
shedding or expiry, no unhealthy core-worker samples and no recorded training errors. Training
continued through 103 publications. Processing p95 was in the <=2 second histogram bucket;
critical-event p95 was in <=1 second. Brief peaks reached about 11.3 and 6 seconds respectively.

Copied execution receipts were checked independently of the live database: 125 recent entries
used Baseline approval and 125 exits recorded the active Exit Champion with the existing hard-exit
and fee/provenance requirements. Exit was healthy at 57 usable outcomes from 60 observed. Other
skills remained subject to their own current proof. These are bounded observations, not a complete
history or a guarantee that a future Entry Champion will qualify.

Core database live pages decreased during that review, within the configured budget. Raw-event
retention was still catching up through bounded cleanup. The separate diagnostics recorder used
about 9.2 MB of its 512 MiB budget with no current writer error or early eviction. Some collection
items were skipped under contention and intervals were labelled with gaps. Telemetry is best-effort;
it cannot prove uninterrupted performance or reconstruct missing evidence.

## Upgrade contract

v1.10.6 uses schema 15. The migration adds bounded per-season records of actual strategy use;
it preserves bankrolls, positions, accounting, settings, learning evidence and Champion history.
The v1.10.5-to-v1.10.6 update keeps Baseline v1.5 and the current feature schema. Existing saved
automatic-support permission is preserved; installations without that preference start disabled.
Current activation receipts are checked on restart. A saved Champion alone is not trading authority.

Published schema-14 images cannot open schema 15. A rollback to those images requires their matching
pre-upgrade backup. Prepare maintenance and take a consistent backup before a community upgrade;
never copy a live SQLite main file without accounting for its WAL.

## Screenshot provenance and remaining limits

The [v1.10.6 capture record](screenshots/v1.10.6-live-2026-09-07/README.md) documents fresh desktop
and mobile views of the locally deployed release. All earlier screenshot sets are preserved.
The [Coach follow-up capture](screenshots/v1.10.6-coach-2026-09-07/README.md) shows the clarified
contribution permission and explanation after the same-schema follow-up.
The capture uses real HTTP/WebSocket data, blocks write requests and changes no engine, learning,
provider or risk settings. Viewport and local graphics preferences affect presentation only.

The local maintenance handoff preserved the season, settings, data mount and active Exit support.
The provider briefly returned HTTP 413 during reconnection, then recovered automatically. Two later
processing bursts expired 2,128 low-priority candidates during the review; both episodes resolved
and current processing caught up. The receipts screenshot retains the recent-event warning, which
can remain visible after recovery while the recent-event window still contains those drops.
The paper execution audit stayed verified, training continued, and diagnostics kept recording.
Browser capture and isolated tests shared the host, so these observations do not establish the
cause of the burst or an isolated before/after performance comparison.

Real phones, different GPUs, ARM64/community hosts, provider outages and month-long storage/memory
equilibrium still require ongoing use and monitoring. Observed responsiveness does not isolate the
effect of each change, and correct learning gates do not guarantee profitable trading outcomes.
