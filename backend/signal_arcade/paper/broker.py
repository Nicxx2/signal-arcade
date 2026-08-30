from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from ..config import Settings
from ..database import Database
from ..intelligence.features import TokenState
from ..models import (
    RISK_LIMITS,
    Decision,
    DecisionAction,
    EventKind,
    FeatureSnapshot,
    FillReceipt,
    OrderStatus,
    PaperOrder,
    PortfolioSnapshot,
    Position,
    PositionMarketStatus,
    QuoteCurrency,
    RiskLimits,
    RiskMode,
    Side,
)
from ..risk_profiles import SeasonProfile
from .curve_math import quote_buy, quote_sell
from .exit_policy import ROUTE_BLOCKERS, assess_exit

logger = logging.getLogger(__name__)
LAMPORTS_PER_SOL = 1_000_000_000
USDC_MINOR_PER_UNIT = 1_000_000
EQUITY_PEAK_BASIS = "executable-route-v1"
UNFILLABLE_BUY_FLAGS = {
    "missing_curve_reserves",
    "stale_market_data",
    "curve_complete_route_unconfirmed",
    "pumpswap_route_unverified",
    "unsupported_quote_mint_v1",
    "unsupported_token_program",
    "mint_safety_unverified",
    "mint_account_failed_safety_checks",
}
UNFILLABLE_SELL_FLAGS = ROUTE_BLOCKERS


class PaperBroker:
    """Crash-recoverable event-time paper broker; no signing code exists here."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.initialized = bool(database.get_setting("portfolio_initialized", False))
        self.quote_currency = QuoteCurrency(
            database.get_setting("quote_currency", QuoteCurrency.SOL.value)
        )
        self.quote_decimals = 9 if self.quote_currency == QuoteCurrency.SOL else 6
        self.starting_lamports = int(database.get_setting("starting_lamports", 0))
        self.season_id = database.get_setting("season_id")
        if self.initialized and not self.season_id:
            self.season_id = "legacy-season-" + uuid.uuid4().hex
            database.set_setting("season_id", self.season_id)
        if self.initialized and self.season_id:
            database.ensure_current_season(
                str(self.season_id),
                self.starting_lamports,
                self.quote_currency.value,
            )
        current_season = database.current_paper_season() if self.initialized else None
        self.season_profile: dict[str, Any] | None = (
            dict(current_season["profile"])
            if current_season and isinstance(current_season.get("profile"), dict)
            else None
        )
        if self.season_profile is not None:
            SeasonProfile.model_validate(self.season_profile)
        self.positions = {item.mint: item for item in database.list_positions()}
        self.pending = {
            item.order_id: item for item in database.list_orders([OrderStatus.PENDING.value])
        }
        self.traded_mints = {
            fill.mint for fill in database.list_fills(100_000) if fill.side == Side.BUY
        }
        self._last_equity_recorded_at: datetime | None = None

    def initialize(
        self,
        quote_currency: QuoteCurrency,
        starting_minor: int,
        season_profile: dict[str, Any] | None = None,
    ) -> None:
        if self.initialized:
            raise ValueError("paper portfolio is already initialized")
        if starting_minor <= 0:
            raise ValueError("starting bankroll must be positive")
        season_id = "season-" + uuid.uuid4().hex
        self.database.initialize_portfolio(
            season_id,
            starting_minor,
            quote_currency.value,
            season_profile,
        )
        self.quote_currency = quote_currency
        self.quote_decimals = 9 if quote_currency == QuoteCurrency.SOL else 6
        self.starting_lamports = starting_minor
        self.initialized = True
        self.season_id = season_id
        self.season_profile = dict(season_profile) if season_profile else None
        self._last_equity_recorded_at = datetime.now(UTC)

    @property
    def cash_lamports(self) -> int:
        return self.database.ledger_balance("cash")

    def risk_limits(self, mode: RiskMode | None = None) -> RiskLimits:
        raw_profile_mode = (
            self.season_profile.get("risk_mode") if self.season_profile is not None else None
        )
        selected = (
            mode
            if mode is not None
            else RiskMode(raw_profile_mode)
            if isinstance(raw_profile_mode, str)
            else RiskMode.BALANCED
        )
        if (
            self.season_profile is not None
            and self.season_profile.get("risk_mode") == selected.value
        ):
            return RiskLimits.model_validate(self.season_profile["risk_limits"])
        return RISK_LIMITS[selected]

    def drawdown_limit_fraction(self, mode: RiskMode | None = None) -> float | None:
        """Return the typed portfolio halt only; every other risk limit stays unchanged."""

        raw_profile_mode = (
            self.season_profile.get("risk_mode") if self.season_profile is not None else None
        )
        selected = (
            mode
            if mode is not None
            else RiskMode(raw_profile_mode)
            if isinstance(raw_profile_mode, str)
            else RiskMode.BALANCED
        )
        if (
            self.season_profile is not None
            and self.season_profile.get("risk_mode") == selected.value
            and "effective_drawdown_bps" in self.season_profile
        ):
            bps = self.season_profile.get("effective_drawdown_bps")
            return None if bps is None else int(bps) / 10_000
        return self.risk_limits(selected).max_drawdown_fraction

    def has_pending_for(self, mint: str, side: Side | None = None) -> bool:
        return any(
            order.mint == mint and (side is None or order.side == side)
            for order in self.pending.values()
        )

    def submit_decision(
        self, decision: Decision, *, sol_usd_price: float | None = None
    ) -> PaperOrder | None:
        order, _ = self.submit_decision_with_reason(decision, sol_usd_price=sol_usd_price)
        return order

    def entry_blocker(
        self,
        decision: Decision,
        *,
        sol_usd_price: float | None = None,
    ) -> str | None:
        """Read-only portfolio gate used to keep learning attribution honest."""

        blocker, _, _ = self._entry_assessment(decision, sol_usd_price)
        return blocker

    def submit_decision_with_reason(
        self, decision: Decision, *, sol_usd_price: float | None = None
    ) -> tuple[PaperOrder | None, str | None]:
        blocker, request, required = self._entry_assessment(decision, sol_usd_price)
        if blocker:
            return None, blocker
        assert request is not None and required is not None
        order = PaperOrder(
            order_id=uuid.uuid4().hex,
            decision_id=decision.decision_id,
            mint=decision.mint,
            symbol=decision.symbol,
            side=Side.BUY,
            requested_sol_lamports=request,
            reserved_account_minor=required,
            fill_after=decision.created_at + timedelta(milliseconds=self.settings.entry_latency_ms),
            risk_mode_at_entry=decision.risk_mode,
        )
        self.pending[order.order_id] = order
        self.database.save_order(order)
        return order, None

    def planned_order_size_sol(
        self,
        mode: RiskMode,
        *,
        sol_usd_price: float | None = None,
    ) -> float:
        """Scale slowly with realized results while respecting per-position exposure."""
        limits = self.risk_limits(mode)
        if not self.initialized or self.starting_lamports <= 0:
            return limits.order_size_sol
        portfolio = self.snapshot(mode)
        realized_equity = max(
            1,
            self.starting_lamports + portfolio.realized_pnl_lamports,
        )
        growth_ratio = realized_equity / self.starting_lamports
        growth_factor = max(0.5, min(1.5, math.sqrt(max(0.0, growth_ratio))))
        grown_lamports = int(limits.order_size_sol * LAMPORTS_PER_SOL * growth_factor)
        account_cap = int(
            portfolio.equity_lamports * limits.max_exposure_fraction / limits.max_open_positions
        )
        try:
            exposure_cap_lamports = self._sol_lamports_from_account_minor(
                account_cap,
                sol_usd_price,
            )
        except ValueError:
            return limits.order_size_sol
        planned_lamports = max(1, min(grown_lamports, exposure_cap_lamports))
        return planned_lamports / LAMPORTS_PER_SOL

    def can_fund_permitted_entry(
        self,
        mode: RiskMode,
        *,
        sol_usd_price: float | None = None,
    ) -> tuple[bool | None, int | None]:
        """Return whether current cash can fund the broker's actual next minimum entry.

        ``None`` means required accounting evidence (currently SOL/USD for USDC books) is
        unavailable. Unknown is deliberately distinct from an exhausted bankroll.
        """

        if not self.initialized:
            return None, None
        request = max(
            1,
            int(self.planned_order_size_sol(mode, sol_usd_price=sol_usd_price) * LAMPORTS_PER_SOL),
        )
        try:
            required = self._account_minor_from_sol(
                request + self.settings.network_fee_lamports + self.settings.priority_fee_lamports,
                sol_usd_price,
                ROUND_CEILING,
            )
        except ValueError:
            return None, None
        return required <= self.cash_lamports, required

    def fresh_season_can_fund_entry(
        self,
        mode: RiskMode,
        *,
        sol_usd_price: float | None = None,
    ) -> tuple[bool | None, int | None]:
        """Check that resetting to the original bankroll would restore real capacity.

        This prevents an undersized starting bankroll from generating empty rollover loops.
        """

        if not self.initialized or self.starting_lamports <= 0:
            return None, None
        limits = self.risk_limits(mode)
        account_cap = int(
            self.starting_lamports * limits.max_exposure_fraction / limits.max_open_positions
        )
        try:
            exposure_cap_lamports = self._sol_lamports_from_account_minor(
                account_cap,
                sol_usd_price,
            )
            request = max(
                1,
                min(
                    int(limits.order_size_sol * LAMPORTS_PER_SOL),
                    exposure_cap_lamports,
                ),
            )
            required = self._account_minor_from_sol(
                request + self.settings.network_fee_lamports + self.settings.priority_fee_lamports,
                sol_usd_price,
                ROUND_CEILING,
            )
        except ValueError:
            return None, None
        return required <= self.starting_lamports, required

    def _entry_assessment(
        self, decision: Decision, sol_usd_price: float | None
    ) -> tuple[str | None, int | None, int | None]:
        if not self.initialized:
            return "paper_portfolio_not_initialized", None, None
        if decision.action != DecisionAction.ENTER:
            return "decision_is_not_an_entry", None, None
        if decision.mint in self.traded_mints:
            return "mint_already_traded_this_season", None, None
        if decision.mint in self.positions:
            return "position_already_open", None, None
        if self.has_pending_for(decision.mint):
            return "order_already_pending", None, None
        limits = self.risk_limits(decision.risk_mode)
        portfolio = self.snapshot(decision.risk_mode)
        capacity_positions = self._capacity_positions(portfolio)
        pending_buys = [order for order in self.pending.values() if order.side == Side.BUY]
        if len(capacity_positions) + len(pending_buys) >= limits.max_open_positions:
            return "portfolio_capacity_reached", None, None
        drawdown_limit = self.drawdown_limit_fraction(decision.risk_mode)
        if drawdown_limit is not None and portfolio.drawdown_fraction >= drawdown_limit:
            return "portfolio_drawdown_limit_reached", None, None
        request = int((decision.planned_order_size_sol or limits.order_size_sol) * LAMPORTS_PER_SOL)
        try:
            required = self._account_minor_from_sol(
                request + self.settings.network_fee_lamports + self.settings.priority_fee_lamports,
                sol_usd_price,
                ROUND_CEILING,
            )
        except ValueError:
            return "fresh_sol_usdc_conversion_unavailable", None, None
        exposure = sum(position.entry_cost_lamports for position in capacity_positions)
        exposure += sum(self._pending_reservation(order, sol_usd_price) for order in pending_buys)
        maximum = int(portfolio.equity_lamports * limits.max_exposure_fraction)
        if exposure + required > maximum:
            return "portfolio_exposure_limit_reached", None, None
        reserved_cash = sum(
            self._pending_reservation(order, sol_usd_price) for order in pending_buys
        )
        if required > max(0, self.cash_lamports - reserved_cash):
            return "unreserved_paper_cash_insufficient", None, None
        return None, request, required

    def on_market_state(
        self,
        *,
        state: TokenState,
        features: FeatureSnapshot,
        event_kind: EventKind,
        source_event_id: str,
        now: datetime,
        mode: RiskMode,
        sol_usd_price: float | None = None,
        soft_hold_seconds: int | None = None,
    ) -> list[FillReceipt]:
        if event_kind != EventKind.TRADE:
            return []
        receipts: list[FillReceipt] = []
        self._mark_position(
            state,
            features,
            sol_usd_price,
            self._mark_timestamp(state, features, now),
        )
        self._schedule_exit_if_needed(
            state,
            features,
            now,
            mode,
            soft_hold_seconds=soft_hold_seconds,
        )
        receipts.extend(
            self.process_due_orders(
                state=state,
                features=features,
                source_event_id=source_event_id,
                now=now,
                mode=mode,
                sol_usd_price=sol_usd_price,
                record_equity=False,
            )
        )
        self.expire_stuck_orders(now)
        self._record_equity(now, force=bool(receipts))
        return receipts

    def process_due_orders(
        self,
        *,
        state: TokenState,
        features: FeatureSnapshot,
        source_event_id: str,
        now: datetime,
        mode: RiskMode,
        sol_usd_price: float | None = None,
        record_equity: bool = True,
    ) -> list[FillReceipt]:
        """Fill elapsed paper orders from the newest still-fresh observed reserve state.

        A blockchain transaction can execute after the configured latency even when no other
        trader produces a subsequent event. Requiring an unrelated future event trapped
        illiquid positions, so the clock loop may now use the latest observed executable state.
        """
        receipts: list[FillReceipt] = []
        self._mark_position(
            state,
            features,
            sol_usd_price,
            self._mark_timestamp(state, features, now),
        )
        for order in list(self.pending.values()):
            if order.mint != state.mint or now < order.fill_after:
                continue
            unfillable = UNFILLABLE_BUY_FLAGS if order.side == Side.BUY else UNFILLABLE_SELL_FLAGS
            if any(flag in unfillable for flag in features.hard_flags):
                continue
            if order.side == Side.BUY:
                blocker = self._pending_buy_fill_blocker(order, mode, sol_usd_price)
                if blocker:
                    self._fail_order(order, f"fill_rejected:{blocker}", now)
                    continue
            receipt = self._fill(order, state, features, source_event_id, now, sol_usd_price)
            if receipt:
                receipts.append(receipt)
        if record_equity:
            self._record_equity(now, force=bool(receipts))
        return receipts

    def observe_market_state(
        self,
        *,
        state: TokenState,
        features: FeatureSnapshot,
        now: datetime,
        sol_usd_price: float | None = None,
    ) -> None:
        """Refresh marks while stopped without scheduling or filling an order."""
        self._mark_position(
            state,
            features,
            sol_usd_price,
            self._mark_timestamp(state, features, now),
        )
        self._record_equity(now)

    def reassess_position(
        self,
        *,
        state: TokenState,
        features: FeatureSnapshot,
        now: datetime,
        mode: RiskMode,
        sol_usd_price: float | None = None,
        soft_hold_seconds: int | None = None,
    ) -> None:
        """Use the freshest retained state to restore risk management after resume."""
        # A clock tick must never turn an old reserve observation into a fresh mark.
        self._mark_position(
            state,
            features,
            sol_usd_price,
            self._mark_timestamp(state, features, now),
        )
        self._schedule_exit_if_needed(
            state,
            features,
            now,
            mode,
            soft_hold_seconds=soft_hold_seconds,
        )

    def cancel_pending_orders(self, now: datetime, reason: str = "paper_engine_stopped") -> int:
        cancelled = 0
        for order in list(self.pending.values()):
            order.status = OrderStatus.CANCELLED
            order.failure_reason = reason
            order.filled_at = now
            self.database.save_order(order)
            self.pending.pop(order.order_id, None)
            cancelled += 1
        return cancelled

    def cancel_pending_buys(self, now: datetime, reason: str) -> int:
        """Freeze new exposure without discarding an exit already crossing its latency window."""

        cancelled = 0
        for order in list(self.pending.values()):
            if order.side != Side.BUY:
                continue
            order.status = OrderStatus.CANCELLED
            order.failure_reason = reason
            order.filled_at = now
            self.database.save_order(order)
            self.pending.pop(order.order_id, None)
            cancelled += 1
        return cancelled

    def cancel_pending_sells(self, now: datetime, reason: str) -> int:
        """Retire unfilled exits at an explicit bounded manual season boundary."""

        cancelled = 0
        for order in list(self.pending.values()):
            if order.side != Side.SELL:
                continue
            order.status = OrderStatus.CANCELLED
            order.failure_reason = reason
            order.filled_at = now
            self.database.save_order(order)
            self.pending.pop(order.order_id, None)
            cancelled += 1
        return cancelled

    def schedule_profile_transition_exits(self, now: datetime) -> int:
        """Request real paper exits for every position with a fresh executable route."""

        scheduled = 0
        portfolio = self.snapshot(persist_peak=False)
        for observed in portfolio.positions:
            if observed.market_status != PositionMarketStatus.ACTIVE or self.has_pending_for(
                observed.mint, Side.SELL
            ):
                continue
            position = self.positions.get(observed.mint)
            if position is None:
                continue
            order = PaperOrder(
                order_id=uuid.uuid4().hex,
                mint=position.mint,
                symbol=position.symbol,
                side=Side.SELL,
                requested_token_units=position.token_units,
                created_at=now,
                fill_after=now + timedelta(milliseconds=self.settings.exit_latency_ms),
                failure_reason="scheduled_reason:manual_profile_change",
                risk_mode_at_entry=position.risk_mode_at_entry,
            )
            self.pending[order.order_id] = order
            self.database.save_order(order)
            scheduled += 1
        return scheduled

    def unresolved_position_records(
        self,
        now: datetime,
        *,
        reason: str,
    ) -> list[dict[str, Any]]:
        """Describe inventory without pretending its last indication was an executable sale."""

        portfolio = self.snapshot(persist_peak=False)
        return [
            {
                "position_id": position.position_id,
                "mint": position.mint,
                "symbol": position.symbol,
                "token_units": position.token_units,
                "entry_cost_minor": position.entry_cost_lamports,
                "book_value_minor": position.book_value_lamports,
                "last_known_mark_minor": position.last_mark_lamports,
                "last_marked_at": (
                    position.last_marked_at.isoformat() if position.last_marked_at else None
                ),
                "market_status": position.market_status.value,
                "mark_blockers": list(position.mark_blockers),
                "quote_currency": self.quote_currency.value,
                "quote_decimals": self.quote_decimals,
                "retirement_reason": reason,
                "retired_at": now.isoformat(),
                "was_executed": False,
            }
            for position in portfolio.positions
        ]

    def _fill(
        self,
        order: PaperOrder,
        state: TokenState,
        features: FeatureSnapshot,
        source_event_id: str,
        now: datetime,
        sol_usd_price: float | None,
    ) -> FillReceipt | None:
        network = self.settings.network_fee_lamports + self.settings.priority_fee_lamports
        fee_bps = state.fee_bps or self.settings.pump_fee_bps
        sell_position: Position | None = None
        try:
            if order.side == Side.BUY:
                quote = quote_buy(
                    virtual_token_reserves=state.virtual_token_reserves,
                    virtual_sol_reserves=state.virtual_quote_reserves,
                    real_token_reserves=state.real_token_reserves,
                    wallet_trade_budget_lamports=order.requested_sol_lamports,
                    fee_bps=fee_bps,
                    network_fee_lamports=network,
                )
            else:
                sell_position = self.positions.get(order.mint)
                if sell_position is None:
                    raise ValueError("position no longer exists")
                quote = quote_sell(
                    virtual_token_reserves=state.virtual_token_reserves,
                    virtual_sol_reserves=state.virtual_quote_reserves,
                    token_units=sell_position.token_units,
                    fee_bps=fee_bps,
                    network_fee_lamports=network,
                    real_quote_reserves=state.real_quote_reserves,
                )
        except ValueError as exc:
            self._fail_order(order, str(exc), now)
            return None
        try:
            account_values = self._account_fill_values(
                side=order.side,
                gross_sol=quote.curve_sol_lamports,
                protocol_fee_sol=quote.protocol_fee_lamports,
                network_fee_sol=quote.network_fee_lamports,
                wallet_sol=quote.wallet_sol_lamports,
                sol_usd_price=sol_usd_price,
            )
        except ValueError as exc:
            self._fail_order(order, str(exc), now)
            return None
        if order.side == Side.BUY and account_values["account_net_minor"] > self.cash_lamports:
            self._fail_order(order, "virtual cash changed before the order filled", now)
            return None
        realized_return = (
            (account_values["account_net_minor"] - sell_position.entry_cost_lamports)
            / sell_position.entry_cost_lamports
            if sell_position is not None and sell_position.entry_cost_lamports
            else None
        )
        peak_return = (
            sell_position.peak_mark_lamports / sell_position.entry_cost_lamports - 1
            if sell_position is not None and sell_position.entry_cost_lamports
            else None
        )
        manual_profile_exit = (
            order.side == Side.SELL
            and order.failure_reason == "scheduled_reason:manual_profile_change"
        )
        receipt = FillReceipt(
            fill_id=uuid.uuid4().hex,
            order_id=order.order_id,
            mint=order.mint,
            symbol=order.symbol,
            side=order.side,
            filled_at=now,
            token_units=quote.token_units,
            gross_sol_lamports=quote.curve_sol_lamports,
            protocol_fee_lamports=quote.protocol_fee_lamports,
            network_fee_lamports=quote.network_fee_lamports,
            net_sol_lamports=quote.wallet_sol_lamports,
            price_impact_fraction=quote.price_impact_fraction,
            latency_ms=max(0, int((now - order.created_at).total_seconds() * 1000)),
            source_event_id=source_event_id,
            venue=state.venue,
            assumptions=[
                *(
                    [order.failure_reason]
                    if order.side == Side.SELL
                    and order.failure_reason
                    and order.failure_reason.startswith("scheduled_reason:")
                    else []
                ),
                f"protocol_fee_bps={fee_bps}",
                "fee_source=observed_event" if state.fee_bps else "fee_source=configured_fallback",
                "filled_after_configured_latency_against_latest_observed_reserves",
                "constant_product_integer_rounding",
            ],
            account_currency=self.quote_currency,
            account_decimals=self.quote_decimals,
            sol_usd_price=sol_usd_price if self.quote_currency == QuoteCurrency.USDC else None,
            # A user-requested boundary is an honest paper fill, but it is not evidence that the
            # old exit policy selected the timing. Keep it out of exit-policy audit metrics.
            exit_assessment=(
                sell_position.exit_assessment
                if sell_position is not None and not manual_profile_exit
                else None
            ),
            position_opened_at=sell_position.opened_at if sell_position else None,
            entry_risk_mode=sell_position.risk_mode_at_entry if sell_position else None,
            peak_account_minor=sell_position.peak_mark_lamports if sell_position else 0,
            realized_return_fraction=(
                max(-1.0, min(10.0, realized_return)) if realized_return is not None else None
            ),
            peak_return_fraction=(
                max(-1.0, min(10.0, peak_return)) if peak_return is not None else None
            ),
            **account_values,
        )
        filled_order = order.model_copy(update={"status": OrderStatus.FILLED, "filled_at": now})
        if order.side == Side.BUY:
            self._account_buy(filled_order, receipt, state)
            self._mark_position(
                state,
                features,
                sol_usd_price,
                self._mark_timestamp(state, features, now),
            )
        else:
            self._account_sell(filled_order, receipt)
        self.pending.pop(order.order_id, None)
        return receipt

    def _account_buy(
        self,
        order: PaperOrder,
        receipt: FillReceipt,
        state: TokenState,
    ) -> None:
        total = receipt.account_net_minor
        network = receipt.account_network_fee_minor
        trade_cost = total - network
        entries = [
            (f"inventory:{order.mint}", trade_cost, 0, "Virtual token inventory"),
            ("network_expense", network, 0, "Simulated network fee"),
            ("cash", 0, total, "Paper buy cash outflow"),
        ]
        position = Position(
            position_id=uuid.uuid4().hex,
            mint=order.mint,
            symbol=order.symbol,
            token_units=receipt.token_units,
            entry_cost_lamports=total,
            book_value_lamports=trade_cost,
            opened_at=receipt.filled_at,
            entry_fill_id=receipt.fill_id,
            risk_mode_at_entry=order.risk_mode_at_entry,
            venue=state.venue,
            curve_address=state.curve_address,
            pool_address=state.pool_address,
            pool_base_token_account=state.pool_base_token_account,
            pool_quote_token_account=state.pool_quote_token_account,
            quote_mint=state.quote_mint,
        )
        self.database.commit_buy_fill(order, receipt, position, entries)
        self.positions[order.mint] = position
        self.traded_mints.add(order.mint)

    def _account_sell(self, order: PaperOrder, receipt: FillReceipt) -> None:
        position = self.positions[order.mint]
        gross = receipt.account_gross_minor
        fees = receipt.account_protocol_fee_minor + receipt.account_network_fee_minor
        entries: list[tuple[str, int, int, str]] = [
            ("cash", receipt.account_net_minor, 0, "Paper sell cash inflow"),
            ("exit_expense", fees, 0, "Protocol and network fees"),
            (
                f"inventory:{order.mint}",
                0,
                position.book_value_lamports,
                "Close virtual token inventory",
            ),
        ]
        if gross >= position.book_value_lamports:
            entries.append(
                ("realized_gain", 0, gross - position.book_value_lamports, "Realized paper gain")
            )
        else:
            entries.append(
                ("realized_loss", position.book_value_lamports - gross, 0, "Realized paper loss")
            )
        realized = receipt.account_net_minor - position.entry_cost_lamports
        running = int(self.database.get_setting("realized_pnl_lamports", 0)) + realized
        self.database.commit_sell_fill(order, receipt, position, entries, running)
        self.positions.pop(order.mint, None)

    def _mark_position(
        self,
        state: TokenState,
        features: FeatureSnapshot,
        sol_usd_price: float | None,
        marked_at: datetime | None = None,
    ) -> None:
        position = self.positions.get(state.mint)
        if position is None:
            return
        position.venue = state.venue
        position.curve_address = state.curve_address
        position.pool_address = state.pool_address
        position.pool_base_token_account = state.pool_base_token_account
        position.pool_quote_token_account = state.pool_quote_token_account
        position.quote_mint = state.quote_mint
        blockers = sorted(set(features.hard_flags) & UNFILLABLE_SELL_FLAGS)
        if "stale_market_data" in blockers:
            position.mark_is_stale = True
            position.mark_is_executable = False
            position.mark_blockers = blockers
            position.market_status = PositionMarketStatus.DORMANT
            self.database.save_position(position)
            return
        was_executable = position.mark_is_executable
        try:
            quote = quote_sell(
                virtual_token_reserves=state.virtual_token_reserves,
                virtual_sol_reserves=state.virtual_quote_reserves,
                token_units=position.token_units,
                fee_bps=state.fee_bps or self.settings.pump_fee_bps,
                network_fee_lamports=(
                    self.settings.network_fee_lamports + self.settings.priority_fee_lamports
                ),
                real_quote_reserves=state.real_quote_reserves,
            )
            position.last_mark_lamports = self._account_minor_from_sol(
                quote.wallet_sol_lamports, sol_usd_price, ROUND_FLOOR
            )
            position.unrealized_pnl_lamports = (
                position.last_mark_lamports - position.entry_cost_lamports
            )
            position.last_marked_at = marked_at or state.last_event_at or datetime.now(UTC)
            position.mark_age_seconds = 0
            position.mark_is_stale = False
        except ValueError as exc:
            calculation_blocker = (
                "fresh_sol_usdc_conversion_unavailable"
                if self.quote_currency == QuoteCurrency.USDC and sol_usd_price is None
                else (
                    "insufficient_real_quote_liquidity"
                    if "real quote reserves" in str(exc)
                    else "mark_calculation_unavailable"
                )
            )
            position.mark_is_executable = False
            position.mark_blockers = sorted({*blockers, calculation_blocker})
            position.market_status = PositionMarketStatus.EXIT_BLOCKED
            self.database.save_position(position)
            return
        position.mark_is_executable = not blockers
        position.mark_blockers = blockers
        position.market_status = (
            PositionMarketStatus.ACTIVE
            if position.mark_is_executable
            else PositionMarketStatus.EXIT_BLOCKED
        )
        # An old indicative peak must not trigger a trailing exit when a route first becomes
        # executable. Start that risk watermark from the first verified mark.
        if position.mark_is_executable and (
            not was_executable or position.last_mark_lamports > position.peak_mark_lamports
        ):
            position.peak_mark_lamports = position.last_mark_lamports
            position.peak_marked_at = position.last_marked_at
        self.database.save_position(position)

    @staticmethod
    def _mark_timestamp(
        state: TokenState,
        features: FeatureSnapshot,
        fallback: datetime,
    ) -> datetime:
        price = features.values.get("price_sol")
        if price is not None:
            return price.as_of
        return state.last_reserve_at or state.last_event_at or fallback

    def _schedule_exit_if_needed(
        self,
        state: TokenState,
        features: FeatureSnapshot,
        now: datetime,
        mode: RiskMode,
        *,
        soft_hold_seconds: int | None = None,
    ) -> None:
        position = self.positions.get(state.mint)
        if position is None or self.has_pending_for(state.mint, Side.SELL):
            return
        limits = self._position_exit_limits(position, mode)
        assessment = assess_exit(
            position=position,
            features=features,
            now=now,
            limits=limits,
            soft_hold_seconds=soft_hold_seconds,
        )
        position.exit_assessment = assessment
        self.database.save_position(position)
        # Keep the policy's exit intent visible, but do not create an order against a mark whose
        # exact current route cannot execute. A later valid reserve observation will reassess it.
        if assessment.action == "exit" and position.mark_is_executable:
            order = PaperOrder(
                order_id=uuid.uuid4().hex,
                mint=position.mint,
                symbol=position.symbol,
                side=Side.SELL,
                requested_token_units=position.token_units,
                created_at=now,
                fill_after=now + timedelta(milliseconds=self.settings.exit_latency_ms),
                failure_reason=f"scheduled_reason:{assessment.reason}",
                risk_mode_at_entry=position.risk_mode_at_entry,
            )
            self.pending[order.order_id] = order
            self.database.save_order(order)

    def _position_exit_limits(self, position: Position, mode: RiskMode) -> RiskLimits:
        current = self.risk_limits(mode)
        if self.season_profile is not None:
            # Exact seasons never combine a later code default with their frozen policy.
            return current
        return self._effective_exit_limits(position, mode)

    @staticmethod
    def _effective_exit_limits(position: Position, mode: RiskMode) -> RiskLimits:
        """A slider change may tighten an open position, but never loosen entry guardrails."""

        current = RISK_LIMITS[mode]
        entered = RISK_LIMITS[position.risk_mode_at_entry or mode]
        return current.model_copy(
            update={
                "stop_loss_fraction": min(current.stop_loss_fraction, entered.stop_loss_fraction),
                "take_profit_fraction": min(
                    current.take_profit_fraction, entered.take_profit_fraction
                ),
                "trailing_stop_fraction": min(
                    current.trailing_stop_fraction, entered.trailing_stop_fraction
                ),
                "minimum_hold_support": max(
                    current.minimum_hold_support, entered.minimum_hold_support
                ),
                "migration_guard_progress": min(
                    current.migration_guard_progress, entered.migration_guard_progress
                ),
                "max_hold_seconds": min(current.max_hold_seconds, entered.max_hold_seconds),
                "hard_max_hold_seconds": min(
                    current.hard_max_hold_seconds, entered.hard_max_hold_seconds
                ),
            }
        )

    def _fail_order(self, order: PaperOrder, reason: str, now: datetime) -> None:
        order.status = OrderStatus.FAILED
        order.failure_reason = reason[:300]
        order.filled_at = now
        self.database.save_order(order)
        self.pending.pop(order.order_id, None)

    def _pending_reservation(self, order: PaperOrder, sol_usd_price: float | None) -> int:
        if order.reserved_account_minor > 0:
            return order.reserved_account_minor
        return self._account_minor_from_sol(
            order.requested_sol_lamports
            + self.settings.network_fee_lamports
            + self.settings.priority_fee_lamports,
            sol_usd_price,
            ROUND_CEILING,
        )

    @staticmethod
    def _capacity_positions(portfolio: PortfolioSnapshot) -> list[Position]:
        """Return holdings that still consume active trading capacity.

        Dormant holdings have no fresh executable route and are already written down in equity.
        Keeping them in the active slot and exposure limits would eventually deadlock a long paper
        season. They remain persisted and monitored; a fresh route changes their next snapshot back
        to active or exit-blocked, at which point they consume capacity again.
        """

        return [
            position
            for position in portfolio.positions
            if position.market_status != PositionMarketStatus.DORMANT
        ]

    def _pending_buy_fill_blocker(
        self,
        order: PaperOrder,
        mode: RiskMode,
        sol_usd_price: float | None,
    ) -> str | None:
        """Recheck limits at fill time in case mode or portfolio state changed."""
        limits = self.risk_limits(mode)
        portfolio = self.snapshot(mode)
        capacity_positions = self._capacity_positions(portfolio)
        if len(capacity_positions) >= limits.max_open_positions:
            return "portfolio_capacity_reached"
        drawdown_limit = self.drawdown_limit_fraction(mode)
        if drawdown_limit is not None and portfolio.drawdown_fraction >= drawdown_limit:
            return "portfolio_drawdown_limit_reached"
        try:
            required = self._account_minor_from_sol(
                order.requested_sol_lamports
                + self.settings.network_fee_lamports
                + self.settings.priority_fee_lamports,
                sol_usd_price,
                ROUND_CEILING,
            )
        except ValueError:
            return "fresh_sol_usdc_conversion_unavailable"
        exposure = sum(position.entry_cost_lamports for position in capacity_positions)
        maximum = int(portfolio.equity_lamports * limits.max_exposure_fraction)
        if exposure + required > maximum:
            return "portfolio_exposure_limit_reached"
        if required > self.cash_lamports:
            return "paper_cash_insufficient"
        return None

    def expire_stuck_orders(self, now: datetime) -> list[PaperOrder]:
        expired: list[PaperOrder] = []
        for order in list(self.pending.values()):
            if (now - order.fill_after).total_seconds() > 90:
                self._fail_order(order, "no_fresh_executable_market_state_within_90_seconds", now)
                expired.append(order)
        return expired

    def snapshot(
        self,
        mode: RiskMode | None = None,
        *,
        persist_peak: bool = True,
    ) -> PortfolioSnapshot:
        now = datetime.now(UTC)
        positions: list[Position] = []
        active_positions: list[Position] = []
        blocked_positions: list[Position] = []
        stale_positions: list[Position] = []
        for stored in self.positions.values():
            age = (
                max(0.0, (now - stored.last_marked_at).total_seconds())
                if stored.last_marked_at
                else None
            )
            stale = (
                stored.mark_is_stale
                or age is None
                or age > self.settings.position_mark_stale_seconds
            )
            status = (
                PositionMarketStatus.DORMANT
                if stale
                else (
                    PositionMarketStatus.ACTIVE
                    if stored.mark_is_executable
                    else PositionMarketStatus.EXIT_BLOCKED
                )
            )
            blockers = list(stored.mark_blockers)
            if stale and "stale_market_data" not in blockers:
                blockers.append("stale_market_data")
            position = stored.model_copy(
                update={
                    "mark_age_seconds": age,
                    "mark_is_stale": stale,
                    "mark_is_executable": bool(not stale and stored.mark_is_executable),
                    "mark_blockers": blockers,
                    "market_status": status,
                }
            )
            positions.append(position)
            if stale:
                stale_positions.append(position)
            elif position.mark_is_executable:
                active_positions.append(position)
            else:
                blocked_positions.append(position)
        cash = self.cash_lamports
        inventory_mark = sum(position.last_mark_lamports for position in active_positions)
        blocked_mark = sum(position.last_mark_lamports for position in blocked_positions)
        stale_mark = sum(position.last_mark_lamports for position in stale_positions)
        last_known_inventory_mark = inventory_mark + blocked_mark + stale_mark
        excluded_positions = [*blocked_positions, *stale_positions]
        unrealized = sum(position.unrealized_pnl_lamports for position in active_positions) - sum(
            position.entry_cost_lamports for position in excluded_positions
        )
        reserved_cash = sum(
            order.reserved_account_minor
            for order in self.pending.values()
            if order.side == Side.BUY
        )
        available_cash = max(0, cash - reserved_cash)
        equity = max(0, cash + inventory_mark)
        if self.database.get_setting("equity_peak_basis") != EQUITY_PEAK_BASIS:
            # Older releases allowed indicative/unverified marks into the peak watermark. Their
            # historical equity highs cannot safely govern drawdown after executable-route
            # accounting. Cash observations remain trustworthy, as does current executable equity.
            previous_peak = max(
                self.starting_lamports,
                equity,
                self.database.max_recorded_cash(),
            )
            if persist_peak:
                self.database.set_setting("peak_equity_lamports", previous_peak)
                self.database.set_setting("equity_peak_basis", EQUITY_PEAK_BASIS)
        else:
            previous_peak = int(
                self.database.get_setting("peak_equity_lamports", self.starting_lamports)
            )
        peak = max(previous_peak, equity)
        if persist_peak and peak > previous_peak:
            self.database.set_setting("peak_equity_lamports", peak)
        drawdown = 0.0 if peak <= 0 else max(0.0, min(1.0, 1 - equity / peak))
        limit = self.drawdown_limit_fraction(mode)
        risk_halted = limit is not None and drawdown >= limit
        return PortfolioSnapshot(
            initialized=self.initialized,
            quote_currency=self.quote_currency,
            quote_decimals=self.quote_decimals,
            cash_lamports=cash,
            reserved_cash_lamports=reserved_cash,
            available_cash_lamports=available_cash,
            invested_value_lamports=inventory_mark,
            last_known_invested_value_lamports=last_known_inventory_mark,
            stale_invested_value_lamports=stale_mark,
            stale_position_count=len(stale_positions),
            route_blocked_invested_value_lamports=blocked_mark,
            route_blocked_position_count=len(blocked_positions),
            excluded_invested_value_lamports=blocked_mark + stale_mark,
            excluded_position_count=len(excluded_positions),
            starting_lamports=self.starting_lamports,
            equity_lamports=equity,
            last_known_equity_lamports=max(0, cash + last_known_inventory_mark),
            realized_pnl_lamports=int(self.database.get_setting("realized_pnl_lamports", 0)),
            unrealized_pnl_lamports=unrealized,
            drawdown_fraction=drawdown,
            risk_halted=risk_halted,
            risk_halt_reason=("portfolio_drawdown_limit_reached" if risk_halted else None),
            positions=positions,
            pending_orders=list(self.pending.values()),
        )

    def _record_equity(self, now: datetime, *, force: bool = False) -> None:
        if (
            not force
            and self._last_equity_recorded_at is not None
            and (now - self._last_equity_recorded_at).total_seconds()
            < self.settings.equity_sample_seconds
        ):
            return
        portfolio = self.snapshot()
        self.database.record_equity(portfolio.equity_lamports, portfolio.cash_lamports)
        self._last_equity_recorded_at = now

    def season_summary(self) -> dict[str, int | float]:
        """Return conservative, currency-safe metrics for the active paper season."""

        portfolio = self.snapshot(persist_peak=False)
        fills = self.database.list_fills(100_000)
        buys = {fill.mint: fill for fill in fills if fill.side == Side.BUY}
        closed_pnl = [
            fill.account_net_minor - buys[fill.mint].account_net_minor
            for fill in fills
            if fill.side == Side.SELL and fill.mint in buys
        ]
        total_fees = sum(
            fill.account_protocol_fee_minor + fill.account_network_fee_minor for fill in fills
        )
        return {
            "ending_equity_minor": portfolio.equity_lamports,
            "last_known_ending_equity_minor": portfolio.last_known_equity_lamports,
            "peak_equity_minor": max(
                self.starting_lamports,
                portfolio.equity_lamports,
                int(self.database.get_setting("peak_equity_lamports", 0)),
            ),
            "realized_pnl_minor": portfolio.realized_pnl_lamports,
            "net_pnl_minor": portfolio.equity_lamports - self.starting_lamports,
            "total_fees_minor": total_fees,
            "closed_trades": len(closed_pnl),
            "wins": sum(value > 0 for value in closed_pnl),
            "losses": sum(value < 0 for value in closed_pnl),
            "break_even": sum(value == 0 for value in closed_pnl),
            "ending_drawdown_fraction": portfolio.drawdown_fraction,
            "open_positions": len(portfolio.positions),
        }

    def reset(self) -> None:
        summary = self.season_summary() if self.initialized else None
        now = datetime.now(UTC)
        unresolved = (
            self.unresolved_position_records(now, reason="manual_reset") if self.initialized else []
        )
        self.database.reset_paper_state(
            summary,
            unresolved_positions=unresolved,
            comparable=not unresolved,
        )
        self.positions.clear()
        self.pending.clear()
        self.traded_mints.clear()
        self.starting_lamports = 0
        self.initialized = False
        self.season_id = None
        self.season_profile = None
        self._last_equity_recorded_at = None

    def rollover(
        self,
        now: datetime,
        *,
        next_profile: dict[str, Any] | None = None,
        terminal_reason: str = "auto_drawdown",
        next_running: bool = True,
        comparable: bool = True,
    ) -> tuple[str, str]:
        """Atomically archive this paper season and fund an identical new one."""

        if not self.initialized or not self.season_id:
            raise RuntimeError("automatic rollover requires an initialized paper season")
        if self.pending:
            raise RuntimeError("automatic rollover cannot discard pending paper orders")
        previous_season_id = str(self.season_id)
        next_season_id = "season-" + uuid.uuid4().hex
        resolved_profile = (
            dict(next_profile)
            if next_profile is not None
            else dict(self.season_profile)
            if self.season_profile
            else None
        )
        if resolved_profile is not None:
            resolved_profile["locked_at"] = now.isoformat() if next_running else None
        summary = self.season_summary()
        unresolved = self.unresolved_position_records(now, reason=terminal_reason)
        self.database.rollover_paper_state(
            season_summary=summary,
            next_season_id=next_season_id,
            starting_minor=self.starting_lamports,
            quote_currency=self.quote_currency.value,
            rolled_over_at=now,
            next_season_profile=resolved_profile,
            terminal_reason=terminal_reason,
            next_trading_enabled=next_running,
            unresolved_positions=unresolved,
            comparable=comparable and not unresolved,
        )
        self.positions.clear()
        self.pending.clear()
        self.traded_mints.clear()
        self.season_id = next_season_id
        self.season_profile = resolved_profile
        self._last_equity_recorded_at = now
        return previous_season_id, next_season_id

    def _account_minor_from_sol(
        self,
        sol_lamports: int,
        sol_usd_price: float | None,
        rounding: str,
    ) -> int:
        if self.quote_currency == QuoteCurrency.SOL:
            return sol_lamports
        if sol_usd_price is None or not 0 < sol_usd_price < 1_000_000:
            raise ValueError("fresh SOL/USDC conversion is unavailable")
        converted = (
            Decimal(sol_lamports)
            * Decimal(str(sol_usd_price))
            * Decimal(USDC_MINOR_PER_UNIT)
            / Decimal(LAMPORTS_PER_SOL)
        )
        return max(0, int(converted.to_integral_value(rounding=rounding)))

    def _sol_lamports_from_account_minor(
        self,
        account_minor: int,
        sol_usd_price: float | None,
    ) -> int:
        if self.quote_currency == QuoteCurrency.SOL:
            return max(0, account_minor)
        if sol_usd_price is None or not 0 < sol_usd_price < 1_000_000:
            raise ValueError("fresh SOL/USDC conversion is unavailable")
        converted = (
            Decimal(account_minor)
            * Decimal(LAMPORTS_PER_SOL)
            / (Decimal(str(sol_usd_price)) * Decimal(USDC_MINOR_PER_UNIT))
        )
        return max(0, int(converted.to_integral_value(rounding=ROUND_FLOOR)))

    def _account_fill_values(
        self,
        *,
        side: Side,
        gross_sol: int,
        protocol_fee_sol: int,
        network_fee_sol: int,
        wallet_sol: int,
        sol_usd_price: float | None,
    ) -> dict[str, int]:
        if side == Side.BUY:
            total = self._account_minor_from_sol(wallet_sol, sol_usd_price, ROUND_CEILING)
            protocol = self._account_minor_from_sol(protocol_fee_sol, sol_usd_price, ROUND_CEILING)
            network = self._account_minor_from_sol(network_fee_sol, sol_usd_price, ROUND_CEILING)
            gross = max(0, total - protocol - network)
        else:
            net = self._account_minor_from_sol(wallet_sol, sol_usd_price, ROUND_FLOOR)
            protocol = self._account_minor_from_sol(protocol_fee_sol, sol_usd_price, ROUND_CEILING)
            network = self._account_minor_from_sol(network_fee_sol, sol_usd_price, ROUND_CEILING)
            gross = net + protocol + network
            total = net
        return {
            "account_gross_minor": gross,
            "account_protocol_fee_minor": protocol,
            "account_network_fee_minor": network,
            "account_net_minor": total,
        }
