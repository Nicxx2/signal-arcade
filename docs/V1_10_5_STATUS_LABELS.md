# v1.10.5 skill-status wording check

Checked on 2026-09-05 after the historical battle replay update.

- Candidates still qualifying read **Candidate · collecting proof**. Qualified candidates waiting
  for a comparison read **Candidate · qualified**; the testing artifact reads **Battle contender**.
- Candidate gates and recipes use the same role label. A latest artifact that is already the saved
  Champion reads **Current Champion**.
- Completed comparison footers begin **Last battle:**. An inconclusive result does not suggest
  that the skill has no Champion. A first qualification is a **Last milestone**, without a battle.
- The solo Champion view explains that an opponent appears after qualification and entry into a
  comparison. The existing view-selection and backend qualification rules are unchanged.
- Small status labels and footers wrap instead of hiding their meaning on narrow screens.

Validation: 175 existing App/Arena checks passed; TypeScript, scoped ESLint and production build
passed. Built UI checks covered 11 scenarios at 1440, 390 and 320 pixels (33 views), including
unqualified and qualified candidates, the current Champion, no candidate, missing history,
first qualification, retention, promotion, suspension and paused learning. No browser exceptions,
API mutations or status-label overflow were observed. Desktop and mobile screenshots were inspected.
The existing lazy 3D bundle size warning remains unchanged in substance.

The local Docker update layers only the built UI and README/changelog over the verified replay
runtime. Backend source hashes are checked against both the running image and workspace before
the app's maintenance flow is used. This patch adds no learning/trading logic, RPC calls or timers.

Live verification: maintenance completed at 09:53:51 UTC. All six workers and the container were
healthy; all 33 backend files and nine built UI files matched the workspace. Season 31 retained
its 400 USDC starting bankroll, Balanced profile and 25% drawdown threshold; learning remained
Shadow. Read-only accounting checks found no imbalanced ledger transactions or orphan fills.
All four deployed skill cards were checked at 1440, 390 and 320 pixels with no browser errors,
label overflow or API writes. Exit displayed 24/30 shared outcomes after the update.
