from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .quota import ProviderPlan


class ProviderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    requests_per_minute: int = Field(ge=1, le=60_000)
    monthly_limit: int | None = Field(default=None, ge=1, le=2_000_000_000)
    reserve_fraction: float = Field(default=0.10, ge=0.0, le=0.50)
    paid_mode: bool = False

    @model_validator(mode="after")
    def require_explicit_paid_cap(self) -> ProviderPolicy:
        if self.paid_mode and self.monthly_limit is None:
            raise ValueError("paid mode requires a hard monthly call cap")
        return self

    def plan(self, name: str) -> ProviderPlan:
        return ProviderPlan(
            name=name,
            requests_per_minute=self.requests_per_minute,
            monthly_limit=self.monthly_limit,
            reserve_fraction=self.reserve_fraction,
            billable=self.paid_mode,
            pace_monthly=self.monthly_limit is not None,
        )


class ProviderConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solana: ProviderPolicy = Field(
        default_factory=lambda: ProviderPolicy(
            label="Public RPC",
            requests_per_minute=120,
        )
    )
    dexscreener: ProviderPolicy = Field(
        default_factory=lambda: ProviderPolicy(
            label="Free",
            requests_per_minute=300,
        )
    )
    jupiter: ProviderPolicy = Field(
        default_factory=lambda: ProviderPolicy(
            label="Keyless",
            requests_per_minute=30,
        )
    )
    ollama: ProviderPolicy = Field(
        default_factory=lambda: ProviderPolicy(
            label="Local",
            requests_per_minute=30,
        )
    )

    def plans(self) -> list[ProviderPlan]:
        return [
            self.solana.plan("solana"),
            self.dexscreener.plan("dexscreener"),
            self.jupiter.plan("jupiter"),
            self.ollama.plan("ollama"),
        ]


PROVIDER_PRESETS: dict[str, list[dict[str, Any]]] = {
    "solana": [
        {
            "id": "public",
            "label": "Public RPC",
            "requests_per_minute": 120,
            "monthly_limit": None,
            "paid_mode": False,
        },
        {
            "id": "helius_free",
            "label": "Helius Free (500k HTTP reserve)",
            "requests_per_minute": 600,
            "monthly_limit": 500_000,
            "paid_mode": False,
        },
        {
            "id": "alchemy_free",
            "label": "Alchemy Free (15M CU stream reserve)",
            "requests_per_minute": 3_000,
            "monthly_limit": 1_500_000,
            "paid_mode": False,
        },
        {
            "id": "solanatracker_rpc_free",
            "label": "SolanaTracker RPC Free (250k HTTP reserve)",
            "requests_per_minute": 300,
            "monthly_limit": 250_000,
            "paid_mode": False,
        },
    ],
    "jupiter": [
        {
            "id": "keyless",
            "label": "Keyless",
            "requests_per_minute": 30,
            "monthly_limit": None,
            "paid_mode": False,
        },
        {
            "id": "free_key",
            "label": "Free API key",
            "requests_per_minute": 60,
            "monthly_limit": None,
            "paid_mode": False,
        },
        {
            "id": "developer",
            "label": "Developer",
            "requests_per_minute": 600,
            "monthly_limit": 25_000_000,
            "paid_mode": True,
        },
        {
            "id": "launch",
            "label": "Launch",
            "requests_per_minute": 3_000,
            "monthly_limit": 100_000_000,
            "paid_mode": True,
        },
        {
            "id": "pro",
            "label": "Pro",
            "requests_per_minute": 9_000,
            "monthly_limit": 500_000_000,
            "paid_mode": True,
        },
    ],
}


class ProviderSecretStore:
    """Local server-side provider secrets; never serialize values into API responses."""

    allowed_keys = {
        "solana_http",
        "solana_ws",
        "jupiter_base",
        "jupiter_api_key",
        "ollama_url",
        "ollama_model",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.values: dict[str, str] = {}
        self.last_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            body = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(body, dict):
                raise ValueError("secret store root is not an object")
            for key, value in body.items():
                if key not in self.allowed_keys or not isinstance(value, str):
                    raise ValueError("secret store contains an unsupported value")
                self.values[key] = _bounded_secret(value)
            self._restrict_permissions()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.values.clear()
            self.last_error = (
                "provider secret store could not be read; environment defaults are active"
            )

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def update(self, changes: dict[str, str | None]) -> None:
        next_values = dict(self.values)
        for key, value in changes.items():
            if key not in self.allowed_keys:
                raise ValueError("unsupported provider secret field")
            if value is None:
                next_values.pop(key, None)
            else:
                next_values[key] = _bounded_secret(value)
        self._write(next_values)
        self.values = next_values
        self.last_error = None

    def _write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = json.dumps(values, separators=(",", ":"), sort_keys=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self._restrict_permissions()
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _restrict_permissions(self) -> None:
        with suppress(OSError):
            self.path.chmod(0o600)


def validate_endpoint(
    value: str,
    *,
    allowed_schemes: set[str],
    local_plaintext_schemes: set[str] | None = None,
) -> str:
    value = _bounded_secret(value.strip())
    if any(character in value for character in ("\r", "\n", "\0")):
        raise ValueError("provider endpoint contains control characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("provider endpoint is malformed") from exc
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ValueError("provider endpoint uses an unsupported scheme or host")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("provider endpoint must not contain user-info or a fragment")
    plaintext = local_plaintext_schemes or set()
    local_hosts = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
    if parsed.scheme in plaintext and parsed.hostname.lower() not in local_hosts:
        raise ValueError("unencrypted provider endpoints are only allowed for local services")
    if port is not None and not 1 <= port <= 65_535:
        raise ValueError("provider endpoint port is invalid")
    return value


def endpoint_label(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or "configured endpoint"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme}://{host}"
    except ValueError:
        return "configured endpoint"


def _bounded_secret(value: str) -> str:
    if not value or len(value) > 4_096:
        raise ValueError("provider value must contain between 1 and 4096 characters")
    return value
