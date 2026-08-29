# Provider matrix

| Provider | Key required | Data received | Decision/execution role | Failure behavior |
|---|---:|---|---|---|
| Standard Solana RPC | No | Pump/PumpSwap program logs over WebSocket; mint account bytes over HTTP | Core trade flow, reserves, fees, safety and paper fills | Reconnect; abstain if structural evidence is missing |
| DEX Screener | No | Secondary USD/native prices, liquidity, volume, transactions, market cap and base-token display label | USD context and internally consistent SOL/USD conversion; a bounded name/symbol fallback is display-only and never enters scoring; on-chain reserves and trade flow remain authoritative | Record unknown/stale; unresolved identity shows a shortened mint; SOL paper trading continues, while new USDC entries abstain without a fresh conversion |
| Jupiter API | Optional | Price/route/order response when explicitly called | Adapter only; idle in V1 decisions and paper fills | No effect on V1 trading |
| Ollama | No, local | Plain-English explanations or strict structured criticism of a completed baseline ENTER using normalized saved evidence | Off by default; Shadow has no influence; a separately qualified Guarded model may only veto an entry | Deterministic explanation fallback; invalid/timed-out criticism is ignored and recorded |

The Docker stacks provide Ollama on a private internal network with cloud features disabled and
no published host port. CPU inference is the default; explicit NVIDIA and AMD overlays are
available. Ollama availability never participates in baseline trading health, and its separate
model volume is outside the application storage budget.

No SolanaTracker subscription is required. Users can place a private RPC URL in the standard
Solana HTTP/WebSocket settings without adding provider-specific code.

The Settings UI accepts one write-only API key for the bundled Helius, Alchemy, and SolanaTracker
RPC presets and constructs that provider's mainnet HTTP and WebSocket URLs automatically. Custom
RPC or paid-plan users can instead enter explicit endpoints and limits. Selecting Public RPC
clears saved UI endpoint overrides and restores the environment-configured or bundled endpoint.

Helius, SolanaTracker RPC, and other compatible keyed RPC services do not introduce a different
Pump data vocabulary. They transport the same standard Solana `logsSubscribe` and
`getAccountInfo` requests. A key can improve capacity, retention, and connection reliability,
but it does not silently add new model features. HTTP and WebSocket URLs should belong to the
intended provider/network; switching the stream stops the paper engine and cancels pending orders
before reconnecting.

DEX Screener enrichment uses the documented chain-qualified token endpoint and a central
300-request/minute ceiling. The orchestrator enriches at most 20 recent candidates and waits at
least 60 seconds per candidate. Responses are accepted only when the requested mint is the base
token. Name and symbol are bounded, normalized and used only when the official event did not carry
an identity; they never influence scores, gates, decisions, fills, or learning. Negative/non-finite
values are rejected, each provider has its own observation timestamp, and `priceUsd / priceNative`
supplies one internally consistent SOL/USD rate. DEX context is not treated as a substitute for
the newer on-chain event stream.

## Normalization and disagreement rules

- Only official Pump `TradeEvent` and PumpSwap `BuyEvent`/`SellEvent` records are executable paper
  ticks. Pool deposits, withdrawals, migrations, boosts, and creator metadata updates may refresh
  state but can never fill an order.
- The bundled Pump and PumpSwap IDLs are pinned official schemas. Event discriminators are scoped
  to the emitting program so identical event names in both programs cannot decode as each other.
- Missing, malformed, unsupported, stale, or rate-limited values remain unknown. They are never
  converted to zero or invented by the local AI.
- Provider and token text never becomes an AI instruction. The critic receives a fixed allowlist
  of numeric evidence plus saved baseline reasons/blockers, and any unknown evidence citation or
  schema field invalidates the response.
- On-chain reserves and integer curve math control paper fills. Secondary APIs may enrich context
  or currency conversion, but disagreement cannot rewrite the observed on-chain trade.

## Verified limits (2026-08-26)

| Preset | Provider allowance | Signal Arcade policy |
|---|---|---|
| Solana public RPC | 100 requests/10 seconds/IP; 40/10 seconds per RPC method | 120 tracked HTTP calls/minute; one WebSocket with two subscriptions |
| Helius Free | 10 RPC requests/second; 1M credits/month; standard WSS costs 2 credits/0.1 MB uncompressed | 600/minute; 500k tracked HTTP calls/month, leaving at least half the published credits outside the HTTP budget |
| Alchemy Free | 30M CU/month; `getAccountInfo` costs 10 CU; Solana WSS costs 0.0002 CU/byte | 3,000/minute; 1.5M tracked HTTP calls/month (15M CU), leaving at least 15M CU outside the HTTP budget |
| SolanaTracker RPC Free | 10 general requests/second; 500k credits/month; 2 WebSocket connections | 300/minute; 250k tracked HTTP calls/month, then 10% routine reserve |
| Jupiter keyless | 0.5 requests/second | 30/minute; adapter is idle in V1 |
| Jupiter Free key | 1 request/second, unlimited credits | 60/minute; adapter is idle in V1 |

The keyed Solana presets leave at least half the published allowance outside Signal Arcade's HTTP
budget because WebSocket data consumes provider credits by uncompressed byte. This is a reserve,
not a guarantee: Pump and PumpSwap traffic varies, and Signal Arcade cannot see streamed-byte
usage, account-wide usage, other applications using the key, or billing adjustments. Confirm the
real projection in the provider dashboard after a representative day. Paid Jupiter presets match
its published included-credit tiers, but a smaller custom hard cap is safer when a key is shared.

Sources: [Solana public endpoints](https://solana.com/docs/references/clusters),
[DEX Screener API](https://docs.dexscreener.com/api/reference),
[Helius pricing](https://www.helius.dev/pricing),
[Helius credits](https://www.helius.dev/docs/billing/credits),
[Alchemy plans](https://www.alchemy.com/docs/reference/pricing-plans),
[Alchemy compute-unit costs](https://www.alchemy.com/docs/reference/compute-unit-costs),
[SolanaTracker RPC limits](https://docs.solanatracker.io/solana-rpc/credits-and-rate-limits), and
[Jupiter plans](https://developers.jup.ag/docs/portal/plans).
