from __future__ import annotations

import asyncio
import hashlib
import math
import random
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

from ..models import EventKind, MarketEvent
from .anchor import b58encode


class DemoFeed:
    """Clearly labelled synthetic stream for onboarding and offline verification."""

    def __init__(self, seed: int = 7) -> None:
        self.random = random.Random(seed)  # noqa: S311 -- deterministic synthetic demo
        self.session_id = uuid.uuid4().hex[:12]
        self.sequence = 0
        self.started_at: datetime | None = None
        self.last_message_at: datetime | None = None

    async def run(
        self,
        handler: Callable[[MarketEvent], Awaitable[None]],
        stop: asyncio.Event,
    ) -> None:
        self.started_at = datetime.now(UTC)
        token_index = 0
        while not stop.is_set():
            token_index += 1
            await self._run_token(handler, stop, token_index)

    async def _run_token(
        self,
        handler: Callable[[MarketEvent], Awaitable[None]],
        stop: asyncio.Event,
        token_index: int,
    ) -> None:
        mint = b58encode(
            hashlib.sha256(f"signal-arcade-demo-{self.session_id}-{token_index}".encode()).digest()
        )
        created = datetime.now(UTC)
        virtual_token = 1_073_000_000_000_000
        virtual_sol = 30_000_000_000
        real_token = 793_100_000_000_000
        creator = b58encode(hashlib.sha256(f"creator-{token_index}".encode()).digest())
        await handler(
            self._event(
                EventKind.CREATE,
                mint,
                {
                    "event_name": "create_event",
                    "name": f"Demo Signal {token_index}",
                    "symbol": f"DEMO{token_index}",
                    "uri": "demo://synthetic",
                    "creator": creator,
                    "timestamp": int(created.timestamp()),
                    "virtual_token_reserves": virtual_token,
                    "virtual_sol_reserves": virtual_sol,
                    "real_token_reserves": real_token,
                    "token_total_supply": 1_000_000_000_000_000,
                    "demo": True,
                },
            )
        )
        for tick in range(75):
            if stop.is_set():
                return
            phase = tick / 74
            buy_probability = 0.62 + 0.16 * math.sin(phase * math.pi)
            is_buy = self.random.random() < buy_probability
            quote = self.random.randint(8_000_000, 90_000_000)
            if tick > 55:
                trending_up = token_index % 3 != 0
                is_buy = self.random.random() < (0.92 if trending_up else 0.18)
                quote = self.random.randint(600_000_000, 900_000_000)
            k = virtual_token * virtual_sol
            if is_buy:
                next_sol = virtual_sol + quote
                next_token = math.ceil(k / next_sol)
                token_amount = max(1, virtual_token - next_token)
                virtual_sol, virtual_token = next_sol, next_token
                real_token = max(0, real_token - token_amount)
            else:
                token_amount = max(1, int(quote / max(virtual_sol, 1) * virtual_token))
                next_token = virtual_token + token_amount
                next_sol = max(1, math.ceil(k / next_token))
                quote = max(1, virtual_sol - next_sol)
                virtual_sol, virtual_token = next_sol, next_token
                real_token += token_amount
            user = b58encode(
                hashlib.sha256(f"demo-wallet-{token_index}-{tick % 19}".encode()).digest()
            )
            await handler(
                self._event(
                    EventKind.TRADE,
                    mint,
                    {
                        "event_name": "trade_event",
                        "is_buy": is_buy,
                        "user": user,
                        "creator": creator,
                        "sol_amount": quote,
                        "token_amount": token_amount,
                        "virtual_token_reserves": virtual_token,
                        "virtual_sol_reserves": virtual_sol,
                        "real_token_reserves": real_token,
                        "timestamp": int(datetime.now(UTC).timestamp()),
                        "demo": True,
                    },
                )
            )
            await asyncio.sleep(0.35)
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=5)

    def _event(self, kind: EventKind, mint: str, payload: dict[str, object]) -> MarketEvent:
        self.sequence += 1
        now = datetime.now(UTC)
        self.last_message_at = now
        return MarketEvent(
            event_id=f"demo-{self.session_id}-{self.sequence}",
            source="demo:synthetic",
            kind=kind,
            mint=mint,
            signature=f"DEMO-{self.session_id}-{self.sequence}",
            slot=self.sequence,
            block_time=now,
            received_at=now,
            payload=payload,
        )

    def health(self) -> dict[str, object]:
        return {
            "connected": self.started_at is not None,
            "synthetic": True,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }
