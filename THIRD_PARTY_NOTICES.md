# Third-party notices

Signal Arcade vendors two machine-readable Anchor IDLs from the official
`pump-fun/pump-public-docs` repository:

- `backend/signal_arcade/resources/idl/pump.json`
- `backend/signal_arcade/resources/idl/pump_amm.json`

They were retrieved from the upstream `main` branch on 2026-08-26. They are retained as data so
event discriminators and field layouts are reviewable and deterministic. Check upstream terms
and changes before redistributing a modified copy.

- `pump.json` SHA-256: `B90BC471327F671449271D5D1D42354D1FAE6F5A06502F5834459A3108138E49`
- `pump_amm.json` SHA-256: `6B5C7EC4E5EF9742FA99DC57B0D75B1031B379BBA02A7E1B3C5A4CAD68D77E56`

Application dependencies and their licenses are recorded by `pyproject.toml`, `package.json`,
and `pnpm-lock.yaml`. No source code was copied from the untrusted reference bot repository that
motivated the project.

The optional statistical Challenger uses the CPU-only XGBoost 3.4.1 Python package, distributed
under the Apache License 2.0. Signal Arcade fixes its recipe, thread budget, and random seed and
stores only application-created, digest-verified model JSON.

The supplied Compose stacks reference the official `ollama/ollama:0.33.1` image as a separate
optional service. Ollama is distributed under its upstream MIT license; it is not copied into the
Signal Arcade application image. Models downloaded by a user remain separate artifacts and may
have their own licenses, which the user should review on the official Ollama model page before
redistribution or commercial use.
