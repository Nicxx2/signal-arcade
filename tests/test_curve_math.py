from __future__ import annotations

import pytest
from signal_arcade.paper.curve_math import quote_buy, quote_sell

VIRTUAL_TOKEN = 1_073_000_000_000_000
VIRTUAL_SOL = 30_000_000_000
REAL_TOKEN = 793_100_000_000_000


def test_round_trip_is_net_negative_after_curve_and_fees() -> None:
    buy = quote_buy(
        virtual_token_reserves=VIRTUAL_TOKEN,
        virtual_sol_reserves=VIRTUAL_SOL,
        real_token_reserves=REAL_TOKEN,
        wallet_trade_budget_lamports=25_000_000,
        fee_bps=125,
        network_fee_lamports=15_000,
    )
    next_virtual_token = VIRTUAL_TOKEN - buy.token_units
    next_virtual_sol = VIRTUAL_SOL + buy.curve_sol_lamports
    sell = quote_sell(
        virtual_token_reserves=next_virtual_token,
        virtual_sol_reserves=next_virtual_sol,
        token_units=buy.token_units,
        fee_bps=125,
        network_fee_lamports=15_000,
    )
    assert buy.token_units > 0
    assert buy.wallet_sol_lamports <= 25_015_000
    assert sell.wallet_sol_lamports < buy.wallet_sol_lamports
    assert 0 <= buy.price_impact_fraction < 0.01


def test_buy_never_exceeds_real_reserves() -> None:
    quote = quote_buy(
        virtual_token_reserves=1_000_000,
        virtual_sol_reserves=1_000_000,
        real_token_reserves=10,
        wallet_trade_budget_lamports=900_000,
        fee_bps=0,
        network_fee_lamports=0,
    )
    assert quote.token_units == 10


@pytest.mark.parametrize(
    "token_reserves,sol_reserves",
    [(0, 1), (1, 0), (-1, 1), (1, -1)],
)
def test_invalid_reserves_fail_closed(token_reserves: int, sol_reserves: int) -> None:
    with pytest.raises(ValueError):
        quote_sell(
            virtual_token_reserves=token_reserves,
            virtual_sol_reserves=sol_reserves,
            token_units=10_000_000_000,
            fee_bps=125,
            network_fee_lamports=0,
        )


def test_sell_fails_when_fees_exceed_proceeds() -> None:
    with pytest.raises(ValueError, match="fees exceed"):
        quote_sell(
            virtual_token_reserves=VIRTUAL_TOKEN,
            virtual_sol_reserves=VIRTUAL_SOL,
            token_units=10_000_000_000,
            fee_bps=125,
            network_fee_lamports=1_000_000_000,
        )


def test_sell_cannot_exceed_exact_quote_vault_liquidity() -> None:
    with pytest.raises(ValueError, match="exceeds real quote reserves"):
        quote_sell(
            virtual_token_reserves=1_000_000,
            virtual_sol_reserves=2_000_000,
            token_units=1_000_000,
            fee_bps=0,
            network_fee_lamports=0,
            real_quote_reserves=100,
        )

    quote = quote_sell(
        virtual_token_reserves=1_000_000,
        virtual_sol_reserves=2_000_000,
        token_units=1_000_000,
        fee_bps=0,
        network_fee_lamports=0,
        real_quote_reserves=1_000_000,
    )
    assert quote.curve_sol_lamports == 1_000_000
