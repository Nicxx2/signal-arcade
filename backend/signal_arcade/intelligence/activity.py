"""Bounded descriptive activity evidence; not a trading or qualification policy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from ..models import Side

ACTIVITY_UNITS = {
    "buy_quote_volume_ratio_5m": "fraction",
    "signed_net_quote_flow_ratio_5m": "fraction",
    "meaningful_trade_count_1m": "count",
    "meaningful_trade_count_5m": "count",
    "meaningful_trade_wallet_count_5m": "count",
    "net_buy_wallet_count_5m": "count",
    "trade_amount_coverage_5m": "fraction",
}
MEANINGFUL_QUOTE_LAMPORTS = 10_000_000  # Descriptive 0.01 SOL cutoff, not an entry gate.
ActivityMetric = tuple[float | int | None, float, str | None]


class ActivityTrade(Protocol):
    received_at: datetime
    quote_lamports: int
    user: str
    side: Side


def activity_metrics(trades: Sequence[ActivityTrade], now: datetime) -> dict[str, ActivityMetric]:
    """Use the caller's already filtered, venue-local five-minute window in one pass.

    One wallet is not one person. Wallet counts neither infer independence nor attest
    legitimacy. Partial amounts cannot safely describe value flow (an unknown sell may
    be large), so quantitative results require complete amounts in this observed window.
    Continuity, freshness and buffer coverage remain separate snapshot evidence.
    """
    if not trades:
        return {name: (None, 0.0, "insufficient_trade_evidence") for name in ACTIVITY_UNITS}
    gross = buys = valued = meaningful_1m = meaningful_5m = known = 0
    meaningful_wallets: set[str] = set()
    wallet_net: dict[str, int] = defaultdict(int)
    for trade in trades:
        amount = trade.quote_lamports
        wallet_known = bool(trade.user and trade.user != "unknown")
        known += wallet_known
        if amount <= 0:
            continue
        valued += 1
        gross += amount
        buys += amount if trade.side == Side.BUY else 0
        if wallet_known:
            wallet_net[trade.user] += amount if trade.side == Side.BUY else -amount
        if amount >= MEANINGFUL_QUOTE_LAMPORTS:
            meaningful_5m += 1
            meaningful_1m += (now - trade.received_at).total_seconds() <= 60
            if wallet_known:
                meaningful_wallets.add(trade.user)

    amount_quality = valued / len(trades)
    wallet_quality = min(amount_quality, known / len(trades))

    def metric(value: float | int, quality: float, reason: str) -> ActivityMetric:
        return (value, quality, None) if quality == 1.0 else (None, quality, reason)

    return {
        "trade_amount_coverage_5m": (amount_quality, 1.0, None),
        "buy_quote_volume_ratio_5m": metric(
            buys / gross if gross else 0.0, amount_quality, "trade_amount_unavailable"
        ),
        "signed_net_quote_flow_ratio_5m": metric(
            (2 * buys - gross) / gross if gross else 0.0,
            amount_quality,
            "trade_amount_unavailable",
        ),
        "meaningful_trade_count_1m": metric(
            meaningful_1m, amount_quality, "trade_amount_unavailable"
        ),
        "meaningful_trade_count_5m": metric(
            meaningful_5m, amount_quality, "trade_amount_unavailable"
        ),
        "meaningful_trade_wallet_count_5m": metric(
            len(meaningful_wallets), wallet_quality, "wallet_or_trade_amount_unavailable"
        ),
        "net_buy_wallet_count_5m": metric(
            sum(amount >= MEANINGFUL_QUOTE_LAMPORTS for amount in wallet_net.values()),
            wallet_quality,
            "wallet_or_trade_amount_unavailable",
        ),
    }
