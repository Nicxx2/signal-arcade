"""Pure quote replay from immutable receipts and orders; never trading authority."""

from __future__ import annotations

from typing import Literal

from ..models import FillReceipt, PaperOrder, Side
from .curve_math import quote_buy, quote_sell


def fee_quote_replay_status(
    fill: FillReceipt, order: PaperOrder | None
) -> Literal["unavailable", "invalid_inputs", "matched", "mismatch"]:
    """Check quote arithmetic only, independently of chronology and ledger audits.

    Unknown legacy provenance is not an accounting failure. No current settings,
    market prices, database reads or inferred historical fee splits are used.
    """
    recipe = fill.execution_fee_provenance
    reserve = fill.reserve_snapshot
    if recipe is None or reserve is None or order is None:
        return "unavailable"
    if type(recipe.get("version")) is not int or recipe["version"] != 1:
        return "unavailable"
    if (
        set(recipe) != {"version", "rounding", "fee_components", "lp_fee_bps", "source"}
        or recipe["source"] not in ("observed_event", "configured_fallback")
        or order.order_id != fill.order_id
        or order.mint != fill.mint
        or order.side != fill.side
    ):
        return "invalid_inputs"
    parts = recipe["fee_components"]
    lp = recipe["lp_fee_bps"]
    if type(lp) is not int or not 0 <= lp <= 10_000:
        return "invalid_inputs"
    if parts is None:
        if recipe["rounding"] != "aggregate" or lp != 0:
            return "invalid_inputs"
    elif (
        fill.side != Side.SELL
        or recipe["rounding"] != "components"
        or not isinstance(parts, list)
        or len(parts) > 16
        or any(type(part) is not int or not 0 <= part <= 10_000 for part in parts)
    ):
        return "invalid_inputs"
    try:
        if fill.side == Side.BUY:
            quote = quote_buy(
                virtual_token_reserves=reserve.virtual_token_reserves,
                virtual_sol_reserves=reserve.virtual_quote_reserves,
                real_token_reserves=reserve.real_token_reserves,
                wallet_trade_budget_lamports=order.requested_sol_lamports,
                fee_bps=reserve.fee_bps,
                network_fee_lamports=fill.network_fee_lamports,
            )
        else:
            quote = quote_sell(
                virtual_token_reserves=reserve.virtual_token_reserves,
                virtual_sol_reserves=reserve.virtual_quote_reserves,
                real_quote_reserves=reserve.real_quote_reserves,
                token_units=fill.token_units,
                fee_bps=reserve.fee_bps,
                network_fee_lamports=fill.network_fee_lamports,
                fee_components=tuple(parts) if parts is not None else None,
                lp_fee_bps=lp,
            )
    except ValueError:
        return "invalid_inputs"
    return (
        "matched"
        if (
            quote.token_units == fill.token_units
            and quote.curve_sol_lamports == fill.gross_sol_lamports
            and quote.protocol_fee_lamports == fill.protocol_fee_lamports
            and quote.network_fee_lamports == fill.network_fee_lamports
            and quote.wallet_sol_lamports == fill.net_sol_lamports
        )
        else "mismatch"
    )
