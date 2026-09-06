# Live v1.10.5 screenshots — 6 September 2026

These 17 PNGs were captured from the running paper app on mainnet data between
08:23 and 08:27 BST (07:23–07:27 UTC). They replace the older images linked from
the repository README; earlier screenshot folders are preserved.

The images show actual results, model generations, proof gates and warnings at capture time.
No figures, responses or warnings were substituted or hidden. The saved Exit comparison is
level; the live Sizing comparison has a preliminary advantage. Neither establishes profitability.
Screenshots taken seconds apart can show different evidence timestamps or refresh states.

## Capture method

- Headless Chrome, `en-GB`, `Europe/London`, device scale factor 1.
- Desktop viewport: 1440 × 1040; Champion dialogs: 1440 × 1440; mobile: 390 × 1000.
- Viewport screenshots and direct component screenshots; no image post-processing.
  Scrollable views show the visible portion, rather than every item in their history.
- Low 3D graphics selected only in the isolated browser's local preferences.
- Authenticated, read-only navigation. All attempted app writes were blocked; none occurred.
  No settings, trading controls, model downloads or learning permissions were changed.
- The diagnostics card was recaptured below the sticky header. All 17 images were inspected
  for readability and exposed credentials. No browser errors or failed HTTP responses occurred.

[capture.json](capture.json) records individual timestamps, dimensions, byte counts, SHA-256
hashes and the source Docker image. The complete image set is approximately 3.7 MiB.
This is a documentation capture, not an endurance or profitability test. See the
[release review](../../V1_10_5_FINAL_RELEASE_REVIEW.md) and
[Arena follow-up](../../V1_10_5_ARENA_CONTINUITY.md) for runtime verification and remaining observation.

## Views

| Screenshot | View |
| --- | --- |
| [01](01-arena-overview.png) | Paper Arena, equity and season settings |
| [02](02-decision-board.png) | Current decisions |
| [03](03-season-progress.png) | Default season comparison |
| [04](04-learning-lab.png) | Challenger learning overview |
| [05](05-data-providers.png) | Provider roles, budgets and activity |
| [06](06-local-ai.png) | Local AI models |
| [07](07-mobile-arena.png) | Mobile Arena |
| [08](08-replay-receipts.png) | Replay receipts and modeled friction |
| [09](09-ai-coach-room.png) | AI Coach research |
| [10](10-skill-progress.png) | Four independent skill cards |
| [11](11-champion-arena.png) | Live Sizing comparison and uncertainty |
| [12](12-reigning-champions.png) | Saved Champions and crown retentions |
| [13](13-recorded-battle.png) | Recorded Exit comparison and result |
| [14](14-mobile-battle.png) | Mobile live comparison |
| [15](15-diagnostics-history.png) | Separate diagnostics history allowance |
| [16](16-entry-profile.png) | Current XGBoost Entry contender and proof |
| [17](17-mobile-evidence.png) | Mobile measured advantage and sample requirements |

## Capture a later set

Use [the headless capture script](../../../scripts/capture_live_readme_screenshots.mjs) from the
repository root with Node.js, Playwright and Chrome available. Playwright is a documentation
tool; it is not added to the app's runtime dependencies. The script expects a v1.10.5 paper app
on mainnet data, an active Sizing battle and a saved comparison. If those views are unavailable,
it fails with a partial capture record rather than fabricating a demonstration.

Supply `SIGNAL_ARCADE_CAPTURE_PASSWORD` securely through the process environment, not a command
argument or committed file. Set `SIGNAL_ARCADE_CAPTURE_OUTPUT` to a **new** directory inside
`docs/screenshots/`; its parent must already exist. The script refuses to overwrite any folder.

Optional environment variables are `SIGNAL_ARCADE_CAPTURE_URL` (default
`http://127.0.0.1:8765/`), `SIGNAL_ARCADE_CAPTURE_PLAYWRIGHT` (external module path),
`SIGNAL_ARCADE_CAPTURE_BROWSER` (default `chrome`) and `SIGNAL_ARCADE_CAPTURE_IMAGE`
(source image identifier for provenance).

```sh
node scripts/capture_live_readme_screenshots.mjs
```

Inspect every image and the completed capture record before updating the README links.
Never publish a partial or failed capture as a verified set.
