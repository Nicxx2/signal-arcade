# Contributing

Thank you for helping improve Signal Arcade.

1. Keep V1 paper-only. Never add private-key, seed-phrase, signing, or broadcast code.
2. Open an issue before changing execution math, accounting, risk gates, or stored schemas.
3. Preserve point-in-time evidence: no future data may influence an earlier decision or fill.
4. Represent unavailable data as unknown with a reason; never substitute zero silently.
5. Add tests for malformed provider responses, stale data, rounding, and recovery paths.
6. Run every command in the README verification section before opening a pull request.

Use small commits and explain assumptions in the pull request. UI changes should remain usable
at 360 px width, with keyboard focus and readable contrast.

