# Security policy

## Supported versions

Security fixes are applied to the latest V1 release on the default branch.

## Reporting

Do not open a public issue for a vulnerability that could expose credentials, bypass local
authentication, corrupt the ledger, or enable transaction execution. Use GitHub's private
security advisory flow for the repository after it is published.

Include the affected version, reproduction steps, impact, and any suggested mitigation. Do not
include real private keys or seed phrases in a report—Signal Arcade should never request them.

## Deliberate boundaries

- V1 contains no Solana signing or broadcasting primitives.
- Provider secrets are environment-backed or stored in the local data volume with restricted
  file permissions. They must never appear in snapshots, logs, or browser storage. The local
  secret file is not encrypted, so host and volume administrators remain trusted.
- New secret values are accepted only over HTTPS or from a localhost URL.
- Loopback is the default. Non-loopback binds require HTTP Basic authentication.
- Native installs bind to loopback by default. The supplied Docker Compose stacks publish to LAN
  interfaces for home-server access and always require a password; set
  `SIGNAL_ARCADE_HOST_IP=127.0.0.1` when only the Docker host or a local HTTPS proxy should connect.
- State-changing HTTP requests and browser WebSocket connections are same-origin checked.
- Local AI starts Off. Shadow is observational; a separately qualified Guarded model may only
  turn a baseline ENTER into PASS. It cannot originate or resize an order, weaken a hard gate,
  control exits, access a wallet, or directly mutate the ledger.
- The supplied Ollama service is reachable only on the private Compose network, has cloud features
  disabled, and stores models outside the application data volume.
- Unknown/stale structural data, unsupported Token-2022 layouts, and unproven event provenance
  cause abstention or event rejection.

If a contribution crosses any of these boundaries, it requires a separate threat model and
must not be merged as an ordinary V1 feature.
