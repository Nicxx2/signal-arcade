# v1.10.5 Entry proof and exact-tie clarification

The former “Entry's road to influence” combined the latest legacy Linear model's validation
with current shared activation gates. A skill card could simultaneously show an XGBoost candidate,
making the checklist's subject unclear.

## Behavior

- **Entry proof & activation** contains separate, initially collapsed Linear and XGBoost reports.
  Each names its latest artifact in the exact risk/configuration/baseline/feature context and
  shows that artifact's saved validation and independent Policy evidence. Thirteen Linear and
  fourteen XGBoost checks are explanations, not new qualification rules or a race percentage.
- XGBoost's additional check uses its saved complexity result against the Linear model fitted on
  the same evidence. It never substitutes a later unrelated Linear model. Either family can earn
  the first Entry crown; later contenders require common-forward comparison against the Champion.
- Activation names the engine's eligible subject separately from both latest generations. A newer
  unqualified candidate does not invalidate an older eligible Champion. Saved Champion, active
  identity, current coverage, source, mode and consent are distinct. Supported legacy Linear
  activation remains explicit; it does not invent a Champion record.
- Early Linear artifacts omitted the familiar-evidence metric. Reporting recovers it only from
  the exact immutable source-model version and matching context. If absent, malformed or nonfinite,
  evidence stays unknown. Saved artifacts are not modified. Stored qualification is authoritative;
  displayed check counts neither award a crown nor activate trading.
- Older servers fall back to explicitly labelled **Legacy Linear diagnostics**, not an XGBoost
  checklist. Existing response fields remain compatible. No controls or permissions are added.
- A saved defence with an exactly zero valid mean says **Level result · Champion retained**.
  The explanation distinguishes equal measured average from zero trading profit, unknown data or
  identical policies. Tiny positive/negative values retain their sign. A zero-width uncertainty
  interval is described as a single point; wider uncertainty remains visible.

## Safety and verification

The new `entry_proof` snapshot member and two reporting functions read existing in-memory state.
An AST comparison with the previously deployed backend confirms every existing function, import
and setting is unchanged after excluding this new field and the two reporting functions. There
are no new database writes, RPCs, model loads, training recipes, selection rules, thresholds,
activation decisions or schema changes. Existing status generation is reused; there is no extra
browser polling. A bounded offline sample on the captured live artifact set averaged about
0.96 ms per report with one CPU allocated; this is not an endurance benchmark.

The full backend regression suite passed. New cases cover exact-family attribution, current
context isolation, an older XGBoost Champion with a newer unqualified candidate, legacy/no-model
states, missing and nonfinite data, exact Linear source recovery and no status-report writes.
The final full frontend run passed all 290 cases in 17 files at bounded concurrency (39.93 seconds).
An earlier run exceeded the exhaustive motion test's five-second limit during concurrent work;
its 13-case file then passed in isolation, with 1.53 seconds of test work, and the final full run
also passed it. Backend typing and focused lint passed.

Browser checks exercised both closed and expanded proof at 1440, 390 and 320 pixels, including
actual captured artifacts, an older eligible Champion, active/paused/separate-source states,
older servers, no models, unknown measurements and long identities. Checks found no horizontal
overflow, browser exceptions or API writes. Font sizes and stacked values were then polished for
narrow screens. The initial 54 views and subsequent 18 readability checks passed. Backend lint,
all 64 Python files' CI formatting, frontend ESLint, TypeScript and the production build passed.
Two existing replay files received formatting-only cleanup; AST equivalence was verified for
the installed replay backend. The existing lazy 3D chunk warning remains unchanged.

The user's saved Bright Harbormaster/Steady Trailkeeper Exit comparison remains unchanged:
30 usable of 32 observed outcomes (93.8% coverage), all 12 stored checkpoint means exactly zero,
and the saved Champion retained. Both stored policies selected a 60-second review for this record.
That specific explanation is supported by its saved policies; the generic UI does not infer
identical policies from a tied average.

## Deployment and live checks

Staged and deployed as `signal-arcade:v1.10.5-entry-proof`, image
`sha256:95d8909e06b46368ff99d140634ede90f496d96d6353be348ff0f22ac11ab485`.
Maintenance operation `fed3c66eba8744f999137d02bc98e68e` prepared the app before replacement.
Rollback is available as `signal-arcade:v1.10.5-before-entry-proof`.

Preflight checked all 33 installed backend files, the normalized behavior of every existing
backend function, all nine built UI files and the README. After replacement the running files
matched the workspace. Initial requests arrived during startup and were retried after Docker
reported healthy; no crash or restart loop occurred. All six workers and trading resumed.

Season 31 retained its original data mount, 400 USDC start, Balanced settings, custom 25% drawdown,
Shadow learning and season identity. Database schema remains 14. Checks found no imbalanced ledger
transactions or orphan fills. The live API exposes each family's own current artifact and gates;
six live desktop/phone proof views passed, including 12 px explanatory text on narrow screens.

The user's exact historical Exit recording passed another 12 live views at 1440, 390 and 320 px.
All checkpoint counts and exact-zero measurements remained intact. The new level-result wording
and profit distinction appeared correctly. Playback reused one canvas, made one successful replay
GET and no writes, with no horizontal overflow or browser exceptions.

The final 30.9-second runtime sample processed 2,489 events with no new drops, sampled queue depth
at most 132, critical lag at most 0.0458 seconds, all workers healthy and no degraded reasons.
Snapshot ages were 4.1 and 6.9 seconds. These are short deployment observations, not a guarantee
of long-term performance or profitability; the planned multi-hour observation is still useful.

## Additional compatibility edge-case review

An unsupported or incomplete proof-report envelope could reach the summary before the legacy
fallback and throw a browser exception. An unsupported version with a Champion field could also
contribute a misleading summary. Five regression cases reproduced these problems before the fix.
The panel and summary now share a version/envelope check. Unsupported versions, missing activation,
missing family lists and missing shared-gate lists use explicitly labelled Linear diagnostics;
the unknown report does not contribute Champion evidence. Normal v1 proof remains unchanged.

All 149 targeted Learning/proof/battle tests passed, including the five new cases. TypeScript,
ESLint and the production build passed. Thirty production-preview browser checks covered valid,
unsupported and incomplete reports at 1440, 390 and 320 px, both collapsed and expanded, without
overflow, browser exceptions or writes. This adjustment changes only UI handling and release text;
all 33 installed backend files remain byte-for-byte identical.

The UI-only image is `signal-arcade:v1.10.5-entry-proof-compat`,
`sha256:2a1e4df9b50cf429607a36f4e3137e145dc411215f3f4c34ee4aae3d46315301`.
Its predecessor is retained as `signal-arcade:v1.10.5-before-entry-proof-compat`.

Maintenance operation `aa9c52b0e34e4a5b9f7139247bd71f6e` completed the update. Live file hashes,
six desktop/mobile proof views and 12 historical replay views passed again. Season 31, its data
mount and settings were preserved; all six workers were healthy, with no restart loop, ledger
imbalances or orphan fills. README and built UI matched the staged image.

The final 32-second sample processed 2,957 events with zero new drops and no degraded reasons.
An initial queue of 590 and critical lag of 1.76 seconds cleared to zero queued events and 0.039
seconds at the next sample; the final critical lag was 0.024 seconds. Snapshot ages were 1.7 and
10.0 seconds. This shows a recovered burst during the short check, not proof of constant latency.
No further defect was found in this focused review; multi-hour observation remains the next step.
