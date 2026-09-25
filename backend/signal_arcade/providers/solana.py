from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import struct
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import websockets

from ..models import EventKind, MarketEvent
from .anchor import AnchorEventDecoder, b58encode
from .telemetry import ProviderTelemetry, SubscriptionError, failure, record

logger = logging.getLogger(__name__)
STABLE_STREAM_SECONDS = 60.0

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_AMM_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
SUPPORTED_PROGRAMS = {PUMP_PROGRAM, PUMP_AMM_PROGRAM}
PROGRAM_INVOKE = re.compile(r"^Program ([1-9A-HJ-NP-Za-km-z]{30,50}) invoke \[(\d+)]$")
PROGRAM_EXIT = re.compile(r"^Program ([1-9A-HJ-NP-Za-km-z]{30,50}) (?:success|failed:.*)$")


EVENT_KINDS = {
    "createevent": EventKind.CREATE,
    "createpoolevent": EventKind.CREATE,
    "completeevent": EventKind.COMPLETE,
    "completepumpammmigrationevent": EventKind.MIGRATE,
    "tradeevent": EventKind.TRADE,
    "buyevent": EventKind.TRADE,
    "sellevent": EventKind.TRADE,
    # These update reserves or creator metadata, but are never executable paper ticks.
    "depositevent": EventKind.MARKET,
    "withdrawevent": EventKind.MARKET,
    "boostbuyandburnevent": EventKind.MARKET,
    "setcreatorevent": EventKind.MARKET,
    "adminsetcreatorevent": EventKind.MARKET,
    "migratebondingcurvecreatorevent": EventKind.MARKET,
    "setmetaplexcreatorevent": EventKind.MARKET,
    "setbondingcurvecoincreatorevent": EventKind.MARKET,
    "adminsetcoincreatorevent": EventKind.MARKET,
    "migratepoolcoincreatorevent": EventKind.MARKET,
    "setmetaplexcoincreatorevent": EventKind.MARKET,
}


def _kind_for_event(name: str) -> EventKind | None:
    return EVENT_KINDS.get(name.lower().replace("_", ""))


def _mint_for_payload(payload: dict[str, Any]) -> str | None:
    for key in ("mint", "base_mint", "baseMint", "token_mint", "tokenMint"):
        value = payload.get(key)
        if isinstance(value, str) and 30 <= len(value) <= 50:
            return value
    return None


class SolanaLogProvider:
    """One shared Solana WebSocket connection with two program subscriptions."""

    def __init__(
        self,
        ws_url: str,
        idl_dir: Path,
        *,
        fallback_ws_url: str | None = None,
        max_pool_mappings: int = 50_000,
    ) -> None:
        if max_pool_mappings < 1:
            raise ValueError("max_pool_mappings must be positive")
        self.ws_url = ws_url
        self.fallback_ws_url = fallback_ws_url if fallback_ws_url != ws_url else None
        self.active_ws_url = ws_url
        self.using_fallback = False
        self.fallback_reason: str | None = None
        self.decoder = AnchorEventDecoder([idl_dir / "pump.json", idl_dir / "pump_amm.json"])
        self.connected = False
        self.last_message_at: datetime | None = None
        self.reconnects = 0
        self.last_error: str | None = None
        self.next_retry_at: datetime | None = None
        self.telemetry = ProviderTelemetry("ws")
        self._generation = 0
        self._configuration_changed = asyncio.Event()
        self._attempt_stable = False
        self.max_pool_mappings = max_pool_mappings
        self.pool_mints: OrderedDict[str, str] = OrderedDict()
        self.pool_quotes: OrderedDict[str, str] = OrderedDict()

    def remember_pool_mapping(self, payload: dict[str, Any]) -> None:
        pool = payload.get("pool")
        base_mint = payload.get("base_mint") or payload.get("baseMint") or payload.get("mint")
        if not (
            isinstance(pool, str)
            and 30 <= len(pool) <= 50
            and isinstance(base_mint, str)
            and 30 <= len(base_mint) <= 50
        ):
            return
        self.pool_mints[pool] = base_mint
        self.pool_mints.move_to_end(pool)
        quote_mint = payload.get("quote_mint") or payload.get("quoteMint")
        if isinstance(quote_mint, str) and 30 <= len(quote_mint) <= 50:
            self.pool_quotes[pool] = quote_mint
            self.pool_quotes.move_to_end(pool)
        while len(self.pool_mints) > self.max_pool_mappings:
            removed_pool, _mint = self.pool_mints.popitem(last=False)
            self.pool_quotes.pop(removed_pool, None)

    def mint_for_pool(self, pool: str) -> str | None:
        mint = self.pool_mints.get(pool)
        if mint is not None:
            self.pool_mints.move_to_end(pool)
        return mint

    async def run(
        self,
        handler: Callable[[MarketEvent], Awaitable[None]],
        stop: asyncio.Event,
    ) -> None:
        backoff = 1.0
        try:
            while not stop.is_set():
                generation, telemetry = self._generation, self.telemetry
                self._configuration_changed.clear()
                self._attempt_stable = False
                try:
                    self.next_retry_at = None
                    role = "fallback" if self.using_fallback else "primary"
                    record(telemetry, "attempt", role=role, operation="stream")
                    await self._run_once(handler, stop)
                    backoff = 1.0
                except asyncio.CancelledError:
                    record(telemetry, "cancelled", role=role, operation="stream")
                    raise
                except Exception as exc:  # provider boundary must not stop the app
                    if generation != self._generation:
                        record(telemetry, "context_changed", role=role, operation="stream")
                        backoff = 1.0
                        continue
                    self.connected = False
                    self.last_error = self._safe_error(exc)
                    self.reconnects += 1
                    if self._attempt_stable and not self._is_rate_limited(exc):
                        backoff = 1.0
                    if self._activate_fallback(exc):
                        delay, backoff = 1.0, 1.0
                    else:
                        delay, backoff = self._retry_backoff(exc, backoff)
                    category, code = failure(exc)
                    record(
                        telemetry,
                        category,
                        role=role,
                        operation="stream",
                        code=code,
                        retry=delay,
                    )
                    self.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                    logger.warning("Solana stream disconnected: %s", self.last_error)
                    await self._wait_retry(stop, delay)
                    if generation != self._generation:
                        backoff = 1.0
        finally:
            self.connected = False
            self.next_retry_at = None

    async def _wait_retry(self, stop: asyncio.Event, delay: float) -> None:
        """Both shutdown and explicit settings changes interrupt retry waiting."""
        waiters = [
            asyncio.create_task(event.wait()) for event in (stop, self._configuration_changed)
        ]
        try:
            await asyncio.wait(waiters, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waiters:
                task.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

    async def _run_once(
        self,
        handler: Callable[[MarketEvent], Awaitable[None]],
        stop: asyncio.Event,
    ) -> None:
        generation, telemetry = self._generation, self.telemetry
        self._attempt_stable = False
        acknowledged_at: float | None = None
        async with websockets.connect(
            self.active_ws_url,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=60,
            max_size=4 * 1024 * 1024,
            max_queue=1_024,
            close_timeout=5,
        ) as socket:
            if generation != self._generation:
                return
            self.connected = False
            self.last_error = None
            for request_id, program in enumerate((PUMP_PROGRAM, PUMP_AMM_PROGRAM), start=1):
                if generation != self._generation:
                    return
                await socket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [program]},
                                {"commitment": "confirmed"},
                            ],
                        }
                    )
                )
            acknowledged: dict[int, int] = {}
            while not stop.is_set() and generation == self._generation:
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=30)
                except TimeoutError:
                    await socket.ping()
                    continue
                # A busy provider can keep thousands of already-buffered messages ready. Some
                # WebSocket ``recv`` calls then complete without suspending, so explicitly give
                # HTTP, health and market-worker tasks a scheduling turn between messages.
                await asyncio.sleep(0)
                if generation != self._generation:
                    return
                self.last_message_at = datetime.now(UTC)
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError("Malformed stream envelope")
                if message.get("error") is not None:
                    error = message.get("error") or {}
                    code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                    raise SubscriptionError(code)
                params = message.get("params")
                if not params:
                    response_id = message.get("id")
                    subscription = message.get("result")
                    if (
                        type(response_id) is int
                        and response_id in {1, 2}
                        and type(subscription) is int
                        and subscription >= 0
                    ):
                        acknowledged.setdefault(response_id, subscription)
                        self.connected = (
                            set(acknowledged) == {1, 2} and len(set(acknowledged.values())) == 2
                        )
                        if self.connected and acknowledged_at is None:
                            acknowledged_at = time.monotonic()
                            record(
                                telemetry,
                                "response",
                                operation="stream",
                                role="fallback" if self.using_fallback else "primary",
                            )
                    continue
                if not isinstance(params, dict):
                    raise ValueError("Malformed stream params")
                result = params.get("result", {})
                if not isinstance(result, dict):
                    raise ValueError("Malformed stream result")
                context = result.get("context", {})
                value = result.get("value", {})
                if not isinstance(context, dict) or not isinstance(value, dict):
                    raise ValueError("Malformed stream notification")
                if (
                    not self._attempt_stable
                    and acknowledged_at is not None
                    and time.monotonic() - acknowledged_at >= STABLE_STREAM_SECONDS
                    and message.get("method") == "logsNotification"
                    and type(params.get("subscription")) is int
                    and params["subscription"] in acknowledged.values()
                    and type(context.get("slot")) is int
                    and context["slot"] > 0
                    and isinstance(value.get("signature"), str)
                    and bool(value["signature"])
                    and isinstance(value.get("logs"), list)
                    and "err" in value
                    and (value["err"] is None or isinstance(value["err"], dict))
                    and all(isinstance(line, str) for line in value["logs"])
                ):
                    self._attempt_stable = True
                if value.get("err") is not None:
                    continue
                signature = str(value.get("signature") or "")
                slot = int(context.get("slot") or 0)
                logs = value.get("logs") or []
                for event in self.events_from_logs(signature, slot, logs):
                    # A handler can yield under queue backpressure. Recheck before
                    # handing off another decoded event from the same notification.
                    if stop.is_set() or generation != self._generation:
                        return
                    await handler(event)

    def events_from_logs(
        self,
        signature: str,
        slot: int,
        logs: list[Any],
    ) -> list[MarketEvent]:
        """Decode only data emitted by the active supported program invocation."""
        stack: list[str] = []
        events: list[MarketEvent] = []
        for index, raw_line in enumerate(logs):
            line = str(raw_line)
            invoked = PROGRAM_INVOKE.match(line)
            if invoked:
                program, raw_depth = invoked.groups()
                depth = int(raw_depth)
                if depth < 1 or depth > 64:
                    stack.clear()
                    continue
                stack[depth - 1 :] = [program]
                continue
            exited = PROGRAM_EXIT.match(line)
            if exited:
                program = exited.group(1)
                for position in range(len(stack) - 1, -1, -1):
                    if stack[position] == program:
                        stack[position:] = []
                        break
                continue
            if not stack or stack[-1] not in SUPPORTED_PROGRAMS:
                continue
            decoded = self.decoder.decode_log_line(line, stack[-1])
            if decoded is None:
                continue
            program, event_name, payload = decoded
            if program != stack[-1]:
                continue
            kind = _kind_for_event(event_name)
            if kind is None:
                continue
            payload["event_name"] = event_name
            mint = _mint_for_payload(payload)
            self.remember_pool_mapping(payload)
            pool = payload.get("pool")
            if mint is None and isinstance(pool, str):
                mint = self.mint_for_pool(pool)
            if isinstance(pool, str) and "quote_mint" not in payload:
                quote_mint = self.pool_quotes.get(pool)
                if quote_mint is not None:
                    self.pool_quotes.move_to_end(pool)
                    payload["quote_mint"] = quote_mint
            identity = f"{signature}:{slot}:{program}:{index}:{event_name}"
            event_id = hashlib.sha256(identity.encode()).hexdigest()
            events.append(
                MarketEvent(
                    event_id=event_id,
                    source=f"solana:{program}",
                    kind=kind,
                    mint=mint,
                    signature=signature or None,
                    slot=slot,
                    payload=payload,
                )
            )
        return events

    def decode_pump_swap_pool(self, raw: bytes) -> dict[str, Any] | None:
        decoded = self.decoder.decode_account(
            raw,
            expected_program=PUMP_AMM_PROGRAM,
            expected_name="Pool",
        )
        if decoded is None:
            return None
        _program, _name, values = decoded
        return values

    def decode_pump_bonding_curve(self, raw: bytes) -> dict[str, Any] | None:
        decoded = self.decoder.decode_account(
            raw,
            expected_program=PUMP_PROGRAM,
            expected_name="BondingCurve",
        )
        if decoded is None:
            return None
        _program, _name, values = decoded
        return values

    @staticmethod
    def decode_token_account(raw: bytes) -> dict[str, Any] | None:
        """Decode the fixed SPL account prefix shared by Token and Token-2022 accounts."""

        if len(raw) < 165 or raw[108] not in {1, 2}:
            return None
        return {
            "mint": b58encode(raw[:32]),
            "authority": b58encode(raw[32:64]),
            "amount": struct.unpack_from("<Q", raw, 64)[0],
            "state": raw[108],
        }

    def _safe_error(self, exc: Exception) -> str:
        category, code = failure(exc)
        role = "fallback" if self.using_fallback else "primary"
        return f"{role} stream: {category}" + (f" ({code})" if code is not None else "")

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return bool(status == 429 or re.search(r"\bHTTP\s+429\b", str(exc), re.IGNORECASE))

    def _activate_fallback(self, exc: Exception) -> bool:
        rate_limited = self._is_rate_limited(exc)
        rejected = getattr(getattr(exc, "response", None), "status_code", None) == 413
        if self.using_fallback or self.fallback_ws_url is None or not (rate_limited or rejected):
            return False
        self.active_ws_url = self.fallback_ws_url
        self.using_fallback = True
        self.fallback_reason = "primary_rate_limited" if rate_limited else "primary_http_413"
        return True

    def configure(self, ws_url: str, *, fallback_ws_url: str | None = None) -> None:
        """Apply an explicit provider change and reset any previous runtime fallback."""
        self._generation += 1
        self._configuration_changed.set()
        self._attempt_stable = False
        self.telemetry = ProviderTelemetry("ws")
        self.connected = False
        self.last_error = None
        self.last_message_at = None
        self.ws_url = ws_url
        self.fallback_ws_url = fallback_ws_url if fallback_ws_url != ws_url else None
        self.active_ws_url = ws_url
        self.using_fallback = False
        self.fallback_reason = None
        self.next_retry_at = None

    @staticmethod
    def _retry_backoff(exc: Exception, current: float) -> tuple[float, float]:
        """Honor provider rate limits without turning restarts into a reconnect storm."""
        response = getattr(exc, "response", None)
        rate_limited = SolanaLogProvider._is_rate_limited(exc)
        rejected = getattr(response, "status_code", None) == 413
        if not rate_limited and not rejected:
            return current, min(30.0, current * 2)

        retry_after = 0.0
        headers = getattr(response, "headers", None)
        if headers is not None:
            raw_retry_after = headers.get("Retry-After")
            with suppress(TypeError, ValueError):
                retry_after = float(raw_retry_after)
        if not math.isfinite(retry_after):
            retry_after = 0.0
        if not rate_limited:
            if retry_after <= 0:
                return current, min(30.0, current * 2)
            delay = min(300.0, max(current, retry_after))
            return delay, min(300.0, delay * 2)
        delay = min(300.0, max(60.0, current, retry_after))
        return delay, min(300.0, max(60.0, delay * 2))

    def health(self) -> dict[str, Any]:
        age: float | None = None
        if self.last_message_at:
            age = max(0.0, (datetime.now(UTC) - self.last_message_at).total_seconds())
        return {
            "connected": self.connected,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "message_age_seconds": age,
            "reconnects": self.reconnects,
            "last_error": self.last_error,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "fallback_active": self.using_fallback,
            "fallback_reason": self.fallback_reason,
            "idl_events": len(self.decoder.events),
            "pool_mappings": len(self.pool_mints),
            "max_pool_mappings": self.max_pool_mappings,
        }
