from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import struct
import time
from collections.abc import Callable
from typing import Any

import httpx

from ..quota import QuotaBroker

logger = logging.getLogger(__name__)

SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # noqa: S105
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105
SAFE_TOKEN_2022_MINT_EXTENSIONS = {
    18,  # MetadataPointer
    19,  # TokenMetadata
}  # Neither extension alters transfer amounts or token ownership.
SAFE_TOKEN_2022_EXTENSION_LENGTHS = {18: 64}
MAX_MINT_ACCOUNT_BYTES = 65_536
MAX_SOLANA_ACCOUNT_BYTES = 1_048_576
OLLAMA_INTERACTIVE_WAIT_SECONDS = 1.0


class ProviderError(RuntimeError):
    pass


class HttpProviders:
    def __init__(
        self,
        quota: QuotaBroker,
        *,
        solana_http: str,
        solana_fallback_http: str | None = None,
        jupiter_base: str,
        jupiter_api_key: str | None = None,
        ollama_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "qwen3.5:2b",
    ) -> None:
        self.quota = quota
        self.solana_http = solana_http
        self.solana_fallback_http = (
            solana_fallback_http if solana_fallback_http != solana_http else None
        )
        self.jupiter_base = jupiter_base.rstrip("/")
        self.jupiter_api_key = jupiter_api_key
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        # Ollama is deliberately configured for one CPU inference at a time. Mirror that limit in
        # the app so background Shadow work never builds a hidden queue inside Ollama, and let an
        # interactive explanation fall back quickly when the local model is already occupied.
        self._ollama_generation_lock = asyncio.Lock()
        self._ollama_interactive_waiters = 0
        # Provider backoff is endpoint-specific. A keyed primary returning 429 must not disable
        # the configured public fallback through the shared logical Solana quota bucket.
        self._solana_unavailable_until = {"primary": 0.0, "fallback": 0.0}
        self._solana_failures = {"primary": 0, "fallback": 0}
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10, connect=5),
            follow_redirects=False,
            headers={"User-Agent": "SignalArcade/1.0 (+paper-only; open-source)"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    def configure_solana(self, http_url: str, *, fallback_http_url: str | None = None) -> None:
        """Apply an explicit endpoint change without retaining old runtime cooldowns."""

        self.solana_http = http_url
        self.solana_fallback_http = (
            fallback_http_url if fallback_http_url and fallback_http_url != http_url else None
        )
        self._solana_unavailable_until = {"primary": 0.0, "fallback": 0.0}
        self._solana_failures = {"primary": 0, "fallback": 0}

    @property
    def ollama_generation_busy(self) -> bool:
        return self._ollama_generation_lock.locked()

    async def _solana_rpc_response(
        self,
        request_body: dict[str, Any],
        *,
        critical: bool = False,
    ) -> httpx.Response | None:
        """Send one logical Solana request with bounded, endpoint-local failover."""

        endpoints = [("primary", self.solana_http)]
        if self.solana_fallback_http:
            endpoints.append(("fallback", self.solana_fallback_http))
        now = time.monotonic()
        available = [
            (name, endpoint)
            for name, endpoint in endpoints
            if now >= self._solana_unavailable_until[name]
        ]
        if not available or not await self.quota.acquire("solana", critical=critical):
            return None
        for name, endpoint in available:
            try:
                response = await self.client.post(endpoint, json=request_body)
            except httpx.HTTPError:
                self._cool_down_solana_endpoint(name, None)
                continue
            unavailable = response.status_code in {401, 403, 429} or response.status_code >= 500
            if unavailable:
                self._cool_down_solana_endpoint(name, response)
                continue
            try:
                rpc_error = response.json().get("error") if response.status_code < 400 else None
            except (ValueError, TypeError):
                rpc_error = None
            rpc_code = rpc_error.get("code") if isinstance(rpc_error, dict) else None
            if rpc_code in {-32603, -32016, -32005}:
                # Internal/provider overload and minimum-context lag can differ by endpoint.
                # Trying the configured fallback once is useful; invalid caller requests are not.
                self._cool_down_solana_endpoint(name, None)
                continue
            self._solana_failures[name] = 0
            self._solana_unavailable_until[name] = 0.0
            return response
        return None

    def _cool_down_solana_endpoint(
        self,
        name: str,
        response: httpx.Response | None,
    ) -> None:
        failures = min(8, self._solana_failures[name] + 1)
        self._solana_failures[name] = failures
        if response is not None and response.status_code == 429:
            delay = _retry_after(response)
        elif response is not None and response.status_code in {401, 403}:
            delay = 300.0
        else:
            delay = min(60.0, float(2 ** (failures - 1)))
        self._solana_unavailable_until[name] = time.monotonic() + max(1.0, min(300.0, delay))

    async def solana_mint_safety(self, mint: str) -> dict[str, Any] | None:
        """Inspect the mint account itself; fail closed on malformed or unfamiliar layouts."""
        request_body = {
            "jsonrpc": "2.0",
            "id": "signal-arcade-mint-safety",
            "method": "getAccountInfo",
            "params": [mint, {"encoding": "base64", "commitment": "confirmed"}],
        }
        response = await self._solana_rpc_response(request_body)
        if response is None:
            return None
        response.raise_for_status()
        body = response.json()
        account = (body.get("result") or {}).get("value")
        if not isinstance(account, dict):
            return {
                "safe": False,
                "verified": True,
                "reason": "mint_account_not_found",
            }
        owner = account.get("owner")
        encoded = account.get("data")
        if not isinstance(encoded, list) or not encoded or not isinstance(encoded[0], str):
            return {
                "safe": False,
                "verified": True,
                "reason": "unexpected_account_encoding",
                "owner": owner,
            }
        if len(encoded[0]) > ((MAX_MINT_ACCOUNT_BYTES + 2) // 3) * 4:
            return {
                "safe": False,
                "verified": True,
                "reason": "mint_account_too_large",
                "owner": owner,
            }
        try:
            raw = base64.b64decode(encoded[0], validate=True)
        except (ValueError, TypeError):
            return {
                "safe": False,
                "verified": True,
                "reason": "invalid_account_base64",
                "owner": owner,
            }
        return self._mint_safety_from_raw(owner, raw)

    @staticmethod
    def mint_safety_from_account(account: dict[str, Any] | None) -> dict[str, Any] | None:
        """Assess one already-fetched exact account without inventing a missing result.

        ``getMultipleAccounts`` represents a missing or malformed item as ``None``. Treating that
        as a verified unsafe mint would make a transiently lagging RPC permanently poison a live
        candidate, so batch callers retry it instead. Any present account still fails closed on
        its owner and pinned mint layout.
        """

        if not isinstance(account, dict):
            return None
        raw = account.get("raw")
        if not isinstance(raw, bytes):
            return None
        return HttpProviders._mint_safety_from_raw(account.get("owner"), raw)

    @staticmethod
    def _mint_safety_from_raw(owner: Any, raw: bytes) -> dict[str, Any]:
        if len(raw) < 82 or len(raw) > MAX_MINT_ACCOUNT_BYTES:
            return {
                "safe": False,
                "verified": True,
                "reason": "mint_account_size_outside_supported_range",
                "owner": owner,
            }
        mint_authority_tag = struct.unpack_from("<I", raw, 0)[0]
        supply = struct.unpack_from("<Q", raw, 36)[0]
        decimals = raw[44]
        initialized = raw[45] == 1
        freeze_authority_tag = struct.unpack_from("<I", raw, 46)[0]
        valid_authority_tags = mint_authority_tag in {0, 1} and freeze_authority_tag in {0, 1}
        extension_types = _token_2022_extension_types(raw) if owner == TOKEN_2022_PROGRAM else []
        layout_valid = (owner == SPL_TOKEN_PROGRAM and len(raw) == 82) or (
            owner == TOKEN_2022_PROGRAM and -1 not in extension_types
        )
        has_unreviewed_extensions = any(
            item not in SAFE_TOKEN_2022_MINT_EXTENSIONS for item in extension_types
        )
        supported_owner = owner in {SPL_TOKEN_PROGRAM, TOKEN_2022_PROGRAM}
        safe = all(
            (
                supported_owner,
                layout_valid,
                valid_authority_tags,
                initialized,
                supply > 0,
                decimals == 6,
                mint_authority_tag == 0,
                freeze_authority_tag == 0,
                not has_unreviewed_extensions,
            )
        )
        failures: list[str] = []
        if not supported_owner:
            failures.append("unsupported_account_owner")
        if supported_owner and not layout_valid:
            failures.append("malformed_mint_account_layout")
        if not valid_authority_tags or not initialized:
            failures.append("malformed_or_uninitialized_mint")
        if supply <= 0:
            failures.append("zero_supply")
        if decimals != 6:
            failures.append("unsupported_decimals_v1")
        if mint_authority_tag != 0:
            failures.append("mint_authority_active")
        if freeze_authority_tag != 0:
            failures.append("freeze_authority_active")
        if has_unreviewed_extensions:
            failures.append("token_2022_extensions_not_reviewed_v1")
        return {
            "safe": safe,
            "verified": True,
            "owner": owner,
            "supply": supply,
            "decimals": decimals,
            "mint_authority_revoked": mint_authority_tag == 0,
            "freeze_authority_revoked": freeze_authority_tag == 0,
            "has_unreviewed_extensions": has_unreviewed_extensions,
            "extension_types": extension_types,
            "failures": failures,
        }

    async def solana_account_info(
        self,
        address: str,
        *,
        critical: bool = False,
    ) -> dict[str, Any] | None:
        """Fetch one bounded raw account for route verification.

        This is deliberately separate from mint safety: callers must verify both the owner and
        the pinned account discriminator before using any decoded values.
        """

        request_body = {
            "jsonrpc": "2.0",
            "id": "signal-arcade-route-check",
            "method": "getAccountInfo",
            "params": [address, {"encoding": "base64", "commitment": "confirmed"}],
        }
        response = await self._solana_rpc_response(request_body, critical=critical)
        if response is None:
            return None
        response.raise_for_status()
        body = response.json()
        if body.get("error") is not None:
            return None
        account = (body.get("result") or {}).get("value")
        return _solana_account_value(address, account)

    async def solana_multiple_accounts(
        self,
        addresses: list[str],
        *,
        min_context_slot: int | None = None,
        critical: bool = False,
    ) -> dict[str, Any] | None:
        """Fetch up to 100 exact accounts in one quota-governed RPC request."""

        unique = list(dict.fromkeys(addresses))
        if not unique or len(unique) > 100 or any(not 30 <= len(item) <= 50 for item in unique):
            return None
        config: dict[str, Any] = {"encoding": "base64", "commitment": "confirmed"}
        if min_context_slot is not None and min_context_slot > 0:
            config["minContextSlot"] = min_context_slot
        request_body = {
            "jsonrpc": "2.0",
            "id": "signal-arcade-exact-account-batch",
            "method": "getMultipleAccounts",
            "params": [unique, config],
        }
        response = await self._solana_rpc_response(request_body, critical=critical)
        if response is None:
            return None
        response.raise_for_status()
        body = response.json()
        if body.get("error") is not None:
            return None
        result = body.get("result")
        if not isinstance(result, dict):
            return None
        context = result.get("context")
        values = result.get("value")
        if (
            not isinstance(context, dict)
            or not isinstance(values, list)
            or len(values) != len(unique)
        ):
            return None
        slot = _nonnegative_int(context.get("slot"))
        if slot <= 0 or (min_context_slot is not None and slot < min_context_slot):
            return None
        accounts = {
            address: _solana_account_value(address, value)
            for address, value in zip(unique, values, strict=True)
        }
        return {"slot": slot, "accounts": accounts}

    async def dexscreener_token(self, mint: str) -> dict[str, Any] | None:
        if not await self.quota.acquire("dexscreener"):
            return None
        url = f"https://api.dexscreener.com/tokens/v1/solana/{mint}"
        response = await self.client.get(url)
        if response.status_code == 429:
            await self.quota.penalize("dexscreener", _retry_after(response))
            return None
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            candidates = body
        elif isinstance(body, dict):
            candidates = body.get("pairs") or []
        else:
            candidates = []
        pairs = []
        for pair in candidates[:500]:
            if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                continue
            base_token = pair.get("baseToken")
            if not isinstance(base_token, dict) or base_token.get("address") != mint:
                continue
            pairs.append(pair)
        if not pairs:
            return None
        pairs.sort(
            key=lambda p: _nonnegative_float((p.get("liquidity") or {}).get("usd")) or 0.0,
            reverse=True,
        )
        pair = pairs[0]
        base_token = pair.get("baseToken") or {}
        price_usd = _positive_float(pair.get("priceUsd"))
        price_native = _positive_float(pair.get("priceNative"))
        sol_usd_price = (
            price_usd / price_native if price_usd is not None and price_native is not None else None
        )
        if sol_usd_price is not None and not 0 < sol_usd_price < 1_000_000:
            sol_usd_price = None
        return {
            "source": "dexscreener",
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "base_mint": mint,
            # Untrusted secondary metadata is display-only. Feature scoring never reads it.
            "base_token_name": _bounded_display_text(base_token.get("name"), 100),
            "base_token_symbol": _bounded_display_text(base_token.get("symbol"), 30),
            "quote_mint": (pair.get("quoteToken") or {}).get("address"),
            "price_usd": price_usd,
            "price_native": price_native,
            "sol_usd_price": sol_usd_price,
            "liquidity_usd": _nonnegative_float((pair.get("liquidity") or {}).get("usd")),
            "volume_5m_usd": _nonnegative_float((pair.get("volume") or {}).get("m5")),
            "volume_24h_usd": _nonnegative_float((pair.get("volume") or {}).get("h24")),
            "buys_5m": _nonnegative_int(((pair.get("txns") or {}).get("m5") or {}).get("buys")),
            "sells_5m": _nonnegative_int(((pair.get("txns") or {}).get("m5") or {}).get("sells")),
            "market_cap_usd": _nonnegative_float(pair.get("marketCap")),
            "fdv_usd": _nonnegative_float(pair.get("fdv")),
            "url": pair.get("url"),
        }

    async def jupiter_price(self, mints: list[str], *, critical: bool = False) -> dict[str, Any]:
        if not mints or not await self.quota.acquire("jupiter", critical=critical):
            return {}
        headers = {"x-api-key": self.jupiter_api_key} if self.jupiter_api_key else {}
        response = await self.client.get(
            f"{self.jupiter_base}/price/v3",
            params={"ids": ",".join(mints[:50])},
            headers=headers,
        )
        if response.status_code in {401, 403, 429}:
            if response.status_code == 429:
                await self.quota.penalize("jupiter", _retry_after(response))
            return {}
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    async def jupiter_order(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 100,
        critical: bool = True,
    ) -> dict[str, Any] | None:
        if amount <= 0 or not await self.quota.acquire("jupiter", critical=critical):
            return None
        headers = {"x-api-key": self.jupiter_api_key} if self.jupiter_api_key else {}
        response = await self.client.get(
            f"{self.jupiter_base}/swap/v2/order",
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": str(slippage_bps),
            },
            headers=headers,
        )
        if response.status_code in {400, 401, 403, 404, 429}:
            if response.status_code == 429:
                await self.quota.penalize("jupiter", _retry_after(response))
            return None
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else None

    async def explain_with_ollama(self, prompt: str) -> str | None:
        if not self.ollama_url or not self.ollama_model:
            return None
        self._ollama_interactive_waiters += 1
        acquired = False
        try:
            # The deterministic explanation is always available. Do not make a user wait behind a
            # long CPU Shadow assessment merely to receive optional prose.
            await asyncio.wait_for(
                self._ollama_generation_lock.acquire(),
                timeout=OLLAMA_INTERACTIVE_WAIT_SECONDS,
            )
            acquired = True
        except TimeoutError:
            return None
        finally:
            self._ollama_interactive_waiters -= 1
        try:
            if not await self.quota.acquire("ollama"):
                return None
            response = await self.client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    # Qwen thinking is enabled by default in Ollama. Explanations are a
                    # bounded UI aid, so do not spend the entire timeout on hidden thought.
                    "think": False,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0.1,
                        "num_ctx": 1_024,
                        "num_predict": 96,
                    },
                },
                timeout=25,
            )
            if response.status_code != 200:
                if response.status_code == 429:
                    await self.quota.penalize("ollama", _retry_after(response))
                return None
            body = response.json()
            if not isinstance(body, dict):
                return None
            text = body.get("response")
            return str(text).strip() if text else None
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        finally:
            if acquired:
                self._ollama_generation_lock.release()

    async def ollama_models(self) -> list[dict[str, Any]]:
        if not self.ollama_url:
            return []
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags", timeout=5)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                return []
            models = body.get("models", [])
            if not isinstance(models, list):
                return []
            return [item for item in models if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    async def ollama_runtime_status(self) -> dict[str, Any]:
        """Report Ollama reachability and actual loaded-model compute without guessing."""

        unavailable: dict[str, Any] = {
            "reachable": False,
            "version": None,
            "loaded_model_count": 0,
            "loaded_model_bytes": 0,
            "loaded_vram_bytes": 0,
            "compute": "unavailable",
        }
        if not self.ollama_url:
            return unavailable
        try:
            response = await self.client.get(f"{self.ollama_url}/api/version", timeout=5)
            response.raise_for_status()
            version_body = response.json()
            if not isinstance(version_body, dict):
                return unavailable
            version = version_body.get("version")
        except (httpx.HTTPError, ValueError, TypeError):
            return unavailable

        loaded: list[dict[str, Any]] = []
        try:
            response = await self.client.get(f"{self.ollama_url}/api/ps", timeout=5)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Ollama process response is not an object")
            models = body.get("models", [])
            if not isinstance(models, list):
                raise ValueError("Ollama process list is not an array")
            loaded = [item for item in models if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError, TypeError):
            # The version response already proves the service is reachable. Runtime compute is
            # simply unknown until /api/ps succeeds on a later monitor pass.
            return {
                **unavailable,
                "reachable": True,
                "version": str(version) if version else None,
                "compute": "unknown",
            }

        loaded_bytes = sum(_nonnegative_int(item.get("size")) for item in loaded)
        vram_bytes = sum(_nonnegative_int(item.get("size_vram")) for item in loaded)
        if not loaded:
            compute = "idle"
        elif vram_bytes <= 0:
            compute = "cpu"
        elif loaded_bytes > 0 and vram_bytes < loaded_bytes:
            compute = "hybrid"
        else:
            compute = "gpu"
        return {
            "reachable": True,
            "version": str(version) if version else None,
            "loaded_model_count": len(loaded),
            "loaded_model_bytes": loaded_bytes,
            "loaded_vram_bytes": vram_bytes,
            "compute": compute,
        }

    async def ollama_structured(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        timeout_seconds: float = 20,
        model: str | None = None,
    ) -> tuple[str, int] | None:
        selected_model = model or self.ollama_model
        if not self.ollama_url or not selected_model or timeout_seconds <= 0:
            return None
        started = time.monotonic()
        acquired = False
        # If an explanation arrived between Shadow jobs, yield before joining the lock queue so
        # that interactive work can either run next or take its fast deterministic fallback.
        if self._ollama_interactive_waiters:
            await asyncio.sleep(0)
        try:
            # The caller's timeout is an end-to-end budget, including time behind another local
            # generation. This is essential for Guarded mode: an optional veto must never stall
            # the deterministic paper engine beyond its measured qualification limit.
            await asyncio.wait_for(
                self._ollama_generation_lock.acquire(),
                timeout=timeout_seconds,
            )
            acquired = True
            if not await self.quota.acquire("ollama"):
                return None
            remaining_seconds = timeout_seconds - (time.monotonic() - started)
            if remaining_seconds <= 0:
                return None
            response = await self.client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": selected_model,
                    "prompt": prompt,
                    "stream": False,
                    # The deterministic engine owns every action. Keep this optional,
                    # advisory assessment short enough to remain operational on a CPU.
                    "think": False,
                    "format": schema,
                    "keep_alive": "10m",
                    "options": {
                        "temperature": 0,
                        "num_ctx": 1_024,
                        "num_predict": 96,
                    },
                },
                timeout=remaining_seconds,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                return None
            text = body.get("response")
            if not isinstance(text, str) or not text.strip():
                return None
            return text.strip(), max(0, int((time.monotonic() - started) * 1_000))
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError):
            return None
        finally:
            if acquired:
                self._ollama_generation_lock.release()

    async def pull_ollama_model(
        self,
        model: str,
        on_progress: Callable[[dict[str, Any]], None],
    ) -> None:
        """Stream a model into Ollama's own model store without blocking the app."""

        if not self.ollama_url:
            raise ProviderError("Ollama is not configured")
        try:
            async with self.client.stream(
                "POST",
                f"{self.ollama_url}/api/pull",
                json={"model": model, "stream": True},
                timeout=httpx.Timeout(3_600, connect=10),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if isinstance(item, dict):
                        remote_error = item.get("error")
                        if remote_error:
                            detail = str(remote_error).strip().replace("\r", " ").replace("\n", " ")
                            raise ProviderError(
                                f"Ollama rejected the model download: {detail[:500]}"
                            )
                        on_progress(item)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            detail = str(exc).strip().replace("\r", " ").replace("\n", " ")
            if not detail:
                detail = type(exc).__name__
            raise ProviderError(f"Ollama model download failed: {detail[:500]}") from exc

    async def delete_ollama_model(self, model: str) -> None:
        """Remove one explicitly selected model from Ollama's separate model store."""

        if not self.ollama_url:
            raise ProviderError("Ollama is not configured")
        try:
            response = await self.client.request(
                "DELETE",
                f"{self.ollama_url}/api/delete",
                json={"model": model},
                timeout=30,
            )
            if response.status_code == 404:
                raise ProviderError("the selected Ollama model is not installed")
            response.raise_for_status()
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            detail = str(exc).strip().replace("\r", " ").replace("\n", " ")
            if not detail:
                detail = type(exc).__name__
            raise ProviderError(f"Ollama model removal failed: {detail[:500]}") from exc


def _float(value: Any) -> float | None:
    try:
        result = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return result if result is not None and math.isfinite(result) else None


def _positive_float(value: Any) -> float | None:
    result = _float(value)
    return result if result is not None and result > 0 else None


def _nonnegative_float(value: Any) -> float | None:
    result = _float(value)
    return result if result is not None and result >= 0 else None


def _nonnegative_int(value: Any) -> int:
    try:
        result = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, result)


def _bounded_display_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    printable = "".join(character for character in value if character.isprintable())
    normalized = " ".join(printable.split())
    return normalized[:limit] or None


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(1.0, min(300.0, float(response.headers.get("retry-after", "1"))))
    except (TypeError, ValueError):
        return 1.0


def _solana_account_value(address: str, account: Any) -> dict[str, Any] | None:
    """Decode one bounded base64 account value without trusting its declared layout."""

    if not isinstance(account, dict):
        return None
    encoded = account.get("data")
    if not isinstance(encoded, list) or not encoded or not isinstance(encoded[0], str):
        return None
    if len(encoded[0]) > ((MAX_SOLANA_ACCOUNT_BYTES + 2) // 3) * 4:
        return None
    try:
        raw = base64.b64decode(encoded[0], validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > MAX_SOLANA_ACCOUNT_BYTES:
        return None
    return {
        "address": address,
        "owner": account.get("owner"),
        "lamports": _nonnegative_int(account.get("lamports")),
        "executable": bool(account.get("executable", False)),
        "raw": raw,
    }


def _token_2022_extension_types(raw: bytes) -> list[int]:
    """Read Token-2022 mint TLV records using its padded 165-byte base layout."""
    if len(raw) == 82:
        return []
    if len(raw) < 166 or any(raw[82:165]) or raw[165] != 1:
        return [-1]
    cursor = 166
    result: list[int] = []
    while cursor + 4 <= len(raw):
        extension_type, length = struct.unpack_from("<HH", raw, cursor)
        cursor += 4
        if extension_type == 0:
            if length != 0 or any(raw[cursor:]):
                return [-1]
            break
        end = cursor + length
        if end > len(raw):
            return [-1]
        expected_length = SAFE_TOKEN_2022_EXTENSION_LENGTHS.get(extension_type)
        if expected_length is not None and length != expected_length:
            return [-1]
        if extension_type in result:
            return [-1]
        result.append(extension_type)
        cursor = end
    if cursor < len(raw) and any(raw[cursor:]):
        return [-1]
    return result
