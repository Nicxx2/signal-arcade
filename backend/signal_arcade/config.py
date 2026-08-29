from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with deliberately safe networking defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SIGNAL_ARCADE_",
        extra="ignore",
        case_sensitive=False,
    )

    bind: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    data_dir: Path = Path("data")
    frontend_dir: Path | None = None
    log_level: str = "INFO"
    demo_mode: bool = False
    admin_password: str | None = None

    solana_http: str = "https://api.mainnet-beta.solana.com"
    solana_ws: str = "wss://api.mainnet-beta.solana.com"
    jupiter_base: str = "https://api.jup.ag"
    jupiter_api_key: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:2b"
    ollama_accelerator: Literal["cpu", "nvidia", "amd", "external"] = "external"

    decision_cooldown_seconds: int = Field(default=5, ge=1, le=300)
    stale_market_seconds: int = Field(default=20, ge=5, le=300)
    entry_latency_ms: int = Field(default=850, ge=0, le=30_000)
    exit_latency_ms: int = Field(default=1_100, ge=0, le=30_000)
    network_fee_lamports: int = Field(default=5_000, ge=0, le=50_000_000)
    priority_fee_lamports: int = Field(default=25_000, ge=0, le=1_000_000_000)
    pump_fee_bps: int = Field(default=125, ge=0, le=5_000)
    candidate_window_minutes: int = Field(default=30, ge=5, le=240)
    raw_trade_retention_hours: int = Field(default=6, ge=1, le=720)
    equity_sample_seconds: int = Field(default=5, ge=1, le=300)
    position_mark_stale_seconds: int = Field(default=90, ge=20, le=3_600)
    event_queue_max: int = Field(default=10_000, ge=500, le=100_000)
    event_batch_size: int = Field(default=250, ge=10, le=2_000)
    event_batch_wait_ms: int = Field(default=25, ge=1, le=500)

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return value

    @model_validator(mode="after")
    def protect_non_loopback_bind(self) -> Settings:
        host = self.bind.strip("[]")
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = host.lower() == "localhost"
        if not is_loopback and not self.admin_password:
            raise ValueError(
                "SIGNAL_ARCADE_ADMIN_PASSWORD is required when binding outside localhost"
            )
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "signal_arcade.sqlite3"


def load_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
