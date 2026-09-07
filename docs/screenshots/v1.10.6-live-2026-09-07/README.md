# Signal Arcade v1.10.6 — live screenshots

Captured on **7 September 2026** from the locally deployed v1.10.6 release image:
`sha256:2dfd59e896c5723b73af74ca4517c1de42fb728404d345fcab39f8ec7fd76a18`. Earlier screenshot folders remain unchanged.

The 18 PNGs use actual live HTTP/WebSocket data in a fresh headless Microsoft Edge profile,
with `en-GB` formatting, Europe/London time and Low 3D graphics. Desktop viewports are 1440 pixels
wide and 1040–1440 high; mobile views use 390×1000. Individual cards are captured at their rendered
size. The manifest records exact dimensions, timestamps, hashes and captions.

No synthetic responses, altered figures, hidden warnings or selected performance winners are used.
The captured live comparison was Exit; the recorded comparison was the latest available recap.
Results uses the default comparison group, and Replay inspection selects an early checkpoint by
keyboard rather than choosing a peak. The receipts image was retaken only to bring the table heading
below the fixed navigation bar. Viewport captures may end partway through longer pages.
The receipts view retains a real recent-processing warning; it was not hidden or retouched.

The capture blocks HTTP write requests and opens no credential editor. Engine, learning, provider
and risk settings were unchanged. Automatic Champion support was already enabled, with Exit active
and Sizing still awaiting its current activation proof. These states and all numbers are time-specific,
not promises of profitability or future qualification.

The run received 239 WebSocket frames and recorded no page exceptions, failed
non-authentication HTTP responses or attempted mutations. All images were visually inspected.

| Image | View |
| --- | --- |
| [01-arena-overview.png](01-arena-overview.png) | Live paper Arena: equity, risk profile, positions and engine status. |
| [02-decision-board.png](02-decision-board.png) | Current decision board with real point-in-time evidence. |
| [03-season-progress.png](03-season-progress.png) | Default season comparison and recorded strategy use; no performance group was selected for a better result. |
| [04-learning-lab.png](04-learning-lab.png) | Statistical Challenger training, saved permission and actual independently qualified skill support. |
| [05-data-providers.png](05-data-providers.png) | Provider roles, budgets and current activity; no secret editor is opened. |
| [06-local-ai.png](06-local-ai.png) | Installed local AI models and runtime information. |
| [07-mobile-arena.png](07-mobile-arena.png) | Live paper Arena on a 390-pixel mobile viewport. |
| [08-replay-receipts.png](08-replay-receipts.png) | Latest paper fill receipts with the heading, fees, impact and latency visible. |
| [09-ai-coach-room.png](09-ai-coach-room.png) | Optional AI Coach research, separate from trading authority. |
| [10-skill-progress.png](10-skill-progress.png) | Entry, Manipulation, Sizing and Exit: current candidates, saved Champions and proof gates. |
| [11-champion-arena.png](11-champion-arena.png) | A live Exit comparison: measured advantage and uncertainty, not win probability. |
| [12-reigning-champions.png](12-reigning-champions.png) | Current saved Champions with stable portraits and recorded crown retentions. |
| [13-recorded-battle.png](13-recorded-battle.png) | A saved battle result replayed from the recorded comparison. |
| [14-mobile-battle.png](14-mobile-battle.png) | Mobile live battle, with the same fighters and measured evidence. |
| [15-diagnostics-history.png](15-diagnostics-history.png) | Separate bounded diagnostics history for reviewing long-term operation. |
| [16-entry-profile.png](16-entry-profile.png) | The current Entry model profile, with its family identity and real proof status. |
| [17-mobile-evidence.png](17-mobile-evidence.png) | Mobile advantage readout with timestamp, uncertainty and sample requirements. |
| [18-replay-equity.png](18-replay-equity.png) | Keyboard inspection of a saved equity checkpoint; no best-performing point was selected. |

## Reproducing a new capture

Use [the read-only capture script](../../../scripts/capture_live_readme_screenshots.mjs) with an
external Playwright installation and an installed Chromium browser. It reads the expected version
from the repository package metadata and refuses to overwrite an existing output folder.
Set `SIGNAL_ARCADE_CAPTURE_PASSWORD` in the process environment, never in command arguments or a
committed file. Set `SIGNAL_ARCADE_CAPTURE_OUTPUT` to a new directory;
`SIGNAL_ARCADE_CAPTURE_PLAYWRIGHT` may point at the external Playwright package and
`SIGNAL_ARCADE_CAPTURE_BROWSER` selects the browser channel (`msedge` here). The optional
`SIGNAL_ARCADE_CAPTURE_URL` defaults to localhost port 8765.

The full gallery requires a running mainnet paper app, saved Champions, an active battle and
a recorded recap. An incomplete run records its failure; it does not invent absent UI states.
