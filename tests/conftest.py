from __future__ import annotations

from pathlib import Path

import pytest
from signal_arcade.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        demo_mode=True,
        entry_latency_ms=0,
        exit_latency_ms=0,
        network_fee_lamports=5_000,
        priority_fee_lamports=10_000,
        _env_file=None,
    )
