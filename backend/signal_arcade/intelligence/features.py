from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from threading import RLock
from typing import Any

from ..models import DataValue, EventKind, FeatureSnapshot, MarketEvent, Side

LAMPORTS_PER_SOL = 1_000_000_000
PUMP_TOKEN_DECIMALS = 1_000_000
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"
NATIVE_SOL_MINT = "11111111111111111111111111111111"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # noqa: S105
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105


def _value(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _number(payload: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = _value(payload, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class TradeObservation:
    received_at: datetime
    slot: int
    side: Side
    user: str
    token_units: int
    quote_lamports: int
    price_sol: float
    signature: str = ""
    venue: str = "pump_curve"


IntegrityMetric = tuple[float | None, float, str | None]


@dataclass(slots=True)
class RollingTradeMetrics:
    """At-most-one-second structural view of the bounded five-minute trade window."""

    computed_at: datetime
    venue: str
    trades_1m: tuple[TradeObservation, ...]
    trades_5m: tuple[TradeObservation, ...]
    buys_1m: int
    buys_5m: int
    buy_ratio: float
    users: frozenset[str]
    wallet_volume_hhi: float
    repeated_amount_ratio: float
    same_slot_ratio: float
    integrity: dict[str, IntegrityMetric]
    window_span_seconds: float
    buffer_saturated: bool


@dataclass(slots=True)
class TokenState:
    mint: str
    name: str = "Unknown token"
    symbol: str = "?"
    identity_source: str = "unavailable"
    uri: str = ""
    creator: str = ""
    venue: str = "pump_curve"
    curve_address: str = ""
    pool_address: str = ""
    pool_base_token_account: str = ""
    pool_quote_token_account: str = ""
    quote_mint: str = WRAPPED_SOL_MINT
    route_verified: bool = False
    token_program: str = ""
    created_at: datetime | None = None
    last_event_at: datetime | None = None
    last_event_id: str | None = None
    last_slot: int = 0
    last_reserve_at: datetime | None = None
    last_reserve_slot: int = 0
    reserve_source: str = ""
    # Exact provenance for the reserve state used by paper execution. These fields are kept in
    # memory and copied into immutable fill receipts; raw trade rows may later be pruned.
    last_reserve_event_id: str | None = None
    last_reserve_signature: str | None = None
    virtual_token_reserves: int = 0
    virtual_quote_reserves: int = 0
    real_token_reserves: int = 0
    # Exact spendable quote liquidity when the source exposes it. None keeps legacy/replay
    # evidence usable without pretending that an unobserved vault balance is zero.
    real_quote_reserves: int | None = None
    initial_real_token_reserves: int = 0
    token_total_supply: int = 0
    complete: bool = False
    fee_bps: int = 0
    trades: deque[TradeObservation] = field(default_factory=lambda: deque(maxlen=5_000))
    last_evicted_trade: TradeObservation | None = None
    rolling_trade_metrics: RollingTradeMetrics | None = None
    sources: set[str] = field(default_factory=set)
    enrichment: dict[str, Any] = field(default_factory=dict)
    enrichment_times: dict[str, datetime] = field(default_factory=dict)

    def apply(self, event: MarketEvent) -> None:
        payload = event.payload
        # The live orchestrator rejects queue-order and slot regressions before this method. A
        # monotonic effective timestamp is still required for direct integrations and for the
        # rare case where a host clock is corrected backwards while slots continue forwards.
        effective_at = max(
            observed_at
            for observed_at in (
                event.received_at,
                self.last_event_at,
                self.last_reserve_at,
            )
            if observed_at is not None
        )
        reserve_observed = any(
            _number(payload, key) > 0
            for key in (
                "virtual_token_reserves",
                "virtualTokenReserves",
                "virtual_sol_reserves",
                "virtualSolReserves",
                "virtual_quote_reserves",
                "virtualQuoteReserves",
                "pool_base_token_reserves",
                "poolBaseTokenReserves",
                "pool_base_amount",
                "poolBaseAmount",
                "base_reserves_after",
                "baseReservesAfter",
                "pool_quote_token_reserves",
                "poolQuoteTokenReserves",
                "pool_quote_amount",
                "poolQuoteAmount",
                "real_quote_reserves_after",
                "realQuoteReservesAfter",
            )
        )
        if event.kind != EventKind.MARKET:
            self.last_event_at = effective_at
            self.last_event_id = event.event_id
        self.last_slot = max(self.last_slot, event.slot or 0)
        self.sources.add(event.source)
        curve = _value(payload, "bonding_curve", "bondingCurve")
        if isinstance(curve, str) and 30 <= len(curve) <= 50:
            self.curve_address = curve
        quote_mint = _value(payload, "quote_mint", "quoteMint")
        # Once an AMM route is confirmed from its exact program-owned Pool account, later log
        # payloads for that same pool cannot replace the pinned quote. A newly observed pool below
        # clears route verification and may carry an untrusted provisional quote until RPC checks
        # it.
        if isinstance(quote_mint, str) and not (self.venue == "pump_swap" and self.route_verified):
            self.quote_mint = quote_mint
        token_program = _value(payload, "token_program", "tokenProgram")
        if isinstance(token_program, str):
            self.token_program = token_program
        latest_creator = _value(
            payload,
            "new_coin_creator",
            "newCoinCreator",
            "new_creator",
            "newCreator",
            "coin_creator",
            "coinCreator",
            "creator",
        )
        if isinstance(latest_creator, str):
            self.creator = latest_creator
        if event.kind == EventKind.CREATE:
            name = _bounded_display_text(_value(payload, "name"), 100)
            symbol = _bounded_display_text(_value(payload, "symbol"), 30)
            if name:
                self.name = name
            if symbol:
                self.symbol = symbol
            if name or symbol:
                self.identity_source = "pump_create_event"
            self.uri = str(_value(payload, "uri", default=""))[:500]
            self.creator = str(
                _value(
                    payload,
                    "coin_creator",
                    "coinCreator",
                    "creator",
                    "user",
                    default="",
                )
            )
            timestamp = _number(payload, "timestamp")
            self.created_at = (
                datetime.fromtimestamp(timestamp, UTC)
                if timestamp > 1_500_000_000
                else effective_at
            )
            self.token_total_supply = _number(
                payload, "token_total_supply", "tokenTotalSupply", default=self.token_total_supply
            )
        if event.kind in {EventKind.COMPLETE, EventKind.MIGRATE}:
            self.complete = True
        is_amm = "pAMMBay6" in event.source or str(payload.get("event_name", "")).lower() in {
            "buyevent",
            "sellevent",
            "createpoolevent",
        }
        route_regression = self.venue == "pump_swap" and self.route_verified and not is_amm
        if is_amm:
            self.venue = "pump_swap"
            pool = _value(payload, "pool")
            if isinstance(pool, str) and pool != self.pool_address:
                self.pool_address = pool
                self.route_verified = False
                if isinstance(quote_mint, str):
                    self.quote_mint = quote_mint
            pool_base = _number(
                payload,
                "pool_base_token_reserves",
                "poolBaseTokenReserves",
                "pool_base_amount",
                "poolBaseAmount",
                "base_reserves_after",
                "baseReservesAfter",
            )
            pool_quote = _number(
                payload,
                "pool_quote_token_reserves",
                "poolQuoteTokenReserves",
                "pool_quote_amount",
                "poolQuoteAmount",
                "real_quote_reserves_after",
                "realQuoteReservesAfter",
            )
            pool_quote_observed = _value(
                payload,
                "pool_quote_token_reserves",
                "poolQuoteTokenReserves",
                "pool_quote_amount",
                "poolQuoteAmount",
                "real_quote_reserves_after",
                "realQuoteReservesAfter",
            )
            virtual_quote = _number(payload, "virtual_quote_reserves", "virtualQuoteReserves")
            if pool_base > 0:
                self.virtual_token_reserves = pool_base
                self.real_token_reserves = pool_base
                if self.initial_real_token_reserves == 0:
                    self.initial_real_token_reserves = pool_base
            if pool_quote > 0:
                self.virtual_quote_reserves = max(1, pool_quote + virtual_quote)
            if pool_quote_observed is not None and pool_quote >= 0:
                self.real_quote_reserves = pool_quote
        # Buyback/cashback fields describe redistribution of other fees; charging them again as
        # a percentage of gross output substantially understates a PumpSwap sell.
        fee_keys = (
            (
                ("lp_fee_basis_points", "lpFeeBasisPoints"),
                ("protocol_fee_basis_points", "protocolFeeBasisPoints"),
                ("coin_creator_fee_basis_points", "coinCreatorFeeBasisPoints"),
            )
            if is_amm
            else (
                ("fee_basis_points", "feeBasisPoints"),
                ("creator_fee_basis_points", "creatorFeeBasisPoints"),
            )
        )
        observed_fee_bps = sum(_number(payload, *keys) for keys in fee_keys)
        if not route_regression and 0 < observed_fee_bps <= 5_000:
            self.fee_bps = observed_fee_bps
        if not is_amm and not route_regression:
            self.virtual_token_reserves = _number(
                payload,
                "virtual_token_reserves",
                "virtualTokenReserves",
                default=self.virtual_token_reserves,
            )
            self.virtual_quote_reserves = _number(
                payload,
                "virtual_sol_reserves",
                "virtualSolReserves",
                "virtual_quote_reserves",
                "virtualQuoteReserves",
                default=self.virtual_quote_reserves,
            )
            real_quote_observed = _value(
                payload,
                "real_quote_reserves",
                "realQuoteReserves",
                "real_sol_reserves",
                "realSolReserves",
            )
            if real_quote_observed is not None:
                real_quote = _number(
                    payload,
                    "real_quote_reserves",
                    "realQuoteReserves",
                    "real_sol_reserves",
                    "realSolReserves",
                    default=-1,
                )
                if real_quote >= 0:
                    self.real_quote_reserves = real_quote
        if not route_regression:
            self.real_token_reserves = _number(
                payload,
                "real_token_reserves",
                "realTokenReserves",
                default=self.real_token_reserves,
            )
        if self.initial_real_token_reserves == 0 and self.real_token_reserves > 0:
            self.initial_real_token_reserves = self.real_token_reserves
        if (
            not route_regression
            and reserve_observed
            and self.virtual_token_reserves > 0
            and self.virtual_quote_reserves > 0
        ):
            self.last_reserve_at = (
                max(self.last_reserve_at, effective_at)
                if self.last_reserve_at is not None
                else effective_at
            )
            self.last_reserve_slot = max(self.last_reserve_slot, event.slot or 0)
            self.reserve_source = event.source
            self.last_reserve_event_id = event.event_id
            self.last_reserve_signature = event.signature
        if event.kind == EventKind.TRADE and not route_regression:
            self._apply_trade(event, effective_at=effective_at)

    def _apply_trade(self, event: MarketEvent, *, effective_at: datetime) -> None:
        payload = event.payload
        event_name = str(payload.get("event_name") or "").lower()
        is_buy = _value(payload, "is_buy", "isBuy")
        if is_buy is None:
            is_buy = "buy" in event_name
        side = Side.BUY if bool(is_buy) else Side.SELL
        token_units = _number(
            payload,
            "token_amount",
            "tokenAmount",
            "base_amount_out" if side == Side.BUY else "base_amount_in",
            "baseAmountOut" if side == Side.BUY else "baseAmountIn",
        )
        quote_lamports = _number(
            payload,
            "sol_amount",
            "solAmount",
            "quote_amount_in" if side == Side.BUY else "quote_amount_out",
            "quoteAmountIn" if side == Side.BUY else "quoteAmountOut",
        )
        price = self.price_sol
        if token_units > 0 and quote_lamports > 0:
            price = (quote_lamports / LAMPORTS_PER_SOL) / (token_units / PUMP_TOKEN_DECIMALS)
        if self.trades.maxlen is not None and len(self.trades) >= self.trades.maxlen:
            self.last_evicted_trade = self.trades[0]
        self.trades.append(
            TradeObservation(
                received_at=effective_at,
                slot=event.slot or 0,
                side=side,
                user=str(_value(payload, "user", default="unknown")),
                token_units=max(0, token_units),
                quote_lamports=max(0, quote_lamports),
                price_sol=max(0.0, price),
                signature=event.signature or "",
                venue=self.venue,
            )
        )

    @property
    def price_sol(self) -> float:
        if self.virtual_token_reserves <= 0 or self.virtual_quote_reserves <= 0:
            return 0.0
        return (self.virtual_quote_reserves / LAMPORTS_PER_SOL) / (
            self.virtual_token_reserves / PUMP_TOKEN_DECIMALS
        )


class FeatureEngine:
    def __init__(self, *, stale_market_seconds: int = 20) -> None:
        self.tokens: dict[str, TokenState] = {}
        self.stale_market_seconds = stale_market_seconds
        # UI snapshots are assembled in a worker thread so large database reads cannot
        # stall the market event loop. Protect the in-memory feature state while that
        # thread reads it; otherwise a live trade can mutate a deque mid-snapshot.
        self._lock = RLock()

    def apply(self, event: MarketEvent) -> TokenState | None:
        with self._lock:
            mint = event.mint
            if not mint:
                return None
            state = self.tokens.get(mint)
            if state is None:
                state = TokenState(mint=mint)
                self.tokens[mint] = state
            event_is_amm = "pAMMBay6" in event.source or str(
                event.payload.get("event_name", "")
            ).lower() in {"buyevent", "sellevent", "createpoolevent"}
            if (
                event.kind == EventKind.TRADE
                and state.venue == "pump_swap"
                and state.route_verified
                and not event_is_amm
            ):
                return state
            state.apply(event)
            return state

    def add_enrichment(
        self,
        mint: str,
        data: dict[str, Any],
        at: datetime | None = None,
        *,
        source: str,
    ) -> None:
        with self._lock:
            state = self.tokens.get(mint)
            if state is None:
                return
            state.enrichment.update(data)
            state.enrichment_times[source] = at or datetime.now(UTC)
            if source == "dexscreener":
                fallback_name = _bounded_display_text(data.get("base_token_name"), 100)
                fallback_symbol = _bounded_display_text(data.get("base_token_symbol"), 30)
                identity_added = False
                if state.name == "Unknown token" and fallback_name:
                    state.name = fallback_name
                    identity_added = True
                if state.symbol == "?" and fallback_symbol:
                    state.symbol = fallback_symbol
                    identity_added = True
                if identity_added:
                    state.identity_source = (
                        "dexscreener"
                        if state.identity_source == "unavailable"
                        else "pump_create_event+dexscreener"
                    )

    def prune(self, inactive_before: datetime, keep_mints: set[str]) -> int:
        with self._lock:
            stale = [
                mint
                for mint, state in self.tokens.items()
                if mint not in keep_mints
                and state.last_event_at is not None
                and state.last_event_at < inactive_before
            ]
            for mint in stale:
                self.tokens.pop(mint, None)
            return len(stale)

    def snapshot(self, mint: str, now: datetime | None = None) -> FeatureSnapshot | None:
        with self._lock:
            state = self.tokens.get(mint)
            if state is None:
                return None
            return self._snapshot_state(state, now or datetime.now(UTC))

    def position_snapshot(
        self,
        mint: str,
        now: datetime | None = None,
    ) -> FeatureSnapshot | None:
        """Build a held-position snapshot whose route freshness may come from exact RPC state."""

        with self._lock:
            state = self.tokens.get(mint)
            if state is None:
                return None
            return self._snapshot_state(state, now or datetime.now(UTC), position_mark=True)

    def confirm_pumpswap_route(
        self,
        mint: str,
        *,
        pool_address: str,
        quote_mint: str,
        pool_base_token_account: str = "",
        pool_quote_token_account: str = "",
    ) -> bool:
        """Apply a route only after its on-chain Pool account has been decoded and matched."""

        with self._lock:
            state = self.tokens.get(mint)
            if (
                state is None
                or state.venue != "pump_swap"
                or not pool_address
                or state.pool_address != pool_address
            ):
                return False
            state.quote_mint = quote_mint
            if pool_base_token_account:
                state.pool_base_token_account = pool_base_token_account
            if pool_quote_token_account:
                state.pool_quote_token_account = pool_quote_token_account
            state.route_verified = True
            return True

    def refresh_pump_curve(
        self,
        mint: str,
        *,
        curve_address: str,
        values: dict[str, Any],
        slot: int,
        at: datetime,
        observation_id: str,
    ) -> bool:
        with self._lock:
            state = self.tokens.get(mint)
            if (
                state is None
                or state.venue != "pump_curve"
                or not curve_address
                or state.curve_address != curve_address
                or not observation_id
                or slot < max(state.last_slot, state.last_reserve_slot)
                or (state.last_reserve_slot > 0 and slot <= state.last_reserve_slot)
            ):
                return False
            virtual_token = _number(values, "virtual_token_reserves")
            virtual_quote = _number(
                values,
                "virtual_quote_reserves",
                "virtual_sol_reserves",
            )
            real_token = _number(values, "real_token_reserves")
            real_quote = _number(
                values,
                "real_quote_reserves",
                "real_sol_reserves",
                default=-1,
            )
            quote_mint = values.get("quote_mint")
            if virtual_token <= 0 or virtual_quote <= 0 or real_token < 0:
                return False
            if isinstance(quote_mint, str) and quote_mint != state.quote_mint:
                return False
            state.virtual_token_reserves = virtual_token
            state.virtual_quote_reserves = virtual_quote
            state.real_token_reserves = real_token
            if real_quote >= 0:
                state.real_quote_reserves = real_quote
            state.token_total_supply = max(
                state.token_total_supply,
                _number(values, "token_total_supply"),
            )
            state.complete = bool(values.get("complete", state.complete))
            state.last_reserve_at = max(state.last_reserve_at, at) if state.last_reserve_at else at
            state.last_reserve_slot = slot
            state.reserve_source = "solana_rpc:position_watchdog"
            state.last_reserve_event_id = observation_id
            state.last_reserve_signature = None
            return True

    def refresh_pumpswap_reserves(
        self,
        mint: str,
        *,
        pool_address: str,
        base_token_account: str,
        quote_token_account: str,
        base_amount: int,
        quote_amount: int,
        virtual_quote_reserves: int,
        slot: int,
        at: datetime,
        observation_id: str,
    ) -> bool:
        with self._lock:
            state = self.tokens.get(mint)
            if (
                state is None
                or state.venue != "pump_swap"
                or not state.route_verified
                or state.pool_address != pool_address
                or state.pool_base_token_account != base_token_account
                or state.pool_quote_token_account != quote_token_account
                or not observation_id
                or slot < max(state.last_slot, state.last_reserve_slot)
                or (state.last_reserve_slot > 0 and slot <= state.last_reserve_slot)
                or base_amount <= 0
                or quote_amount < 0
                or virtual_quote_reserves < 0
            ):
                return False
            state.virtual_token_reserves = base_amount
            state.real_token_reserves = base_amount
            state.virtual_quote_reserves = max(1, quote_amount + virtual_quote_reserves)
            state.real_quote_reserves = quote_amount
            if state.initial_real_token_reserves == 0:
                state.initial_real_token_reserves = base_amount
            state.last_reserve_at = max(state.last_reserve_at, at) if state.last_reserve_at else at
            state.last_reserve_slot = slot
            state.reserve_source = "solana_rpc:position_watchdog"
            state.last_reserve_event_id = observation_id
            state.last_reserve_signature = None
            return True

    def _snapshot_state(
        self,
        state: TokenState,
        now: datetime,
        *,
        position_mark: bool = False,
    ) -> FeatureSnapshot:
        last_event = state.last_event_at or state.created_at or now
        freshness = max(0.0, (now - last_event).total_seconds())
        reserve_at = state.last_reserve_at or last_event
        reserve_freshness = max(0.0, (now - reserve_at).total_seconds())
        route_freshness = reserve_freshness if position_mark else freshness
        created = state.created_at or last_event
        age = max(0.0, (now - created).total_seconds())
        rolling = _rolling_trade_metrics(state, now)
        trades_1m = list(rolling.trades_1m)
        trades_5m = list(rolling.trades_5m)
        buys_1m = rolling.buys_1m
        buys_5m = rolling.buys_5m
        sells_5m = len(trades_5m) - buys_5m
        buy_ratio = rolling.buy_ratio
        users = rolling.users
        hhi = rolling.wallet_volume_hhi
        repeated_ratio = rolling.repeated_amount_ratio
        same_slot_ratio = rolling.same_slot_ratio
        integrity = rolling.integrity
        creator_sells = sum(
            trade.side == Side.SELL and trade.user == state.creator for trade in trades_5m
        )
        progress = 0.0
        if state.initial_real_token_reserves > 0 and state.real_token_reserves >= 0:
            progress = 1 - state.real_token_reserves / state.initial_real_token_reserves
        progress = min(1.0, max(0.0, progress))
        momentum_1m = _momentum(trades_1m)
        momentum_5m = _momentum(trades_5m)
        drawdown = _drawdown(trades_5m)
        volume_5m_sol = sum(trade.quote_lamports for trade in trades_5m) / LAMPORTS_PER_SOL
        reserve_sol = state.virtual_quote_reserves / LAMPORTS_PER_SOL
        dex_at = state.enrichment_times.get("dexscreener")
        dex_age = max(0.0, (now - dex_at).total_seconds()) if dex_at else math.inf
        mint_safety_at = state.enrichment_times.get("solana_rpc")
        mint_safety_age = (
            max(0.0, (now - mint_safety_at).total_seconds()) if mint_safety_at else freshness
        )

        hard_flags: list[str] = []
        if state.virtual_token_reserves <= 0 or state.virtual_quote_reserves <= 0:
            hard_flags.append("missing_curve_reserves")
        if route_freshness > self.stale_market_seconds:
            hard_flags.append("stale_market_data")
        if state.complete and state.venue == "pump_curve":
            hard_flags.append("curve_complete_route_unconfirmed")
        if creator_sells:
            hard_flags.append("creator_sold_recently")
        if state.venue == "pump_swap":
            if not state.route_verified:
                hard_flags.append("pumpswap_route_unverified")
            elif state.quote_mint != WRAPPED_SOL_MINT:
                hard_flags.append("unsupported_quote_mint_v1")
        elif state.quote_mint not in {WRAPPED_SOL_MINT, NATIVE_SOL_MINT}:
            hard_flags.append("unsupported_quote_mint_v1")
        if state.token_program and state.token_program not in {
            SPL_TOKEN_PROGRAM,
            TOKEN_2022_PROGRAM,
        }:
            hard_flags.append("unsupported_token_program")
        live_source = any(source.startswith("solana:") for source in state.sources)
        mint_safety = state.enrichment.get("mint_safety")
        if live_source and mint_safety is None:
            hard_flags.append("mint_safety_unverified")
        elif isinstance(mint_safety, dict) and not mint_safety.get("safe", False):
            hard_flags.append("mint_account_failed_safety_checks")

        sources = sorted(state.sources) or ["unknown"]
        values: dict[str, DataValue] = {}
        rolling_freshness = max(0.0, (now - rolling.computed_at).total_seconds())
        rolling_keys = {
            "trade_count_1m",
            "trade_count_5m",
            "buys_1m",
            "buys_5m",
            "sells_5m",
            "buy_ratio_5m",
            "unique_wallets_5m",
            "wallet_volume_hhi",
            "repeated_amount_ratio",
            "same_slot_ratio",
            "known_wallet_trade_coverage",
            "signed_trade_coverage",
            "trade_window_span_seconds",
            "trade_buffer_saturated",
            "trade_density_5m",
            "median_trade_quote_sol",
            "creator_sells_5m",
            "momentum_1m",
            "momentum_5m",
            "drawdown_5m",
            "volume_5m_sol",
            *integrity,
        }

        def put(
            key: str,
            value: float | int | str | bool | None,
            unit: str,
            *,
            quality: float = 1.0,
            source_list: list[str] | None = None,
            item_freshness: float | None = None,
            item_as_of: datetime | None = None,
            missing_reason: str | None = None,
        ) -> None:
            values[key] = DataValue(
                value=value,
                unit=unit,
                as_of=item_as_of or (rolling.computed_at if key in rolling_keys else last_event),
                sources=source_list or sources,
                freshness_seconds=(
                    rolling_freshness
                    if item_freshness is None and key in rolling_keys
                    else freshness
                    if item_freshness is None
                    else item_freshness
                ),
                quality=max(0.0, min(1.0, quality)),
                missing_reason=missing_reason,
            )

        put("age_seconds", age, "seconds")
        put("market_freshness", freshness, "seconds")
        put(
            "reserve_freshness",
            reserve_freshness,
            "seconds",
            source_list=[state.reserve_source] if state.reserve_source else sources,
            item_freshness=reserve_freshness,
            item_as_of=reserve_at,
        )
        put("trade_count_1m", len(trades_1m), "count")
        put("trade_count_5m", len(trades_5m), "count")
        put("buys_1m", buys_1m, "count")
        put("buys_5m", buys_5m, "count")
        put("sells_5m", sells_5m, "count")
        put("buy_ratio_5m", buy_ratio, "fraction")
        put("unique_wallets_5m", len(users), "count")
        put("wallet_volume_hhi", hhi, "fraction")
        put("repeated_amount_ratio", repeated_ratio, "fraction")
        put("same_slot_ratio", same_slot_ratio, "fraction")
        for key in (
            "single_trade_wallet_ratio",
            "round_trip_wallet_ratio",
            "round_trip_volume_ratio",
            "net_quote_flow_ratio",
            "side_alternation_ratio",
            "quantized_amount_repeat_ratio",
            "slot_concentration_hhi",
            "price_direction_consistency",
            "multi_trade_signature_ratio",
            "microtrade_count_ratio",
            "meaningful_volume_ratio",
            "meaningful_wallet_ratio",
            "price_path_efficiency",
            "rapid_price_reversal_ratio",
        ):
            metric = integrity[key]
            put(
                key,
                metric[0],
                "fraction",
                quality=metric[1],
                missing_reason=metric[2],
            )
        put("known_wallet_trade_coverage", integrity["known_wallet_trade_coverage"][0], "fraction")
        put("signed_trade_coverage", integrity["signed_trade_coverage"][0], "fraction")
        put("trade_window_span_seconds", rolling.window_span_seconds, "seconds")
        current_evicted = state.last_evicted_trade
        trade_buffer_saturated = bool(
            rolling.buffer_saturated
            or (
                current_evicted is not None
                and current_evicted.venue == state.venue
                and 0 <= (now - current_evicted.received_at).total_seconds() <= 300
            )
        )
        put("trade_buffer_saturated", trade_buffer_saturated, "boolean")
        put("trade_density_5m", min(1.0, len(trades_5m) / 3_600), "fraction")
        median_trade = integrity["median_trade_quote_sol"]
        put(
            "median_trade_quote_sol",
            median_trade[0],
            "SOL",
            quality=median_trade[1],
            missing_reason=median_trade[2],
        )
        put("creator_sells_5m", creator_sells, "count")
        put("curve_progress", progress, "fraction")
        put("momentum_1m", momentum_1m, "fraction")
        put("momentum_5m", momentum_5m, "fraction")
        put("drawdown_5m", drawdown, "fraction")
        put("volume_5m_sol", volume_5m_sol, "SOL")
        reserve_sources = [state.reserve_source] if state.reserve_source else sources
        put(
            "virtual_quote_reserve_sol",
            reserve_sol,
            "SOL",
            source_list=reserve_sources,
            item_freshness=reserve_freshness,
            item_as_of=reserve_at,
        )
        put(
            "price_sol",
            state.price_sol,
            "SOL/token",
            source_list=reserve_sources,
            item_freshness=reserve_freshness,
            item_as_of=reserve_at,
        )
        identity_sources = (
            ["solana:pump_create_event"]
            if state.identity_source == "pump_create_event"
            else ["dexscreener"]
            if state.identity_source == "dexscreener"
            else ["solana:pump_create_event", "dexscreener"]
            if state.identity_source == "pump_create_event+dexscreener"
            else sources
        )
        put(
            "identity_source",
            state.identity_source,
            "label",
            quality=(
                1.0
                if state.identity_source == "pump_create_event"
                else 0.6
                if state.identity_source in {"dexscreener", "pump_create_event+dexscreener"}
                else 0.0
            ),
            source_list=identity_sources,
            missing_reason=(
                "name_and_symbol_not_observed" if state.identity_source == "unavailable" else None
            ),
        )
        put(
            "observed_fee_bps",
            state.fee_bps or None,
            "basis_points",
            missing_reason=None if state.fee_bps else "not_observed_yet",
        )
        put("complete", state.complete, "boolean")
        put("quote_mint", state.quote_mint, "address")
        put(
            "mint_safety_verified",
            mint_safety.get("safe") if isinstance(mint_safety, dict) else None,
            "boolean",
            quality=1.0 if isinstance(mint_safety, dict) else 0.0,
            source_list=["solana_rpc"],
            item_freshness=mint_safety_age,
            item_as_of=mint_safety_at,
            missing_reason=None if isinstance(mint_safety, dict) else "not_checked_yet",
        )
        dex_values = {
            "liquidity_usd": "USD",
            "volume_5m_usd": "USD",
            "market_cap_usd": "USD",
            "price_usd": "USD/token",
            "price_native": "SOL/token",
            "sol_usd_price": "USD/SOL",
        }
        for key, unit in dex_values.items():
            value = state.enrichment.get(key)
            stale = value is not None and dex_age > 120
            put(
                key,
                value,
                unit,
                quality=0.8 if value is not None and not stale else 0.0,
                source_list=["dexscreener"],
                item_freshness=freshness if math.isinf(dex_age) else dex_age,
                item_as_of=dex_at,
                missing_reason=(
                    "stale_enrichment"
                    if stale
                    else None
                    if value is not None
                    else "not_enriched_or_unavailable"
                ),
            )

        event_score = min(1.0, len(trades_5m) / 30)
        wallet_score = min(1.0, len(users) / 15)
        freshness_score = max(0.0, 1 - freshness / self.stale_market_seconds)
        reserve_score = 1.0 if state.virtual_quote_reserves > 0 else 0.0
        confidence = (
            0.30 * event_score + 0.20 * wallet_score + 0.30 * freshness_score + 0.20 * reserve_score
        )
        return FeatureSnapshot(
            mint=state.mint,
            symbol=state.symbol,
            name=state.name,
            venue=state.venue,
            computed_at=now,
            values=values,
            data_confidence=max(0.0, min(1.0, confidence)),
            hard_flags=hard_flags,
        )

    def list_snapshots(self, limit: int = 50) -> list[FeatureSnapshot]:
        with self._lock:
            oldest = datetime.min.replace(tzinfo=UTC)
            states = sorted(
                self.tokens.values(),
                key=lambda state: state.last_event_at or state.created_at or oldest,
                reverse=True,
            )[:limit]
            now = datetime.now(UTC)
            return [self._snapshot_state(state, now) for state in states]


def _rolling_trade_metrics(state: TokenState, now: datetime) -> RollingTradeMetrics:
    """Build one coherent venue-local window and reuse it briefly during dense bursts."""

    cached = state.rolling_trade_metrics
    if cached is not None and cached.venue == state.venue:
        cache_age = (now - cached.computed_at).total_seconds()
        if 0 <= cache_age < 1.0:
            return cached

    trades_5m = tuple(
        trade
        for trade in state.trades
        if trade.venue == state.venue and 0 <= (now - trade.received_at).total_seconds() <= 300
    )
    trades_1m = tuple(
        trade for trade in trades_5m if (now - trade.received_at).total_seconds() <= 60
    )
    buys_1m = sum(trade.side == Side.BUY for trade in trades_1m)
    buys_5m = sum(trade.side == Side.BUY for trade in trades_5m)
    users = frozenset(trade.user for trade in trades_5m if trade.user != "unknown")
    wallet_volume: dict[str, int] = defaultdict(int)
    for trade in trades_5m:
        wallet_volume[trade.user] += trade.quote_lamports
    total_volume = sum(wallet_volume.values())
    hhi = (
        sum((value / total_volume) ** 2 for value in wallet_volume.values())
        if total_volume > 0
        else 1.0
    )
    amounts = Counter(trade.quote_lamports for trade in trades_5m if trade.quote_lamports > 0)
    repeated_ratio = max(amounts.values(), default=0) / len(trades_5m) if trades_5m else 0.0
    slots = Counter(trade.slot for trade in trades_5m if trade.slot > 0)
    same_slot_ratio = max(slots.values(), default=0) / len(trades_5m) if trades_5m else 0.0
    span = (
        max(0.0, (trades_5m[-1].received_at - trades_5m[0].received_at).total_seconds())
        if len(trades_5m) > 1
        else 0.0
    )
    evicted = state.last_evicted_trade
    buffer_saturated = bool(
        evicted is not None
        and evicted.venue == state.venue
        and 0 <= (now - evicted.received_at).total_seconds() <= 300
    )
    result = RollingTradeMetrics(
        computed_at=now,
        venue=state.venue,
        trades_1m=trades_1m,
        trades_5m=trades_5m,
        buys_1m=buys_1m,
        buys_5m=buys_5m,
        buy_ratio=buys_5m / len(trades_5m) if trades_5m else 0.0,
        users=users,
        wallet_volume_hhi=hhi,
        repeated_amount_ratio=repeated_ratio,
        same_slot_ratio=same_slot_ratio,
        integrity=_stream_integrity_metrics(list(trades_5m)),
        window_span_seconds=span,
        buffer_saturated=buffer_saturated,
    )
    state.rolling_trade_metrics = result
    return result


def _momentum(trades: list[TradeObservation]) -> float:
    prices = [trade.price_sol for trade in trades if trade.price_sol > 0]
    if len(prices) < 2 or prices[0] <= 0:
        return 0.0
    return max(-1.0, min(10.0, prices[-1] / prices[0] - 1))


def _stream_integrity_metrics(trades: list[TradeObservation]) -> dict[str, IntegrityMetric]:
    """Describe stream structure without assigning a scam label or changing a decision.

    Every ratio is derived only from trades already present at the decision timestamp. Coverage
    is kept separate so a missing wallet, amount, slot, price, or signature cannot masquerade as
    reassuring zero evidence.
    """

    count = len(trades)
    missing: IntegrityMetric = (None, 0.0, "insufficient_trade_evidence")
    if count == 0:
        return {
            key: missing
            for key in (
                "single_trade_wallet_ratio",
                "round_trip_wallet_ratio",
                "round_trip_volume_ratio",
                "net_quote_flow_ratio",
                "side_alternation_ratio",
                "quantized_amount_repeat_ratio",
                "slot_concentration_hhi",
                "price_direction_consistency",
                "multi_trade_signature_ratio",
                "microtrade_count_ratio",
                "meaningful_volume_ratio",
                "meaningful_wallet_ratio",
                "median_trade_quote_sol",
                "price_path_efficiency",
                "rapid_price_reversal_ratio",
                "known_wallet_trade_coverage",
                "signed_trade_coverage",
            )
        }

    known = [trade for trade in trades if trade.user and trade.user != "unknown"]
    wallet_coverage = len(known) / count
    wallet_counts = Counter(trade.user for trade in known)
    wallet_sides: dict[str, set[Side]] = defaultdict(set)
    for trade in known:
        wallet_sides[trade.user].add(trade.side)
    round_trip_wallets = {
        wallet for wallet, sides in wallet_sides.items() if {Side.BUY, Side.SELL} <= sides
    }
    single_trade = (
        sum(value == 1 for value in wallet_counts.values()) / len(wallet_counts)
        if wallet_counts
        else None
    )
    round_trip = len(round_trip_wallets) / len(wallet_counts) if wallet_counts else None

    known_volume = sum(trade.quote_lamports for trade in known if trade.quote_lamports > 0)
    round_trip_volume = (
        sum(
            trade.quote_lamports
            for trade in known
            if trade.quote_lamports > 0 and trade.user in round_trip_wallets
        )
        / known_volume
        if known_volume > 0
        else None
    )
    valued = [trade for trade in trades if trade.quote_lamports > 0]
    amount_coverage = len(valued) / count
    gross_quote = sum(trade.quote_lamports for trade in valued)
    net_quote = sum(
        trade.quote_lamports if trade.side == Side.BUY else -trade.quote_lamports
        for trade in valued
    )
    net_flow = abs(net_quote) / gross_quote if gross_quote > 0 else None
    amount_buckets = Counter(_amount_bucket(trade.quote_lamports) for trade in valued)
    quantized_repetition = max(amount_buckets.values(), default=0) / len(valued) if valued else None
    microtrade_lamports = 3_000_000
    meaningful_lamports = 10_000_000
    valued_amounts = sorted(trade.quote_lamports for trade in valued)
    median_lamports = (
        (
            valued_amounts[len(valued_amounts) // 2]
            if len(valued_amounts) % 2
            else (
                valued_amounts[len(valued_amounts) // 2 - 1]
                + valued_amounts[len(valued_amounts) // 2]
            )
            / 2
        )
        if valued_amounts
        else None
    )
    microtrade_ratio = (
        sum(trade.quote_lamports <= microtrade_lamports for trade in valued) / len(valued)
        if valued
        else None
    )
    meaningful_volume_ratio = (
        sum(trade.quote_lamports for trade in valued if trade.quote_lamports >= meaningful_lamports)
        / gross_quote
        if gross_quote > 0
        else None
    )
    wallet_quote: dict[str, int] = defaultdict(int)
    for trade in known:
        if trade.quote_lamports > 0:
            wallet_quote[trade.user] += trade.quote_lamports
    meaningful_wallet_ratio = (
        sum(value >= meaningful_lamports for value in wallet_quote.values()) / len(wallet_quote)
        if wallet_quote
        else None
    )

    ordered = sorted(enumerate(trades), key=lambda row: (row[1].received_at, row[1].slot, row[0]))
    ordered_trades = [trade for _, trade in ordered]
    alternation = (
        sum(left.side != right.side for left, right in pairwise(ordered_trades)) / (count - 1)
        if count > 1
        else None
    )

    known_slots = [trade.slot for trade in trades if trade.slot > 0]
    slot_coverage = len(known_slots) / count
    slot_counts = Counter(known_slots)
    slot_hhi = (
        sum((slot_count / len(known_slots)) ** 2 for slot_count in slot_counts.values())
        if known_slots
        else None
    )

    prices = [trade.price_sol for trade in ordered_trades if trade.price_sol > 0]
    price_coverage = len(prices) / count
    price_moves = [right - left for left, right in pairwise(prices) if right != left]
    direction_consistency = (
        max(
            sum(move > 0 for move in price_moves),
            sum(move < 0 for move in price_moves),
        )
        / len(price_moves)
        if price_moves
        else 0.0
        if len(prices) >= 2
        else None
    )
    total_price_travel = sum(abs(move) for move in price_moves)
    path_efficiency = (
        abs(prices[-1] - prices[0]) / total_price_travel
        if len(prices) >= 2 and total_price_travel > 0
        else None
    )
    move_signs = [1 if move > 0 else -1 for move in price_moves]
    reversal_ratio = (
        sum(left != right for left, right in pairwise(move_signs)) / (len(move_signs) - 1)
        if len(move_signs) > 1
        else None
    )

    signed = [trade.signature for trade in trades if trade.signature]
    signature_coverage = len(signed) / count
    signature_counts = Counter(signed)
    bundled = (
        sum(value for value in signature_counts.values() if value > 1) / len(signed)
        if signed
        else None
    )

    def metric(
        value: float | None,
        quality: float,
        reason: str,
        *,
        minimum_quality: float = 0.0,
    ) -> IntegrityMetric:
        if value is None or quality < minimum_quality:
            return None, max(0.0, min(1.0, quality)), reason
        return max(0.0, min(1.0, value)), max(0.0, min(1.0, quality)), None

    return {
        "single_trade_wallet_ratio": metric(
            single_trade, wallet_coverage, "wallet_identity_unavailable", minimum_quality=0.8
        ),
        "round_trip_wallet_ratio": metric(
            round_trip, wallet_coverage, "wallet_identity_unavailable", minimum_quality=0.8
        ),
        "round_trip_volume_ratio": metric(
            round_trip_volume,
            min(wallet_coverage, amount_coverage),
            "wallet_or_trade_amount_unavailable",
            minimum_quality=0.8,
        ),
        "net_quote_flow_ratio": metric(
            net_flow, amount_coverage, "trade_amount_unavailable", minimum_quality=0.8
        ),
        "side_alternation_ratio": metric(alternation, 1.0, "insufficient_trade_sequence"),
        "quantized_amount_repeat_ratio": metric(
            quantized_repetition,
            amount_coverage,
            "trade_amount_unavailable",
            minimum_quality=0.8,
        ),
        "slot_concentration_hhi": metric(
            slot_hhi, slot_coverage, "slot_evidence_unavailable", minimum_quality=0.8
        ),
        "price_direction_consistency": metric(
            direction_consistency,
            price_coverage,
            "price_path_unavailable",
            minimum_quality=0.8,
        ),
        "multi_trade_signature_ratio": metric(
            bundled,
            signature_coverage,
            "signature_evidence_unavailable",
            minimum_quality=0.8,
        ),
        "microtrade_count_ratio": metric(
            microtrade_ratio,
            amount_coverage,
            "trade_amount_unavailable",
            minimum_quality=0.8,
        ),
        "meaningful_volume_ratio": metric(
            meaningful_volume_ratio,
            amount_coverage,
            "trade_amount_unavailable",
            minimum_quality=0.8,
        ),
        "meaningful_wallet_ratio": metric(
            meaningful_wallet_ratio,
            min(wallet_coverage, amount_coverage),
            "wallet_or_trade_amount_unavailable",
            minimum_quality=0.8,
        ),
        "median_trade_quote_sol": (
            None if median_lamports is None else median_lamports / LAMPORTS_PER_SOL,
            amount_coverage,
            (
                None
                if median_lamports is not None and amount_coverage >= 0.8
                else "trade_amount_unavailable"
            ),
        ),
        "price_path_efficiency": metric(
            path_efficiency,
            price_coverage,
            "price_path_unavailable",
            minimum_quality=0.8,
        ),
        "rapid_price_reversal_ratio": metric(
            reversal_ratio,
            price_coverage,
            "price_path_unavailable",
            minimum_quality=0.8,
        ),
        "known_wallet_trade_coverage": (wallet_coverage, 1.0, None),
        "signed_trade_coverage": (signature_coverage, 1.0, None),
    }


def _amount_bucket(value: int) -> int:
    """Round a positive raw amount to two significant digits for sizing-pattern evidence."""

    if value <= 0:
        return 0
    width = 10 ** max(0, int(math.floor(math.log10(value))) - 1)
    return int(round(value / width) * width)


def _drawdown(trades: list[TradeObservation]) -> float:
    prices = [trade.price_sol for trade in trades if trade.price_sol > 0]
    if not prices:
        return 0.0
    peak = max(prices)
    return 0.0 if peak <= 0 else min(1.0, max(0.0, 1 - prices[-1] / peak))


def _bounded_display_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    printable = "".join(character for character in value if character.isprintable())
    normalized = " ".join(printable.split())
    return normalized[:limit] or None
