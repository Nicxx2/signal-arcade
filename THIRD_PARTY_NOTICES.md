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

Champion Arena uses Three.js 0.185.1 and its `BufferGeometryUtils` helper, distributed under the
MIT license below. `@types/three` 0.185.4 supplies development-only type definitions. The robots,
segmented rigs, static SVG portraits, stage geometry and animation recipe are original application
code. There are no downloaded character models, texture packs, external fonts or audio assets.

### Three.js license

Copyright © 2010-2026 three.js authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

### Other runtime dependencies

The optional statistical Challenger uses the CPU-only XGBoost 3.4.1 Python package, distributed
under the Apache License 2.0. Signal Arcade fixes its recipe, thread budget, and random seed and
stores only application-created, digest-verified model JSON.

Solders 0.29.0 supplies Solana public-key and program-derived-address validation for on-chain
reserve snapshots. Its package metadata and bundled license accompany the installed dependency.
Fee calculations were checked against the official `@pump-fun/pump-sdk` 1.36.0 and
`@pump-fun/pump-swap-sdk` 1.19.0. These SDKs are reference implementations, not runtime dependencies
bundled into the app; the pinned local IDLs keep decoding deterministic.

The reserve-account compatibility adapter and fee rules also reference the official
`pump-rust-client` 0.1.13, published on 2026-09-09 and linked from the official Pump documentation.
The package declares the MIT license. A scoped account-definition subset is retained as the
independent test fixture `tests/fixtures/pump_rust_account_contract_0_1_13.json`; the Rust runtime,
program binaries and SDK source are not bundled into the application. Package source:
https://crates.io/crates/pump-rust-client/0.1.13.
Reviewed archive SHA-256: `29a237bca320b7bad7b4a9ca900dbf93236a1ca4527464b87777426a63de1a6d`.

Holder-reward account and event definitions are referenced from official `pump-fun/pump-public-docs`
revision `f216b6724c6ede79d7cef9ce210b741f7e17e93b`, merged on 2026-09-12. The scoped independent
fixture `tests/fixtures/pump_holder_rewards_contract_20260912.json` records source URLs and hashes;
the runtime event IDLs remain unchanged. Account/fee semantics are described at
https://github.com/pump-fun/pump-public-docs/blob/f216b6724c6ede79d7cef9ce210b741f7e17e93b/docs/HOLDER_REWARDS_README.md.

The supplied Compose stacks reference the official `ollama/ollama:0.33.1` image as a separate
optional service. Ollama is distributed under its upstream MIT license; it is not copied into the
Signal Arcade application image. Models downloaded by a user remain separate artifacts and may
have their own licenses, which the user should review on the official Ollama model page before
redistribution or commercial use.
