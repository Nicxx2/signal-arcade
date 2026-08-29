from __future__ import annotations

from dataclasses import dataclass


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return -(-numerator // denominator)


@dataclass(frozen=True, slots=True)
class CurveQuote:
    token_units: int
    curve_sol_lamports: int
    protocol_fee_lamports: int
    network_fee_lamports: int
    wallet_sol_lamports: int
    price_impact_fraction: float


def quote_buy(
    *,
    virtual_token_reserves: int,
    virtual_sol_reserves: int,
    real_token_reserves: int,
    wallet_trade_budget_lamports: int,
    fee_bps: int,
    network_fee_lamports: int,
) -> CurveQuote:
    """Quote a Pump-style constant-product buy with conservative integer rounding."""
    _validate_reserves(virtual_token_reserves, virtual_sol_reserves)
    if real_token_reserves <= 0:
        raise ValueError("no real token reserves remain")
    if wallet_trade_budget_lamports <= 0:
        raise ValueError("trade budget must be positive")
    if not 0 <= fee_bps <= 10_000:
        raise ValueError("fee_bps outside supported range")
    curve_input = wallet_trade_budget_lamports * 10_000 // (10_000 + fee_bps)
    while curve_input > 0:
        protocol_fee = ceil_div(curve_input * fee_bps, 10_000)
        if curve_input + protocol_fee <= wallet_trade_budget_lamports:
            break
        curve_input -= 1
    if curve_input <= 0:
        raise ValueError("trade budget is smaller than fees")
    invariant = virtual_token_reserves * virtual_sol_reserves
    next_sol = virtual_sol_reserves + curve_input
    next_token = ceil_div(invariant, next_sol)
    token_out = min(real_token_reserves, virtual_token_reserves - next_token)
    if token_out <= 0:
        raise ValueError("quote produced no token output")
    spot = virtual_sol_reserves / virtual_token_reserves
    execution = curve_input / token_out
    impact = max(0.0, execution / spot - 1) if spot > 0 else 1.0
    return CurveQuote(
        token_units=token_out,
        curve_sol_lamports=curve_input,
        protocol_fee_lamports=protocol_fee,
        network_fee_lamports=network_fee_lamports,
        wallet_sol_lamports=curve_input + protocol_fee + network_fee_lamports,
        price_impact_fraction=min(1.0, impact),
    )


def quote_sell(
    *,
    virtual_token_reserves: int,
    virtual_sol_reserves: int,
    token_units: int,
    fee_bps: int,
    network_fee_lamports: int,
    real_quote_reserves: int | None = None,
) -> CurveQuote:
    """Quote a Pump-style constant-product sell with fees deducted from proceeds."""
    _validate_reserves(virtual_token_reserves, virtual_sol_reserves)
    if token_units <= 0:
        raise ValueError("token amount must be positive")
    if not 0 <= fee_bps <= 10_000:
        raise ValueError("fee_bps outside supported range")
    invariant = virtual_token_reserves * virtual_sol_reserves
    next_token = virtual_token_reserves + token_units
    next_sol = ceil_div(invariant, next_token)
    gross = virtual_sol_reserves - next_sol
    if gross <= 0:
        raise ValueError("quote produced no SOL output")
    if real_quote_reserves is not None:
        if real_quote_reserves < 0 or real_quote_reserves.bit_length() > 127:
            raise ValueError("real quote reserves are invalid")
        # Virtual reserves shape Pump/PumpSwap pricing but are not spendable liquidity.
        # Never report or fill a paper exit that the exact quote vault cannot cover.
        if gross > real_quote_reserves:
            raise ValueError("sell output exceeds real quote reserves")
    protocol_fee = ceil_div(gross * fee_bps, 10_000)
    wallet_received = gross - protocol_fee - network_fee_lamports
    if wallet_received <= 0:
        raise ValueError("fees exceed sell proceeds")
    spot = virtual_sol_reserves / virtual_token_reserves
    execution = gross / token_units
    impact = max(0.0, 1 - execution / spot) if spot > 0 else 1.0
    return CurveQuote(
        token_units=token_units,
        curve_sol_lamports=gross,
        protocol_fee_lamports=protocol_fee,
        network_fee_lamports=network_fee_lamports,
        wallet_sol_lamports=wallet_received,
        price_impact_fraction=min(1.0, impact),
    )


def _validate_reserves(token_reserves: int, sol_reserves: int) -> None:
    if token_reserves <= 0 or sol_reserves <= 0:
        raise ValueError("reserves must be positive")
    if token_reserves.bit_length() > 127 or sol_reserves.bit_length() > 127:
        raise ValueError("reserve value is unreasonably large")
